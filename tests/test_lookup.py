"""resolve / resolve_address on the mini fixture: every status, filter and fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import build
import lookup
import schema
from helpers import MINI, outcome


@pytest.fixture(scope="module")
def ix() -> lookup.Index:
    return lookup.build_index(outcome().build.tables["dso_lookup.csv"])


def keys(found: dict[str, Any]) -> list[str]:
    if found["status"] == "choose_commune":
        return [commune["ins"] for commune in found["communes"]]
    return [section["section_key"] for section in found["sections"]]


def test_ok_carries_the_whole_result(ix: lookup.Index) -> None:
    found = lookup.resolve(ix, "1300")
    assert found["status"] == "ok"
    assert found["data_version"] == "2026.10.0-draft"
    assert found["result"] == {
        "postcode": "1300",
        "ins": "25112",
        "commune": {"fr": "Wavre", "nl": "Waver", "de": "Wavre"},
        "section": None,
        "region": "WAL",
        "province": "BE-WBR",
        "regulator": "BE-WAL-CWAPE",
        "elec": {"operator": "rew", "designated": "rew"},
        "gas": {"status": "designated", "operator": "ores"},
        "flags": [],
        "note_key": "",
        "source_ids": ["agw-rew-wavre", "cwape-grd-gaz", "cwape-power-bi", "odwb-ores-gas"],
        "valid_from": "",
        "data_version": "2026.10.0-draft",
    }


def test_regulator_follows_the_region(ix: lookup.Index) -> None:
    assert lookup.resolve(ix, "1000")["result"]["regulator"] == "BE-BRU-BRUGEL"
    found = lookup.resolve(ix, "2387", section="baarle-hertog")
    assert found["result"]["regulator"] == "BE-VLA-VREG"


def test_choose_commune_lists_the_communes_by_ins(ix: lookup.Index) -> None:
    found = lookup.resolve(ix, "1050")
    assert found["status"] == "choose_commune"
    assert found["communes"] == [
        {"ins": "21004", "name": {"fr": "Bruxelles", "nl": "Brussel", "de": "Brüssel"}},
        {"ins": "21009", "name": {"fr": "Ixelles", "nl": "Elsene", "de": "Ixelles"}},
    ]


def test_choose_section_lists_sections_with_their_operator(ix: lookup.Index) -> None:
    found = lookup.resolve(ix, "5020")
    assert found["status"] == "choose_section"
    assert found["ins"] == "92094"
    assert found["commune"] == {"fr": "Namur", "nl": "Namen", "de": "Namür"}
    assert found["sections"] == [
        {
            "section_key": "champion",
            "name": {"fr": "Champion", "nl": "", "de": ""},
            "elec_operator": "ores",
        },
        {
            "section_key": "flawinne",
            "name": {"fr": "Flawinne", "nl": "", "de": ""},
            "elec_operator": "aieg",
        },
    ]


def test_sections_that_agree_on_electricity_allow_a_prefill(ix: lookup.Index) -> None:
    """Baarle-Hertog: both sections are Fluvius Kempen, only the gas differs."""
    found = lookup.resolve(ix, "2387")
    assert {section["elec_operator"] for section in found["sections"]} == {"fluvius-kempen"}


def test_a_single_section_for_the_postcode_is_ok(ix: lookup.Index) -> None:
    found = lookup.resolve(ix, "5003")
    assert found["status"] == "ok"
    assert found["result"]["section"] == {
        "section_key": "saint-marc",
        "name": {"fr": "Saint-Marc", "nl": "", "de": ""},
    }
    assert found["result"]["flags"] == ["transition", "operator_differs", "to_confirm"]
    assert found["result"]["elec"] == {"operator": "aieg", "designated": "ores"}


@pytest.mark.parametrize(
    "postcode", ["9999", "0000", "502", "50200", "5O20", "", None, chr(0x2003) + "5020"]
)
def test_not_found(ix: lookup.Index, postcode: str | None) -> None:
    assert lookup.resolve(ix, postcode) == {
        "status": "not_found",
        "data_version": "2026.10.0-draft",
    }


def test_ins_filter_applies_when_it_matches(ix: lookup.Index) -> None:
    assert lookup.resolve(ix, "1050", ins="21009")["result"]["ins"] == "21009"
    assert lookup.resolve(ix, "1050", ins=" 21009 ")["result"]["ins"] == "21009"


@pytest.mark.parametrize(
    ("postcode", "ins", "section", "status", "expected"),
    [
        ("1040", "99999", None, "choose_commune", ["21004", "21005"]),
        ("5020", "21004", None, "choose_section", ["champion", "flawinne"]),
        ("5020", None, "zzz", "choose_section", ["champion", "flawinne"]),
        ("1300", "99999", "zzz", "ok", None),
    ],
)
def test_filters_that_match_nothing_are_ignored(
    ix: lookup.Index,
    postcode: str,
    ins: str | None,
    section: str | None,
    status: str,
    expected: list[str] | None,
) -> None:
    found = lookup.resolve(ix, postcode, ins, section)
    assert found["status"] == status
    if expected is not None:
        assert keys(found) == expected


def test_section_filter_waits_for_a_single_commune(ix: lookup.Index) -> None:
    """A section key never picks a commune: 1040 with section=x still asks for the commune."""
    assert lookup.resolve(ix, "1040", section="flawinne")["status"] == "choose_commune"
    found = lookup.resolve(ix, "5020", ins="92094", section="flawinne")
    assert found["result"]["section"]["section_key"] == "flawinne"


# --- resolve_address ------------------------------------------------------------------------


def test_address_unsectioned_commune_ignores_the_post_name(ix: lookup.Index) -> None:
    found = lookup.resolve_address(ix, "25112", "1300", "Mont-de-l'Enclus")
    assert found["status"] == "ok"
    assert found["result"]["ins"] == "25112"


def test_address_falls_back_on_the_ins_when_the_postcode_is_not_its_own(ix: lookup.Index) -> None:
    found = lookup.resolve_address(ix, "21009", "1000")
    assert found["result"]["ins"] == "21009"
    assert found["result"]["postcode"] == "1050"


@pytest.mark.parametrize("nis", ["99999", "", None, "2100"])
def test_address_unknown_ins(ix: lookup.Index, nis: str | None) -> None:
    assert lookup.resolve_address(ix, nis, "1000")["status"] == "not_found"


@pytest.mark.parametrize(
    ("post_name", "section"),
    [("FLAWINNE", "flawinne"), ("  flawinne ", "flawinne"), ("Champion", "champion")],
)
def test_address_post_name_picks_one_section(
    ix: lookup.Index, post_name: str, section: str
) -> None:
    found = lookup.resolve_address(ix, "92094", "5020", post_name)
    assert found["status"] == "ok"
    assert found["result"]["section"]["section_key"] == section


def test_address_accents_hyphens_and_spaces_are_ignored(ix: lookup.Index) -> None:
    found = lookup.resolve_address(ix, "92094", "5024", "Marche lès Dames")
    assert found["result"]["section"]["section_key"] == "marche-les-dames"


@pytest.mark.parametrize("post_name", ["", None, "Namur", "Namen", "NAMÜR", "Malonne"])
def test_address_choose_section_when_the_post_name_does_not_decide(
    ix: lookup.Index, post_name: str | None
) -> None:
    found = lookup.resolve_address(ix, "92094", "5020", post_name)
    assert found["status"] == "choose_section"
    assert keys(found) == ["champion", "flawinne"]


def test_address_commune_name_never_picks_the_homonymous_section(ix: lookup.Index) -> None:
    """BeST's Flemish postal name is often the commune: "Baarle-Hertog" may be Zondereigen."""
    found = lookup.resolve_address(ix, "13002", "2387", "Baarle-Hertog")
    assert found["status"] == "choose_section"
    assert lookup.resolve_address(ix, "13002", "2387", "Zondereigen")["result"]["gas"] == {
        "status": "designated",
        "operator": "fluvius-kempen",
    }


