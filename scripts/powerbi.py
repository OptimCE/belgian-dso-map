"""The CWaPE Power BI « GRD par commune », read by hand: what it shows for an attribution.

The report (https://www.cwape.be/node/6468) is never queried automatically (CLAUDE.md).
It was read by hand, once per vector, through the visual's accessible table. The full
readings, `cwape_powerbi_elec.csv` and `cwape_powerbi_gas.csv` (one row per (commune
label, GRD label), with the count the report shows and the operator id of the label:
"ORES Namur" -> ores), stay in `curation/private/`, which git ignores: their licence is
not stated and a substantial extract of a database is reserved to its maker. The report
covers Wallonia only.

What the repository keeps is the summary `curation/powerbi_checks.csv`: per Walloon row
(an assignment, or a section) and vector, the value of the data that was compared, whether
the report agrees and, only when it does not, what it showed. `summarize()` writes it from
the full readings (`validate.py --refresh-powerbi-summary`); `validate.py` lists its
disagreements and, when the full readings are present, refuses a summary that does not
follow from them. Neither the summary nor the full readings is required: without both, the
Walloon rows are not cross-checked with the report.

assemble.py cites a reading on the rows it agrees with (`agrees()`: the full reading of a
vector when present, else the summary, provided it compared the same value). validate.py
checks each row of a full reading with `label_matches()` (the commune label names its INS)
and `label_to_id()` (the operator id follows the GRD label).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import csvio
import lookup

Row = Mapping[str, str]
SummaryKey = tuple[str, str, str]  # (ins, section_key, vector)

HEADER = ("commune_label", "ins", "grd_label", "grd_id", "count")
# vector -> (full reading in curation/private/, id of the reading in data/sources.csv)
READINGS = {
    "elec": ("cwape_powerbi_elec.csv", "cwape-powerbi-grd-elec-2026-10-12"),
    "gas": ("cwape_powerbi_gas.csv", "cwape-powerbi-grd-gas-2026-10-12"),
}
PRIVATE_DIR = "private"  # curation/private/: the full readings, git-ignored
SUMMARY_FILE = "powerbi_checks.csv"  # curation/powerbi_checks.csv: committed
SUMMARY_HEADER = ("ins", "section_key", "vector", "data", "agrees", "observed")
NONE = "none"  # `data` of a row without a gas DSO; `observed` when the report shows no GRD
# `observed` of a disagreement: "none", or the GRD labels shown with their counts.
OBSERVED_RE = re.compile(r"none|[^+]*[^+ ] [1-9][0-9]*(?: \+ [^+]*[^+ ] [1-9][0-9]*)*")


@dataclass(frozen=True)
class Reading:
    """The rows of each vector's full reading. A vector without a reading is absent."""

    rows: Mapping[str, Sequence[Row]]

    def labels(self, ins: str) -> set[str]:
        """The normalised commune labels of an INS, in any vector."""
        return {
            lookup.normalize_name(row["commune_label"])
            for rows in self.rows.values()
            for row in rows
            if row["ins"] == ins
        }

    def entries(
        self,
        vector: str,
        ins: str,
        section_names: Collection[str] = (),
        commune_names: Collection[str] = (),
    ) -> list[Row] | None:
        """The rows the reading shows for a commune, or for one of its sections.

        A commune (no `section_names`) gets every row of its INS. A section gets the rows
        of its own label when the reading has one (Bertogne, merged into Bastogne, keeps
        its label), otherwise those of the commune's label (`commune_names`). An empty
        list is a GRD-less entry (no gas). None when the reading does not cover the INS
        (outside Wallonia, a vector not read) or has no label for the section.
        """
        if vector not in self.rows:
            return None
        labels = self.labels(ins)
        if not labels:
            return None
        rows = [row for row in self.rows[vector] if row["ins"] == ins]
        if not section_names:
            return rows
        for names in (section_names, commune_names):
            wanted = {lookup.normalize_name(name) for name in names} - {""}
            if wanted & labels:
                return [
                    row for row in rows if lookup.normalize_name(row["commune_label"]) in wanted
                ]
        return None

    def shown(
        self,
        vector: str,
        ins: str,
        section_names: Collection[str] = (),
        commune_names: Collection[str] = (),
    ) -> set[str] | None:
        """The operator ids shown (empty: no GRD), or None when not covered (`entries`)."""
        rows = self.entries(vector, ins, section_names, commune_names)
        return None if rows is None else {row["grd_id"] for row in rows}


@dataclass(frozen=True)
class Target:
    """A row of the data compared with the report: an assignment or a section."""

    ins: str
    section_key: str  # empty for an assignment
    section_names: tuple[str, ...]  # FR, NL, DE names of a section; empty for a commune
    commune_names: tuple[str, ...]  # FR, NL, DE names of the commune
    elec_designated: str
    gas_operator: str

    @property
    def label(self) -> str:
        return f"{self.ins}/{self.section_key}" if self.section_key else self.ins


