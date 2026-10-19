"""Statbel: the 565 communes of REFNIS 2025 and the 1,152 (postcode, INS) pairs.

Three files of Statbel (CC BY 4.0), downloaded by fetch.py:

- `REFNIS_2025.csv`: `|`-separated, UTF-8 with a BOM, CRLF. Every administrative unit,
  with a French and a Dutch name; the communes are the rows with a `Langue`
  (N -> VLA, F and D -> WAL, FN -> BRU, schema.LANGUE_REGION).
- `NIS6withnamefrom01012025.xlsx`: the statistical sub-divisions; its `T_MUN_DE` column
  is the only Statbel source of the German commune names.
- `Conversion Postal code_Refnis code_va01012025.xlsx`: the postcode -> INS table that
  Statbel derives from bpost's "Postkantons".

Names: `nom_fr` and `nom_nl` are REFNIS's, as written. `nom_de` is NIS6's `T_MUN_DE`,
except when NIS6 gives the French or the Dutch name as the German one (`T_MUN_DE`
equal to its own `T_MUN_FR` or `T_MUN_NL`): then it is that name as REFNIS writes it,
so a commune never has two spellings of one name (NIS6 writes typographic apostrophes
and "Blegny", REFNIS ASCII apostrophes and "Blégny"). "Brüssel" or "Bastnach" stay.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

import openpyxl

import lookup
import schema
import validate

Row = dict[str, str]

REFNIS_COLUMNS = (
    "Code INS",
    "Entités administratives",
    "Langue",
    "Code NIS",
    "Administratieve eenheden",
    "Taal",
)
NIS6_COLUMNS = (
    "CNIS5_2025",
    "T_MUN_NL",
    "T_MUN_FR",
    "T_MUN_DE",
    "C_NIS6",
    "T_NIS6_NL",
    "T_NIS6_FR",
)
POSTCODES_COLUMNS = ("Postal code", "Refnis code", "Gemeentenaam", "Nom commune")

# Facts of the 2025 mergers that the extracts must show (README, vectors.csv).
KNOWN_POSTCODES = {
    "82039": {"6600", "6686", "6687", "6688"},  # Bastogne, with Bertogne (6686-6688)
    "23106": {"1540", "1541", "1570", "1755"},  # Pajottegem (Galmaarden, Gooik, Herne)
}


class AcquisitionError(ValueError):
    """A source does not have the shape or the content the acquisition expects."""


def clean(value: object) -> str:
    """A cell as text: TRIMmed (README's TRIM, plus inner whitespace kept), NFC."""
    text = "" if value is None else str(value)
    return unicodedata.normalize("NFC", lookup.trim(text))


def parse_refnis(data: bytes) -> list[Row]:
    """The communes of REFNIS_2025.csv: `ins,nom_fr,nom_nl,langue`, sorted by INS."""
    text = data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="|"))
    if not rows or tuple(rows[0][: len(REFNIS_COLUMNS)]) != REFNIS_COLUMNS:
        raise AcquisitionError(f"REFNIS header {rows[0] if rows else []!r}")
    communes: dict[str, Row] = {}
    for number, cells in enumerate(rows[1:], start=2):
        if not any(cells):
            continue
        if len(cells) < len(REFNIS_COLUMNS) or any(cells[len(REFNIS_COLUMNS) :]):
            raise AcquisitionError(f"REFNIS line {number}: unexpected cells {cells!r}")
        ins, nom_fr, langue, nis, nom_nl, _ = (clean(cell) for cell in cells[:6])
        if not langue:
            continue  # a region, province or arrondissement
        if ins != nis or not schema.INS_RE.fullmatch(ins):
            raise AcquisitionError(f"REFNIS line {number}: INS {ins!r} / NIS {nis!r}")
        if langue not in schema.LANGUE_REGION:
            raise AcquisitionError(f"REFNIS line {number}: Langue {langue!r}")
        if not nom_fr or not nom_nl or ins in communes:
            raise AcquisitionError(f"REFNIS line {number}: missing name or duplicate INS {ins}")
        communes[ins] = {"ins": ins, "nom_fr": nom_fr, "nom_nl": nom_nl, "langue": langue}
    return [communes[ins] for ins in sorted(communes)]


