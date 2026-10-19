"""REPORT.md: the review report of a build, deterministic and dated by the version.

Eric reads it in every data PR. It holds the validation result, the inputs'
sha256, the counts, every flagged row with its FR note and acceptance state,
the sources with their ages, the cross-check disagreements and the open
questions. Nothing in it depends on the clock: ages are counted from the as-of
date, which is the version date unless validate.py is given --as-of.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import schema

Row = Mapping[str, str]

# The spec's count of communes per Flemish DSO (it cites no source for this list).
VREG_COUNTS = {
    "fluvius-antwerpen": 28,
    "fluvius-halle-vilvoorde": 29,
    "fluvius-imewo": 38,
    "fluvius-kempen": 27,
    "fluvius-limburg": 39,
    "fluvius-midden-vlaanderen": 21,
    "fluvius-west": 59,
    "fluvius-zenne-dijle": 44,
}
# AGW of 9 June 2022 (and CWaPE opinion 0899): ORES designated for electricity in 190
# communes, named before the 2025 mergers. The other designation orders and the mergers
# each move the expected count (curation/wal_designations.csv transcribes them all).
# Couvin and Brunehaut were never in the 190: their ORES designations were the
# prolongations of the AIESH and AIEG orders, which ended in 2024 and 2026.
ORES_2022_COUNT = 190
ORES_ADJUSTMENTS = (
    (
        "Bastogne absorbed Bertogne on 02/12/2024 (Walloon decree of 19/05/2023, art. 2; "
        "both in the 190)",
        -1,
    ),
    ("Profondeville: AGW of 15/07/2022", 1),
    ("Hamoir and Jemeppe-sur-Sambre: AGW of 01/07/2022", 2),
    ("Philippeville: AGWs of 01/07/2022 and 12/10/2023", 1),
    ("Brugelette: AGW of 08/12/2022", 1),
)

OPEN_QUESTIONS = (
    (
        "Q2",
        "Namur and Gesves: the ORES ↔ AIEG network exchange was decided to take effect on "
        "01/07/2026; ORES operates Namur and the AIEG operates Gesves today; no public "
        "confirmation that the exchange is complete (to_confirm). The sources disagree on "
        "who operated these networks before the exchange; the notes stay neutral.",
    ),
    (
        "Q3",
        "Saint-Vith gas: answered. The AGW of 25/06/2026 (MB 07/07/2026) designates RESA "
        "from 01/06/2026 to 01/06/2046; the row keeps `transition`. For Eric's information.",
    ),
    (
        "Q4",
        "Flanders: the electricity designations ran until 05/09/2026 (Voeren until "
        "01/01/2028, BESL-2016-31); Fluvius applied for their renewal; no regulator "
        "decision published as of 12/10/2026 (dataset note, or to_confirm everywhere).",
    ),
    ("G5", "Brunehaut gas: no designation found after IGH ended on 01/01/2023 (to_confirm)."),
    (
        "G20",
        "Walcourt gas: ORES + to_confirm. ORES distributes gas at Tarcienne (CWaPE Power BI: "
        "ORES Namur 2; ORES open data: 7 to 8 access points a year, 2020-2024), but no "
        "designation order was found.",
    ),
    (
        "G21",
        "Bastogne gas: two sections since the merger of 02/12/2024 (Walloon decree of "
        "19/05/2023, art. 2). Bastogne (6600): ORES; "
        "Bertogne (6686-6688): no gas DSO, since the ORES gas order of 09/06/2022 names "
        "Bastogne only and ORES open data count no gas access point at 6686-6688.",
    ),
    (
        "G22",
        "Marchin gas: RESA + to_confirm. The CWaPE Power BI shows RESA (1), but no designation "
        "order was found: Marchin is in none of RESA's gas orders.",
    ),
    (
        "Q5",
        "Licence of the compiled data: answered. CC BY 4.0 by OptimCE (`LICENSE`); the "
        "sources keep their own licences and credits (`ATTRIBUTION.md`), the Statbel postcode "
        "file (derived by Statbel from bpost data) included. For Eric's information.",
    ),
    (
        "Q6",
        "CWaPE Power BI « GRD par commune »: read by hand on 12/10/2026 (no export). It lags "
        "for Couvin (ORES Namur 10 beside AIESH 30; AIESH since 01/01/2024) and Brunehaut "
        "(ORES Hainaut 19; AIEG since 01/01/2026; electricity data 2026-T1): explained "
        "warnings. Habay, Ramillies, Villers-la-Ville (ORES) and Comblain-au-Pont (RESA) have "
        "a gas designation but no gas GRD on the map: kept designated. The full reading stays "
        "out of the public repository (licence not stated); `curation/powerbi_checks.csv` "
        "keeps the comparison of each Walloon row.",
    ),
    ("Q7", "The Sibelga EAN prefix 5414489 also starts the Liège demo EANs (RESA)."),
)


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}"


@dataclass
class Findings:
    """Errors fail validation; warnings and pending acceptances do not."""

    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    pending: list[Finding] = field(default_factory=list)
    crosscheck: list[Finding] = field(default_factory=list)

    def error(self, rule: str, message: str) -> None:
        self.errors.append(Finding(rule, message))

    def warn(self, rule: str, message: str) -> None:
        self.warnings.append(Finding(rule, message))

    def pend(self, rule: str, message: str) -> None:
        self.pending.append(Finding(rule, message))

    def disagree(self, rule: str, message: str) -> None:
        """A cross-check disagreement: a warning, also listed in its own report section."""
        self.crosscheck.append(Finding(rule, message))
        self.warn(rule, message)

    @property
    def ok(self) -> bool:
        return not self.errors


def md(value: object) -> str:
    """A Markdown table cell: pipes escaped, an empty value shown as "-"."""
    text = str(value)
    return text.replace("|", "\\|") if text else "-"


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(md(cell) for cell in row) + " |" for row in rows]
    return lines


def _findings(title: str, items: Sequence[Finding]) -> list[str]:
    if not items:
        return []
    return [f"## {title}", "", *(f"- {item}" for item in items), ""]


def _age_days(earlier: str, later: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def _national_counts(communes: Mapping[str, Row], designated: Mapping[str, set[str]]) -> list[str]:
    """Rule 10 tables: Flemish DSOs against the spec's list, ORES against the 2022 opinion."""

    def in_region(operator: str, region: str) -> int:
        inses = designated.get(operator, set())
        return len({ins for ins in inses if communes.get(ins, {}).get("region") == region})

    out = ["Flanders against the spec's VREG list (unsourced in the spec):", ""]
    out += _table(
        ("DSO", "expected", "found"),
        [
            (operator, expected, in_region(operator, "VLA"))
            for operator, expected in VREG_COUNTS.items()
        ],
    )
    expected_ores = ORES_2022_COUNT + sum(delta for _, delta in ORES_ADJUSTMENTS)
    out += [
        "",
        f"ORES designated in {in_region('ores', 'WAL')} Walloon communes; the 2022 opinion "
        f"lists {ORES_2022_COUNT}, {expected_ores} after the known changes:",
        "",
        *(f"- {label}" for label, _ in ORES_ADJUSTMENTS),
        "",
    ]
    return out


