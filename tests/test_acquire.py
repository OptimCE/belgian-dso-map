"""scripts/acquire/: parsers of the M sources, the cache and sources.csv, and the extracts."""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest

import csvio
import fetch
import fluvius
import odwb
import schema
import statbel
from helpers import ROOT

DERIVED = ROOT / "curation" / "derived"

REFNIS_SAMPLE = (
    "﻿Code INS|Entités administratives|Langue|Code NIS|Administratieve eenheden|Taal|||\r\n"
    "01000|ROYAUME||01000|HET RIJK||||\r\n"
    "21004|Bruxelles|FN|21004|Brussel|NF|||\r\n"
    "13002|Baerle-Duc|N|13002|Baarle-Hertog|N|||\r\n"
    "63023|Eupen|D|63023|Eupen|D|||\r\n"
    "92000|Arrondissement de Namur||92000|Arrondissement Namen||||\r\n"
).encode()


def workbook(path: Path, rows: list[tuple[object, ...]]) -> Path:
    book = openpyxl.Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(list(row))
    book.save(path)
    return path


# --- Statbel --------------------------------------------------------------------------------


def test_refnis_keeps_the_communes_with_a_langue() -> None:
    assert statbel.parse_refnis(REFNIS_SAMPLE) == [
        {"ins": "13002", "nom_fr": "Baerle-Duc", "nom_nl": "Baarle-Hertog", "langue": "N"},
        {"ins": "21004", "nom_fr": "Bruxelles", "nom_nl": "Brussel", "langue": "FN"},
        {"ins": "63023", "nom_fr": "Eupen", "nom_nl": "Eupen", "langue": "D"},
    ]


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Code INS|", "INS|"),  # header
        ("|N|13002|", "|X|13002|"),  # unknown Langue
        ("|D|63023|", "|D|63024|"),  # INS != NIS
        ("|D|||\r\n", "|D||x|\r\n"),  # unexpected trailing cell
    ],
)
def test_refnis_refuses_an_unexpected_shape(old: str, new: str) -> None:
    data = REFNIS_SAMPLE.decode().replace(old, new, 1).encode()
    with pytest.raises(statbel.AcquisitionError):
        statbel.parse_refnis(data)


@pytest.mark.parametrize(
    ("nom_fr", "nom_nl", "nis6", "expected"),
    [
        ("Bruxelles", "Brussel", ("Brussel", "Bruxelles", "Brüssel"), "Brüssel"),
        ("Anvers", "Antwerpen", ("Antwerpen", "Anvers", "Antwerpen"), "Antwerpen"),
        ("Eupen", "Eupen", ("Eupen", "Eupen", "Eupen"), "Eupen"),
        # NIS6 writes the French name differently: REFNIS's spelling wins.
        (
            "Braine-l'Alleud",
            "Eigenbrakel",
            ("Eigenbrakel", "Braine-l\u2019Alleud", "Braine-l\u2019Alleud"),
            "Braine-l'Alleud",
        ),
        ("Blégny", "Blégny", ("Blegny", "Blegny", "Blegny"), "Blégny"),
        ("Zwalm", "Zwalm", ("Zwalm", "Zwalin", "Zwalm"), "Zwalm"),
    ],
)
def test_german_name(nom_fr: str, nom_nl: str, nis6: tuple[str, str, str], expected: str) -> None:
    assert statbel.german_name(nom_fr, nom_nl, nis6) == expected


def test_commune_rows_take_region_and_province_from_the_ins() -> None:
    refnis = statbel.parse_refnis(REFNIS_SAMPLE)
    nis6 = {
        "13002": ("Baarle-Hertog", "Baerle-Duc", "Baarle-Hertog"),
        "21004": ("Brussel", "Bruxelles", "Brüssel"),
        "63023": ("Eupen", "Eupen", "Eupen"),
    }
    assert statbel.commune_rows(refnis, nis6) == [
        {
            "ins": "13002",
            "nom_fr": "Baerle-Duc",
            "nom_nl": "Baarle-Hertog",
            "nom_de": "Baarle-Hertog",
            "region": "VLA",
            "province": "BE-VAN",
        },
        {
            "ins": "21004",
            "nom_fr": "Bruxelles",
            "nom_nl": "Brussel",
            "nom_de": "Brüssel",
            "region": "BRU",
            "province": "",
        },
        {
            "ins": "63023",
            "nom_fr": "Eupen",
            "nom_nl": "Eupen",
            "nom_de": "Eupen",
            "region": "WAL",
            "province": "BE-WLG",
        },
    ]
    refnis[0]["langue"] = "F"  # a Walloon Langue on a Flemish INS
    with pytest.raises(statbel.AcquisitionError, match="13002"):
        statbel.commune_rows(refnis, nis6)


