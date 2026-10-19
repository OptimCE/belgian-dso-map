"""Headers, vocabularies and patterns of the data contract, and the loader of a data directory.

Every file layout of README.md is defined here once, so build.py, validate.py,
lookup.py and the tests agree on it. The website and dso-lookup copy these
headers as constants.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import csvio

Row = dict[str, str]

# --- Editable files (data/) -------------------------------------------------------------

COMMUNES_HEADER = ("ins", "nom_fr", "nom_nl", "nom_de", "region", "province")
POSTCODES_HEADER = ("postcode", "ins")
ATTRIBUTION_COLUMNS = (
    "elec_operator",
    "elec_designated",
    "gas_status",
    "gas_operator",
    "flags",
    "note_key",
    "source_ids",
    "valid_from",
)
ASSIGNMENTS_HEADER = ("ins", *ATTRIBUTION_COLUMNS)
SECTIONS_HEADER = (
    "ins",
    "section_key",
    "nom_fr",
    "nom_nl",
    "nom_de",
    "postcodes",
    *ATTRIBUTION_COLUMNS,
)
OPERATORS_HEADER = (
    "id",
    "kind",
    "name",
    "legal_name",
    "region",
    "elec",
    "gas",
    "website",
    "regulator",
    "tariffs_url",
    "lookup",
    "replaced_by",
)
SOURCES_HEADER = (
    "id",
    "role",
    "publisher",
    "title",
    "url",
    "retrieved_at",
    "sha256",
    "license",
    "note",
)
NOTE_TEXT_COLUMNS = ("fr", "nl", "de", "en")
NOTES_HEADER = ("key", *NOTE_TEXT_COLUMNS, "accepted_by", "accepted_on")

DATA_FILES: dict[str, tuple[str, ...]] = {
    "communes.csv": COMMUNES_HEADER,
    "postcodes.csv": POSTCODES_HEADER,
    "assignments.csv": ASSIGNMENTS_HEADER,
    "sections.csv": SECTIONS_HEADER,
    "operators.csv": OPERATORS_HEADER,
    "sources.csv": SOURCES_HEADER,
    "notes.csv": NOTES_HEADER,
}

# --- Published files (a version, dist/) -------------------------------------------------

DATE_COLUMNS = ("first_seen", "changed_at", "data_version")
DSO_LOOKUP_DATA_COLUMNS = (
    "postcode",
    "ins",
    "commune_fr",
    "commune_nl",
    "commune_de",
    "region",
    "province",
    "section_key",
    "section_fr",
    "section_nl",
    "section_de",
    *ATTRIBUTION_COLUMNS,
)
DSO_LOOKUP_HEADER = (*DSO_LOOKUP_DATA_COLUMNS, *DATE_COLUMNS)
DSO_LOOKUP_KEY = ("postcode", "ins", "section_key")
DIST_OPERATORS_HEADER = (*OPERATORS_HEADER, *DATE_COLUMNS)
DIST_SOURCES_HEADER = (*SOURCES_HEADER, *DATE_COLUMNS)
DIST_NOTES_DATA_COLUMNS = ("key", *NOTE_TEXT_COLUMNS)
DIST_NOTES_HEADER = (*DIST_NOTES_DATA_COLUMNS, *DATE_COLUMNS)

# --- Shared test cases (tests/vectors.csv) ----------------------------------------------

VECTORS_HEADER = (
    "name",
    "kind",
    "postcode",
    "ins",
    "section_key",
    "post_name",
    "ean",
    "expect_status",
    "expect_key",
    "expect_elec",
    "expect_gas_status",
    "expect_gas",
    "expect_flags",
)
# Input cells keep their padding: " 5020 " and NBSP+"5020" are test cases of TRIM.
VECTOR_INPUT_COLUMNS = ("postcode", "ins", "section_key", "post_name", "ean")
VECTOR_KINDS = ("postcode", "address", "ean")
TO_CONFIRM_VECTOR_PREFIX = "tc-"

# --- Curation worksheets (curation/) ----------------------------------------------------

WORKSHEET_HEADER = ("grd", "vector", "name_in_source", "ins", "source_id", "locator")
# A name that the name rule does not map to its INS (a misprint, a merged commune, a section)
ALIASES_HEADER = ("name_in_source", "ins", "reason")
SPOT_CHECKS_HEADER = ("date", "tool", "ins", "vector", "observed", "matches")
DERIVED_COMMUNES_HEADER = ("ins", "nom_fr", "nom_nl", "langue")
DERIVED_POSTCODES_HEADER = ("postcode", "ins")
DERIVED_FLUVIUS_HEADER = ("postcode", "community", "ins", "elec_id", "gas_id", "gastype")

# --- Vocabularies -----------------------------------------------------------------------

REGIONS = ("BRU", "VLA", "WAL")
# Display order of operators (README): kind first, then region.
KIND_RANK = {"grd": 0, "gas_foreign": 1, "grtl": 2}
REGION_RANK = {"WAL": 0, "BRU": 1, "VLA": 2}
GAS_STATUSES = ("designated", "none", "foreign")
ROLES = ("R", "M", "C", "X")
FLAGS = ("transition", "operator_differs", "to_confirm", "propane_note")
BOOLEANS = ("true", "false")
VECTORS = ("elec", "gas")
LOOKUP_STATUSES = ("ok", "choose_commune", "choose_section", "not_found")
EAN_STATUSES = ("format_ok", "format_invalid")
EAN_FLAGS = ("belgian_prefix", "gs1_ok")
LANGUE_REGION = {"N": "VLA", "F": "WAL", "D": "WAL", "FN": "BRU"}

PROVINCES = (
    "BE-VAN",
    "BE-VBR",
    "BE-VLI",
    "BE-VOV",
    "BE-VWV",
    "BE-WBR",
    "BE-WHT",
    "BE-WLG",
    "BE-WLX",
    "BE-WNA",
)
# INS prefix -> (region, ISO 3166-2 province). Brussels has no province.
_INS_PREFIXES = (
    ("21", "BRU", ""),
    ("23", "VLA", "BE-VBR"),
    ("24", "VLA", "BE-VBR"),
    ("25", "WAL", "BE-WBR"),
    ("1", "VLA", "BE-VAN"),
    ("3", "VLA", "BE-VWV"),
    ("4", "VLA", "BE-VOV"),
    ("5", "WAL", "BE-WHT"),
    ("6", "WAL", "BE-WLG"),
    ("7", "VLA", "BE-VLI"),
    ("8", "WAL", "BE-WLX"),
    ("9", "WAL", "BE-WNA"),
)

# --- Patterns (ASCII only: Python's \d also matches full-width digits) ------------------

INS_RE = re.compile(r"[1-9][0-9]{4}")
POSTCODE_RE = re.compile(r"[1-9][0-9]{3}")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
VERSION_RE = re.compile(r"([0-9]{4})\.(0[1-9]|1[0-2])\.(0|[1-9][0-9]*)")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
URL_RE = re.compile(r"https?://\S+")
DATASET_NOTE_RE = re.compile(r"dataset-(bru|vla|wal)-[a-z0-9]+(?:-[a-z0-9]+)*")
DRAFT_SUFFIX = "-draft"
# Sources behind communes.csv, postcodes.csv and section names: no row cites them.
GEOGRAPHY_SOURCE_PREFIX = "geo-"


def is_date(value: str) -> bool:
    """A real calendar date written YYYY-MM-DD."""
    if not DATE_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def version_key(version: str) -> tuple[int, int, int]:
    """(year, month, n) of `YYYY.MM.N` or `YYYY.MM.N-draft`. ValueError if malformed."""
    base = version.removesuffix(DRAFT_SUFFIX)
    match = VERSION_RE.fullmatch(base)
    if not match:
        raise ValueError(f"version {version!r} is not YYYY.MM.N")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_draft(version: str) -> bool:
    return version.endswith(DRAFT_SUFFIX)


def split_list(cell: str) -> list[str]:
    """Values of a `|`-separated list cell; an empty cell is the empty list."""
    return cell.split("|") if cell else []


def join_list(values: list[str]) -> str:
    return "|".join(values)


def canonical_flags(flags: list[str]) -> list[str]:
    """Flags in the canonical order of FLAGS (unknown flags last, as given)."""
    known = [flag for flag in FLAGS if flag in flags]
    return known + [flag for flag in flags if flag not in FLAGS]


def ins_geography(ins: str) -> tuple[str, str] | None:
    """(region, province) implied by an INS code, or None for an unknown prefix."""
    for prefix, region, province in _INS_PREFIXES:
        if ins.startswith(prefix):
            return region, province
    return None


def slugify(name: str) -> str:
    """Suggested `section_key` for a name: "Marche-les-Dames" -> "marche-les-dames"."""
    decomposed = unicodedata.normalize("NFKD", name)
    unmarked = "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M"))
    return re.sub(r"[^a-z0-9]+", "-", unmarked.lower()).strip("-")


@dataclass(frozen=True)
class Dataset:
    """The seven editable files of a data directory, parsed and format-checked by csvio."""

    communes: list[Row]
    postcodes: list[Row]
    assignments: list[Row]
    sections: list[Row]
    operators: list[Row]
    sources: list[Row]
    notes: list[Row]
    hashes: dict[str, str]  # file name -> sha256 of its bytes (listed in REPORT.md)


def load_dataset(data_dir: Path) -> Dataset:
    """Read the seven files of `data_dir`. CsvError on any dialect or header problem."""
    tables: dict[str, list[Row]] = {}
    hashes: dict[str, str] = {}
    for name, header in DATA_FILES.items():
        data = (data_dir / name).read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        _, tables[name] = csvio.parse_csv(data, name=name, header=header)
    return Dataset(
        communes=tables["communes.csv"],
        postcodes=tables["postcodes.csv"],
        assignments=tables["assignments.csv"],
        sections=tables["sections.csv"],
        operators=tables["operators.csv"],
        sources=tables["sources.csv"],
        notes=tables["notes.csv"],
        hashes=hashes,
    )