def test_address_single_candidate_is_ok_whatever_the_post_name(ix: lookup.Index) -> None:
    found = lookup.resolve_address(ix, "92094", "5003", "Namur")
    assert found["result"]["section"]["section_key"] == "saint-marc"


def test_address_without_postcode_uses_every_section(ix: lookup.Index) -> None:
    assert lookup.resolve_address(ix, "92094", None, "Saint-Marc")["status"] == "ok"
    found = lookup.resolve_address(ix, "92094", "", "")
    assert keys(found) == [
        "champion",
        "flawinne",
        "gelbressee",
        "marche-les-dames",
        "namur-centre",
        "saint-marc",
    ]


# --- vectors --------------------------------------------------------------------------------


def vector(**values: str) -> dict[str, str]:
    row = {column: "" for column in schema.VECTORS_HEADER}
    row.update(name="t", kind="postcode")
    row.update(values)
    return row


def test_mini_vectors_pass(ix: lookup.Index) -> None:
    assert lookup.run_vectors(ix, lookup.read_vectors(MINI / "vectors.csv")) == []


def test_vector_star_skips_and_empty_means_empty(ix: lookup.Index) -> None:
    base = {"postcode": "1300", "expect_status": "ok", "expect_key": "25112", "expect_elec": "rew"}
    assert lookup.check_vector(ix, vector(**base, expect_gas_status="*", expect_gas="*")) == []
    problems = lookup.check_vector(ix, vector(**base))
    assert problems == [
        "t: gas_status expected '', got 'designated'",
        "t: gas expected '', got 'ores'",
    ]