def render_report(
    *,
    data_version: str,
    version_date: str,
    as_of: str,
    mode: str,
    dataset: schema.Dataset,
    lookup_rows: Sequence[Row],
    findings: Findings,
    vectors_total: int,
    national: bool,
) -> str:
    """The report. `national` adds the rule 10 comparisons (not for a small fixture)."""
    communes = {row["ins"]: row for row in dataset.communes}
    notes = {row["key"]: row for row in dataset.notes}
    attributions = [*dataset.assignments, *dataset.sections]
    status = "PASS" if findings.ok else "FAIL"
    out = [
        f"# Data report — {data_version}",
        "",
        f"Version date: {version_date} · as of: {as_of} · mode: {mode}",
        "",
        "## Status",
        "",
        f"**{status}** — {len(findings.errors)} errors, {len(findings.warnings)} warnings, "
        f"{len(findings.pending)} pending acceptances, {vectors_total} vectors.",
        "",
    ]
    out += _findings("Errors", findings.errors)
    out += _findings("Pending acceptances", findings.pending)
    out += _findings("Warnings", findings.warnings)

    out += ["## Inputs", ""]
    out += _table(("file", "sha256"), sorted(dataset.hashes.items()))
    out += [""]

    rows_by_region = Counter(row["region"] for row in lookup_rows)
    communes_by_region = Counter(row["region"] for row in dataset.communes)
    sections_by_region = Counter(
        communes[row["ins"]]["region"] for row in dataset.sections if row["ins"] in communes
    )
    pairs = Counter(row["postcode"] for row in dataset.postcodes)
    out += ["## Counts", ""]
    out += _table(
        ("region", "communes", "sections", "published rows"),
        [
            (region, communes_by_region[region], sections_by_region[region], rows_by_region[region])
            for region in schema.REGIONS
        ],
    )
    multi = sorted(postcode for postcode, count in pairs.items() if count > 1)
    out += [
        "",
        f"Postcodes: {len(pairs)} distinct, {len(dataset.postcodes)} (postcode, INS) pairs; "
        f"shared by several communes: {', '.join(multi) or 'none'}.",
        "",
    ]

    out += ["## Electricity", ""]
    operated: dict[str, set[str]] = {}
    designated: dict[str, set[str]] = {}
    for row in attributions:
        operated.setdefault(row["elec_operator"], set()).add(row["ins"])
        designated.setdefault(row["elec_designated"], set()).add(row["ins"])
    out += _table(
        ("operator", "communes operated", "communes designated"),
        [
            (operator, len(operated.get(operator, ())), len(designated.get(operator, ())))
            for operator in sorted(set(operated) | set(designated))
        ],
    )
    out += [""]
    if national:
        out += _national_counts(communes, designated)

    out += ["## Gas", ""]
    gas = Counter((row["gas_status"], row["gas_operator"]) for row in attributions)
    out += _table(("status", "operator", "attributions"), [(*key, gas[key]) for key in sorted(gas)])
    out += [""]

    out += ["## Flagged attributions", ""]
    flagged = sorted(
        (row for row in attributions if row["flags"]),
        key=lambda row: (row["ins"], row.get("section_key", "")),
    )
    out += _table(
        ("INS", "commune", "section", "flags", "note", "FR note", "accepted"),
        [
            (
                row["ins"],
                communes.get(row["ins"], {}).get("nom_fr", "?"),
                row.get("section_key", ""),
                row["flags"],
                row["note_key"],
                notes.get(row["note_key"], {}).get("fr", ""),
                _acceptance(notes.get(row["note_key"])) if row["note_key"] else "",
            )
            for row in flagged
        ],
    )
    dataset_notes = sorted(key for key in notes if schema.DATASET_NOTE_RE.fullmatch(key))
    out += ["", "Dataset-level notes:", ""]
    out += _table(
        ("key", "FR note", "accepted"),
        [(key, notes[key]["fr"], _acceptance(notes[key])) for key in dataset_notes],
    )
    out += [""]

    out += ["## Transitions and operator_differs", ""]
    out += _table(
        ("INS", "section", "operator", "designated", "valid_from", "flags"),
        [
            (
                row["ins"],
                row.get("section_key", ""),
                row["elec_operator"],
                row["elec_designated"],
                row["valid_from"],
                row["flags"],
            )
            for row in flagged
            if {"transition", "operator_differs"} & set(schema.split_list(row["flags"]))
        ],
    )
    out += [""]

    usage = Counter(
        source for row in attributions for source in schema.split_list(row["source_ids"])
    )
    out += ["## Sources", ""]
    out += _table(
        ("id", "role", "publisher", "attributions", "retrieved_at", "age (days)"),
        [
            (
                row["id"],
                row["role"],
                row["publisher"],
                usage[row["id"]],
                row["retrieved_at"],
                _age_days(row["retrieved_at"], as_of)
                if schema.is_date(row["retrieved_at"])
                else "?",
            )
            for row in sorted(dataset.sources, key=lambda row: row["id"])
        ],
    )
    out += [""]

    out += ["## Cross-check disagreements", ""]
    out += [f"- {finding}" for finding in findings.crosscheck] or ["None."]
    out += ["", "## Open questions", ""]
    out += [f"- **{key}** {text}" for key, text in OPEN_QUESTIONS]
    return "\n".join(out) + "\n"


def _acceptance(note: Row | None) -> str:
    """Acceptance state. The reviewer's name is never printed: REPORT.md is published."""
    if note is None:
        return "missing note"
    if note["accepted_by"] and note["accepted_on"]:
        return f"accepted {note['accepted_on']}"
    return "pending"
