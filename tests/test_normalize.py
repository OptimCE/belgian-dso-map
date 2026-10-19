"""TRIM, postcode and name normalisation: the same definitions in all three repositories."""

from __future__ import annotations

import pytest

import lookup
import schema

NBSP = chr(0xA0)
BOM = chr(0xFEFF)
EM_SPACE = chr(0x2003)
RIGHT_QUOTE = chr(0x2019)
FULLWIDTH_5020 = "".join(chr(0xFF10 + int(digit)) for digit in "5020")
LIGATURE_FI = chr(0xFB01)


def test_trim_removes_exactly_the_contract_characters() -> None:
    assert lookup.TRIM_CHARS == " \t\r\n" + NBSP + BOM
    assert lookup.trim(" \t\r\n" + NBSP + BOM + "x" + BOM + NBSP + " ") == "x"
    assert lookup.trim(EM_SPACE + "x") == EM_SPACE + "x"
    assert lookup.trim(None) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5020", "5020"),
        (" 5020 ", "5020"),
        ("\t5020\n", "5020"),
        (NBSP + "5020", "5020"),
        (BOM + "5020", "5020"),
        ("0999", "0999"),
        (EM_SPACE + "5020", None),
        (FULLWIDTH_5020, None),
        ("502", None),
        ("50200", None),
        ("5O20", None),
        ("50 20", None),
        ("5020\n\n", "5020"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_postcode(raw: str | None, expected: str | None) -> None:
    assert lookup.normalize_postcode(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Marche lès Dames", "marchelesdames"),
        ("MARCHE-LES-DAMES", "marchelesdames"),
        ("Mont-de-l'Enclus", "montdelenclus"),
        ("Mont-de-l" + RIGHT_QUOTE + "Enclus", "montdelenclus"),
        ("  Saint-Marc ", "saintmarc"),
        ("Namür", "namur"),
        ("Gelbressée", "gelbressee"),
        ("Baarle-Hertog", "baarlehertog"),
        (LIGATURE_FI + "ne", "fine"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_name(raw: str | None, expected: str) -> None:
    assert lookup.normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Marche-les-Dames", "marche-les-dames"),
        ("Gelbressée", "gelbressee"),
        ("Namur (centre)", "namur-centre"),
        ("Baarle-Hertog", "baarle-hertog"),
    ],
)
def test_slugify_suggests_section_keys(name: str, slug: str) -> None:
    assert schema.slugify(name) == slug
    assert schema.SLUG_RE.fullmatch(slug)


@pytest.mark.parametrize(
    ("ins", "geography"),
    [
        ("11002", ("VLA", "BE-VAN")),
        ("21004", ("BRU", "")),
        ("23106", ("VLA", "BE-VBR")),
        ("24062", ("VLA", "BE-VBR")),
        ("25112", ("WAL", "BE-WBR")),
        ("31005", ("VLA", "BE-VWV")),
        ("46030", ("VLA", "BE-VOV")),
        ("57093", ("WAL", "BE-WHT")),
        ("62063", ("WAL", "BE-WLG")),
        ("73109", ("VLA", "BE-VLI")),
        ("82039", ("WAL", "BE-WLX")),
        ("92094", ("WAL", "BE-WNA")),
    ],
)
def test_region_and_iso_province_follow_the_ins_prefix(
    ins: str, geography: tuple[str, str]
) -> None:
    assert schema.ins_geography(ins) == geography


def test_version_keys_and_draft_suffix() -> None:
    assert schema.version_key("2026.10.0") == (2026, 10, 0)
    assert schema.version_key("2026.10.12-draft") == (2026, 10, 12)
    assert schema.is_draft("2026.10.0-draft")
    for bad in ("2026.13.0", "2026.1.0", "2026.10.01", "26.10.0", "2026.10"):
        with pytest.raises(ValueError, match="YYYY.MM.N"):
            schema.version_key(bad)
