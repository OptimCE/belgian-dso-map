"""scripts/powerbi.py: what the CWaPE Power BI readings show for a commune or a section,
and the committed summary that stands for the full readings (local only) everywhere else."""

from __future__ import annotations

from pathlib import Path

import pytest

import csvio
import powerbi
import schema
from helpers import ROOT

PRIVATE = ROOT / "curation" / powerbi.PRIVATE_DIR
SUMMARY = ROOT / "curation" / powerbi.SUMMARY_FILE

BASTOGNE = ("Bastogne", "Bastenaken", "Bastnach")


def entry(label: str, ins: str, grd_label: str, grd_id: str, count: str = "1") -> dict[str, str]:
    return {
        "commune_label": label, "ins": ins, "grd_label": grd_label, "grd_id": grd_id,
        "count": count,
    }  # fmt: skip


# Synthetic counts, except Couvin's electricity: a disagreement, which the committed
# summary states anyway. Agreeing rows of the real readings are never copied (CLAUDE.md).
READING = powerbi.Reading(
    {
        "elec": [
            entry("BASTOGNE", "82039", "ORES Luxembourg", "ores", "4"),
            entry("BERTOGNE", "82039", "ORES Luxembourg", "ores", "2"),
            entry("COUVIN", "93014", "AIESH", "aiesh", "30"),
            entry("COUVIN", "93014", "ORES Namur", "ores", "10"),
        ],
        "gas": [entry("BASTOGNE", "82039", "ORES Luxembourg", "ores", "1")],
    }
)


def test_a_commune_gets_every_row_of_its_ins() -> None:
    assert READING.shown("elec", "93014") == {"aiesh", "ores"}
    assert READING.shown("elec", "82039") == {"ores"}
    assert READING.shown("gas", "82039") == {"ores"}


def test_a_commune_missing_from_a_vector_shows_no_dso() -> None:
    assert READING.shown("gas", "93014") == set()


def test_outside_the_reading_nothing_is_shown() -> None:
    assert READING.shown("elec", "21004") is None
    assert powerbi.Reading({"elec": READING.rows["elec"]}).shown("gas", "93014") is None


def test_a_section_with_its_own_label() -> None:
    assert READING.shown("gas", "82039", ("Bertogne", "Bertogne", ""), BASTOGNE) == set()
    assert READING.shown("gas", "82039", BASTOGNE, BASTOGNE) == {"ores"}
    assert [
        e["count"] for e in READING.entries("elec", "82039", ("Bertogne",), BASTOGNE) or []
    ] == ["2"]


def test_a_section_without_a_label_gets_the_commune_label() -> None:
    assert READING.shown("gas", "82039", ("Noville",), BASTOGNE) == {"ores"}
    assert READING.shown("gas", "82039", ("Noville",), ("Elsewhere",)) is None


def test_expected_follows_the_designated_dso() -> None:
    assert powerbi.expected("elec", elec_designated="aieg", gas_operator="") == {"aieg"}
    assert powerbi.expected("gas", elec_designated="aieg", gas_operator="") == set()
    assert powerbi.expected("gas", elec_designated="aieg", gas_operator="resa") == {"resa"}


def test_label_to_id() -> None:
    """Every ORES sub-region is ores; any other label is its operator id in lower case."""
    assert powerbi.label_to_id("ORES Namur") == "ores"
    assert powerbi.label_to_id("ORES Brabant wallon") == "ores"
    assert powerbi.label_to_id("AIESH") == "aiesh"
    assert powerbi.label_to_id("RESA") == "resa"
    assert powerbi.label_to_id("REW") == "rew"
    assert powerbi.label_to_id("ORESTE") == "oreste"  # not an ORES sub-region


def test_label_matches_a_name_of_its_ins_or_an_alias() -> None:
    aliases = {("Bertogne", "82039")}
    assert powerbi.label_matches("BASTOGNE", "82039", BASTOGNE, aliases)
    assert powerbi.label_matches("BASTENAKEN", "82039", BASTOGNE, ())
    assert powerbi.label_matches("BRAINE-L'ALLEUD", "25014", ("Braine-l'Alleud",), ())
    assert powerbi.label_matches("BERTOGNE", "82039", BASTOGNE, aliases)
    assert not powerbi.label_matches("BERTOGNE", "82039", BASTOGNE, ())
    assert not powerbi.label_matches("BERTOGNE", "82039", BASTOGNE, {("Bertogne", "82009")})
    assert not powerbi.label_matches("WAVRE", "25005", ("Beauvechain", "Bevekom", ""), ())
    assert not powerbi.label_matches("", "82039", ("", "Bastogne"), ())


