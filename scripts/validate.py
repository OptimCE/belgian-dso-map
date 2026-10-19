"""Validate the data: rules 1-10 and 8bis of the contract, plus consistency checks.

    python scripts/validate.py [--ignore-acceptance] [--release] [--as-of YYYY-MM-DD]
                               [--report REPORT.md] [--sources-md SOURCES.md]
                               [--refresh-powerbi-summary]
    python scripts/validate.py --fixture --ignore-acceptance     # tests/fixtures/mini

Exit codes: 0 = pass (warnings allowed), 1 = errors, 2 = usage or I/O error.
Runs offline on data/, curation/ and tests/vectors.csv, against an in-memory build.

Rules (README.md, "Validation"):
1. 565 INS (285 VLA / 261 WAL / 19 BRU), equal to REFNIS 2025; region and province
   agree with the INS.
2. Each commune has an electricity operator and an explicit gas_status; `none` cites
   an R source.
3. Each attribution cites an R source; in VLA/WAL also an M or C source of another
   publisher, or it carries `to_confirm`.
4. Each `to_confirm` has a note accepted by Eric (accepted_by + accepted_on).
5. Postcode <-> INS coverage; section postcodes are Statbel pairs and cover every pair
   of the INS.
6. Operator ids exist with the right kind, vector, region and `lookup:true`.
7. An INS is in assignments XOR sections; section keys are unique per INS.
8. tests/vectors.csv passes against the built dso_lookup.csv.
8bis. Two builds are byte-identical; unchanged rows keep their dates; no date after
   the version date.
9. A source retrieved more than 365 days before the as-of date: warning; after the
   version date: error.
10. Warnings: Flemish counts per DSO against the spec's list; ORES against the 2022
   opinion.

Cross-checks (warnings, also listed under "Cross-check disagreements" in REPORT.md): the
worksheets, the spot checks, the Fluvius extract (Flemish rows) and the CWaPE Power BI
summary (Walloon rows, scripts/powerbi.py). A disagreement is "explained" when the row
carries a `valid_from` (a dated change the reading may predate) or `to_confirm`, or, for
gas, when the row has a designated DSO that the map does not show (a designation does
not guarantee a network).

The Power BI findings come from the committed summary curation/powerbi_checks.csv only,
so REPORT.md does not depend on the full readings, which stay local in curation/private/
(git-ignored). When they are present, their format is checked and the summary must follow
from them (an error otherwise); --refresh-powerbi-summary rewrites it from them first.
Their absence is never an error.

--fixture skips the national checks of rules 1, 5 and 10 (a small dataset has no 565
communes): the counts, the REFNIS and Statbel extracts, REFNIS Langue -> region.
Outside fixture mode a missing REFNIS or Statbel extract is an error: the equality
of rules 1 and 5 cannot be skipped by deleting a file.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import build
import csvio
import dates
import lookup
import powerbi
import report
import schema
from report import Findings

Row = Mapping[str, str]

COMMUNE_COUNTS = {"VLA": 285, "WAL": 261, "BRU": 19}
POSTCODE_PAIRS = 1152
MULTI_INS_POSTCODES = {"1040", "1050", "1804"}
STALE_DAYS = 365
COUNT_RE = re.compile(r"[1-9][0-9]*")


@dataclass(frozen=True)
class Outcome:
    build: build.Build
    findings: Findings
    files: dict[str, bytes]  # every output file, REPORT.md and SHA256SUMS included


def build_and_check(
    ctx: build.Context,
    *,
    draft: bool,
    release: bool,
    ignore_acceptance: bool,
    as_of: str,
    refresh_powerbi: bool = False,
) -> Outcome:
    """Build in memory, validate the data and the build, render REPORT.md.

    `refresh_powerbi` first rewrites curation/powerbi_checks.csv from the full Power BI
    readings of curation/private/ (when they are present and well formed).
    """

    def make() -> build.Build:
        return build.make_build(
            ctx.dataset,
            version=ctx.version,
            date=ctx.date,
            draft=draft,
            previous=ctx.previous,
            vectors_bytes=ctx.vectors_bytes,
            attribution_bytes=ctx.attribution_bytes,
        )

    built = make()
    findings = Checker(
        ctx,
        built,
        release=release,
        ignore_acceptance=ignore_acceptance,
        as_of=as_of,
        refresh_powerbi=refresh_powerbi,
    ).run(rebuild=make)
    mode = ("release" if release else "draft" if draft else "check") + (
        " (fixture)" if ctx.fixture else ""
    )
    text = report.render_report(
        data_version=built.data_version,
        version_date=ctx.date,
        as_of=as_of,
        mode=mode,
        dataset=ctx.dataset,
        lookup_rows=built.tables["dso_lookup.csv"],
        findings=findings,
        vectors_total=len(ctx.vectors),
        national=not ctx.fixture,
    )
    return Outcome(built, findings, build.finalize(built, text))


def _sorted_check(findings: Findings, name: str, rows: Sequence[Row], *columns: str) -> None:
    """Rows sorted by `columns`, without duplicate keys."""
    keys = [tuple(row[column] for column in columns) for row in rows]
    if keys != sorted(keys):
        findings.error("format", f"{name}: rows are not sorted by {', '.join(columns)}")
    for key, count in sorted(Counter(keys).items()):
        if count > 1:
            findings.error("format", f"{name}: duplicate key {'|'.join(key)}")


class Checker:
    def __init__(
        self,
        ctx: build.Context,
        built: build.Build,
        *,
        release: bool,
        ignore_acceptance: bool,
        as_of: str,
        refresh_powerbi: bool = False,
    ) -> None:
        self.ctx = ctx
        self.ds = ctx.dataset
        self.built = built
        self.release = release
        self.ignore_acceptance = ignore_acceptance
        self.as_of = as_of
        self.refresh_powerbi = refresh_powerbi
        self.strict = not ctx.fixture
        self.f = Findings()
        self.communes = {row["ins"]: row for row in self.ds.communes}
        self.operators = {row["id"]: row for row in self.ds.operators}
        self.sources = {row["id"]: row for row in self.ds.sources}
        self.notes = {row["key"]: row for row in self.ds.notes}
        self.sectioned = {row["ins"] for row in self.ds.sections}
        self.pairs = {(row["postcode"], row["ins"]) for row in self.ds.postcodes}
        self.worksheet_sources: set[str] = set()

    # --- helpers --------------------------------------------------------------------------

    def attributions(self) -> list[tuple[str, Row]]:
        """(label, row) of every assignment and section."""
        labelled: list[tuple[str, Row]] = [(row["ins"], row) for row in self.ds.assignments]
        labelled += [(f"{row['ins']}/{row['section_key']}", row) for row in self.ds.sections]
        return labelled

    def region(self, row: Row) -> str:
        return self.communes.get(row["ins"], {}).get("region", "")

    def cited(self, row: Row, roles: Sequence[str]) -> list[Row]:
        cited = (self.sources.get(source) for source in schema.split_list(row["source_ids"]))
        return [source for source in cited if source is not None and source["role"] in roles]

    def run(self, *, rebuild: Callable[[], build.Build] | None) -> Findings:
        self.check_formats()
        self.rule1_communes()
        self.rule2_coverage()
        self.rule3_sources()
        self.rule4_acceptance()
        self.rule5_postcodes()
        self.rule6_operators()
        self.rule7_sections()
        self.rule8_vectors()
        self.rule8bis_dates(rebuild)
        self.rule9_source_ages()
        if self.strict:
            self.rule10_counts()
        self.check_consistency()
        self.check_curation()
        self.check_references()
        return self.f

    # --- formats --------------------------------------------------------------------------

    def check_formats(self) -> None:
        f, ds = self.f, self.ds
        _sorted_check(f, "communes.csv", ds.communes, "ins")
        for row in ds.communes:
            if not schema.INS_RE.fullmatch(row["ins"]):
                f.error("format", f"communes.csv: INS {row['ins']!r} is not 5 digits")
            if not row["nom_fr"] or not row["nom_nl"]:
                f.error("format", f"communes.csv {row['ins']}: nom_fr and nom_nl are required")
            if row["region"] not in schema.REGIONS:
                f.error("format", f"communes.csv {row['ins']}: region {row['region']!r}")
            if row["province"] and row["province"] not in schema.PROVINCES:
                f.error("format", f"communes.csv {row['ins']}: province {row['province']!r}")

        _sorted_check(f, "postcodes.csv", ds.postcodes, "postcode", "ins")
        for row in ds.postcodes:
            if not schema.POSTCODE_RE.fullmatch(row["postcode"]):
                f.error("format", f"postcodes.csv: postcode {row['postcode']!r} is not 4 digits")
            if not schema.INS_RE.fullmatch(row["ins"]):
                f.error("format", f"postcodes.csv {row['postcode']}: INS {row['ins']!r}")

        _sorted_check(f, "assignments.csv", ds.assignments, "ins")
        _sorted_check(f, "sections.csv", ds.sections, "ins", "section_key")
        for label, attribution in self.attributions():
            self.check_attribution_format(label, attribution)
        for row in ds.sections:
            label = f"sections.csv {row['ins']}/{row['section_key']}"
            if not schema.SLUG_RE.fullmatch(row["section_key"]):
                f.error("format", f"{label}: section_key is not a lowercase slug")
            if not row["nom_fr"]:
                f.error("format", f"{label}: nom_fr is required")
            postcodes = schema.split_list(row["postcodes"])
            if not postcodes or postcodes != sorted(set(postcodes)):
                f.error("format", f"{label}: postcodes must be a sorted list without duplicates")
            for postcode in postcodes:
                if not schema.POSTCODE_RE.fullmatch(postcode):
                    f.error("format", f"{label}: postcode {postcode!r} is not 4 digits")

        self.check_operators_format()

        _sorted_check(f, "sources.csv", ds.sources, "id")
        for row in ds.sources:
            label = f"sources.csv {row['id']}"
            if not schema.SLUG_RE.fullmatch(row["id"]):
                f.error("format", f"{label}: id is not a lowercase slug")
            if row["role"] not in schema.ROLES:
                f.error("format", f"{label}: role {row['role']!r} is not R, M, C or X")
            if not row["publisher"] or not row["title"]:
                f.error("format", f"{label}: publisher and title are required")
            if not schema.URL_RE.fullmatch(row["url"]):
                f.error("format", f"{label}: url {row['url']!r} is not an http(s) URL")
            if not schema.is_date(row["retrieved_at"]):
                f.error("format", f"{label}: retrieved_at {row['retrieved_at']!r} is not a date")
            if row["sha256"] and not schema.SHA256_RE.fullmatch(row["sha256"]):
                f.error("format", f"{label}: sha256 is not 64 lowercase hex digits")

        _sorted_check(f, "notes.csv", ds.notes, "key")
        for row in ds.notes:
            label = f"notes.csv {row['key']}"
            if not schema.SLUG_RE.fullmatch(row["key"]):
                f.error("format", f"{label}: key is not a lowercase slug")
            if row["key"].startswith("dataset-") and not schema.DATASET_NOTE_RE.fullmatch(
                row["key"]
            ):
                f.error("format", f"{label}: dataset notes are named dataset-<bru|vla|wal>-...")
            if not row["fr"]:
                f.error("notes", f"{label}: the FR text is required")
            if self.release:
                missing = [lang for lang in schema.NOTE_TEXT_COLUMNS if not row[lang]]
                if missing:
                    f.error(
                        "notes",
                        f"{label}: a release needs every language (missing {', '.join(missing)})",
                    )

    def check_attribution_format(self, label: str, row: Row) -> None:
        f = self.f
        if not schema.INS_RE.fullmatch(row["ins"]):
            f.error("format", f"{label}: INS {row['ins']!r} is not 5 digits")
        for column in ("elec_operator", "elec_designated"):
            if not row[column]:
                f.error("rule 2", f"{label}: {column} is required")
        if row["gas_status"] not in schema.GAS_STATUSES:
            f.error(
                "rule 2",
                f"{label}: gas_status {row['gas_status']!r} is not designated, none or foreign",
            )
        flags = schema.split_list(row["flags"])
        unknown = [flag for flag in flags if flag not in schema.FLAGS]
        if unknown:
            f.error("format", f"{label}: unknown flags {', '.join(unknown)}")
        elif flags != schema.canonical_flags(flags) or len(set(flags)) != len(flags):
            f.error(
                "format", f"{label}: flags must be unique, in the order {'|'.join(schema.FLAGS)}"
            )
        if row["note_key"] and not schema.SLUG_RE.fullmatch(row["note_key"]):
            f.error("format", f"{label}: note_key {row['note_key']!r} is not a slug")
        source_ids = schema.split_list(row["source_ids"])
        if len(set(source_ids)) != len(source_ids):
            f.error("format", f"{label}: duplicate source id")
        if row["valid_from"] and not schema.is_date(row["valid_from"]):
            f.error("format", f"{label}: valid_from {row['valid_from']!r} is not a date")

    def check_operators_format(self) -> None:
        f = self.f
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        previous_rank: tuple[int, int] = (-1, -1)
        for row in self.ds.operators:
            label = f"operators.csv {row['id']}"
            if not schema.SLUG_RE.fullmatch(row["id"]):
                f.error("format", f"{label}: id is not a lowercase slug")
            if row["id"] in seen_ids or row["name"] in seen_names:
                f.error("format", f"{label}: duplicate id or name")
            seen_ids.add(row["id"])
            seen_names.add(row["name"])
            if row["kind"] not in schema.KIND_RANK or row["region"] not in schema.REGION_RANK:
                f.error("format", f"{label}: kind {row['kind']!r} or region {row['region']!r}")
                continue
            rank = (schema.KIND_RANK[row["kind"]], schema.REGION_RANK[row["region"]])
            if rank < previous_rank:
                f.error(
                    "format",
                    f"{label}: operators are listed by kind (grd, gas_foreign, grtl), "
                    "then region (WAL, BRU, VLA)",
                )
            previous_rank = max(previous_rank, rank)
            if not row["name"] or not row["legal_name"]:
                f.error("format", f"{label}: name and legal_name are required")
            for column in ("elec", "gas", "lookup"):
                if row[column] not in schema.BOOLEANS:
                    f.error("format", f"{label}: {column} must be true or false")
            if "true" not in (row["elec"], row["gas"]):
                f.error("format", f"{label}: an operator carries electricity, gas or both")
            for column in ("website", "tariffs_url"):
                if row[column] and not (
                    row[column].startswith("https://") and schema.URL_RE.fullmatch(row[column])
                ):
                    f.error("format", f"{label}: {column} must be an https URL or empty")
            if row["regulator"] != lookup.REGION_REGULATOR[row["region"]]:
                f.error(
                    "format",
                    f"{label}: the regulator of {row['region']} is "
                    f"{lookup.REGION_REGULATOR[row['region']]}",
                )
            if row["kind"] == "grtl" and row["lookup"] != "false":
                f.error(
                    "rule 6",
                    f"{label}: a local transmission operator is never returned by a lookup",
                )
            if row["replaced_by"] and (
                row["replaced_by"] == row["id"] or row["replaced_by"] not in self.operators
            ):
                f.error(
                    "format", f"{label}: replaced_by {row['replaced_by']!r} is not another operator"
                )

    # --- rules ----------------------------------------------------------------------------

    def rule1_communes(self) -> None:
        f = self.f
        for row in self.ds.communes:
            geography = schema.ins_geography(row["ins"])
            if geography is None:
                f.error("rule 1", f"{row['ins']}: no region for this INS prefix")
            elif (row["region"], row["province"]) != geography:
                f.error(
                    "rule 1",
                    f"{row['ins']}: region/province {row['region']}/{row['province'] or '-'}, "
                    f"the INS implies {geography[0]}/{geography[1] or '-'}",
                )
        if not self.strict:
            return
        by_region = {region: 0 for region in schema.REGIONS}
        for row in self.ds.communes:
            by_region[row["region"]] = by_region.get(row["region"], 0) + 1
        if len(self.ds.communes) != sum(COMMUNE_COUNTS.values()) or any(
            by_region.get(region) != count for region, count in COMMUNE_COUNTS.items()
        ):
            f.error(
                "rule 1",
                f"{len(self.ds.communes)} communes {by_region}, expected 565 {COMMUNE_COUNTS}",
            )
        derived = self.derived("statbel_refnis_2025_communes.csv", schema.DERIVED_COMMUNES_HEADER)
        if derived is None:
            f.error(
                "rule 1",
                "curation/derived/statbel_refnis_2025_communes.csv missing: "
                "REFNIS equality not checked",
            )
            return
        refnis = {row["ins"]: row for row in derived}
        if set(refnis) != set(self.communes):
            only_data = sorted(set(self.communes) - set(refnis))
            only_refnis = sorted(set(refnis) - set(self.communes))
            f.error(
                "rule 1",
                f"INS differ from REFNIS 2025: data only {only_data}, REFNIS only {only_refnis}",
            )
        for ins, row in sorted(refnis.items()):
            commune = self.communes.get(ins)
            if commune and schema.LANGUE_REGION.get(row["langue"]) != commune["region"]:
                f.error(
                    "rule 1",
                    f"{ins}: region {commune['region']} but REFNIS Langue {row['langue']!r}",
                )

    def rule2_coverage(self) -> None:
        f = self.f
        assigned = {row["ins"] for row in self.ds.assignments}
        for ins in sorted(self.communes):
            if ins not in assigned and ins not in self.sectioned:
                f.error("rule 2", f"{ins} {self.communes[ins]['nom_fr']}: no electricity operator")
        for label, row in self.attributions():
            status, operator = row["gas_status"], row["gas_operator"]
            if status in ("designated", "foreign") and not operator:
                f.error("rule 2", f"{label}: gas {status} needs a gas_operator")
            if status == "none":
                if operator:
                    f.error("rule 2", f"{label}: gas none with a gas_operator")
                if not self.cited(row, ("R",)):
                    f.error(
                        "rule 2", f"{label}: gas none must cite an R source showing the absence"
                    )

    def rule3_sources(self) -> None:
        f = self.f
        for label, row in self.attributions():
            references = self.cited(row, ("R",))
            if not references:
                f.error("rule 3", f"{label}: no R source")
                continue
            if self.region(row) not in ("VLA", "WAL"):
                continue
            checks = self.cited(row, ("M", "C"))
            independent = any(
                check["publisher"] != reference["publisher"]
                for reference in references
                for check in checks
            )
            if not independent and "to_confirm" not in schema.split_list(row["flags"]):
                f.error(
                    "rule 3",
                    f"{label}: one R plus one M/C source of another publisher, or to_confirm",
                )

    def acceptance(self, note: Row, why: str) -> None:
        f = self.f
        accepted_by, accepted_on = note["accepted_by"], note["accepted_on"]
        label = f"note {note['key']}"
        if bool(accepted_by) != bool(accepted_on):
            f.error("rule 4", f"{label}: accepted_by and accepted_on go together")
        elif accepted_on and not schema.is_date(accepted_on):
            f.error("rule 4", f"{label}: accepted_on {accepted_on!r} is not a date")
        elif accepted_on and accepted_on > self.ctx.date:
            f.error("rule 4", f"{label}: accepted after the version date")
        elif not accepted_by:
            if self.ignore_acceptance:
                f.pend("rule 4", f"{label} ({why}): PENDING acceptance by Eric")
            else:
                f.error(
                    "rule 4", f"{label} ({why}): not accepted (accepted_by/accepted_on are Eric's)"
                )

    def rule4_acceptance(self) -> None:
        needing: dict[str, str] = {}
        for label, row in self.attributions():
            if "to_confirm" not in schema.split_list(row["flags"]):
                continue
            if not row["note_key"]:
                self.f.error("rule 4", f"{label}: to_confirm without a note_key")
            else:
                needing.setdefault(row["note_key"], f"to_confirm on {label}")
        if self.release:
            for key in self.notes:
                needing.setdefault(key, "release")
        for key, why in sorted(needing.items()):
            note = self.notes.get(key)
            if note is not None:
                self.acceptance(note, why)

    def rule5_postcodes(self) -> None:
        f = self.f
        with_postcode = set()
        for postcode, ins in sorted(self.pairs):
            if ins not in self.communes:
                f.error("rule 5", f"postcode {postcode}: unknown INS {ins}")
            with_postcode.add(ins)
        for ins in sorted(set(self.communes) - with_postcode):
            f.error("rule 5", f"{ins} {self.communes[ins]['nom_fr']}: no postcode")
        covered = set()
        for row in self.ds.sections:
            for postcode in schema.split_list(row["postcodes"]):
                if (postcode, row["ins"]) not in self.pairs:
                    f.error(
                        "rule 5",
                        f"{row['ins']}/{row['section_key']}: {postcode} is not a postcode "
                        f"of {row['ins']}",
                    )
                covered.add((postcode, row["ins"]))
        for postcode, ins in sorted(self.pairs):
            if ins in self.sectioned and (postcode, ins) not in covered:
                f.error("rule 5", f"{ins}: no section covers postcode {postcode}")
        if not self.strict:
            return
        if len(self.pairs) != POSTCODE_PAIRS:
            f.error("rule 5", f"{len(self.pairs)} (postcode, INS) pairs, expected {POSTCODE_PAIRS}")
        counts: dict[str, int] = {}
        for postcode, _ in self.pairs:
            counts[postcode] = counts.get(postcode, 0) + 1
        multi = {postcode for postcode, count in counts.items() if count > 1}
        if multi != MULTI_INS_POSTCODES:
            f.error(
                "rule 5",
                f"postcodes shared by several INS: {sorted(multi)}, "
                f"expected {sorted(MULTI_INS_POSTCODES)}",
            )
        derived = self.derived("statbel_postcodes_2025.csv", schema.DERIVED_POSTCODES_HEADER)
        if derived is None:
            f.error(
                "rule 5",
                "curation/derived/statbel_postcodes_2025.csv missing: Statbel pairs not checked",
            )
        elif {(row["postcode"], row["ins"]) for row in derived} != self.pairs:
            f.error(
                "rule 5", "postcodes.csv differs from curation/derived/statbel_postcodes_2025.csv"
            )

    def check_operator(
        self, label: str, operator_id: str, *, vector: str, kinds: Sequence[str], region: str
    ) -> None:
        f = self.f
        operator = self.operators.get(operator_id)
        if operator is None:
            f.error("rule 6", f"{label}: unknown operator {operator_id!r}")
            return
        if operator["kind"] not in kinds:
            f.error(
                "rule 6",
                f"{label}: {operator_id} is a {operator['kind']}, expected {' or '.join(kinds)}",
            )
        if operator[vector] != "true":
            f.error("rule 6", f"{label}: {operator_id} does not operate {vector}")
        if operator["lookup"] != "true":
            f.error("rule 6", f"{label}: {operator_id} has lookup:false and is never assigned")
        if operator["replaced_by"]:
            f.error("rule 6", f"{label}: {operator_id} was replaced by {operator['replaced_by']}")
        if operator["kind"] != "gas_foreign" and region and operator["region"] != region:
            f.error(
                "rule 6", f"{label}: {operator_id} is a {operator['region']} operator in {region}"
            )

    def rule6_operators(self) -> None:
        for label, row in self.attributions():
            region = self.region(row)
            for column in ("elec_operator", "elec_designated"):
                if row[column]:
                    self.check_operator(
                        label, row[column], vector="elec", kinds=("grd",), region=region
                    )
            if row["gas_operator"]:
                kinds = ("gas_foreign",) if row["gas_status"] == "foreign" else ("grd",)
                self.check_operator(
                    label, row["gas_operator"], vector="gas", kinds=kinds, region=region
                )

    def rule7_sections(self) -> None:
        f = self.f
        for ins in sorted(self.sectioned & {row["ins"] for row in self.ds.assignments}):
            f.error("rule 7", f"{ins}: in assignments.csv and sections.csv (all or nothing)")
        for label, row in self.attributions():
            if row["ins"] not in self.communes:
                f.error("rule 7", f"{label}: unknown INS")

    def rule8_vectors(self) -> None:
        for problem in vector_problems(self.ctx.vectors):
            self.f.error("rule 8", problem)
        index = lookup.build_index(self.built.tables["dso_lookup.csv"])
        for failure in lookup.run_vectors(index, self.ctx.vectors):
            self.f.error("rule 8", failure)

    def rule8bis_dates(self, rebuild: Callable[[], build.Build] | None) -> None:
        f, built = self.f, self.built
        if rebuild is not None:
            again = rebuild()
            for name in sorted(set(built.files) | set(again.files)):
                if built.files.get(name) != again.files.get(name):
                    f.error("rule 8bis", f"{name}: two builds of the same inputs differ")
        previous = self.ctx.previous
        for name, rows in built.tables.items():
            data_columns, key_columns, _ = build.DATED_TABLES[name]
            before: dict[tuple[str, ...], Row] = {}
            columns: tuple[str, ...] = ()
            if previous is not None:
                header, previous_rows = previous.tables[name]
                before = {
                    tuple(row[column] for column in key_columns): row for row in previous_rows
                }
                columns = dates.compared_columns(data_columns, header)
            for row in rows:
                key = tuple(row[column] for column in key_columns)
                label = f"{name} {'|'.join(key)}"
                if row["data_version"] != built.data_version:
                    f.error("rule 8bis", f"{label}: data_version {row['data_version']}")
                if not row["first_seen"] <= row["changed_at"] <= self.ctx.date:
                    f.error(
                        "rule 8bis", f"{label}: first_seen <= changed_at <= {self.ctx.date} broken"
                    )
                old = before.get(key)
                unchanged = old is not None and dates.fingerprint(
                    old, columns
                ) == dates.fingerprint(row, columns)
                moved = old is not None and (old["first_seen"], old["changed_at"]) != (
                    row["first_seen"],
                    row["changed_at"],
                )
                if unchanged and moved:
                    f.error(
                        "rule 8bis", f"{label}: unchanged since the previous version, dates moved"
                    )

    def rule9_source_ages(self) -> None:
        stale_before = (date.fromisoformat(self.as_of) - timedelta(days=STALE_DAYS)).isoformat()
        for row in self.ds.sources:
            retrieved = row["retrieved_at"]
            if not schema.is_date(retrieved):
                continue
            if retrieved > self.ctx.date:
                self.f.error(
                    "rule 9",
                    f"source {row['id']}: retrieved {retrieved}, "
                    f"after the version date {self.ctx.date}",
                )
            elif retrieved < stale_before:
                self.f.warn(
                    "rule 9",
                    f"source {row['id']}: retrieved {retrieved}, "
                    f"more than {STALE_DAYS} days before {self.as_of}",
                )

    def rule10_counts(self) -> None:
        designated: dict[str, set[str]] = {}
        for _, row in self.attributions():
            designated.setdefault(row["elec_designated"], set()).add(row["ins"])
        vla = {
            operator: {ins for ins in inses if self.communes.get(ins, {}).get("region") == "VLA"}
            for operator, inses in designated.items()
        }
        for operator, expected in report.VREG_COUNTS.items():
            found = len(vla.get(operator, ()))
            if found != expected:
                self.f.warn(
                    "rule 10",
                    f"{operator}: designated in {found} Flemish communes, "
                    f"the spec's list says {expected}",
                )
        ores = {
            ins
            for ins in designated.get("ores", ())
            if self.communes.get(ins, {}).get("region") == "WAL"
        }
        expected_ores = report.ORES_2022_COUNT + sum(delta for _, delta in report.ORES_ADJUSTMENTS)
        if len(ores) != expected_ores:
            self.f.warn(
                "rule 10",
                f"ores: designated in {len(ores)} Walloon communes, {expected_ores} expected "
                f"from the 2022 opinion ({report.ORES_2022_COUNT}) and the known changes",
            )

    # --- consistency, curation and references -------------------------------------------

    def check_consistency(self) -> None:
        f = self.f
        stale_before = (date.fromisoformat(self.as_of) - timedelta(days=STALE_DAYS)).isoformat()
        for label, row in self.attributions():
            flags = schema.split_list(row["flags"])
            differs = row["elec_operator"] != row["elec_designated"]
            if differs != ("operator_differs" in flags):
                f.error(
                    "consistency",
                    f"{label}: operator_differs is set exactly when operator != designated",
                )
            if "transition" in flags:
                if not row["note_key"]:
                    f.error("consistency", f"{label}: transition needs a note")
                if row["valid_from"] and row["valid_from"] < stale_before:
                    f.warn(
                        "consistency",
                        f"{label}: transition since {row['valid_from']}, "
                        "over a year: drop the flag?",
                    )
            if "propane_note" in flags and self.region(row) != "WAL":
                f.error("consistency", f"{label}: propane_note is a Walloon (RESA) flag")
            if row["valid_from"] and row["valid_from"] > self.ctx.date:
                f.error(
                    "consistency",
                    f"{label}: valid_from {row['valid_from']} is after the version date",
                )

    def derived(self, name: str, header: Sequence[str]) -> list[dict[str, str]] | None:
        if self.ctx.curation_dir is None:
            return None
        path = self.ctx.curation_dir / "derived" / name
        if not path.is_file():
            return None
        try:
            return csvio.read_csv(path, header)
        except csvio.CsvError as exc:
            self.f.error("curation", str(exc))
            return None

    def check_curation(self) -> None:
        if self.ctx.curation_dir is None:
            return
        f = self.f
        by_ins: dict[str, list[Row]] = {}
        for _, row in self.attributions():
            by_ins.setdefault(row["ins"], []).append(row)
        for path in sorted(self.ctx.curation_dir.glob("*_designations.csv")):
            try:
                rows = csvio.read_csv(path, schema.WORKSHEET_HEADER)
            except csvio.CsvError as exc:
                f.error("curation", str(exc))
                continue
            for number, row in enumerate(rows, start=2):
                label = f"{path.name}:{number}"
                if row["grd"] not in self.operators or row["vector"] not in schema.VECTORS:
                    f.error(
                        "curation",
                        f"{label}: unknown operator {row['grd']!r} or vector {row['vector']!r}",
                    )
                    continue
                if row["ins"] not in self.communes:
                    f.error("curation", f"{label}: unknown INS {row['ins']!r}")
                    continue
                if row["source_id"] not in self.sources:
                    f.error("curation", f"{label}: unknown source {row['source_id']!r}")
                self.worksheet_sources.add(row["source_id"])
                column = "elec_designated" if row["vector"] == "elec" else "gas_operator"
                if not any(
                    attribution[column] == row["grd"] for attribution in by_ins.get(row["ins"], ())
                ):
                    f.disagree(
                        "curation",
                        f"{label}: {row['source_id']} designates {row['grd']} ({row['vector']}) "
                        f"in {row['ins']}, the data does not",
                    )
        spot_checks = self.ctx.curation_dir / "spot_checks.csv"
        if spot_checks.is_file():
            self.check_spot_checks(spot_checks, by_ins)
        self.check_fluvius()
        self.check_powerbi()

    def check_spot_checks(self, path: Path, by_ins: Mapping[str, list[Row]]) -> None:
        f = self.f
        try:
            rows = csvio.read_csv(path, schema.SPOT_CHECKS_HEADER)
        except csvio.CsvError as exc:
            f.error("curation", str(exc))
            return
        for number, row in enumerate(rows, start=2):
            label = f"spot_checks.csv:{number}"
            if (
                not schema.is_date(row["date"])
                or row["tool"] not in self.sources
                or row["ins"] not in self.communes
                or row["vector"] not in schema.VECTORS
                or row["matches"] not in schema.BOOLEANS
                or (row["observed"] != "none" and row["observed"] not in self.operators)
            ):
                f.error(
                    "curation",
                    f"{label}: date, tool (a source id), INS, vector, "
                    "observed (operator id or none), matches",
                )
                continue
            self.worksheet_sources.add(row["tool"])
            attributions = by_ins.get(row["ins"], ())
            if row["vector"] == "elec":
                agrees = any(a["elec_operator"] == row["observed"] for a in attributions)
            elif row["observed"] == "none":
                agrees = any(a["gas_status"] == "none" for a in attributions)
            else:
                agrees = any(a["gas_operator"] == row["observed"] for a in attributions)
            if not agrees or row["matches"] == "false":
                no_network = (
                    row["vector"] == "gas"
                    and row["observed"] == "none"
                    and any(a["gas_operator"] for a in attributions)
                )
                f.disagree(
                    "curation",
                    f"{label}: {row['tool']} on {row['date']} shows {row['observed']} "
                    f"({row['vector']}) in {row['ins']} (matches={row['matches']})"
                    + explanation(attributions, no_network=no_network),
                )

    def check_fluvius(self) -> None:
        derived = self.derived("fluvius_1_23.csv", schema.DERIVED_FLUVIUS_HEADER)
        if derived is None:
            if self.strict:
                self.f.warn(
                    "cross-check",
                    "curation/derived/fluvius_1_23.csv missing: Flemish rows not cross-checked",
                )
            return
        rows = {(row["postcode"], row["ins"]): row for row in self.built.tables["dso_lookup.csv"]}
        for item in derived:
            row = rows.get((item["postcode"], item["ins"]))
            if row is None or row["section_key"]:
                continue
            gas = item["gas_id"] or ""
            if row["elec_operator"] != item["elec_id"] or row["gas_operator"] != gas:
                explained = (
                    f" (explained: valid_from {row['valid_from']})" if row["valid_from"] else ""
                )
                self.f.disagree(
                    "cross-check",
                    f"Fluvius {item['postcode']} {item['community']}: "
                    f"{item['elec_id']}/{gas or 'none'}, data {row['elec_operator']}/"
                    f"{row['gas_operator'] or 'none'}{explained}",
                )

    def powerbi_targets(self) -> list[tuple[Row, powerbi.Target]]:
        """(row, target) of every Walloon assignment and section, in attribution order."""
        return [
            (row, powerbi.target(self.communes[row["ins"]], row))
            for _, row in self.attributions()
            if self.region(row) == "WAL"
        ]

    def check_powerbi(self) -> None:
        """The CWaPE Power BI cross-check of every Walloon row (scripts/powerbi.py).

        The findings come from the committed summary (curation/powerbi_checks.csv) only,
        so REPORT.md is the same with or without the full readings, which are local
        (curation/private/, git-ignored). When they are present, they are checked and the
        summary must follow from them (--refresh-powerbi-summary rewrites it).
        """
        if self.ctx.curation_dir is None:
            return
        f = self.f
        summary_path = self.ctx.curation_dir / powerbi.SUMMARY_FILE
        aliases_path = self.ctx.curation_dir / "aliases.csv"
        try:
            reading = powerbi.load(self.ctx.curation_dir / powerbi.PRIVATE_DIR)
            summary = powerbi.load_summary(summary_path)
            aliases = {
                (row["name_in_source"], row["ins"])
                for row in (
                    csvio.read_csv(aliases_path, schema.ALIASES_HEADER)
                    if aliases_path.is_file()
                    else []
                )
            }
        except csvio.CsvError as exc:
            f.error("curation", str(exc))
            return
        if reading is not None and self.powerbi_format(reading, aliases):
            targets = [item for _, item in self.powerbi_targets()]
            computed = powerbi.summarize(reading, targets, keep=summary or [])
            if self.refresh_powerbi:
                csvio.write_csv(summary_path, powerbi.SUMMARY_HEADER, computed)
                summary = computed
            elif computed != summary:
                f.error(
                    "curation",
                    f"curation/{powerbi.SUMMARY_FILE} does not follow from the readings of "
                    f"curation/{powerbi.PRIVATE_DIR}/: run scripts/validate.py "
                    "--refresh-powerbi-summary",
                )
        if summary is None:
            if self.strict:
                f.warn(
                    "cross-check",
                    f"curation/{powerbi.SUMMARY_FILE} missing: Walloon rows not cross-checked "
                    "with the CWaPE Power BI",
                )
            return
        if self.powerbi_summary_format(summary):
            self.compare_powerbi(summary)

    def compare_powerbi(self, summary: Sequence[Row]) -> None:
        """The disagreements of the summary, and the rows changed since it was written."""
        f = self.f
        by_key = {powerbi.summary_key(row): row for row in summary}
        refresh = (
            f"run scripts/validate.py --refresh-powerbi-summary (it needs the full readings "
            f"of curation/{powerbi.PRIVATE_DIR}/)"
        )
        for vector, (name, _) in powerbi.READINGS.items():
            if self.strict and not any(row["vector"] == vector for row in summary):
                f.warn(
                    "cross-check",
                    f"curation/{powerbi.SUMMARY_FILE} has no {vector} row ({name} not read): "
                    "Walloon rows not cross-checked with the CWaPE Power BI",
                )
        targets = self.powerbi_targets()
        known = {(item.ins, item.section_key) for _, item in targets}
        for number, row in enumerate(summary, start=2):
            if (row["ins"], row["section_key"]) not in known:
                f.warn(
                    "cross-check",
                    f"{powerbi.SUMMARY_FILE}:{number}: "
                    f"{row['ins']}{'/' + row['section_key'] if row['section_key'] else ''} "
                    f"is no longer a row of the data: {refresh}",
                )
        for row, item in targets:
            for vector in schema.VECTORS:
                entry = by_key.get((item.ins, item.section_key, vector))
                if entry is None:
                    continue
                data = powerbi.data_value(vector, item)
                if entry["data"] != data:
                    f.warn(
                        "cross-check",
                        f"CWaPE Power BI {vector}, {item.label}: the summary compared "
                        f"{entry['data']}, the data now say {data}: {refresh}",
                    )
                    continue
                if entry["agrees"] == "true":
                    continue
                shown = entry["observed"]
                no_network = vector == "gas" and shown == powerbi.NONE and data != powerbi.NONE
                f.disagree(
                    "cross-check",
                    f"CWaPE Power BI {vector}, {item.label} {self.communes[item.ins]['nom_fr']}: "
                    f"{'no GRD shown' if shown == powerbi.NONE else shown}; data {data}"
                    + explanation([row], no_network=no_network),
                )

    def powerbi_summary_format(self, summary: Sequence[Row]) -> bool:
        """Sorted rows of a Walloon INS, a vector, the value compared (a DSO carrying the
        vector, or `none` for gas), `agrees`, and `observed` exactly on a disagreement."""
        f = self.f
        name = powerbi.SUMMARY_FILE
        ok = True
        _sorted_check(f, name, summary, "ins", "section_key", "vector")
        for number, row in enumerate(summary, start=2):
            operator = self.operators.get(row["data"], {})
            vector = row["vector"]
            data_ok = (vector == "gas" and row["data"] == powerbi.NONE) or (
                operator.get("kind") in ("grd", "gas_foreign") and operator.get(vector) == "true"
            )
            observed_ok = (
                row["observed"] == ""
                if row["agrees"] == "true"
                else bool(powerbi.OBSERVED_RE.fullmatch(row["observed"]))
            )
            if (
                self.communes.get(row["ins"], {}).get("region") != "WAL"
                or (row["section_key"] and not schema.SLUG_RE.fullmatch(row["section_key"]))
                or vector not in powerbi.READINGS
                or row["agrees"] not in schema.BOOLEANS
                or not data_ok
                or not observed_ok
            ):
                ok = False
                f.error(
                    "curation",
                    f"{name}:{number}: a Walloon INS, an empty or slug section_key, a vector, "
                    "the value compared (a DSO carrying the vector, or none for gas), agrees "
                    "(true or false), and observed only when it disagrees ('none' or the "
                    "GRD labels with their counts)",
                )
        return ok

    def powerbi_format(
        self, reading: powerbi.Reading, aliases: Collection[tuple[str, str]]
    ) -> bool:
        """Sorted rows of Walloon INS, labels, DSOs of the vector and positive counts.

        Each commune label names its INS (FR, NL or DE name under the name rule, or an
        alias of curation/aliases.csv: BERTOGNE -> 82039), and each `grd_id` is the id of
        its GRD label (`powerbi.label_to_id`: every "ORES ..." label is `ores`).
        """
        f = self.f
        ok = True
        for vector, rows in reading.rows.items():
            name = powerbi.READINGS[vector][0]
            _sorted_check(f, name, rows, "ins", "commune_label", "grd_label")
            for number, row in enumerate(rows, start=2):
                commune = self.communes.get(row["ins"], {})
                operator = self.operators.get(row["grd_id"], {})
                if (
                    commune.get("region") != "WAL"
                    or operator.get("kind") != "grd"
                    or operator.get(vector) != "true"
                    or not row["commune_label"]
                    or not row["grd_label"]
                    or not COUNT_RE.fullmatch(row["count"])
                ):
                    ok = False
                    f.error(
                        "curation",
                        f"{name}:{number}: a Walloon INS, a commune label, a GRD label, "
                        f"the id of a DSO carrying {vector} and a positive count",
                    )
                    continue
                names = [commune["nom_fr"], commune["nom_nl"], commune["nom_de"]]
                if not powerbi.label_matches(row["commune_label"], row["ins"], names, aliases):
                    ok = False
                    f.error(
                        "curation",
                        f"{name}:{number}: {row['commune_label']!r} is not a name of "
                        f"{row['ins']} ({commune['nom_fr']}) nor an alias of it in aliases.csv",
                    )
                grd_id = powerbi.label_to_id(row["grd_label"])
                if row["grd_id"] != grd_id:
                    ok = False
                    f.error(
                        "curation",
                        f"{name}:{number}: the GRD label {row['grd_label']!r} is {grd_id}, "
                        f"not {row['grd_id']}",
                    )
        return ok

    def check_references(self) -> None:
        f = self.f
        used_sources = set(self.worksheet_sources)
        used_notes = set()
        for label, row in self.attributions():
            for source in schema.split_list(row["source_ids"]):
                used_sources.add(source)
                if source not in self.sources:
                    f.error("references", f"{label}: unknown source {source!r}")
            if row["note_key"]:
                used_notes.add(row["note_key"])
                if row["note_key"] not in self.notes:
                    f.error("references", f"{label}: unknown note {row['note_key']!r}")
        for source in sorted(set(self.sources) - used_sources):
            if not source.startswith(schema.GEOGRAPHY_SOURCE_PREFIX):
                f.warn("references", f"source {source} is cited by no row")
        for key in sorted(set(self.notes) - used_notes):
            if not schema.DATASET_NOTE_RE.fullmatch(key):
                f.warn("references", f"note {key} is used by no row")


def explanation(rows: Sequence[Row], *, no_network: bool = False) -> str:
    """The suffix ' (explained: ...)' of a cross-check that may disagree with right rows.

    A row's `valid_from` is a dated change that the reading may predate; `to_confirm`
    marks an open question; for gas, `no_network` is a designated DSO that the map does
    not show: a designation does not guarantee a network (spec, "what the tool does not
    affirm"). Empty when nothing explains the disagreement.
    """
    reasons = [f"valid_from {day}" for day in sorted({row["valid_from"] for row in rows} - {""})]
    if any("to_confirm" in schema.split_list(row["flags"]) for row in rows):
        reasons.append("to_confirm")
    if no_network:
        reasons.append("a designation does not guarantee a network")
    return f" (explained: {', '.join(reasons)})" if reasons else ""


def vector_problems(vectors: Sequence[Row]) -> list[str]:
    """Format problems of a vectors.csv (README.md, "vectors.csv")."""
    problems = []
    names: set[str] = set()
    for vector in vectors:
        label = f"vector {vector['name']}"
        if not schema.SLUG_RE.fullmatch(vector["name"]) or vector["name"] in names:
            problems.append(f"{label}: names are unique lowercase slugs")
        names.add(vector["name"])
        kind = vector["kind"]
        if kind not in schema.VECTOR_KINDS:
            problems.append(f"{label}: kind {kind!r} is not postcode, address or ean")
            continue
        statuses = schema.EAN_STATUSES if kind == "ean" else schema.LOOKUP_STATUSES
        if vector["expect_status"] not in (*statuses, lookup.ANY):
            problems.append(f"{label}: expect_status {vector['expect_status']!r}")
        unused = {
            "postcode": ("post_name", "ean"),
            "address": ("section_key", "ean"),
            "ean": ("postcode", "ins", "section_key", "post_name"),
        }[kind]
        if any(vector[column] for column in unused):
            problems.append(f"{label}: a {kind} vector leaves {', '.join(unused)} empty")
        if kind == "ean":
            unused_expect = ("expect_key", "expect_gas_status", "expect_gas")
            if any(vector[column] not in ("", lookup.ANY) for column in unused_expect):
                problems.append(f"{label}: an ean vector only asserts status, elec and flags")
            allowed_flags: Sequence[str] = schema.EAN_FLAGS
        else:
            allowed_flags = schema.FLAGS
            if vector["expect_gas_status"] not in ("", lookup.ANY, *schema.GAS_STATUSES):
                problems.append(f"{label}: expect_gas_status {vector['expect_gas_status']!r}")
        flags = vector["expect_flags"]
        if flags != lookup.ANY and not set(schema.split_list(flags)) <= set(allowed_flags):
            problems.append(f"{label}: expect_flags {flags!r}")
    return problems


def render_sources_md(dataset: schema.Dataset) -> str:
    """SOURCES.md: every source, by role then publisher."""
    titles = {
        "R": "Legal references (R)",
        "M": "Machine-readable data (M)",
        "C": "Cross-checks (C)",
        "X": "Not used as a source (X)",
    }
    out = [
        "# Sources",
        "",
        "Generated by `scripts/validate.py --sources-md` from `data/sources.csv`.",
        "",
    ]
    for role in schema.ROLES:
        rows = sorted(
            (row for row in dataset.sources if row["role"] == role),
            key=lambda row: (row["publisher"], row["id"]),
        )
        if not rows:
            continue
        out += [f"## {titles[role]}", ""]
        out += [
            f"- **{row['publisher']}** — [{row['title']}]({row['url']})"
            + f" · retrieved {row['retrieved_at']}"
            + (f" · {row['license']}" if row["license"] else "")
            + f" · `{row['id']}`"
            for row in rows
        ]
        out += [""]
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    csvio.utf8_console()
    parser = argparse.ArgumentParser(description="Validate the data (see the module docstring).")
    build.add_common_arguments(parser)
    acceptance = parser.add_mutually_exclusive_group()
    acceptance.add_argument(
        "--ignore-acceptance", action="store_true", help="report unaccepted notes as PENDING"
    )
    acceptance.add_argument(
        "--release", action="store_true", help="strict: every note accepted, in 4 languages"
    )
    parser.add_argument(
        "--as-of", metavar="YYYY-MM-DD", help="reference date of rule 9 (default: version date)"
    )
    parser.add_argument("--report", type=Path, help="write REPORT.md here")
    parser.add_argument("--sources-md", type=Path, help="write SOURCES.md here")
    parser.add_argument(
        "--refresh-powerbi-summary",
        action="store_true",
        help=f"rewrite curation/{powerbi.SUMMARY_FILE} from the full Power BI readings of "
        f"curation/{powerbi.PRIVATE_DIR}/ (local only), then validate",
    )
    args = parser.parse_args(argv)
    if args.as_of is not None and not schema.is_date(args.as_of):
        parser.error(f"--as-of {args.as_of!r} is not YYYY-MM-DD")
    try:
        ctx = build.load_context(args, release=args.release)
        if args.refresh_powerbi_summary and (
            ctx.curation_dir is None or powerbi.load(ctx.curation_dir / powerbi.PRIVATE_DIR) is None
        ):
            print(
                f"error: --refresh-powerbi-summary needs the full readings in "
                f"curation/{powerbi.PRIVATE_DIR}/ (git-ignored, kept locally only)",
                file=sys.stderr,
            )
            return 2
        outcome = build_and_check(
            ctx,
            draft=not args.release,
            release=args.release,
            ignore_acceptance=args.ignore_acceptance,
            as_of=args.as_of or ctx.date,
            refresh_powerbi=args.refresh_powerbi_summary,
        )
        if args.report:
            csvio.write_bytes(args.report, outcome.files["REPORT.md"])
        if args.sources_md:
            csvio.write_bytes(args.sources_md, render_sources_md(ctx.dataset).encode("utf-8"))
    except build.BUILD_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = outcome.findings
    for kind, items in (
        ("error", findings.errors),
        ("pending", findings.pending),
        ("warning", findings.warnings),
    ):
        for item in items:
            print(f"{kind} {item}")
    print(
        f"{'PASS' if findings.ok else 'FAIL'}: {len(findings.errors)} errors, "
        f"{len(findings.warnings)} warnings, {len(findings.pending)} pending acceptances"
    )
    return 0 if findings.ok else 1


if __name__ == "__main__":
    sys.exit(main())
