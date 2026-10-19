"""Fluvius open data 1_23: the electricity and gas DSO of each Flemish sub-municipality.

The CSV export of `1_23-dnb-per-gemeente-en-per-sector` (`;`-separated, UTF-8 with a
BOM, CRLF) has one row per (postcode, `community`), where `community` is a
sub-municipality ("Tollembeek", "Kallo (Kieldrecht)"), not an INS commune. The extract
`curation/derived/fluvius_1_23.csv` keeps every row, adds the INS joined on the
postcode (Statbel pairs; a postcode of several INS is settled by the community name),
and maps the operator names to the ids of `data/operators.csv`.

`gastype` is the export's `gastype` column, as written (H, L, L(H), H(L), H-L). The
export also has `gastype_fluvius` ("H" or "Niet Fluvius"), which is not kept.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Collection, Mapping

import lookup
import schema
from statbel import AcquisitionError, clean

Row = dict[str, str]

COLUMNS = ("code", "community", "dnbelectricity", "dnbgas", "gastype", "gastype_fluvius")
FOREIGN_NAMES = {"Enexis Netbeheer": "enexis"}


def parse(data: bytes) -> list[Row]:
    """The rows of the CSV export, every cell TRIMmed."""
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    header = tuple(clean(cell) for cell in next(reader, []))
    if header != COLUMNS:
        raise AcquisitionError(f"Fluvius header {header!r}, expected {COLUMNS!r}")
    rows = []
    for number, cells in enumerate(reader, start=2):
        if not any(cells):
            continue
        if len(cells) != len(COLUMNS):
            raise AcquisitionError(f"Fluvius line {number}: {cells!r}")
        rows.append(dict(zip(COLUMNS, (clean(cell) for cell in cells), strict=True)))
    return rows


def operator_id(name: str, operators: Collection[str]) -> str:
    """The operator id of a Fluvius name: "Fluvius Imewo" -> fluvius-imewo, "" -> ""."""
    if not name:
        return ""
    operator = FOREIGN_NAMES.get(name) or schema.slugify(name)
    if operator not in operators:
        raise AcquisitionError(f"Fluvius operator {name!r}: no operator {operator!r}")
    return operator


def join_ins(
    postcode: str,
    community: str,
    owners: Mapping[str, set[str]],
    names: Mapping[str, Collection[str]],
) -> str:
    """The INS of a Fluvius row: its postcode's, or the one whose name is the community's."""
    inses = owners.get(postcode, set())
    if len(inses) == 1:
        return next(iter(inses))
    wanted = lookup.normalize_name(community)
    matches = [ins for ins in sorted(inses) if wanted in names.get(ins, ())]
    if len(matches) != 1:
        raise AcquisitionError(
            f"Fluvius {postcode} {community}: postcode of {sorted(inses) or 'no'} INS"
        )
    return matches[0]


def derive(
    rows: list[Row],
    *,
    owners: Mapping[str, set[str]],
    communes: Mapping[str, Row],
    operators: Collection[str],
) -> list[Row]:
    """The rows of fluvius_1_23.csv, sorted, without exact duplicates."""
    names = {
        ins: {lookup.normalize_name(row[column]) for column in ("nom_fr", "nom_nl", "nom_de")}
        for ins, row in communes.items()
    }
    derived = set()
    for row in rows:
        postcode = row["code"]
        if not schema.POSTCODE_RE.fullmatch(postcode):
            raise AcquisitionError(f"Fluvius postcode {postcode!r}")
        ins = join_ins(postcode, row["community"], owners, names)
        if communes[ins]["region"] != "VLA":
            raise AcquisitionError(f"Fluvius {postcode} {row['community']}: {ins} is not Flemish")
        derived.add(
            (
                postcode,
                row["community"],
                ins,
                operator_id(row["dnbelectricity"], operators),
                operator_id(row["dnbgas"], operators),
                row["gastype"],
            )
        )
    return [dict(zip(schema.DERIVED_FLUVIUS_HEADER, item, strict=True)) for item in sorted(derived)]
