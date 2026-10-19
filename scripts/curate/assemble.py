"""Assemble data/assignments.csv and data/sections.csv from the curation files.

    python scripts/curate/assemble.py [--data-dir data] [--curation curation] [--check]

Inputs (curation/README.md describes them):

- `curation/*_designations.csv`: the transcribed lists (R and C sources);
- `curation/aliases.csv`: the names of a list that the name rule does not map to
  their INS (a misprint, a merged commune, a section);
- `curation/overrides.csv`: one row per research-driven decision, with its sources
  and reason;
- `curation/derived/`: the extracts of the M sources (ORES on ODWB, Fluvius 1_23);
- the CWaPE Power BI report (C, read by hand): its full readings in `curation/private/`
  (git-ignored, local only) when present, else the committed summary
  `curation/powerbi_checks.csv` (scripts/powerbi.py); neither is required;
- `data/communes.csv`, `data/postcodes.csv`, `data/operators.csv`, `data/sources.csv`.

For each commune, the R entries of the worksheets give the designated operator of each
vector: exactly one operator, or the commune needs an override (Brunehaut, Couvin). No
R gas entry means `gas_status` `none`. The overrides then set values, dates, flags,
notes and sources, and declare the sections. A row cites the worksheet sources whose
entry agrees with its final value, the M extracts that agree with it, the CWaPE Power
BI readings that show its DSO (scripts/powerbi.py), and the sources of its overrides.
A section is checked against the ODWB localities of its own postcodes. A Flemish or
Walloon row without an M or C source of another publisher than its R sources gets
`to_confirm` and the shared single-source note.

The output is deterministic (sorted rows and lists, no clock). `--check` writes nothing
and exits 1 when the files on disk differ from the assembly. Exit codes: 0 = written
or up to date, 1 = a curation error or a difference, 2 = a file error.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import csvio  # noqa: E402
import powerbi  # noqa: E402
import schema  # noqa: E402

ROOT = SCRIPTS.parent
Row = dict[str, str]
# curation/powerbi_checks.csv by (ins, section_key, vector)
PowerBISummary = dict[powerbi.SummaryKey, Row]

OVERRIDES_HEADER = (
    "ins",
    "field",
    "value",
    "valid_from",
    "flags",
    "note_key",
    "source_ids",
    "reason",
)
VALUE_FIELDS = ("elec", "elec_operator", "elec_designated", "gas")
SECTION_FIELDS = ("nom_fr", "nom_nl", "nom_de", "postcodes")
OTHER_FIELDS = ("annotate", "gas_none_sources")
FIELDS = (*VALUE_FIELDS, *SECTION_FIELDS, *OTHER_FIELDS)
SINGLE_SOURCE_NOTES = {"WAL": "wal-single-source", "VLA": "vla-single-source"}
INDEPENDENCE_REGIONS = ("VLA", "WAL")
CHECK_ROLES = ("M", "C")

# The M extracts of curation/derived/ and what they show: source id -> (file, vector, operator).
ODWB_EXTRACTS = {
    "odwb-ores-elec": ("ores_odwb_elec.csv", "elec", "ores"),
    "odwb-ores-gas": ("ores_odwb_gas.csv", "gas", "ores"),
}
ODWB_HEADER = ("year", "postcode", "localite", "commune", "secteur", "ins")
FLUVIUS_SOURCE = "fluvius-1-23"
FLUVIUS_EXTRACT = "fluvius_1_23.csv"


class CurationError(ValueError):
    """The curation files are inconsistent: nothing is written."""


def normalize_name(name: str) -> str:
    """The name rule of README.md: NFKD, no marks, lower(), only [a-z0-9]."""
    decomposed = unicodedata.normalize("NFKD", name)
    unmarked = "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M"))
    return re.sub(r"[^a-z0-9]", "", unmarked.lower())


@dataclass
class Attribution:
    """One row of assignments.csv (section_key empty) or sections.csv, being assembled."""

    ins: str
    section_key: str = ""
    elec_operator: str = ""
    elec_designated: str = ""
    gas_status: str = ""
    gas_operator: str = ""
    flags: set[str] = field(default_factory=set)
    note_key: str = ""
    sources: set[str] = field(default_factory=set)
    valid_from: str = ""
    names: dict[str, str] = field(default_factory=dict)
    postcodes: str = ""

    @property
    def label(self) -> str:
        return f"{self.ins}/{self.section_key}" if self.section_key else self.ins


@dataclass(frozen=True)
class Curation:
    communes: dict[str, Row]
    pairs: set[tuple[str, str]]
    operators: dict[str, Row]
    sources: dict[str, Row]
    worksheet: list[Row]  # every *_designations.csv row, with "file" and "line"
    aliases: dict[tuple[str, str], str]
    overrides: list[Row]  # with "line"
    odwb: dict[str, set[tuple[str, str]]]  # source id -> (postcode, INS) in the extract
    fluvius: dict[str, list[Row]]  # INS -> rows of the Fluvius extract
    powerbi: powerbi.Reading | None  # the full CWaPE Power BI readings, when present
    powerbi_summary: PowerBISummary  # the committed summary, used without the readings


@dataclass(frozen=True)
class Assembly:
    assignments: list[Row]
    sections: list[Row]
    summary: list[str]


def load(data_dir: Path, curation_dir: Path) -> Curation:
    """Read every input. CsvError or OSError on a malformed or missing file."""
    communes = {
        row["ins"]: row for row in csvio.read_csv(data_dir / "communes.csv", schema.COMMUNES_HEADER)
    }
    pairs = {
        (row["postcode"], row["ins"])
        for row in csvio.read_csv(data_dir / "postcodes.csv", schema.POSTCODES_HEADER)
    }
    operators = {
        row["id"]: row
        for row in csvio.read_csv(data_dir / "operators.csv", schema.OPERATORS_HEADER)
    }
    sources = {
        row["id"]: row for row in csvio.read_csv(data_dir / "sources.csv", schema.SOURCES_HEADER)
    }
    worksheet: list[Row] = []
    for path in sorted(curation_dir.glob("*_designations.csv")):
        rows = csvio.read_csv(path, schema.WORKSHEET_HEADER)
        worksheet += [
            {**row, "file": path.name, "line": str(number)}
            for number, row in enumerate(rows, start=2)
        ]
    aliases = {
        (row["name_in_source"], row["ins"]): row["reason"]
        for row in csvio.read_csv(curation_dir / "aliases.csv", schema.ALIASES_HEADER)
    }
    overrides = [
        {**row, "line": str(number)}
        for number, row in enumerate(
            csvio.read_csv(curation_dir / "overrides.csv", OVERRIDES_HEADER), start=2
        )
    ]
    derived = curation_dir / "derived"
    odwb = {
        source_id: {
            (row["postcode"], row["ins"]) for row in csvio.read_csv(derived / name, ODWB_HEADER)
        }
        for source_id, (name, _, _) in ODWB_EXTRACTS.items()
    }
    fluvius: dict[str, list[Row]] = {}
    for row in csvio.read_csv(derived / FLUVIUS_EXTRACT, schema.DERIVED_FLUVIUS_HEADER):
        fluvius.setdefault(row["ins"], []).append(row)
    summary = powerbi.load_summary(curation_dir / powerbi.SUMMARY_FILE) or []
    return Curation(
        communes,
        pairs,
        operators,
        sources,
        worksheet,
        aliases,
        overrides,
        odwb,
        fluvius,
        powerbi.load(curation_dir / powerbi.PRIVATE_DIR),
        {powerbi.summary_key(row): row for row in summary},
    )


def check_worksheet(cur: Curation) -> list[str]:
    """Unknown operator, vector, INS or source, and names the rule and the aliases do not map."""
    errors = []
    for row in cur.worksheet:
        label = f"{row['file']}:{row['line']}"
        commune = cur.communes.get(row["ins"])
        if row["grd"] not in cur.operators or row["vector"] not in schema.VECTORS:
            errors.append(f"{label}: operator {row['grd']!r} or vector {row['vector']!r}")
        if row["source_id"] not in cur.sources:
            errors.append(f"{label}: unknown source {row['source_id']!r}")
        elif cur.sources[row["source_id"]]["role"] not in ("R", "C"):
            errors.append(f"{label}: {row['source_id']} is neither an R nor a C source")
        if commune is None:
            errors.append(f"{label}: unknown INS {row['ins']!r}")
            continue
        names = {normalize_name(commune[column]) for column in ("nom_fr", "nom_nl", "nom_de")}
        mapped = normalize_name(row["name_in_source"]) in names
        if not mapped and (row["name_in_source"], row["ins"]) not in cur.aliases:
            errors.append(
                f"{label}: {row['name_in_source']!r} is not a name of {row['ins']} "
                f"({commune['nom_fr']}) and is not in aliases.csv"
            )
    for name, ins in sorted(cur.aliases):
        if ins not in cur.communes:
            errors.append(f"aliases.csv: {name!r} maps to an unknown INS {ins!r}")
    return errors


def designations(cur: Curation) -> dict[tuple[str, str], set[str]]:
    """(ins, vector) -> operators designated by the R entries of the worksheets."""
    found: dict[tuple[str, str], set[str]] = {}
    for row in cur.worksheet:
        if cur.sources.get(row["source_id"], {}).get("role") == "R":
            found.setdefault((row["ins"], row["vector"]), set()).add(row["grd"])
    return found


def check_override(cur: Curation, row: Row) -> list[str]:
    label = f"overrides.csv:{row['line']}"
    errors = []
    target, _, section_key = row["ins"].partition("/")
    region_row = target in schema.REGIONS
    if not region_row and target not in cur.communes:
        errors.append(f"{label}: {row['ins']!r} is not an INS, INS/section or region")
    if section_key and not schema.SLUG_RE.fullmatch(section_key):
        errors.append(f"{label}: section key {section_key!r} is not a slug")
    if region_row and section_key:
        errors.append(f"{label}: a region has no sections")
    if row["field"] not in FIELDS:
        errors.append(f"{label}: unknown field {row['field']!r}")
    if row["field"] in SECTION_FIELDS and not section_key:
        errors.append(f"{label}: {row['field']} applies to a section (INS/section_key)")
    if row["field"] == "gas_none_sources" and not region_row:
        errors.append(f"{label}: gas_none_sources applies to a region")
    if row["field"] in OTHER_FIELDS and row["value"]:
        errors.append(f"{label}: {row['field']} takes no value")
    if row["field"] in ("elec", "elec_operator", "elec_designated") and (
        row["value"] not in cur.operators
    ):
        errors.append(f"{label}: unknown operator {row['value']!r}")
    if row["field"] == "gas":
        status, _, operator = row["value"].partition(":")
        if status not in schema.GAS_STATUSES or (status == "none") != (not operator):
            errors.append(f"{label}: gas is none, designated:<id> or foreign:<id>")
        elif operator and operator not in cur.operators:
            errors.append(f"{label}: unknown operator {operator!r}")
    for flag in schema.split_list(row["flags"]):
        if flag not in schema.FLAGS or flag == "operator_differs":
            errors.append(f"{label}: flag {flag!r} (operator_differs is derived)")
    if row["valid_from"] and not schema.is_date(row["valid_from"]):
        errors.append(f"{label}: valid_from {row['valid_from']!r}")
    for source in schema.split_list(row["source_ids"]):
        if source not in cur.sources:
            errors.append(f"{label}: unknown source {source!r}")
    if not row["reason"]:
        errors.append(f"{label}: a reason is required")
    return errors


def merge_meta(attribution: Attribution, row: Row, errors: list[str]) -> None:
    """valid_from, flags, note_key and source_ids of an override row."""
    label = f"overrides.csv:{row['line']}"
    for column, current in (
        ("valid_from", attribution.valid_from),
        ("note_key", attribution.note_key),
    ):
        value = row[column]
        if value and current and value != current:
            errors.append(f"{label}: {attribution.label} gets two {column} ({current}, {value})")
        elif value:
            setattr(attribution, column, value)
    attribution.flags |= set(schema.split_list(row["flags"]))
    attribution.sources |= set(schema.split_list(row["source_ids"]))


def apply_value(attribution: Attribution, row: Row) -> None:
    value = row["value"]
    match row["field"]:
        case "elec":
            attribution.elec_operator = attribution.elec_designated = value
        case "elec_operator":
            attribution.elec_operator = value
        case "elec_designated":
            attribution.elec_designated = value
        case "gas":
            status, _, operator = value.partition(":")
            attribution.gas_status, attribution.gas_operator = status, operator
        case "nom_fr" | "nom_nl" | "nom_de":
            attribution.names[row["field"]] = value
        case "postcodes":
            attribution.postcodes = value


def agreeing_sources(cur: Curation, attribution: Attribution) -> set[str]:
    """Worksheet sources, M extracts and Power BI readings that agree with the final values."""
    agreeing = set()
    for row in cur.worksheet:
        if row["ins"] != attribution.ins:
            continue
        expected = (
            attribution.elec_designated if row["vector"] == "elec" else attribution.gas_operator
        )
        if row["grd"] == expected:
            agreeing.add(row["source_id"])
    # A section is present in an ODWB extract through its own postcodes only.
    postcodes = set(schema.split_list(attribution.postcodes)) if attribution.section_key else None
    for source_id, (_, vector, operator) in ODWB_EXTRACTS.items():
        if source_id not in cur.sources:
            continue
        present = any(
            ins == attribution.ins and (postcodes is None or postcode in postcodes)
            for postcode, ins in cur.odwb[source_id]
        )
        value = attribution.elec_designated if vector == "elec" else attribution.gas_operator
        if present and value == operator:
            agreeing.add(source_id)
        if (
            vector == "gas"
            and not present
            and attribution.gas_status == "none"
            and cur.communes[attribution.ins]["region"] == "WAL"
        ):
            agreeing.add(source_id)  # ORES has no gas access point there
    agreeing |= powerbi_sources(cur, attribution)
    rows = cur.fluvius.get(attribution.ins, [])

    def matches(item: Row) -> bool:
        return (
            item["elec_id"] == attribution.elec_operator
            and item["gas_id"] == attribution.gas_operator
        )

    if FLUVIUS_SOURCE not in cur.sources:
        return agreeing
    if rows and (any(map(matches, rows)) if attribution.section_key else all(map(matches, rows))):
        agreeing.add(FLUVIUS_SOURCE)
    return agreeing


def powerbi_sources(cur: Curation, attribution: Attribution) -> set[str]:
    """The CWaPE Power BI readings that show exactly the attribution's DSO (or no gas DSO).

    The full reading of a vector decides when it is present (curation/private/), otherwise
    the committed summary does (`powerbi.agrees`): the same citations with or without the
    local files, as long as the summary is up to date (validate.py checks it).
    """
    commune = cur.communes[attribution.ins]
    item = powerbi.Target(
        ins=attribution.ins,
        section_key=attribution.section_key,
        section_names=tuple(attribution.names.values()) if attribution.section_key else (),
        commune_names=(commune["nom_fr"], commune["nom_nl"], commune["nom_de"]),
        elec_designated=attribution.elec_designated,
        gas_operator=attribution.gas_operator,
    )
    return {
        source_id
        for vector, (_, source_id) in powerbi.READINGS.items()
        if source_id in cur.sources
        and powerbi.agrees(cur.powerbi, cur.powerbi_summary, vector, item)
    }


def independent(cur: Curation, sources: set[str]) -> bool:
    """One R source plus one M or C source of another publisher."""
    cited = [cur.sources[source] for source in sorted(sources)]
    references = [source for source in cited if source["role"] == "R"]
    checks = [source for source in cited if source["role"] in CHECK_ROLES]
    return any(
        check["publisher"] != reference["publisher"] for reference in references for check in checks
    )


def to_row(attribution: Attribution, *, section: bool) -> Row:
    flags = set(attribution.flags)
    if attribution.elec_operator != attribution.elec_designated:
        flags.add("operator_differs")
    row = {
        "ins": attribution.ins,
        "elec_operator": attribution.elec_operator,
        "elec_designated": attribution.elec_designated,
        "gas_status": attribution.gas_status,
        "gas_operator": attribution.gas_operator,
        "flags": schema.join_list(schema.canonical_flags(sorted(flags))),
        "note_key": attribution.note_key,
        "source_ids": schema.join_list(sorted(attribution.sources)),
        "valid_from": attribution.valid_from,
    }
    if section:
        row |= {
            "section_key": attribution.section_key,
            "nom_fr": attribution.names.get("nom_fr", ""),
            "nom_nl": attribution.names.get("nom_nl", ""),
            "nom_de": attribution.names.get("nom_de", ""),
            "postcodes": attribution.postcodes,
        }
    return row


def assemble(cur: Curation) -> Assembly:
    """The rows of assignments.csv and sections.csv. CurationError lists every problem."""
    errors = check_worksheet(cur)
    for row in cur.overrides:
        errors += check_override(cur, row)
    if errors:
        raise CurationError("\n".join(errors))

    designated = designations(cur)
    # Regions whose gas lists are transcribed: there, no R gas entry means no gas DSO.
    gas_regions = {cur.communes[ins]["region"] for ins, vector in designated if vector == "gas"}
    by_target: dict[str, list[Row]] = {}
    for row in cur.overrides:
        by_target.setdefault(row["ins"], []).append(row)
    sections_of: dict[str, list[str]] = {}
    for target in by_target:
        ins, _, section_key = target.partition("/")
        if section_key:
            sections_of.setdefault(ins, []).append(section_key)

    attributions: list[Attribution] = []
    changed: list[str] = []
    for ins in sorted(cur.communes):
        region = cur.communes[ins]["region"]
        base = Attribution(ins)
        elec = designated.get((ins, "elec"), set())
        gas = designated.get((ins, "gas"), set())
        if len(elec) == 1:
            base.elec_operator = base.elec_designated = next(iter(elec))
        if len(gas) == 1:
            base.gas_status, base.gas_operator = "designated", next(iter(gas))
        elif not gas and region in gas_regions:
            base.gas_status = "none"
        derived_elec = base.elec_designated if len(elec) == 1 else None
        derived_gas = (
            (base.gas_status, base.gas_operator)
            if len(gas) == 1 or (not gas and region in gas_regions)
            else None
        )
        for row in [*by_target.get(region, []), *by_target.get(ins, [])]:
            if row["field"] == "gas_none_sources":
                continue  # applied below, to the rows whose gas_status ends up none
            apply_value(base, row)
            merge_meta(base, row, errors)
        if (derived_elec is not None and base.elec_designated != derived_elec) or (
            derived_gas is not None and (base.gas_status, base.gas_operator) != derived_gas
        ):
            changed.append(ins)
        if len(elec) > 1 and not any(
            row["field"] in ("elec", "elec_designated") for row in by_target.get(ins, [])
        ):
            errors.append(f"{ins}: the R lists designate {sorted(elec)} for electricity: override")
        if len(gas) > 1 and not any(row["field"] == "gas" for row in by_target.get(ins, [])):
            errors.append(f"{ins}: the R lists designate {sorted(gas)} for gas: override")
        keys = sorted(sections_of.get(ins, [])) or [""]
        for section_key in keys:
            attribution = Attribution(
                ins,
                section_key,
                base.elec_operator,
                base.elec_designated,
                base.gas_status,
                base.gas_operator,
                set(base.flags),
                base.note_key,
                set(base.sources),
                base.valid_from,
            )
            for row in by_target.get(f"{ins}/{section_key}", []) if section_key else []:
                apply_value(attribution, row)
                merge_meta(attribution, row, errors)
            attributions.append(attribution)

    gas_none_sources = {
        region: {
            source
            for row in by_target.get(region, [])
            if row["field"] == "gas_none_sources"
            for source in schema.split_list(row["source_ids"])
        }
        for region in schema.REGIONS
    }
    single_source: list[str] = []
    for attribution in attributions:
        region = cur.communes[attribution.ins]["region"]
        if not attribution.elec_designated or not attribution.elec_operator:
            errors.append(f"{attribution.label}: no electricity operator")
        if not attribution.gas_status:
            errors.append(f"{attribution.label}: no gas_status (no transcribed gas list)")
        attribution.sources |= agreeing_sources(cur, attribution)
        if attribution.gas_status == "none":
            attribution.sources |= gas_none_sources[region]
        if region in INDEPENDENCE_REGIONS and not independent(cur, attribution.sources):
            single_source.append(attribution.label)
            if attribution.note_key and attribution.note_key != SINGLE_SOURCE_NOTES[region]:
                errors.append(
                    f"{attribution.label}: single source, but it already has the note "
                    f"{attribution.note_key}: decide by hand"
                )
            attribution.flags.add("to_confirm")
            attribution.note_key = SINGLE_SOURCE_NOTES[region]
        if attribution.section_key:
            pairs = {(postcode, attribution.ins) for postcode in attribution.postcodes.split("|")}
            if not attribution.names.get("nom_fr") or not pairs <= cur.pairs:
                errors.append(
                    f"{attribution.label}: a section needs nom_fr and postcodes of its INS"
                )
    if errors:
        raise CurationError("\n".join(errors))

    assignments = [to_row(a, section=False) for a in attributions if not a.section_key]
    sections = [to_row(a, section=True) for a in attributions if a.section_key]
    return Assembly(assignments, sections, summarize(cur, attributions, changed, single_source))


def summarize(
    cur: Curation,
    attributions: Sequence[Attribution],
    changed: Sequence[str],
    single: Sequence[str],
) -> list[str]:
    """Counts per region and operator, the overridden communes, the to_confirm rows."""
    lines = []
    for region in schema.REGIONS:
        rows = [a for a in attributions if cur.communes[a.ins]["region"] == region]
        inses = {a.ins for a in rows}
        lines.append(f"{region}: {len(inses)} communes, {len(rows)} rows")
        for label, column in (
            ("elec designated", "elec_designated"),
            ("elec operator", "elec_operator"),
        ):
            counts: dict[str, set[str]] = {}
            for a in rows:
                counts.setdefault(getattr(a, column), set()).add(a.ins)
            lines.append(
                f"  {label}: " + ", ".join(f"{op} {len(ins)}" for op, ins in sorted(counts.items()))
            )
        gas: dict[str, set[str]] = {}
        for a in rows:
            gas.setdefault(f"{a.gas_status}:{a.gas_operator}".rstrip(":"), set()).add(a.label)
        lines.append("  gas: " + ", ".join(f"{key} {len(v)}" for key, v in sorted(gas.items())))
    confirm = [a.label for a in attributions if "to_confirm" in a.flags]
    lines.append(f"overrides changing a worksheet value: {', '.join(changed) or 'none'}")
    lines.append(f"to_confirm: {len(confirm)} ({', '.join(confirm) or 'none'})")
    lines.append(f"single-source rows: {len(single)} ({', '.join(single) or 'none'})")
    return lines


def render(assembly: Assembly) -> dict[str, bytes]:
    return {
        "assignments.csv": csvio.render_csv(schema.ASSIGNMENTS_HEADER, assembly.assignments),
        "sections.csv": csvio.render_csv(
            schema.SECTIONS_HEADER,
            sorted(assembly.sections, key=lambda row: (row["ins"], row["section_key"])),
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    csvio.utf8_console()
    parser = argparse.ArgumentParser(description="Assemble the attributions (module docstring).")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--curation", type=Path, default=ROOT / "curation")
    parser.add_argument("--check", action="store_true", help="compare, write nothing")
    args = parser.parse_args(argv)
    try:
        assembly = assemble(load(args.data_dir, args.curation))
    except (CurationError, csvio.CsvError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    files: Mapping[str, bytes] = render(assembly)
    for line in assembly.summary:
        print(line)
    if args.check:
        stale = [
            name
            for name, data in files.items()
            if not (args.data_dir / name).is_file() or (args.data_dir / name).read_bytes() != data
        ]
        for name in stale:
            print(f"differs: {args.data_dir / name}", file=sys.stderr)
        return 1 if stale else 0
    for name, data in files.items():
        csvio.write_bytes(args.data_dir / name, data)
        print(f"wrote {args.data_dir / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
