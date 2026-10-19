"""operators.csv against the app: names identical to crm-frontend GRD_OPTIONS, the spec's ids."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

import csvio
import lookup
import schema
from helpers import MINI, ROOT

# crm-frontend src/app/shared/constants/grd.ts, GRD_OPTIONS names as of 2026-10-12, in order.
GRD_OPTIONS = (
    "ORES",
    "RESA",
    "AIEG",
    "AIESH",
    "REW",
    "Sibelga",
    "Fluvius Antwerpen",
    "Fluvius Halle-Vilvoorde",
    "Fluvius Imewo",
    "Fluvius Kempen",
    "Fluvius Limburg",
    "Fluvius Midden-Vlaanderen",
    "Fluvius West",
    "Fluvius Zenne-Dijle",
)
# Spec §6.2: stable identifiers, never renamed.
SPEC_IDS = {
    "aieg", "aiesh", "ores", "resa", "rew", "sibelga",
    "fluvius-antwerpen", "fluvius-halle-vilvoorde", "fluvius-imewo", "fluvius-kempen",
    "fluvius-limburg", "fluvius-midden-vlaanderen", "fluvius-west", "fluvius-zenne-dijle",
    "enexis", "elia",
}  # fmt: skip


def monorepo() -> Path:
    return Path(os.environ.get("OPTIMCE_MONOREPO", ROOT.parent / "monorepo"))


@pytest.fixture(scope="module")
def operators() -> list[dict[str, str]]:
    return csvio.read_csv(ROOT / "data" / "operators.csv", schema.OPERATORS_HEADER)


def test_ids_are_the_spec_ids(operators: list[dict[str, str]]) -> None:
    assert {row["id"] for row in operators} == SPEC_IDS


def test_distribution_operators_follow_grd_options(operators: list[dict[str, str]]) -> None:
    assert tuple(row["name"] for row in operators if row["kind"] == "grd") == GRD_OPTIONS
    assert all(
        row["lookup"] == "true" and row["elec"] == "true"
        for row in operators
        if row["kind"] == "grd"
    )


def test_elia_and_enexis(operators: list[dict[str, str]]) -> None:
    by_id = {row["id"]: row for row in operators}
    elia, enexis = by_id["elia"], by_id["enexis"]
    assert (elia["name"], elia["kind"], elia["region"], elia["regulator"]) == (
        "Elia",
        "grtl",
        "WAL",
        "BE-WAL-CWAPE",
    )
    assert (elia["elec"], elia["gas"], elia["lookup"]) == ("true", "false", "false")
    assert (enexis["name"], enexis["kind"], enexis["region"]) == ("Enexis", "gas_foreign", "VLA")
    assert (enexis["elec"], enexis["gas"], enexis["lookup"]) == ("false", "true", "true")
    assert [row["id"] for row in operators][-2:] == ["enexis", "elia"]


def test_fixture_operators_are_the_real_ones() -> None:
    assert (MINI / "operators.csv").read_bytes() == (ROOT / "data" / "operators.csv").read_bytes()


def test_regulators_are_hard_coded() -> None:
    assert lookup.REGION_REGULATOR == {
        "BRU": "BE-BRU-BRUGEL",
        "VLA": "BE-VLA-VREG",
        "WAL": "BE-WAL-CWAPE",
    }


def test_regulators_match_the_monorepo_reference() -> None:
    path = monorepo() / "reference" / "regulators.json"
    if not path.is_file():
        pytest.skip(f"{path} not found (set OPTIMCE_MONOREPO)")
    codes = {entry["code"] for entry in json.loads(path.read_text(encoding="utf-8"))}
    assert codes == set(lookup.REGION_REGULATOR.values())


def test_grd_options_match_the_monorepo_frontend(operators: list[dict[str, str]]) -> None:
    path = monorepo() / "crm-frontend" / "src" / "app" / "shared" / "constants" / "grd.ts"
    if not path.is_file():
        pytest.skip(f"{path} not found (set OPTIMCE_MONOREPO)")
    block = re.search(
        r"GRD_OPTIONS[^=]*=\s*\[(.*?)\];", path.read_text(encoding="utf-8"), re.DOTALL
    )
    assert block is not None, "GRD_OPTIONS not found in grd.ts"
    assert tuple(re.findall(r"name:\s*'([^']+)'", block.group(1))) == GRD_OPTIONS
    ids = re.findall(r"id:\s*'([^']+)'", block.group(1))
    if ids:  # lot E2 adds the stable ids to GRD_OPTIONS
        assert ids == [row["id"] for row in operators if row["kind"] == "grd"]