def test_vector_key_and_flags_are_sets(ix: lookup.Index) -> None:
    row = vector(
        postcode="5020",
        section_key="flawinne",
        expect_status="ok",
        expect_key="92094/flawinne",
        expect_elec="aieg",
        expect_gas_status="designated",
        expect_gas="ores",
        expect_flags="to_confirm|transition|operator_differs",
    )
    assert lookup.check_vector(ix, row) == []
    row["expect_flags"] = "transition|to_confirm"
    assert lookup.check_vector(ix, row) == [
        "t: flags expected 'transition|to_confirm', got 'transition|operator_differs|to_confirm'"
    ]
    choose = vector(postcode="5020", expect_status="choose_section", expect_key="flawinne|champion")
    assert lookup.check_vector(ix, choose) == []


def test_ean_vector_flags(ix: lookup.Index) -> None:
    row = vector(
        kind="ean",
        ean="541448200000000001",
        expect_status="format_ok",
        expect_flags="belgian_prefix",
    )
    assert lookup.check_vector(ix, row) == []


# --- published file and CLI -----------------------------------------------------------------


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    build.write_outputs(out, outcome().files)
    return out


def test_load_index_reads_the_published_file(dist: Path, ix: lookup.Index) -> None:
    loaded = lookup.load_index(dist / "dso_lookup.csv")
    assert loaded == ix


def test_cli_postcode(dist: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert lookup.main(["--dist", str(dist), "postcode", "5020", "--section", "flawinne"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["result"]["elec"]["operator"] == "aieg"


def test_cli_address_and_ean(dist: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        lookup.main(
            [
                "--dist",
                str(dist),
                "address",
                "13002",
                "--postcode",
                "2387",
                "--post-name",
                "Zondereigen",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["result"]["section"]["section_key"] == "zondereigen"
    assert lookup.main(["ean", "541448200000000008"]) == 0
    assert json.loads(capsys.readouterr().out)["gs1_check"] is True


def test_cli_vectors(dist: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert lookup.main(["--dist", str(dist), "vectors"]) == 0
    assert "66/66 vectors pass" in capsys.readouterr().out
    failing = tmp_path / "vectors.csv"
    failing.write_bytes(
        (dist / "vectors.csv")
        .read_bytes()
        .replace(b"bru-1000,postcode,1000,,,,,ok,21004", b"bru-1000,postcode,1000,,,,,ok,21005")
    )
    assert lookup.main(["--dist", str(dist), "vectors", str(failing)]) == 1
    assert "bru-1000: key expected '21005', got '21004'" in capsys.readouterr().out


def test_cli_missing_dist(tmp_path: Path) -> None:
    assert lookup.main(["--dist", str(tmp_path), "postcode", "1000"]) == 2