def test_nis6_names_per_commune(tmp_path: Path) -> None:
    rows: list[tuple[object, ...]] = [
        statbel.NIS6_COLUMNS,
        ("21004", "Brussel", "Bruxelles", "Brüssel", "21004A", "PENTAGOON", "PENTAGONE"),
        ("21004", "Brussel", "Bruxelles", "Brüssel", "21004B", "WETSTRAAT", "RUE DE LA LOI"),
    ]
    path = workbook(tmp_path / "nis6.xlsx", rows)
    assert statbel.parse_nis6(path) == {"21004": ("Brussel", "Bruxelles", "Brüssel")}
    rows.append(("21004", "Brussel", "Bruxelles", "Brussel", "21004C", "LOUISA", "LOUISE"))
    with pytest.raises(statbel.AcquisitionError, match="two sets of names"):
        statbel.parse_nis6(workbook(tmp_path / "nis6b.xlsx", rows))


def test_postcode_pairs_are_sorted_and_unique(tmp_path: Path) -> None:
    path = workbook(
        tmp_path / "postcodes.xlsx",
        [
            statbel.POSTCODES_COLUMNS,
            ("1050", "21009", "Elsene", "Ixelles"),
            ("1000", "21004", "Brussel", "Bruxelles"),
            ("1050", "21004", "Brussel", "Bruxelles"),
            ("1000", "21004", "Brussel", "Bruxelles"),
            (None, None, None, None),
        ],
    )
    assert statbel.parse_postcodes(path) == [
        ("1000", "21004"),
        ("1050", "21004"),
        ("1050", "21009"),
    ]
    bad = workbook(tmp_path / "bad.xlsx", [statbel.POSTCODES_COLUMNS, ("105", "21009", "x", "y")])
    with pytest.raises(statbel.AcquisitionError):
        statbel.parse_postcodes(bad)
    wrong_header = workbook(tmp_path / "header.xlsx", [("Postcode", "INS", "NL", "FR")])
    with pytest.raises(statbel.AcquisitionError, match="header"):
        statbel.parse_postcodes(wrong_header)


def test_national_facts_are_enforced() -> None:
    communes = [{"ins": "21004", "region": "BRU"}]
    with pytest.raises(statbel.AcquisitionError, match="1 communes"):
        statbel.check_national(communes, [("1000", "21004")])


# --- Fluvius --------------------------------------------------------------------------------

FLUVIUS_SAMPLE = (
    "﻿code;community;dnbelectricity;dnbgas;gastype;gastype_fluvius\r\n"
    "2387;Baarle-Hertog (uitgezonderd Zondereigen);Fluvius Kempen;Enexis Netbeheer;L;"
    "Niet Fluvius\r\n"
    "2387;Zondereigen;Fluvius Kempen;Fluvius Kempen;L;H\r\n"
    "3790;Voeren/Fourons;Fluvius Limburg;;H;Niet Fluvius\r\n"
    "3790;Voeren/Fourons;Fluvius Limburg;;H;Niet Fluvius\r\n"
    "1804;Vilvoorde;Fluvius Halle-Vilvoorde;Fluvius Halle-Vilvoorde;L;H\r\n"
).encode()
FLEMISH = {
    "13002": {"nom_fr": "Baerle-Duc", "nom_nl": "Baarle-Hertog", "nom_de": "", "region": "VLA"},
    "73109": {"nom_fr": "Fourons", "nom_nl": "Voeren", "nom_de": "", "region": "VLA"},
    "23088": {"nom_fr": "Vilvorde", "nom_nl": "Vilvoorde", "nom_de": "", "region": "VLA"},
    "23096": {"nom_fr": "Zemst", "nom_nl": "Zemst", "nom_de": "", "region": "VLA"},
    "21004": {"nom_fr": "Bruxelles", "nom_nl": "Brussel", "nom_de": "", "region": "BRU"},
}
OWNERS = {"2387": {"13002"}, "3790": {"73109"}, "1804": {"23088", "23096"}, "1000": {"21004"}}
OPERATORS = {"fluvius-kempen", "fluvius-limburg", "fluvius-halle-vilvoorde", "enexis"}


def test_fluvius_operator_names_map_to_ids() -> None:
    assert fluvius.operator_id("Fluvius Halle-Vilvoorde", OPERATORS) == "fluvius-halle-vilvoorde"
    assert fluvius.operator_id("Enexis Netbeheer", OPERATORS) == "enexis"
    assert fluvius.operator_id("", OPERATORS) == ""
    with pytest.raises(statbel.AcquisitionError, match="Fluvius Noord"):
        fluvius.operator_id("Fluvius Noord", OPERATORS)


