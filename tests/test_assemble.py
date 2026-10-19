"""scripts/curate/assemble.py: worksheets + aliases + overrides -> assignments and sections."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

import assemble
import csvio
import powerbi
import schema
from helpers import ROOT

Row = dict[str, str]

COMMUNES = [
    {"ins": "13002", "nom_fr": "Baerle-Duc", "nom_nl": "Baarle-Hertog", "nom_de": "Baarle-Hertog",
     "region": "VLA", "province": "BE-VAN"},
    {"ins": "21004", "nom_fr": "Bruxelles", "nom_nl": "Brussel", "nom_de": "Brüssel",
     "region": "BRU", "province": ""},
    {"ins": "57093", "nom_fr": "Brunehaut", "nom_nl": "Brunehaut", "nom_de": "Brunehaut",
     "region": "WAL", "province": "BE-WHT"},
    {"ins": "92048", "nom_fr": "Fosses-la-Ville", "nom_nl": "Fosses-la-Ville",
     "nom_de": "Fosses-la-Ville", "region": "WAL", "province": "BE-WNA"},
    {"ins": "92094", "nom_fr": "Namur", "nom_nl": "Namen", "nom_de": "Namür",
     "region": "WAL", "province": "BE-WNA"},
]  # fmt: skip
POSTCODES = [
    ("1000", "21004"), ("2387", "13002"), ("5000", "92094"), ("5020", "92094"), ("5070", "92048"),
    ("7620", "57093"),
]  # fmt: skip


PBI_ELEC = powerbi.READINGS["elec"][1]
PBI_GAS = powerbi.READINGS["gas"][1]


def source(id_: str, role: str, publisher: str) -> Row:
    return {
        "id": id_, "role": role, "publisher": publisher, "title": id_,
        "url": f"https://example.org/{id_}", "retrieved_at": "2026-10-12", "sha256": "",
        "license": "", "note": "",
    }  # fmt: skip


SOURCES = [
    source("agw-elec", "R", "Gouvernement wallon"),
    source("agw-gaz", "R", "Gouvernement wallon"),
    source("agw-aieg", "R", "Gouvernement wallon"),
    source("cwape-gaz", "C", "CWaPE"),
    source("aieg-page", "C", "AIEG"),
    source("odwb-ores-elec", "M", "ORES"),
    source("odwb-ores-gas", "M", "ORES"),
    source("fluvius-1-23", "M", "Fluvius"),
    source("vnr-elec", "R", "Vlaamse Nutsregulator"),
    source("vnr-gas", "R", "Vlaamse Nutsregulator"),
    source("vnr-zondereigen", "R", "Vlaamse Nutsregulator"),
    source("brugel", "R", "Brugel"),
    source(PBI_ELEC, "C", "CWaPE"),
    source(PBI_GAS, "C", "CWaPE"),
]


def ws(grd: str, vector: str, name: str, ins: str, source_id: str) -> Row:
    return {"grd": grd, "vector": vector, "name_in_source": name, "ins": ins,
            "source_id": source_id, "locator": "art. 1er"}  # fmt: skip


WAL = [
    ws("ores", "elec", "Namur", "92094", "agw-elec"),
    ws("ores", "elec", "Fosse-la-ville", "92048", "agw-elec"),
    ws("aieg", "elec", "Brunehaut", "57093", "agw-aieg"),
    ws("ores", "elec", "Brunehaut", "57093", "agw-aieg"),
    ws("aieg", "elec", "Brunehaut", "57093", "aieg-page"),
    ws("ores", "gas", "Namur", "92094", "agw-gaz"),
    ws("ores", "gas", "NAMUR", "92094", "cwape-gaz"),
]
VLA = [
    ws("fluvius-kempen", "elec", "Baarle-Hertog", "13002", "vnr-elec"),
    ws("fluvius-kempen", "gas", "Baarle-Hertog", "13002", "vnr-gas"),
    ws("fluvius-kempen", "gas", "Zondereigen", "13002", "vnr-zondereigen"),
]
ALIASES = [
    {"name_in_source": "Fosse-la-ville", "ins": "92048", "reason": "misprint"},
    {"name_in_source": "Zondereigen", "ins": "13002", "reason": "wijk"},
]


def override(ins: str, field: str, value: str = "", **meta: str) -> Row:
    row = {"ins": ins, "field": field, "value": value, "valid_from": "", "flags": "",
           "note_key": "", "source_ids": "", "reason": "test"}  # fmt: skip
    row.update(meta)
    return row


OVERRIDES = [
    override("57093", "elec", "aieg", valid_from="2026-01-01", flags="transition",
             note_key="brunehaut", source_ids="aieg-page"),
    override("13002/enclaves", "gas", "foreign:enexis", source_ids="vnr-zondereigen"),
    override("13002/enclaves", "nom_fr", "Baarle-Hertog"),
    override("13002/enclaves", "postcodes", "2387"),
    override("13002/zondereigen", "nom_fr", "Zondereigen"),
    override("13002/zondereigen", "postcodes", "2387"),
    override("BRU", "elec", "sibelga", source_ids="brugel"),
    override("BRU", "gas", "designated:sibelga", source_ids="brugel"),
    override("WAL", "gas_none_sources", source_ids="agw-gaz"),
]  # fmt: skip
ODWB_ELEC = [("5000", "92094"), ("5070", "92048"), ("7620", "57093")]
ODWB_GAS = [("5000", "92094")]
FLUVIUS = [
    {"postcode": "2387", "community": "Baarle-Hertog (uitgezonderd Zondereigen)", "ins": "13002",
     "elec_id": "fluvius-kempen", "gas_id": "enexis", "gastype": "L"},
    {"postcode": "2387", "community": "Zondereigen", "ins": "13002",
     "elec_id": "fluvius-kempen", "gas_id": "fluvius-kempen", "gastype": "L"},
]  # fmt: skip


def write_case(
    root: Path,
    *,
    wal: list[Row] | None = None,
    overrides: list[Row] | None = None,
    aliases: list[Row] | None = None,
    sources: list[Row] | None = None,
    readings: dict[str, list[tuple[str, str, str, str]]] | None = None,
    summary: list[Row] | None = None,
) -> tuple[Path, Path]:
    """The files of a small case. `readings`: vector -> (label, INS, GRD label, GRD id),
    the full Power BI readings (curation/private/); `summary`: curation/powerbi_checks.csv."""
    data, curation = root / "data", root / "curation"
    data.mkdir(parents=True)
    (curation / "derived").mkdir(parents=True)
    csvio.write_csv(data / "communes.csv", schema.COMMUNES_HEADER, COMMUNES)
    csvio.write_csv(
        data / "postcodes.csv",
        schema.POSTCODES_HEADER,
        [{"postcode": p, "ins": i} for p, i in POSTCODES],
    )
    shutil.copy(ROOT / "data" / "operators.csv", data / "operators.csv")
    csvio.write_csv(data / "sources.csv", schema.SOURCES_HEADER, sources or SOURCES)
    csvio.write_csv(
        curation / "wal_designations.csv", schema.WORKSHEET_HEADER, WAL if wal is None else wal
    )
    csvio.write_csv(curation / "vla_designations.csv", schema.WORKSHEET_HEADER, VLA)
    csvio.write_csv(
        curation / "aliases.csv",
        schema.ALIASES_HEADER,
        ALIASES if aliases is None else aliases,
    )
    csvio.write_csv(
        curation / "overrides.csv",
        assemble.OVERRIDES_HEADER,
        OVERRIDES if overrides is None else overrides,
    )
    for name, pairs in (("ores_odwb_elec.csv", ODWB_ELEC), ("ores_odwb_gas.csv", ODWB_GAS)):
        csvio.write_csv(
            curation / "derived" / name,
            assemble.ODWB_HEADER,
            [
                {"year": "2024", "postcode": p, "localite": "X", "commune": "X", "secteur": "X",
                 "ins": i}
                for p, i in pairs
            ],
        )  # fmt: skip
    csvio.write_csv(
        curation / "derived" / "fluvius_1_23.csv", schema.DERIVED_FLUVIUS_HEADER, FLUVIUS
    )
    for vector, entries in (readings or {}).items():
        csvio.write_csv(
            curation / powerbi.PRIVATE_DIR / powerbi.READINGS[vector][0],
            powerbi.HEADER,
            [
                {"commune_label": label, "ins": ins, "grd_label": grd_label, "grd_id": grd,
                 "count": "1"}
                for label, ins, grd_label, grd in entries
            ],
        )  # fmt: skip
    if summary is not None:
        csvio.write_csv(curation / powerbi.SUMMARY_FILE, powerbi.SUMMARY_HEADER, summary)
    return data, curation


def run(tmp_path: Path, **case: Any) -> assemble.Assembly:
    return assemble.assemble(assemble.load(*write_case(tmp_path, **case)))


def by_label(result: assemble.Assembly) -> dict[str, Row]:
    rows = {row["ins"]: row for row in result.assignments}
    rows |= {f"{row['ins']}/{row['section_key']}": row for row in result.sections}
    return rows


def test_the_committed_data_equals_the_assembly() -> None:
    assert assemble.main(["--check"]) == 0


def test_rows_follow_the_worksheets_and_the_overrides(tmp_path: Path) -> None:
    rows = by_label(run(tmp_path))
    assert rows["92094"] == {
        "ins": "92094", "elec_operator": "ores", "elec_designated": "ores",
        "gas_status": "designated", "gas_operator": "ores", "flags": "", "note_key": "",
        "source_ids": "agw-elec|agw-gaz|cwape-gaz|odwb-ores-elec|odwb-ores-gas", "valid_from": "",
    }  # fmt: skip
    # The R lists of Brunehaut disagree: the override decides, and the source of the
    # other value (the ORES entry of the same order) is still cited by its AIEG entry.
    brunehaut = rows["57093"]
    assert (brunehaut["elec_operator"], brunehaut["elec_designated"]) == ("aieg", "aieg")
    assert (brunehaut["flags"], brunehaut["note_key"], brunehaut["valid_from"]) == (
        "transition", "brunehaut", "2026-01-01"
    )  # fmt: skip
    # No R gas entry in a region whose gas lists are transcribed: none, with the region's
    # absence sources and the ORES extract that has no access point there.
    assert (brunehaut["gas_status"], brunehaut["gas_operator"]) == ("none", "")
    assert brunehaut["source_ids"] == "agw-aieg|agw-gaz|aieg-page|odwb-ores-gas"
    assert rows["21004"]["source_ids"] == "brugel"
    assert rows["21004"]["gas_status"] == "designated"


def test_sections_come_from_the_overrides(tmp_path: Path) -> None:
    result = run(tmp_path)
    assert "13002" not in {row["ins"] for row in result.assignments}
    rows = by_label(result)
    enclaves, zondereigen = rows["13002/enclaves"], rows["13002/zondereigen"]
    assert (enclaves["gas_status"], enclaves["gas_operator"]) == ("foreign", "enexis")
    assert (zondereigen["gas_status"], zondereigen["gas_operator"]) == (
        "designated", "fluvius-kempen"
    )  # fmt: skip
    assert enclaves["nom_fr"] == "Baarle-Hertog" and enclaves["postcodes"] == "2387"
    # Each section cites the Fluvius row that agrees with it, and only agreeing entries.
    assert enclaves["source_ids"] == "fluvius-1-23|vnr-elec|vnr-zondereigen"
    assert zondereigen["source_ids"] == "fluvius-1-23|vnr-elec|vnr-gas|vnr-zondereigen"


def test_a_name_that_maps_to_nothing_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(assemble.CurationError, match=r"'Fosse-la-ville' is not a name of 92048"):
        run(tmp_path, aliases=[ALIASES[1]])


def test_conflicting_r_lists_need_an_override(tmp_path: Path) -> None:
    with pytest.raises(assemble.CurationError, match=r"57093: the R lists designate"):
        run(tmp_path, overrides=[row for row in OVERRIDES if row["ins"] != "57093"])


def test_a_single_source_row_gets_to_confirm(tmp_path: Path) -> None:
    wal = [row for row in WAL if row["source_id"] != "cwape-gaz"]
    rows = by_label(run(tmp_path, wal=wal, sources=[s for s in SOURCES if s["role"] != "M"]))
    assert (rows["92094"]["flags"], rows["92094"]["note_key"]) == (
        "to_confirm", "wal-single-source"
    )  # fmt: skip
    assert rows["57093"]["note_key"] == "brunehaut"  # an AIEG page checks the order
    assert (rows["92048"]["flags"], rows["92048"]["note_key"]) == (
        "to_confirm", "wal-single-source"
    )  # fmt: skip
    # The Flemish sections have no M source left either.
    assert rows["13002/zondereigen"]["note_key"] == "vla-single-source"


def test_a_single_source_row_with_another_note_is_an_error(tmp_path: Path) -> None:
    sources = [s for s in SOURCES if s["id"] != "aieg-page" and s["role"] != "M"]
    wal = [row for row in WAL if row["source_id"] != "aieg-page"]
    overrides = [{**OVERRIDES[0], "source_ids": ""}, *OVERRIDES[1:]]
    with pytest.raises(assemble.CurationError, match=r"57093: single source.*brunehaut"):
        run(tmp_path, wal=wal, sources=sources, overrides=overrides)


def test_operator_differs_is_derived(tmp_path: Path) -> None:
    rows = by_label(
        run(tmp_path, overrides=[*OVERRIDES, override("92094", "elec_operator", "aieg")])
    )
    assert rows["92094"]["flags"] == "operator_differs"
    assert (rows["92094"]["elec_operator"], rows["92094"]["elec_designated"]) == ("aieg", "ores")


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (override("92094", "colour", "red"), "unknown field"),
        (override("92094", "elec", "nobody"), "unknown operator"),
        (override("92094", "gas", "designated"), "gas is none"),
        (override("92094", "annotate", flags="operator_differs"), "operator_differs is derived"),
        (override("92094", "nom_fr", "Namur"), "applies to a section"),
        (override("92094", "gas_none_sources"), "applies to a region"),
        (override("99999", "annotate"), "is not an INS"),
        (override("92094", "annotate", source_ids="nowhere"), "unknown source"),
        ({**override("92094", "annotate"), "reason": ""}, "a reason is required"),
    ],
)
def test_malformed_overrides_are_refused(tmp_path: Path, bad: Row, message: str) -> None:
    with pytest.raises(assemble.CurationError, match=message):
        run(tmp_path, overrides=[*OVERRIDES, bad])


def test_two_overrides_disagreeing_on_a_date_are_refused(tmp_path: Path) -> None:
    extra = override("57093", "annotate", valid_from="2025-01-01")
    with pytest.raises(assemble.CurationError, match="two valid_from"):
        run(tmp_path, overrides=[*OVERRIDES, extra])


def test_the_assembly_is_deterministic(tmp_path: Path) -> None:
    first = assemble.render(run(tmp_path / "a"))
    second = assemble.render(
        run(tmp_path / "b", wal=list(reversed(WAL)), overrides=list(reversed(OVERRIDES)))
    )
    assert first == second
    for name, data in first.items():
        header = schema.ASSIGNMENTS_HEADER if name == "assignments.csv" else schema.SECTIONS_HEADER
        csvio.parse_csv(data, name=name, header=header)


def test_check_reports_a_stale_file(tmp_path: Path) -> None:
    data, curation = write_case(tmp_path)
    args = ["--data-dir", str(data), "--curation", str(curation)]
    assert assemble.main(args) == 0
    assert assemble.main([*args, "--check"]) == 0
    (data / "assignments.csv").write_bytes(b"ins\n")
    assert assemble.main([*args, "--check"]) == 1


READINGS = {
    "elec": [
        ("BRUNEHAUT", "57093", "ORES Hainaut", "ores"),  # disagrees: AIEG since 2026
        ("FOSSES-LA-VILLE", "92048", "ORES Namur", "ores"),
        ("NAMUR", "92094", "ORES Namur", "ores"),
    ],
    "gas": [("NAMUR", "92094", "ORES Namur", "ores")],
}


def test_powerbi_readings_are_cited_where_they_agree(tmp_path: Path) -> None:
    rows = by_label(run(tmp_path, readings=READINGS))
    assert rows["92094"]["source_ids"] == (
        f"agw-elec|agw-gaz|cwape-gaz|{PBI_ELEC}|{PBI_GAS}|odwb-ores-elec|odwb-ores-gas"
    )
    # A commune missing from the gas reading shows no gas DSO: it agrees with none.
    assert schema.split_list(rows["92048"]["source_ids"]) == [
        "agw-elec", "agw-gaz", PBI_ELEC, PBI_GAS, "odwb-ores-elec", "odwb-ores-gas"
    ]  # fmt: skip
    assert PBI_ELEC not in rows["57093"]["source_ids"]
    assert PBI_GAS in rows["57093"]["source_ids"]
    # Brussels and Flanders are outside the report.
    assert PBI_ELEC not in rows["21004"]["source_ids"]


def test_a_reading_is_cited_only_with_its_source(tmp_path: Path) -> None:
    """Readings without their sources.csv rows, or sources without readings: no change."""
    without_sources = [s for s in SOURCES if s["id"] not in (PBI_ELEC, PBI_GAS)]
    assert assemble.render(run(tmp_path / "a")) == assemble.render(
        run(tmp_path / "b", sources=without_sources, readings=READINGS)
    )


def test_a_walloon_section_is_checked_with_its_own_postcodes_and_label(tmp_path: Path) -> None:
    """Bastogne's case: a section without gas, whose postcodes ODWB does not list and whose
    label the gas reading does not show (the other section keeps both)."""
    sections = [
        override("92094/namur", "nom_fr", "Namur"),
        override("92094/namur", "postcodes", "5000"),
        override("92094/flawinne", "nom_fr", "Flawinne"),
        override("92094/flawinne", "postcodes", "5020"),
        override("92094/flawinne", "gas", "none"),
    ]
    readings = {
        "elec": [*READINGS["elec"], ("FLAWINNE", "92094", "AIEG", "aieg")],
        "gas": READINGS["gas"],
    }
    rows = by_label(run(tmp_path, overrides=[*OVERRIDES, *sections], readings=readings))
    assert rows["92094/namur"]["source_ids"] == (
        f"agw-elec|agw-gaz|cwape-gaz|{PBI_ELEC}|{PBI_GAS}|odwb-ores-elec|odwb-ores-gas"
    )
    # 5020 has no ORES locality in either extract: no ODWB electricity, the absence of
    # gas access points instead; its own label shows AIEG (no) and no gas DSO (yes).
    assert rows["92094/flawinne"]["source_ids"] == f"agw-elec|agw-gaz|{PBI_GAS}|odwb-ores-gas"
    assert (rows["92094/flawinne"]["gas_status"], rows["92094/flawinne"]["flags"]) == ("none", "")


def summary_of(tmp_path: Path, **case: Any) -> list[Row]:
    """What validate.py --refresh-powerbi-summary writes for a case: the full readings
    compared with the assembled Walloon rows."""
    data, curation = write_case(tmp_path, **case)
    result = assemble.assemble(assemble.load(data, curation))
    reading = powerbi.load(curation / powerbi.PRIVATE_DIR)
    assert reading is not None
    communes = {row["ins"]: row for row in COMMUNES}
    targets = [
        powerbi.target(communes[row["ins"]], row)
        for row in [*result.assignments, *result.sections]
        if communes[row["ins"]]["region"] == "WAL"
    ]
    return powerbi.summarize(reading, targets)


def test_without_the_full_readings_the_summary_gives_the_same_citations(tmp_path: Path) -> None:
    """CI has no curation/private/: the committed summary must cite exactly the same."""
    summary = summary_of(tmp_path / "summary", readings=READINGS)
    assert [row for row in summary if row["agrees"] == "false"] == [
        {"ins": "57093", "section_key": "", "vector": "elec", "data": "aieg", "agrees": "false",
         "observed": "ORES Hainaut 1"},
    ]  # fmt: skip
    with_readings = assemble.render(run(tmp_path / "a", readings=READINGS))
    with_summary = assemble.render(run(tmp_path / "b", summary=summary))
    assert with_summary == with_readings
    assert with_readings != assemble.render(run(tmp_path / "c"))  # the readings count
    # Both present: the full readings decide (here they say the same).
    assert assemble.render(run(tmp_path / "d", readings=READINGS, summary=summary)) == with_readings


def test_a_summary_row_of_another_value_is_not_cited(tmp_path: Path) -> None:
    """A row changed since the summary was written: its comparison no longer holds."""
    summary = summary_of(tmp_path / "summary", readings=READINGS)
    stale = [
        {**row, "data": "aieg"} if (row["ins"], row["vector"]) == ("92094", "elec") else row
        for row in summary
    ]
    rows = by_label(run(tmp_path / "a", summary=stale))
    assert PBI_ELEC not in rows["92094"]["source_ids"]
    assert PBI_GAS in rows["92094"]["source_ids"]


def test_a_full_reading_of_one_vector_and_the_summary_of_the_other(tmp_path: Path) -> None:
    """Each vector comes from its full reading when present, else from the summary."""
    summary = summary_of(tmp_path / "summary", readings=READINGS)
    gas_only = [row for row in summary if row["vector"] == "gas"]
    rows = by_label(run(tmp_path / "a", readings={"elec": READINGS["elec"]}, summary=gas_only))
    assert by_label(run(tmp_path / "b", readings=READINGS)) == rows


def test_check_passes_with_or_without_the_full_readings(tmp_path: Path) -> None:
    """assemble.py --check after a refresh: green with curation/private/, and without it."""
    summary = summary_of(tmp_path / "summary", readings=READINGS)
    data, curation = write_case(tmp_path / "a", readings=READINGS, summary=summary)
    args = ["--data-dir", str(data), "--curation", str(curation)]
    assert assemble.main(args) == 0
    shutil.rmtree(curation / powerbi.PRIVATE_DIR)
    assert assemble.main([*args, "--check"]) == 0