def target(commune: Row, row: Row) -> Target:
    """The target of a row of assignments.csv or sections.csv (it has a `section_key`)."""
    section_key = row.get("section_key", "")
    return Target(
        ins=row["ins"],
        section_key=section_key,
        section_names=(row["nom_fr"], row["nom_nl"], row["nom_de"]) if section_key else (),
        commune_names=(commune["nom_fr"], commune["nom_nl"], commune["nom_de"]),
        elec_designated=row["elec_designated"],
        gas_operator=row["gas_operator"],
    )


def label_to_id(grd_label: str) -> str:
    """The operator id of a GRD label of the report.

    Every ORES sub-region ("ORES Namur", "ORES Brabant wallon") is `ores`; any other label
    is the operator id in upper case ("AIESH" -> aiesh, "REW" -> rew).
    """
    return "ores" if grd_label.startswith("ORES ") else grd_label.lower()


def label_matches(
    label: str, ins: str, names: Collection[str], aliases: Collection[tuple[str, str]]
) -> bool:
    """Whether a commune label of the report denotes `ins`.

    True when the label, under the name rule of README.md, equals one of the INS's
    `names` (FR, NL, DE), or when (label, INS) is an alias of curation/aliases.csv
    (`name_in_source`, `ins`), compared under the same rule (BERTOGNE -> 82039, merged
    into Bastogne). An alias of another INS does not count.
    """
    key = lookup.normalize_name(label)
    if not key:
        return False
    if key in {lookup.normalize_name(name) for name in names}:
        return True
    return any(
        alias_ins == ins and lookup.normalize_name(name) == key for name, alias_ins in aliases
    )


def expected(vector: str, *, elec_designated: str, gas_operator: str) -> set[str]:
    """What the report should show for an attribution.

    Like ODWB, the report is keyed by the designated DSO (Namur and Gesves showed their
    designated DSO while the other one operated part of the network), so electricity is
    compared with `elec_designated`. A commune without a gas DSO shows no gas GRD.
    """
    if vector == "elec":
        return {elec_designated}
    return {gas_operator} if gas_operator else set()


def data_value(vector: str, item: Target) -> str:
    """The value of the data compared with the report: the designated electricity DSO,
    the gas DSO, or `none` without one (the `data` column of the summary)."""
    return item.elec_designated if vector == "elec" else item.gas_operator or NONE


def compare(reading: Reading, vector: str, item: Target) -> dict[str, str] | None:
    """The summary row of a target and vector, or None when the reading does not cover it.

    `observed` is empty when the report agrees; otherwise it is what the report showed:
    its GRD labels with their counts ("AIESH 30 + ORES Namur 10"), or `none`.
    """
    entries = reading.entries(vector, item.ins, item.section_names, item.commune_names)
    if entries is None:
        return None
    shown = {entry["grd_id"] for entry in entries}
    agrees = shown == expected(
        vector, elec_designated=item.elec_designated, gas_operator=item.gas_operator
    )
    observed = " + ".join(f"{entry['grd_label']} {entry['count']}" for entry in entries)
    return {
        "ins": item.ins,
        "section_key": item.section_key,
        "vector": vector,
        "data": data_value(vector, item),
        "agrees": "true" if agrees else "false",
        "observed": "" if agrees else observed or NONE,
    }


def summary_key(row: Row) -> SummaryKey:
    return (row["ins"], row["section_key"], row["vector"])


def summarize(
    reading: Reading, targets: Iterable[Target], keep: Iterable[Row] = ()
) -> list[dict[str, str]]:
    """The summary of the vectors read, sorted by (ins, section_key, vector).

    The rows of `keep` (the committed summary) are kept for the vectors that `reading`
    lacks, so refreshing one vector never drops the other.
    """
    rows = [dict(row) for row in keep if row["vector"] not in reading.rows]
    for item in targets:
        for vector in READINGS:
            if vector in reading.rows:
                row = compare(reading, vector, item)
                if row is not None:
                    rows.append(row)
    return sorted(rows, key=summary_key)


def agrees(
    reading: Reading | None, summary: Mapping[SummaryKey, Row], vector: str, item: Target
) -> bool:
    """Whether the report shows exactly the target's DSO (or no gas DSO without one).

    The full reading of the vector decides when it is present; otherwise the committed
    summary does, provided it compared the same value (a row changed since the summary
    was written is not counted as agreeing).
    """
    if reading is not None and vector in reading.rows:
        row: Row | None = compare(reading, vector, item)
    else:
        row = summary.get((item.ins, item.section_key, vector))
    return row is not None and row["agrees"] == "true" and row["data"] == data_value(vector, item)


def load(private: Path) -> Reading | None:
    """The full readings present in `private`, or None without any. CsvError if malformed."""
    rows = {
        vector: csvio.read_csv(private / name, HEADER)
        for vector, (name, _) in READINGS.items()
        if (private / name).is_file()
    }
    return Reading(rows) if rows else None


def load_summary(path: Path) -> list[dict[str, str]] | None:
    """The committed summary, or None when the file is absent. CsvError if malformed."""
    return csvio.read_csv(path, SUMMARY_HEADER) if path.is_file() else None