def test_fluvius_rows_join_on_the_postcode_then_the_community() -> None:
    rows = fluvius.derive(
        fluvius.parse(FLUVIUS_SAMPLE), owners=OWNERS, communes=FLEMISH, operators=OPERATORS
    )
    assert [tuple(row.values()) for row in rows] == [
        ("1804", "Vilvoorde", "23088", "fluvius-halle-vilvoorde", "fluvius-halle-vilvoorde", "L"),
        (
            "2387",
            "Baarle-Hertog (uitgezonderd Zondereigen)",
            "13002",
            "fluvius-kempen",
            "enexis",
            "L",
        ),
        ("2387", "Zondereigen", "13002", "fluvius-kempen", "fluvius-kempen", "L"),
        ("3790", "Voeren/Fourons", "73109", "fluvius-limburg", "", "H"),
    ]
    assert list(rows[0]) == list(schema.DERIVED_FLUVIUS_HEADER)


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("1804;Grimbergen;Fluvius Halle-Vilvoorde;;L;H", "1804 Grimbergen"),  # no tie-break
        ("9999;Nergens;Fluvius Kempen;;L;H", "9999 Nergens"),  # not a Statbel postcode
        ("1000;Brussel;Fluvius Kempen;;L;H", "not Flemish"),
    ],
)
def test_fluvius_rows_that_do_not_join_are_refused(line: str, message: str) -> None:
    data = FLUVIUS_SAMPLE + f"{line}\r\n".encode()
    with pytest.raises(statbel.AcquisitionError, match=message):
        fluvius.derive(fluvius.parse(data), owners=OWNERS, communes=FLEMISH, operators=OPERATORS)


# --- ODWB -----------------------------------------------------------------------------------

ODWB_GAS_SAMPLE = (
    "﻿" + ";".join(odwb.GAS_COLUMNS) + "\r\n"
    "GAZ;2023;Namur;5000;NAMUR;Résidentiel;10;Namur;50.4, 4.8;Arr;Prov\r\n"
    "GAZ;2024;Namur;5000;NAMUR;Résidentiel;12;Namur;50.4, 4.8;Arr;Prov\r\n"
    "GAZ;2024;Namur;5000;NAMUR;Professionnel;3;Namur;50.4, 4.8;Arr;Prov\r\n"
    "GAZ;2024;Namur;5020;FLAWINNE;Résidentiel;5;Namur;50.4, 4.8;Arr;Prov\r\n"
    "GAZ;2024;Namur;EXC;EXC;Professionnel;1;;;;\r\n"
).encode()
WALLOON = {"92094": {"nom_fr": "Namur", "nom_nl": "Namen", "nom_de": "Namur", "region": "WAL"}}


def test_odwb_keeps_the_distinct_localities_of_the_latest_year() -> None:
    year, rows, dropped = odwb.derive(
        odwb.parse(ODWB_GAS_SAMPLE, "gas"),
        owners={"5000": {"92094"}, "5020": {"92094"}},
        communes=WALLOON,
    )
    assert (year, dropped) == ("2024", 1)
    assert rows == [
        {
            "year": "2024",
            "postcode": "5000",
            "localite": "NAMUR",
            "commune": "Namur",
            "secteur": "Namur",
            "ins": "92094",
        },
        {
            "year": "2024",
            "postcode": "5020",
            "localite": "FLAWINNE",
            "commune": "Namur",
            "secteur": "Namur",
            "ins": "92094",
        },
    ]


def test_odwb_refuses_another_fluid_or_an_unknown_postcode() -> None:
    with pytest.raises(statbel.AcquisitionError, match="header"):
        odwb.parse(ODWB_GAS_SAMPLE, "elec")
    electricity = ODWB_GAS_SAMPLE.replace(b"\r\nGAZ;2023", b"\r\nELECTRICITE;2023")
    with pytest.raises(statbel.AcquisitionError, match="fluide"):
        odwb.parse(electricity, "gas")
    with pytest.raises(statbel.AcquisitionError, match="5020 Namur"):
        odwb.derive(
            odwb.parse(ODWB_GAS_SAMPLE, "gas"), owners={"5000": {"92094"}}, communes=WALLOON
        )


# --- fetch: cache and sources.csv -----------------------------------------------------------


