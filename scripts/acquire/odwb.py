"""ORES on the Open Data Wallonie-Bruxelles portal: the localities ORES serves.

Two CSV exports (`;`-separated, UTF-8 with a BOM, CRLF), one row per (year, postcode,
locality, client type[, voltage]) with a count of access points:

- electricity: `ores-electricite-_nb-points-prelevement-par-localite-et-type-client-tension-annu`
- gas: `ores-gaz-nombre-de-points-de-prelevement-par-localite-annuel`

The extracts `curation/derived/ores_odwb_elec.csv` and `ores_odwb_gas.csv` keep the
latest year only, as distinct `year,postcode,localite,commune,secteur` rows (the counts
and client types are dropped), plus the INS of the postcode (Statbel pairs; a postcode
of several INS is settled by the commune name). Rows whose postcode is `EXC` (ORES's
aggregate of exceptional connections, without a locality) are left out.

ODWB is keyed by the *designated* DSO: it cross-checks `elec_designated` and the gas
operator, never the operator of a network that another DSO runs (Namur and Gesves).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping

import lookup
import schema
from statbel import AcquisitionError, clean

Row = dict[str, str]

HEADER = ("year", "postcode", "localite", "commune", "secteur", "ins")
ELEC_COLUMNS = (
    "fluide",
    "annee",
    "secteur_geographique",
    "code_postal",
    "localite",
    "type_de_client_consommateur",
    "tension",
    "nombre_de_points_d_acces_actifs",
    "nom_commune",
    "centroid",
    "arrondissement",
    "province",
)
GAS_COLUMNS = (
    "fluide",
    "annee",
    "secteur_geographique",
    "code_postal",
    "localite",
    "type_de_client_consommateur",
    "nombre_total_de_points_d_acces",
    "nom_commune",
    "centroid",
    "arrondissement",
    "province",
)
FLUIDS = {"elec": ("ELECTRICITE", ELEC_COLUMNS), "gas": ("GAZ", GAS_COLUMNS)}
EXCEPTIONS = "EXC"


def parse(data: bytes, vector: str) -> list[Row]:
    """The rows of an export (`vector` is elec or gas), every cell TRIMmed."""
    fluid, columns = FLUIDS[vector]
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    header = tuple(clean(cell) for cell in next(reader, []))
    if header != columns:
        raise AcquisitionError(f"ODWB {vector} header {header!r}, expected {columns!r}")
    rows = []
    for number, cells in enumerate(reader, start=2):
        if not any(cells):
            continue
        if len(cells) != len(columns):
            raise AcquisitionError(f"ODWB {vector} line {number}: {cells!r}")
        row = dict(zip(columns, (clean(cell) for cell in cells), strict=True))
        if row["fluide"] != fluid:
            raise AcquisitionError(f"ODWB {vector} line {number}: fluide {row['fluide']!r}")
        year = row["annee"][:4]
        if not (year.isascii() and year.isdigit()):
            raise AcquisitionError(f"ODWB {vector} line {number}: annee {row['annee']!r}")
        row["annee"] = year
        rows.append(row)
    return rows


def join_ins(
    postcode: str, commune: str, owners: Mapping[str, set[str]], communes: Mapping[str, Row]
) -> str:
    """The INS of a locality: its postcode's, or the one named like the ODWB commune."""
    inses = owners.get(postcode, set())
    if len(inses) == 1:
        return next(iter(inses))
    wanted = lookup.normalize_name(commune)
    matches = [
        ins
        for ins in sorted(inses)
        if wanted
        in {lookup.normalize_name(communes[ins][column]) for column in ("nom_fr", "nom_nl")}
    ]
    if len(matches) != 1:
        raise AcquisitionError(f"ODWB {postcode} {commune}: postcode of {sorted(inses)} INS")
    return matches[0]


def derive(
    rows: list[Row], *, owners: Mapping[str, set[str]], communes: Mapping[str, Row]
) -> tuple[str, list[Row], int]:
    """(latest year, extract rows sorted without duplicates, number of EXC rows dropped)."""
    if not rows:
        raise AcquisitionError("ODWB export without rows")
    latest = max(row["annee"] for row in rows)
    distinct = set()
    dropped = 0
    for row in rows:
        if row["annee"] != latest:
            continue
        postcode = row["code_postal"]
        if postcode == EXCEPTIONS:
            dropped += 1
            continue
        if not schema.POSTCODE_RE.fullmatch(postcode):
            raise AcquisitionError(f"ODWB postcode {postcode!r}")
        ins = join_ins(postcode, row["nom_commune"], owners, communes)
        if communes[ins]["region"] != "WAL":
            raise AcquisitionError(f"ODWB {postcode} {row['localite']}: {ins} is not Walloon")
        distinct.add(
            (
                latest,
                postcode,
                row["localite"],
                row["nom_commune"],
                row["secteur_geographique"],
                ins,
            )
        )
    return latest, [dict(zip(HEADER, item, strict=True)) for item in sorted(distinct)], dropped
