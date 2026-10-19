"""tests/vectors.csv: well formed always; passing on the real data once data/ is filled."""

from __future__ import annotations

from pathlib import Path

import pytest

import csvio
import lookup
import schema
import validate
from helpers import MINI, ROOT, outcome

REAL = ROOT / "tests" / "vectors.csv"


def has_rows(name: str) -> bool:
    return bool((ROOT / "data" / name).read_bytes().split(b"\n", 1)[1].strip())


def has_real_data() -> bool:
    """The geography (communes, postcodes) is acquired before the attributions are curated."""
    return has_rows("communes.csv")


def has_attributions() -> bool:
    return has_rows("assignments.csv") or has_rows("sections.csv")


def postcode_pairs(data_dir: Path) -> set[tuple[str, str]]:
    rows = csvio.read_csv(data_dir / "postcodes.csv", schema.POSTCODES_HEADER)
    return {(row["postcode"], row["ins"]) for row in rows}


def pair_problems(vectors: list[dict[str, str]], pairs: set[tuple[str, str]]) -> list[str]:
    """Vectors whose commune is not one of their postcode's (Statbel pairs).

    The address route falls back to every row of the INS when the postcode is not one of
    its own, so an address vector with a wrong nis_code passes the lookup silently: this
    check catches it. Vectors named `*-postcode-of-another-commune` test that fallback.
    """
    problems = []
    for vector in vectors:
        postcode = lookup.normalize_postcode(vector["postcode"])
        status, key = vector["expect_status"], vector["expect_key"]
        if vector["kind"] == "ean" or postcode is None or "another-commune" in vector["name"]:
            continue
        if vector["kind"] == "address" and status != "not_found":
            inses = {vector["ins"]}
        elif status == "ok" and key != lookup.ANY:
            inses = {key.split("/")[0]}
        elif status == "choose_commune":
            inses = set(schema.split_list(key))
        else:
            continue
        problems += [
            f"{vector['name']}: {postcode} is not a postcode of {ins}"
            for ins in sorted(inses)
            if (postcode, ins) not in pairs
        ]
    return problems


def test_mini_vectors_name_the_communes_of_their_postcodes() -> None:
    assert pair_problems(lookup.read_vectors(MINI / "vectors.csv"), postcode_pairs(MINI)) == []


def test_pair_check_catches_a_wrong_nis_code_that_the_lookup_lets_through() -> None:
    """The Mont-de-l'Enclus case: nis 57096 (Mouscron) with postcode 7750 still gave ok."""
    vector = {
        **next(
            v for v in lookup.read_vectors(MINI / "vectors.csv") if v["name"] == "addr-ixelles-1050"
        ),
        "name": "addr-etterbeek-1050",
        "ins": "21005",
        "expect_key": "21005",
    }
    index = lookup.build_index(outcome().build.tables["dso_lookup.csv"])
    assert lookup.run_vectors(index, [vector]) == []
    assert pair_problems([vector], postcode_pairs(MINI)) == [
        "addr-etterbeek-1050: 1050 is not a postcode of 21005"
    ]


@pytest.mark.parametrize("path", [REAL, MINI / "vectors.csv"], ids=["real", "mini"])
def test_vectors_are_well_formed(path: Path) -> None:
    rows = lookup.read_vectors(path)
    assert validate.vector_problems(rows) == []
    kinds = {row["kind"] for row in rows}
    assert kinds == set(schema.VECTOR_KINDS)


def test_mini_vectors_cover_every_status() -> None:
    rows = lookup.read_vectors(MINI / "vectors.csv")
    statuses = {(row["kind"], row["expect_status"]) for row in rows}
    assert {("postcode", status) for status in schema.LOOKUP_STATUSES} <= statuses
    assert {("address", "ok"), ("address", "choose_section"), ("address", "not_found")} <= statuses
    assert {("ean", "format_ok"), ("ean", "format_invalid")} <= statuses
    assert any(row["name"].startswith(schema.TO_CONFIRM_VECTOR_PREFIX) for row in rows)
    assert any(lookup.ANY in row.values() for row in rows)


def test_real_vectors_include_the_cross_check_cases() -> None:
    rows = {row["name"]: row for row in lookup.read_vectors(REAL)}
    assert rows["edge-1300-ins-99999-ignored"]["expect_status"] == "ok"
    assert rows["baarle-2387-ins-21004-ignored"]["expect_status"] == "choose_section"
    assert rows["tc-namur-5020-ins-21004-ignored"]["expect_status"] == "ok"
    assert rows["edge-em-space-5020"]["expect_status"] == "not_found"
    assert rows["addr-baarle-commune-name"]["expect_status"] == "choose_section"
    assert {
        rows[f"pajottegem-{postcode}"]["expect_key"] for postcode in ("1570", "1540", "1755")
    } == {"23106"}


@pytest.mark.skipif(not has_real_data(), reason="data/communes.csv has no rows yet (curation wave)")
def test_real_vectors_name_statbel_pairs() -> None:
    assert pair_problems(lookup.read_vectors(REAL), postcode_pairs(ROOT / "data")) == []


@pytest.mark.skipif(
    not has_attributions(), reason="data/assignments.csv has no rows yet (curation wave)"
)
def test_real_vectors_pass_on_the_real_data() -> None:
    result = outcome(ROOT / "data", fixture=False, vectors=REAL)
    index = lookup.build_index(result.build.tables["dso_lookup.csv"])
    assert lookup.run_vectors(index, lookup.read_vectors(REAL)) == []