def test_fetch_downloads_once_then_reads_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def download(url: str) -> bytes:
        calls.append(url)
        return b"postcode,ins\n"

    monkeypatch.setattr(fetch, "download", download)
    source = fetch.SOURCES["geo-statbel-postcodes-2025"]
    first = fetch.fetch(source, cache=tmp_path)
    assert first.path == tmp_path / source.id / source.filename
    meta = json.loads((tmp_path / source.id / "fetch.json").read_bytes())
    assert meta["sha256"] == first.sha256 == fetch.sha256_hex(b"postcode,ins\n")
    assert schema.is_date(meta["retrieved_at"])
    assert fetch.fetch(source, cache=tmp_path) == first
    assert len(calls) == 1
    first.path.write_bytes(b"tampered\n")  # bytes that no longer match fetch.json
    fetch.fetch(source, cache=tmp_path)
    assert len(calls) == 2
    fetch.fetch(source, cache=tmp_path, refresh=True)
    assert len(calls) == 3


def test_record_keeps_the_other_sources(tmp_path: Path) -> None:
    sources = tmp_path / "sources.csv"
    other = {
        "id": "brugel-grd",
        "role": "R",
        "publisher": "Brugel",
        "title": "GRD",
        "url": "https://brugel.brussels/",
        "retrieved_at": "2026-10-12",
        "sha256": "",
        "license": "",
        "note": "",
    }
    csvio.write_csv(sources, schema.SOURCES_HEADER, [other])
    source = fetch.SOURCES["fluvius-1-23"]
    item = fetch.Fetched(source, tmp_path / "x.csv", "a" * 64, "2026-10-01", 10)
    fetch.record([item], sources)
    rows = csvio.read_csv(sources, schema.SOURCES_HEADER)
    assert [row["id"] for row in rows] == ["brugel-grd", "fluvius-1-23"]
    assert rows[0] == other
    assert rows[1]["role"] == "M"
    assert (rows[1]["retrieved_at"], rows[1]["sha256"]) == ("2026-10-01", "a" * 64)


def test_the_sources_are_https_slugs() -> None:
    for source_id, source in fetch.SOURCES.items():
        assert source.id == source_id
        assert schema.SLUG_RE.fullmatch(source_id)
        assert source.url.startswith("https://")
        assert source.filename and "/" not in source.filename


# --- The committed extracts and data --------------------------------------------------------


def test_derived_extracts_have_their_headers() -> None:
    headers = {
        "statbel_refnis_2025_communes.csv": schema.DERIVED_COMMUNES_HEADER,
        "statbel_postcodes_2025.csv": schema.DERIVED_POSTCODES_HEADER,
        "fluvius_1_23.csv": schema.DERIVED_FLUVIUS_HEADER,
        "ores_odwb_elec.csv": odwb.HEADER,
        "ores_odwb_gas.csv": odwb.HEADER,
    }
    for name, header in headers.items():
        assert csvio.read_csv(DERIVED / name, header), name


def test_communes_and_postcodes_follow_the_statbel_extracts() -> None:
    communes = csvio.read_csv(ROOT / "data" / "communes.csv", schema.COMMUNES_HEADER)
    refnis = csvio.read_csv(
        DERIVED / "statbel_refnis_2025_communes.csv", schema.DERIVED_COMMUNES_HEADER
    )
    assert [(row["ins"], row["nom_fr"], row["nom_nl"]) for row in communes] == [
        (row["ins"], row["nom_fr"], row["nom_nl"]) for row in refnis
    ]
    assert (ROOT / "data" / "postcodes.csv").read_bytes() == (
        DERIVED / "statbel_postcodes_2025.csv"
    ).read_bytes()


def test_record_writes_the_role_of_the_source(tmp_path: Path) -> None:
    """The decree of the Bastogne-Bertogne merger is a legal reference (R), not M data."""
    sources = tmp_path / "sources.csv"
    csvio.write_csv(sources, schema.SOURCES_HEADER, [])
    source = fetch.SOURCES["decret-2023-05-19-fusion-bastogne-bertogne"]
    fetch.record([fetch.Fetched(source, tmp_path / "x.html", "b" * 64, "2026-10-12", 10)], sources)
    [row] = csvio.read_csv(sources, schema.SOURCES_HEADER)
    assert (row["role"], row["publisher"]) == ("R", "Parlement wallon (Moniteur belge)")


def test_sources_csv_records_every_source_as_fetched() -> None:
    rows = {
        row["id"]: row
        for row in csvio.read_csv(ROOT / "data" / "sources.csv", schema.SOURCES_HEADER)
    }
    assert {source.role for source in fetch.SOURCES.values()} == {"M", "R"}
    for source in fetch.SOURCES.values():
        row = rows[source.id]
        assert (row["role"], row["publisher"], row["url"]) == (
            source.role,
            source.publisher,
            source.url,
        )
        assert (row["title"], row["license"], row["note"]) == (
            source.title,
            source.license,
            source.note,
        )
        assert schema.SHA256_RE.fullmatch(row["sha256"])
        assert schema.is_date(row["retrieved_at"])