def _sheet_rows(path: Path, columns: tuple[str, ...]) -> list[tuple[str, ...]]:
    """The rows of the first sheet of a workbook whose header must be `columns`."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        values = workbook.worksheets[0].iter_rows(values_only=True)
        header = tuple(clean(cell) for cell in next(values, ()))
        if header[: len(columns)] != columns or any(header[len(columns) :]):
            raise AcquisitionError(f"{path.name}: header {header!r}, expected {columns!r}")
        rows = []
        for cells in values:
            row = tuple(clean(cell) for cell in cells[: len(columns)])
            if any(row):
                rows.append(row)
        return rows
    finally:
        workbook.close()


def parse_nis6(path: Path) -> dict[str, tuple[str, str, str]]:
    """INS -> (T_MUN_NL, T_MUN_FR, T_MUN_DE), one entry per commune."""
    names: dict[str, tuple[str, str, str]] = {}
    for row in _sheet_rows(path, NIS6_COLUMNS):
        ins, commune = row[0], (row[1], row[2], row[3])
        if not schema.INS_RE.fullmatch(ins) or not all(commune):
            raise AcquisitionError(f"{path.name}: commune {row!r}")
        if names.setdefault(ins, commune) != commune:
            raise AcquisitionError(f"{path.name}: {ins} has two sets of names")
    return names


def parse_postcodes(path: Path) -> list[tuple[str, str]]:
    """The (postcode, INS) pairs of the conversion table, sorted, without duplicates."""
    pairs = set()
    for row in _sheet_rows(path, POSTCODES_COLUMNS):
        postcode, ins = row[0], row[1]
        if not schema.POSTCODE_RE.fullmatch(postcode) or not schema.INS_RE.fullmatch(ins):
            raise AcquisitionError(f"{path.name}: pair {row!r}")
        pairs.add((postcode, ins))
    return sorted(pairs)


def german_name(nom_fr: str, nom_nl: str, nis6: tuple[str, str, str]) -> str:
    """`nom_de`: NIS6's German name, or REFNIS's French or Dutch name when NIS6 says the
    German name is its French or Dutch one. `nis6` is (T_MUN_NL, T_MUN_FR, T_MUN_DE)."""
    t_mun_nl, t_mun_fr, t_mun_de = nis6
    if t_mun_de == t_mun_fr:
        return nom_fr
    if t_mun_de == t_mun_nl:
        return nom_nl
    return t_mun_de


def commune_rows(refnis: Iterable[Row], nis6: Mapping[str, tuple[str, str, str]]) -> list[Row]:
    """The rows of data/communes.csv."""
    rows = []
    for commune in refnis:
        ins = commune["ins"]
        geography = schema.ins_geography(ins)
        if geography is None or ins not in nis6:
            raise AcquisitionError(f"{ins}: unknown INS prefix or not in NIS6")
        region, province = geography
        if schema.LANGUE_REGION[commune["langue"]] != region:
            raise AcquisitionError(f"{ins}: Langue {commune['langue']} but INS region {region}")
        rows.append(
            {
                "ins": ins,
                "nom_fr": commune["nom_fr"],
                "nom_nl": commune["nom_nl"],
                "nom_de": german_name(commune["nom_fr"], commune["nom_nl"], nis6[ins]),
                "region": region,
                "province": province,
            }
        )
    return rows


def check_national(communes: list[Row], pairs: list[tuple[str, str]]) -> None:
    """The national facts of README.md and validate.py (565 communes, 1,152 pairs, ...)."""
    regions = Counter(row["region"] for row in communes)
    if dict(regions) != validate.COMMUNE_COUNTS:
        raise AcquisitionError(f"{len(communes)} communes {dict(regions)}")
    if len(pairs) != validate.POSTCODE_PAIRS:
        raise AcquisitionError(f"{len(pairs)} (postcode, INS) pairs")
    by_postcode = Counter(postcode for postcode, _ in pairs)
    multi = {postcode for postcode, count in by_postcode.items() if count > 1}
    if multi != validate.MULTI_INS_POSTCODES:
        raise AcquisitionError(f"postcodes of several INS: {sorted(multi)}")
    inses = {row["ins"] for row in communes}
    if {ins for _, ins in pairs} != inses:
        raise AcquisitionError("the INS of the postcode table differ from REFNIS")
    for ins, expected in KNOWN_POSTCODES.items():
        found = {postcode for postcode, owner in pairs if owner == ins}
        if found != expected:
            raise AcquisitionError(f"{ins}: postcodes {sorted(found)}, expected {sorted(expected)}")


def postcode_owners(pairs: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    """postcode -> the set of its INS."""
    owners: dict[str, set[str]] = {}
    for postcode, ins in pairs:
        owners.setdefault(postcode, set()).add(ins)
    return owners