def test_load(tmp_path: Path) -> None:
    assert powerbi.load(tmp_path) is None
    csvio.write_csv(tmp_path / "cwape_powerbi_gas.csv", powerbi.HEADER, READING.rows["gas"])
    loaded = powerbi.load(tmp_path)
    assert loaded is not None and set(loaded.rows) == {"gas"}


def target(ins: str, elec: str, gas: str, section_key: str = "", *names: str) -> powerbi.Target:
    return powerbi.Target(ins, section_key, names, BASTOGNE if ins == "82039" else (), elec, gas)


def test_compare_agrees_or_says_what_the_report_showed() -> None:
    couvin = target("93014", "aiesh", "")
    assert powerbi.compare(READING, "elec", couvin) == {
        "ins": "93014", "section_key": "", "vector": "elec", "data": "aiesh", "agrees": "false",
        "observed": "AIESH 30 + ORES Namur 10",
    }  # fmt: skip
    assert powerbi.compare(READING, "gas", couvin) == {
        "ins": "93014", "section_key": "", "vector": "gas", "data": "none", "agrees": "true",
        "observed": "",
    }  # fmt: skip
    bertogne = target("82039", "ores", "ores", "bertogne", "Bertogne")
    assert powerbi.compare(READING, "gas", bertogne) == {
        "ins": "82039", "section_key": "bertogne", "vector": "gas", "data": "ores",
        "agrees": "false", "observed": "none",
    }  # fmt: skip
    assert powerbi.compare(READING, "elec", target("21004", "sibelga", "sibelga")) is None


def test_summarize_sorts_and_keeps_the_vectors_not_read() -> None:
    targets = [
        target("93014", "aiesh", ""),
        target("82039", "ores", "", "bertogne", "Bertogne"),
        target("82039", "ores", "ores", "bastogne", *BASTOGNE),
        target("21004", "sibelga", "sibelga"),  # outside the report: no row
    ]
    summary = powerbi.summarize(READING, targets)
    assert [powerbi.summary_key(row) for row in summary] == [
        ("82039", "bastogne", "elec"), ("82039", "bastogne", "gas"),
        ("82039", "bertogne", "elec"), ("82039", "bertogne", "gas"),
        ("93014", "", "elec"), ("93014", "", "gas"),
    ]  # fmt: skip
    assert all(row["agrees"] == "true" for row in summary if row["ins"] == "82039")
    elec_only = powerbi.Reading({"elec": READING.rows["elec"]})
    assert powerbi.summarize(elec_only, targets, keep=summary) == summary
    assert [row["vector"] for row in powerbi.summarize(elec_only, targets)] == ["elec"] * 3


def test_agrees_from_the_full_reading_or_the_summary() -> None:
    couvin, bastogne = target("93014", "aiesh", ""), target("82039", "ores", "ores")
    summary = {
        powerbi.summary_key(row): row for row in powerbi.summarize(READING, [couvin, bastogne])
    }
    for reading in (READING, None):
        assert not powerbi.agrees(reading, summary, "elec", couvin)
        assert powerbi.agrees(reading, summary, "gas", couvin)
        assert powerbi.agrees(reading, summary, "elec", bastogne)
    # The summary compared other values than the row has now: no agreement from it ...
    moved = target("82039", "aieg", "ores")
    assert not powerbi.agrees(None, summary, "elec", moved)
    # ... and nothing at all without either.
    assert not powerbi.agrees(None, {}, "gas", couvin)
    # The full reading of a vector decides, whatever the summary says.
    assert powerbi.agrees(READING, {}, "gas", couvin)
    wrong = {key: {**row, "agrees": "true", "observed": ""} for key, row in summary.items()}
    assert not powerbi.agrees(READING, wrong, "elec", couvin)
    assert powerbi.agrees(powerbi.Reading({"gas": []}), wrong, "elec", couvin)


def test_observed_format() -> None:
    for good in ("none", "ORES Hainaut 19", "AIESH 30 + ORES Namur 10"):
        assert powerbi.OBSERVED_RE.fullmatch(good), good
    for bad in ("", "ORES Hainaut", "ORES Hainaut 0", "AIESH 30 +ORES Namur 10", " 3"):
        assert not powerbi.OBSERVED_RE.fullmatch(bad), bad


def test_load_summary(tmp_path: Path) -> None:
    assert powerbi.load_summary(tmp_path / powerbi.SUMMARY_FILE) is None
    rows = powerbi.summarize(READING, [target("93014", "aiesh", "")])
    csvio.write_csv(tmp_path / powerbi.SUMMARY_FILE, powerbi.SUMMARY_HEADER, rows)
    assert powerbi.load_summary(tmp_path / powerbi.SUMMARY_FILE) == rows


def real_targets() -> list[powerbi.Target]:
    communes = {
        row["ins"]: row
        for row in csvio.read_csv(ROOT / "data" / "communes.csv", schema.COMMUNES_HEADER)
    }
    rows = [
        *csvio.read_csv(ROOT / "data" / "assignments.csv", schema.ASSIGNMENTS_HEADER),
        *csvio.read_csv(ROOT / "data" / "sections.csv", schema.SECTIONS_HEADER),
    ]
    return [
        powerbi.target(communes[row["ins"]], row)
        for row in rows
        if communes[row["ins"]]["region"] == "WAL"
    ]


def test_the_committed_summary() -> None:
    """Every Walloon row, both vectors; a label and a count only where the report disagrees.

    It is no copy of the report: no commune label, no GRD label or count of an agreeing
    row (the full readings stay in curation/private/, git-ignored).
    """
    summary = powerbi.load_summary(SUMMARY)
    assert summary is not None
    targets = {(item.ins, item.section_key): item for item in real_targets()}
    assert len(targets) == 262  # 261 Walloon communes, Bastogne in two sections
    assert {(row["ins"], row["section_key"]) for row in summary} == set(targets)
    assert {row["vector"] for row in summary} == {"elec", "gas"}
    assert len(summary) == 2 * len(targets)
    for row in summary:
        assert row["data"] == powerbi.data_value(
            row["vector"], targets[(row["ins"], row["section_key"])]
        )
    disagreements = {
        (row["ins"], row["vector"]): row["observed"] for row in summary if row["agrees"] == "false"
    }
    assert disagreements == {
        ("25107", "gas"): "none",  # Villers-la-Ville
        ("25122", "gas"): "none",  # Ramillies
        ("57093", "elec"): "ORES Hainaut 19",  # Brunehaut
        ("62026", "gas"): "none",  # Comblain-au-Pont
        ("63067", "gas"): "none",  # Saint-Vith
        ("85046", "gas"): "none",  # Habay
        ("93014", "elec"): "AIESH 30 + ORES Namur 10",  # Couvin
    }
    assert all(row["observed"] == "" for row in summary if row["agrees"] == "true")


def test_the_full_readings_when_present() -> None:
    """Every Walloon commune is in the electricity reading, Bertogne under its own label,
    and the committed summary follows from the readings (validate.py refuses it otherwise).

    The readings are local (curation/private/ is git-ignored): skipped in CI.
    """
    reading = powerbi.load(PRIVATE)
    if reading is None:
        pytest.skip("the full Power BI readings are local only (curation/private/)")
    assert set(reading.rows) == {"elec", "gas"}
    assert len({row["ins"] for row in reading.rows["elec"]}) == 261
    assert reading.labels("82039") == {"bastogne", "bertogne"}
    assert {row["grd_id"] for rows in reading.rows.values() for row in rows} == {
        "aieg", "aiesh", "ores", "resa", "rew"
    }  # fmt: skip
    assert all(
        row["grd_id"] == powerbi.label_to_id(row["grd_label"])
        for rows in reading.rows.values()
        for row in rows
    )
    assert powerbi.summarize(reading, real_targets()) == powerbi.load_summary(SUMMARY)


def test_the_full_readings_are_never_committed() -> None:
    """curation/private/ is git-ignored, and no reading is left in curation/derived/."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"curation/{powerbi.PRIVATE_DIR}/" in ignore
    for name, _ in powerbi.READINGS.values():
        assert not (ROOT / "curation" / "derived" / name).exists()
