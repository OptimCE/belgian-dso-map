"""validate.py: the mini fixture passes, and one mutation per rule fails it."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest

import build
import csvio
import dates
import powerbi
import schema
import validate
from helpers import MINI, context, edit_csv, error_rules, outcome, row_of, warning_rules

Row = dict[str, str]

# REFNIS `Langue` of a commune of each region (schema.LANGUE_REGION, one value each).
LANGUE = {"BRU": "FN", "VLA": "N", "WAL": "F"}


def mutate(path: Path, **match_and_values: dict[str, str]) -> None:
    """mutate(file, where={...}, set={...}): update the single matching row."""
    edit_csv(
        path, lambda rows: row_of(rows, **match_and_values["where"]).update(match_and_values["set"])
    )


def messages(result: validate.Outcome, rule: str) -> list[str]:
    return [finding.message for finding in result.findings.errors if finding.rule == rule]


def strict(data_dir: Path) -> validate.Outcome:
    """Validate a copy of the mini fixture outside fixture mode (its curation/ in use)."""
    ctx = dataclasses.replace(context(data_dir), fixture=False)
    return validate.build_and_check(
        ctx, draft=True, release=False, ignore_acceptance=True, as_of=ctx.date
    )


def write_extracts(data_dir: Path) -> Path:
    """curation/derived/ extracts that agree with the data: REFNIS communes, Statbel pairs."""
    derived = data_dir / "curation" / "derived"
    derived.mkdir()
    communes = csvio.read_csv(data_dir / "communes.csv", schema.COMMUNES_HEADER)
    csvio.write_csv(
        derived / "statbel_refnis_2025_communes.csv",
        schema.DERIVED_COMMUNES_HEADER,
        [{**commune, "langue": LANGUE[commune["region"]]} for commune in communes],
    )
    shutil.copyfile(data_dir / "postcodes.csv", derived / "statbel_postcodes_2025.csv")
    return derived


def test_mini_fixture_passes_with_one_pending_acceptance() -> None:
    result = outcome()
    assert result.findings.errors == []
    assert result.findings.warnings == []
    assert [finding.message for finding in result.findings.pending] == [
        "note namur-aieg-sections (to_confirm on 92094/flawinne): PENDING acceptance by Eric"
    ]


# --- rule 1 ---------------------------------------------------------------------------------


def test_rule1_region_must_follow_the_ins(mini_copy: Path) -> None:
    mutate(mini_copy / "communes.csv", where={"ins": "21009"}, set={"region": "WAL"})
    assert "rule 1" in error_rules(outcome(mini_copy))


def test_rule1_province_must_follow_the_ins(mini_copy: Path) -> None:
    mutate(mini_copy / "communes.csv", where={"ins": "25112"}, set={"province": "BE-WHT"})
    assert messages(outcome(mini_copy), "rule 1") == [
        "25112: region/province WAL/BE-WHT, the INS implies WAL/BE-WBR"
    ]


def test_rule1_national_count_outside_fixture_mode() -> None:
    result = outcome(fixture=False, vectors=MINI / "vectors.csv")
    messages = [finding.message for finding in result.findings.errors if finding.rule == "rule 1"]
    assert any("expected 565" in message for message in messages)


def test_strict_mode_with_extracts_that_agree(mini_copy: Path) -> None:
    write_extracts(mini_copy)
    result = strict(mini_copy)
    rule1 = messages(result, "rule 1")
    assert len(rule1) == 1 and "expected 565" in rule1[0], rule1
    assert messages(result, "rule 5") == [
        "12 (postcode, INS) pairs, expected 1152",
        "postcodes shared by several INS: ['1040', '1050'], expected ['1040', '1050', '1804']",
    ]


def test_rule1_ins_set_equals_refnis(mini_copy: Path) -> None:
    derived = write_extracts(mini_copy)
    edit_csv(
        derived / "statbel_refnis_2025_communes.csv",
        lambda rows: [{**row, "ins": "21001"} if row["ins"] == "21005" else row for row in rows],
    )
    assert "INS differ from REFNIS 2025: data only ['21005'], REFNIS only ['21001']" in messages(
        strict(mini_copy), "rule 1"
    )


def test_rule1_region_follows_the_refnis_langue(mini_copy: Path) -> None:
    derived = write_extracts(mini_copy)
    mutate(
        derived / "statbel_refnis_2025_communes.csv", where={"ins": "21004"}, set={"langue": "N"}
    )
    assert "21004: region BRU but REFNIS Langue 'N'" in messages(strict(mini_copy), "rule 1")


def test_rule5_pairs_equal_statbel(mini_copy: Path) -> None:
    derived = write_extracts(mini_copy)
    edit_csv(
        derived / "statbel_postcodes_2025.csv",
        lambda rows: [row for row in rows if row["postcode"] != "1301"],
    )
    assert "postcodes.csv differs from curation/derived/statbel_postcodes_2025.csv" in messages(
        strict(mini_copy), "rule 5"
    )


def test_missing_extracts_are_errors_outside_fixture_mode(mini_copy: Path) -> None:
    """Deleting curation/derived/ must not turn the equality checks of rules 1 and 5 off."""
    result = strict(mini_copy)
    assert (
        "curation/derived/statbel_refnis_2025_communes.csv missing: REFNIS equality not checked"
        in messages(result, "rule 1")
    )
    assert (
        "curation/derived/statbel_postcodes_2025.csv missing: Statbel pairs not checked"
        in messages(result, "rule 5")
    )
    assert "curation/derived/fluvius_1_23.csv missing: Flemish rows not cross-checked" in [
        finding.message for finding in result.findings.warnings
    ]


# --- rule 2 ---------------------------------------------------------------------------------


def test_rule2_gas_none_needs_an_r_source(mini_copy: Path) -> None:
    mutate(
        mini_copy / "sections.csv",
        where={"section_key": "zondereigen"},
        set={"gas_status": "none", "gas_operator": "", "source_ids": "fluvius-1-23"},
    )
    messages = [finding.message for finding in outcome(mini_copy).findings.errors]
    assert "13002/zondereigen: gas none must cite an R source showing the absence" in messages


def test_rule2_designated_gas_needs_an_operator(mini_copy: Path) -> None:
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set={"gas_operator": ""})
    assert "rule 2" in error_rules(outcome(mini_copy))


def test_rule2_gas_none_has_no_operator(mini_copy: Path) -> None:
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set={"gas_status": "none"})
    assert "25112: gas none with a gas_operator" in messages(outcome(mini_copy), "rule 2")


def test_rule2_every_commune_has_an_attribution(mini_copy: Path) -> None:
    edit_csv(
        mini_copy / "assignments.csv", lambda rows: [row for row in rows if row["ins"] != "21005"]
    )
    messages = [
        finding.message
        for finding in outcome(mini_copy).findings.errors
        if finding.rule == "rule 2"
    ]
    assert messages == ["21005 Etterbeek: no electricity operator"]


# --- rule 3 ---------------------------------------------------------------------------------


def test_rule3_needs_an_independent_second_source(mini_copy: Path) -> None:
    mutate(
        mini_copy / "sections.csv",
        where={"section_key": "zondereigen"},
        set={"source_ids": "vreg-aanwijzing"},
    )
    messages = [finding.message for finding in outcome(mini_copy).findings.errors]
    assert (
        "13002/zondereigen: one R plus one M/C source of another publisher, or to_confirm"
        in messages
    )


def test_rule3_same_publisher_is_not_independent(mini_copy: Path) -> None:
    mutate(
        mini_copy / "assignments.csv",
        where={"ins": "25112"},
        set={"source_ids": "cwape-grd-gaz|cwape-power-bi"},
    )
    assert "rule 3" in error_rules(outcome(mini_copy))


def test_rule3_to_confirm_is_the_way_out(mini_copy: Path) -> None:
    mutate(
        mini_copy / "sections.csv",
        where={"section_key": "zondereigen"},
        set={
            "source_ids": "vreg-aanwijzing",
            "flags": "to_confirm",
            "note_key": "baarle-hertog-enclaves",
        },
    )
    edit_csv(
        mini_copy / "vectors.csv",
        lambda rows: [row for row in rows if "zondereigen" not in row["name"]],
    )
    assert "rule 3" not in error_rules(outcome(mini_copy))


def test_rule3_needs_an_r_source(mini_copy: Path) -> None:
    mutate(mini_copy / "assignments.csv", where={"ins": "21004"}, set={"source_ids": ""})
    assert "21004: no R source" in [f.message for f in outcome(mini_copy).findings.errors]


# --- rule 4 ---------------------------------------------------------------------------------


def test_rule4_unaccepted_note_fails_unless_ignored() -> None:
    assert error_rules(outcome(ignore_acceptance=False)) == {"rule 4"}


def accepted(notes: list[Row], **values: str) -> list[Row]:
    """Notes with acceptance values IN MEMORY: no notes.csv is ever written with them."""
    return [{**note, **values} if note["key"] == "namur-aieg-sections" else note for note in notes]


def check_with_notes(notes: list[Row], *, release: bool = False) -> validate.Findings:
    ctx = context(release=release)
    ctx = dataclasses.replace(ctx, dataset=dataclasses.replace(ctx.dataset, notes=notes))
    return validate.build_and_check(
        ctx, draft=not release, release=release, ignore_acceptance=False, as_of=ctx.date
    ).findings


def test_rule4_accepted_note_passes() -> None:
    notes = accepted(context().dataset.notes, accepted_by="Reviewer", accepted_on="2026-10-12")
    assert check_with_notes(notes).errors == []


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"accepted_by": "Reviewer"}, "go together"),
        ({"accepted_by": "Reviewer", "accepted_on": "12/10/2026"}, "not a date"),
        ({"accepted_by": "Reviewer", "accepted_on": "2026-10-13"}, "after the version date"),
    ],
)
def test_rule4_acceptance_must_be_complete_and_dated(values: dict[str, str], message: str) -> None:
    notes = accepted(context().dataset.notes, **values)
    assert any(message in finding.message for finding in check_with_notes(notes).errors)


def test_rule4_release_needs_every_note_accepted_in_four_languages() -> None:
    notes = accepted(context().dataset.notes, accepted_by="Reviewer", accepted_on="2026-10-12")
    findings = check_with_notes(notes, release=True)
    assert {f.message.split(" (")[0] for f in findings.errors if f.rule == "rule 4"} == {
        "note baarle-hertog-enclaves",
        "note dataset-vla-designations-2026",
    }
    notes = [{**note, "en": ""} if note["key"] == "namur-aieg-sections" else note for note in notes]
    assert any(
        f.rule == "notes" and "missing en" in f.message
        for f in check_with_notes(notes, release=True).errors
    )


def test_rule4_to_confirm_needs_a_note(mini_copy: Path) -> None:
    mutate(mini_copy / "sections.csv", where={"section_key": "flawinne"}, set={"note_key": ""})
    assert "92094/flawinne: to_confirm without a note_key" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


# --- rule 5 ---------------------------------------------------------------------------------


def test_rule5_section_postcode_must_be_a_postcode_of_the_ins(mini_copy: Path) -> None:
    mutate(
        mini_copy / "sections.csv",
        where={"section_key": "champion"},
        set={"postcodes": "5020|5021"},
    )
    assert "rule 5" in error_rules(outcome(mini_copy))


def test_rule5_every_pair_of_a_sectioned_ins_is_covered(mini_copy: Path) -> None:
    edit_csv(
        mini_copy / "postcodes.csv",
        lambda rows: sorted(
            [*rows, {"postcode": "5021", "ins": "92094"}],
            key=lambda row: (row["postcode"], row["ins"]),
        ),
    )
    assert "92094: no section covers postcode 5021" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


def test_rule5_every_commune_has_a_postcode(mini_copy: Path) -> None:
    edit_csv(
        mini_copy / "postcodes.csv", lambda rows: [row for row in rows if row["ins"] != "21005"]
    )
    assert "21005 Etterbeek: no postcode" in [f.message for f in outcome(mini_copy).findings.errors]


def test_rule5_postcode_of_an_unknown_ins(mini_copy: Path) -> None:
    edit_csv(
        mini_copy / "postcodes.csv", lambda rows: [*rows, {"postcode": "9999", "ins": "99999"}]
    )
    assert "postcode 9999: unknown INS 99999" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


# --- rule 6 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"elec_operator": "nobody", "elec_designated": "nobody"}, "unknown operator 'nobody'"),
        ({"elec_operator": "elia", "elec_designated": "elia"}, "elia is a grtl"),
        (
            {"elec_operator": "sibelga", "elec_designated": "sibelga"},
            "sibelga is a BRU operator in WAL",
        ),
        ({"gas_operator": "aieg"}, "aieg does not operate gas"),
        ({"gas_status": "foreign", "gas_operator": "ores"}, "ores is a grd, expected gas_foreign"),
    ],
)
def test_rule6_operator_checks(mini_copy: Path, values: dict[str, str], message: str) -> None:
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set=values)
    messages = [f.message for f in outcome(mini_copy).findings.errors if f.rule == "rule 6"]
    assert any(message in m for m in messages), messages


def test_rule6_lookup_false_is_never_assigned(mini_copy: Path) -> None:
    mutate(mini_copy / "operators.csv", where={"id": "rew"}, set={"lookup": "false"})
    assert "25112: rew has lookup:false and is never assigned" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


def test_rule6_a_grtl_is_never_a_lookup_result(mini_copy: Path) -> None:
    mutate(mini_copy / "operators.csv", where={"id": "elia"}, set={"lookup": "true"})
    assert "rule 6" in error_rules(outcome(mini_copy))


def test_rule6_a_replaced_operator_is_never_assigned(mini_copy: Path) -> None:
    mutate(mini_copy / "operators.csv", where={"id": "aieg"}, set={"replaced_by": "ores"})
    assert "92094/flawinne: aieg was replaced by ores" in messages(outcome(mini_copy), "rule 6")


def test_rule6_checks_the_designated_operator_too(mini_copy: Path) -> None:
    mutate(
        mini_copy / "assignments.csv",
        where={"ins": "25112"},
        set={"elec_designated": "sibelga", "flags": "operator_differs"},
    )
    assert messages(outcome(mini_copy), "rule 6") == ["25112: sibelga is a BRU operator in WAL"]


# --- rule 7 ---------------------------------------------------------------------------------


def test_rule7_all_or_nothing_sections(mini_copy: Path) -> None:
    extra = {
        "ins": "92094",
        "elec_operator": "ores",
        "elec_designated": "ores",
        "gas_status": "designated",
        "gas_operator": "ores",
        "flags": "",
        "note_key": "",
        "source_ids": "cwape-avis-ores-2022|odwb-ores-elec",
        "valid_from": "",
    }
    edit_csv(mini_copy / "assignments.csv", lambda rows: [*rows, extra])
    assert "92094: in assignments.csv and sections.csv (all or nothing)" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


def test_rule7_attribution_of_an_unknown_ins(mini_copy: Path) -> None:
    extra = {
        "ins": "21001",
        "elec_operator": "sibelga",
        "elec_designated": "sibelga",
        "gas_status": "designated",
        "gas_operator": "sibelga",
        "flags": "",
        "note_key": "",
        "source_ids": "brugel-grd",
        "valid_from": "",
    }
    edit_csv(mini_copy / "assignments.csv", lambda rows: [extra, *rows])
    assert messages(outcome(mini_copy), "rule 7") == ["21001: unknown INS"]


def test_rule7_duplicate_section_key(mini_copy: Path) -> None:
    edit_csv(mini_copy / "sections.csv", lambda rows: [*rows[:3], rows[2], *rows[3:]])
    assert "sections.csv: duplicate key 92094|champion" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


# --- rule 8 ---------------------------------------------------------------------------------


def test_rule8_vectors_must_pass(mini_copy: Path) -> None:
    mutate(mini_copy / "vectors.csv", where={"name": "wavre-1300"}, set={"expect_elec": "ores"})
    assert "wavre-1300: elec expected 'ores', got 'rew'" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"kind": "street"}, "kind 'street'"),
        ({"expect_status": "format_ok"}, "expect_status 'format_ok'"),
        ({"ean": "541448200000000008"}, "leaves post_name, ean empty"),
        ({"expect_flags": "gs1_ok"}, "expect_flags 'gs1_ok'"),
        ({"name": "Wavre 1300"}, "unique lowercase slugs"),
    ],
)
def test_rule8_vector_format(mini_copy: Path, values: dict[str, str], message: str) -> None:
    mutate(mini_copy / "vectors.csv", where={"name": "wavre-1300"}, set=values)
    messages = [f.message for f in outcome(mini_copy).findings.errors if f.rule == "rule 8"]
    assert any(message in m for m in messages), messages


@pytest.mark.parametrize(
    ("name", "values", "message"),
    [
        ("wavre-1300", {"expect_gas_status": "maybe"}, "expect_gas_status 'maybe'"),
        (
            "ean-dev-008-gs1-true",
            {"expect_key": "25112"},
            "an ean vector only asserts status, elec and flags",
        ),
    ],
)
def test_rule8_vector_expectations(
    mini_copy: Path, name: str, values: dict[str, str], message: str
) -> None:
    mutate(mini_copy / "vectors.csv", where={"name": name}, set=values)
    assert f"vector {name}: {message}" in messages(outcome(mini_copy), "rule 8")


# --- rule 8bis ------------------------------------------------------------------------------


def test_rule8bis_two_builds_must_be_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = iter(range(100))
    real = build.make_build

    def unstable(*args: object, **kwargs: object) -> build.Build:
        made = real(*args, **kwargs)  # type: ignore[arg-type]
        made.files["release.json"] += str(next(calls)).encode()
        return made

    monkeypatch.setattr(build, "make_build", unstable)
    assert "release.json: two builds of the same inputs differ" in [
        f.message for f in outcome().findings.errors
    ]


def test_rule8bis_unchanged_rows_keep_their_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "a"
    assert build.main(["--fixture", "--draft", "--out", str(first)]) == 0
    real = dates.stamp

    def careless(*args: object, **kwargs: object) -> tuple[list[Row], list[dates.Change]]:
        rows, changes = real(*args, **kwargs)  # type: ignore[arg-type]
        return [{**row, "changed_at": kwargs["version_date"]} for row in rows], changes  # type: ignore[misc]

    monkeypatch.setattr(dates, "stamp", careless)
    result = outcome(previous=first, version="2026.11.0", date="2026-11-02")
    assert any("dates moved" in f.message for f in result.findings.errors if f.rule == "rule 8bis")


def test_rule8bis_no_date_after_the_version_date(monkeypatch: pytest.MonkeyPatch) -> None:
    real = dates.stamp

    def ahead(*args: object, **kwargs: object) -> tuple[list[Row], list[dates.Change]]:
        rows, changes = real(*args, **kwargs)  # type: ignore[arg-type]
        return [{**row, "changed_at": "2026-10-13"} for row in rows], changes

    monkeypatch.setattr(dates, "stamp", ahead)
    assert "dso_lookup.csv 1000|21004|: first_seen <= changed_at <= 2026-10-12 broken" in (
        messages(outcome(), "rule 8bis")
    )


# --- rule 9 ---------------------------------------------------------------------------------


def test_rule9_old_source_is_a_warning(mini_copy: Path) -> None:
    mutate(
        mini_copy / "sources.csv",
        where={"id": "cwape-power-bi"},
        set={"retrieved_at": "2025-10-11"},
    )
    result = outcome(mini_copy)
    assert error_rules(result) == set()
    assert "rule 9" in warning_rules(result)


def test_rule9_as_of_moves_the_age_check() -> None:
    assert "rule 9" in warning_rules(outcome(as_of="2027-10-13"))
    assert "rule 9" not in warning_rules(outcome())


def test_rule9_source_after_the_version_date_is_an_error(mini_copy: Path) -> None:
    mutate(
        mini_copy / "sources.csv",
        where={"id": "cwape-power-bi"},
        set={"retrieved_at": "2026-10-13"},
    )
    assert "rule 9" in error_rules(outcome(mini_copy))


# --- rule 10 --------------------------------------------------------------------------------


def test_rule10_counts_are_warnings_outside_fixture_mode() -> None:
    assert "rule 10" in warning_rules(outcome(fixture=False, vectors=MINI / "vectors.csv"))
    assert "rule 10" not in warning_rules(outcome())


# --- consistency, references, formats, curation ---------------------------------------------


@pytest.mark.parametrize(
    ("file", "where", "values", "rule"),
    [
        (
            "sections.csv",
            {"section_key": "flawinne"},
            {"flags": "transition|to_confirm"},
            "consistency",
        ),
        ("sections.csv", {"section_key": "champion"}, {"flags": "operator_differs"}, "consistency"),
        ("sections.csv", {"section_key": "zondereigen"}, {"flags": "propane_note"}, "consistency"),
        ("assignments.csv", {"ins": "25112"}, {"flags": "transition"}, "consistency"),
        ("assignments.csv", {"ins": "25112"}, {"valid_from": "2026-12-01"}, "consistency"),
        ("assignments.csv", {"ins": "25112"}, {"note_key": "nowhere"}, "references"),
        (
            "assignments.csv",
            {"ins": "25112"},
            {"source_ids": "agw-rew-wavre|nowhere|odwb-ores-gas"},
            "references",
        ),
        ("assignments.csv", {"ins": "25112"}, {"flags": "to_confirm|transition"}, "format"),
        ("assignments.csv", {"ins": "25112"}, {"flags": "maybe"}, "format"),
        ("sections.csv", {"section_key": "champion"}, {"postcodes": "5020|5020"}, "format"),
        ("communes.csv", {"ins": "21005"}, {"province": "BE-BRU"}, "format"),
        ("operators.csv", {"id": "rew"}, {"regulator": "BE-VLA-VREG"}, "format"),
        ("operators.csv", {"id": "rew"}, {"website": "http://www.rew.be"}, "format"),
        ("operators.csv", {"id": "rew"}, {"replaced_by": "rew"}, "format"),
        ("sources.csv", {"id": "brugel-grd"}, {"role": "Q"}, "format"),
        ("sources.csv", {"id": "brugel-grd"}, {"sha256": "ABC"}, "format"),
        (
            "notes.csv",
            {"key": "dataset-vla-designations-2026"},
            {"key": "dataset-flanders"},
            "format",
        ),
        ("notes.csv", {"key": "baarle-hertog-enclaves"}, {"fr": ""}, "notes"),
    ],
)
def test_one_mutation_one_error(
    mini_copy: Path, file: str, where: dict[str, str], values: dict[str, str], rule: str
) -> None:
    mutate(mini_copy / file, where=where, set=values)
    assert rule in error_rules(outcome(mini_copy))


@pytest.mark.parametrize(
    ("file", "where", "values", "message"),
    [
        (
            "operators.csv",
            {"id": "enexis"},
            {"gas": "false"},
            "operators.csv enexis: an operator carries electricity, gas or both",
        ),
        (
            "operators.csv",
            {"id": "rew"},
            {"name": "AIEG"},
            "operators.csv rew: duplicate id or name",
        ),
        (
            "operators.csv",
            {"id": "rew"},
            {"lookup": "yes"},
            "operators.csv rew: lookup must be true or false",
        ),
        (
            "operators.csv",
            {"id": "rew"},
            {"replaced_by": "nobody"},
            "operators.csv rew: replaced_by 'nobody' is not another operator",
        ),
        (
            "postcodes.csv",
            {"postcode": "1000"},
            {"postcode": "0999"},
            "postcodes.csv: postcode '0999' is not 4 digits",
        ),
        (
            "communes.csv",
            {"ins": "21009"},
            {"ins": "2100A"},
            "communes.csv: INS '2100A' is not 5 digits",
        ),
        (
            "communes.csv",
            {"ins": "21005"},
            {"nom_nl": ""},
            "communes.csv 21005: nom_fr and nom_nl are required",
        ),
        (
            "sources.csv",
            {"id": "brugel-grd"},
            {"url": "ftp://brugel.brussels/"},
            "sources.csv brugel-grd: url 'ftp://brugel.brussels/' is not an http(s) URL",
        ),
        (
            "sources.csv",
            {"id": "brugel-grd"},
            {"retrieved_at": "2026-13-01"},
            "sources.csv brugel-grd: retrieved_at '2026-13-01' is not a date",
        ),
        (
            "sections.csv",
            {"section_key": "champion"},
            {"section_key": "Champion"},
            "sections.csv 92094/Champion: section_key is not a lowercase slug",
        ),
        (
            "assignments.csv",
            {"ins": "25112"},
            {"valid_from": "2026-02-30"},
            "25112: valid_from '2026-02-30' is not a date",
        ),
        (
            "assignments.csv",
            {"ins": "25112"},
            {"source_ids": "agw-rew-wavre|agw-rew-wavre|odwb-ores-gas"},
            "25112: duplicate source id",
        ),
    ],
)
def test_one_mutation_one_message(
    mini_copy: Path, file: str, where: dict[str, str], values: dict[str, str], message: str
) -> None:
    mutate(mini_copy / file, where=where, set=values)
    assert message in [finding.message for finding in outcome(mini_copy).findings.errors]


def test_an_old_transition_is_a_warning(mini_copy: Path) -> None:
    mutate(
        mini_copy / "sections.csv",
        where={"section_key": "flawinne"},
        set={"valid_from": "2025-10-11"},
    )
    result = outcome(mini_copy)
    assert error_rules(result) == set()
    assert [f.message for f in result.findings.warnings] == [
        "92094/flawinne: transition since 2025-10-11, over a year: drop the flag?"
    ]


def test_files_must_stay_sorted(mini_copy: Path) -> None:
    edit_csv(mini_copy / "communes.csv", lambda rows: list(reversed(rows)))
    assert "communes.csv: rows are not sorted by ins" in [
        f.message for f in outcome(mini_copy).findings.errors
    ]


def test_operators_are_grouped_by_kind_then_region(mini_copy: Path) -> None:
    edit_csv(mini_copy / "operators.csv", lambda rows: [rows[-1], *rows[:-1]])
    assert "format" in error_rules(outcome(mini_copy))


def test_unused_sources_and_notes_are_warnings(mini_copy: Path) -> None:
    mutate(mini_copy / "sections.csv", where={"section_key": "baarle-hertog"}, set={"note_key": ""})
    result = outcome(mini_copy)
    assert error_rules(result) == set()
    assert [f.message for f in result.findings.warnings] == [
        "note baarle-hertog-enclaves is used by no row"
    ]


def test_worksheet_disagreement_is_a_cross_check_warning(mini_copy: Path) -> None:
    mutate(
        mini_copy / "curation" / "wal_designations.csv", where={"ins": "25112"}, set={"grd": "aieg"}
    )
    result = outcome(mini_copy)
    assert error_rules(result) == set()
    assert len(result.findings.crosscheck) == 1
    assert "designates aieg (elec) in 25112" in result.findings.crosscheck[0].message


def test_worksheet_with_an_unknown_source_is_an_error(mini_copy: Path) -> None:
    mutate(
        mini_copy / "curation" / "wal_designations.csv",
        where={"ins": "25112"},
        set={"source_id": "nowhere"},
    )
    assert "curation" in error_rules(outcome(mini_copy))


def test_worksheet_with_an_unknown_ins_is_an_error(mini_copy: Path) -> None:
    mutate(
        mini_copy / "curation" / "wal_designations.csv",
        where={"ins": "25112"},
        set={"ins": "99999"},
    )
    assert messages(outcome(mini_copy), "curation") == [
        "wal_designations.csv:3: unknown INS '99999'"
    ]


def test_spot_check_marked_as_not_matching_is_reported(mini_copy: Path) -> None:
    mutate(
        mini_copy / "curation" / "spot_checks.csv", where={"ins": "25112"}, set={"matches": "false"}
    )
    assert [f.message for f in outcome(mini_copy).findings.crosscheck] == [
        "spot_checks.csv:2: cwape-power-bi on 2026-10-11 shows rew (elec) in 25112 (matches=false)"
    ]


def test_spot_check_mismatch_is_reported(mini_copy: Path) -> None:
    mutate(
        mini_copy / "curation" / "spot_checks.csv",
        where={"ins": "25112"},
        set={"observed": "ores", "matches": "false"},
    )
    result = outcome(mini_copy)
    assert error_rules(result) == set()
    assert (
        "cwape-power-bi on 2026-10-11 shows ores (elec) in 25112"
        in result.findings.crosscheck[0].message
    )


def test_spot_check_tool_is_a_source(mini_copy: Path) -> None:
    mutate(
        mini_copy / "curation" / "spot_checks.csv",
        where={"ins": "25112"},
        set={"tool": "power-bi"},
    )
    assert "curation" in error_rules(outcome(mini_copy))


def test_fluvius_extract_disagreement_is_reported(mini_copy: Path) -> None:
    derived = mini_copy / "curation" / "derived"
    derived.mkdir()
    (derived / "fluvius_1_23.csv").write_bytes(
        b"postcode,community,ins,elec_id,gas_id,gastype\n"
        b"1000,Brussel,21004,fluvius-west,,H\n"
        b"2387,Baarle-Hertog,13002,fluvius-kempen,enexis,H\n"  # sectioned: checked by curation
    )
    result = outcome(mini_copy)
    assert error_rules(result) == set()
    assert [finding.message for finding in result.findings.crosscheck] == [
        "Fluvius 1000 Brussel: fluvius-west/none, data sibelga/sibelga"
    ]


def test_fluvius_disagreement_explained_by_valid_from(mini_copy: Path) -> None:
    derived = mini_copy / "curation" / "derived"
    derived.mkdir()
    (derived / "fluvius_1_23.csv").write_bytes(
        b"postcode,community,ins,elec_id,gas_id,gastype\n1000,Brussel,21004,fluvius-west,,H\n"
    )
    mutate(mini_copy / "assignments.csv", where={"ins": "21004"}, set={"valid_from": "2026-01-01"})
    assert [finding.message for finding in outcome(mini_copy).findings.crosscheck] == [
        "Fluvius 1000 Brussel: fluvius-west/none, data sibelga/sibelga "
        "(explained: valid_from 2026-01-01)"
    ]


# Synthetic counts: the rows of the real readings are never copied (CLAUDE.md).
POWERBI_HEADER = b"commune_label,ins,grd_label,grd_id,count\n"
POWERBI_ELEC = b"WAVRE,25112,REW,rew,3\nNAMUR,92094,ORES Namur,ores,5\n"
POWERBI_GAS = b"WAVRE,25112,ORES Brabant wallon,ores,2\nNAMUR,92094,ORES Namur,ores,4\n"
SUMMARY_HEADER = b"ins,section_key,vector,data,agrees,observed\n"


def write_powerbi(data_dir: Path, elec: bytes = POWERBI_ELEC, gas: bytes = POWERBI_GAS) -> Path:
    """The two full Power BI readings of the mini fixture's Walloon communes (sorted by
    INS), in curation/private/ (git-ignored in the real repository)."""
    private = data_dir / "curation" / powerbi.PRIVATE_DIR
    private.mkdir(exist_ok=True)
    (private / "cwape_powerbi_elec.csv").write_bytes(POWERBI_HEADER + elec)
    (private / "cwape_powerbi_gas.csv").write_bytes(POWERBI_HEADER + gas)
    return private


def refresh(data_dir: Path) -> validate.Outcome:
    """validate.py --refresh-powerbi-summary: the summary from the full readings."""
    ctx = context(data_dir)
    return validate.build_and_check(
        ctx, draft=True, release=False, ignore_acceptance=True, as_of=ctx.date, refresh_powerbi=True
    )


def summary_of(data_dir: Path) -> bytes:
    return (data_dir / "curation" / powerbi.SUMMARY_FILE).read_bytes()


@pytest.fixture(params=[True, False], ids=["with-readings", "summary-only"])
def full_readings(request: pytest.FixtureRequest) -> bool:
    """Validate with the full readings (Eric's checkout) or with the summary only (CI)."""
    return bool(request.param)


def checked(data_dir: Path, full_readings: bool) -> validate.Outcome:
    """Refresh the summary from the full readings, then validate with them, or without
    them as CI does: both must give the same findings."""
    refresh(data_dir)
    if not full_readings:
        shutil.rmtree(data_dir / "curation" / powerbi.PRIVATE_DIR)
    return outcome(data_dir)


def test_powerbi_readings_that_agree_add_nothing(mini_copy: Path, full_readings: bool) -> None:
    write_powerbi(mini_copy)
    result = checked(mini_copy, full_readings)
    assert result.findings.errors == []
    assert result.findings.warnings == []
    assert summary_of(mini_copy) == SUMMARY_HEADER + (
        b"25112,,elec,rew,true,\n25112,,gas,ores,true,\n"
        + b"".join(
            f"92094,{key},elec,ores,true,\n92094,{key},gas,ores,true,\n".encode()
            for key in (
                "champion",
                "flawinne",
                "gelbressee",
                "marche-les-dames",
                "namur-centre",
                "saint-marc",
            )
        )  # fmt: skip
    )


def test_powerbi_disagreement_is_reported(mini_copy: Path, full_readings: bool) -> None:
    write_powerbi(
        mini_copy,
        elec=b"WAVRE,25112,ORES Brabant wallon,ores,1\nWAVRE,25112,REW,rew,3\n"
        b"NAMUR,92094,ORES Namur,ores,5\n",
    )
    result = checked(mini_copy, full_readings)
    assert error_rules(result) == set()
    assert [finding.message for finding in result.findings.crosscheck] == [
        "CWaPE Power BI elec, 25112 Wavre: ORES Brabant wallon 1 + REW 3; data rew"
    ]
    assert b"25112,,elec,rew,false,ORES Brabant wallon 1 + REW 3\n" in summary_of(mini_copy)


def test_powerbi_disagreements_explained(mini_copy: Path, full_readings: bool) -> None:
    """A dated change, and a designated gas DSO that the map does not show."""
    write_powerbi(
        mini_copy,
        elec=b"WAVRE,25112,ORES Brabant wallon,ores,8\nNAMUR,92094,ORES Namur,ores,5\n",
        gas=b"NAMUR,92094,ORES Namur,ores,4\n",
    )
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set={"valid_from": "2026-01-01"})
    assert [
        finding.message for finding in checked(mini_copy, full_readings).findings.crosscheck
    ] == [
        "CWaPE Power BI elec, 25112 Wavre: ORES Brabant wallon 8; data rew "
        "(explained: valid_from 2026-01-01)",
        "CWaPE Power BI gas, 25112 Wavre: no GRD shown; data ores "
        "(explained: valid_from 2026-01-01, a designation does not guarantee a network)",
    ]


def write_aliases(data_dir: Path, *rows: tuple[str, str]) -> None:
    """curation/aliases.csv with (name_in_source, ins) rows."""
    csvio.write_csv(
        data_dir / "curation" / "aliases.csv",
        schema.ALIASES_HEADER,
        [{"name_in_source": name, "ins": ins, "reason": "test"} for name, ins in rows],
    )


def test_powerbi_section_with_its_own_label(mini_copy: Path, full_readings: bool) -> None:
    """Flawinne has its own label: only its rows apply to it (to_confirm explains them).

    The other sections of Namur have no label of their own: the commune's label applies.
    A label that is not a name of its INS needs an alias (like BERTOGNE -> 82039).
    """
    write_aliases(mini_copy, ("Flawinne", "92094"))
    write_powerbi(
        mini_copy,
        elec=b"WAVRE,25112,REW,rew,3\nFLAWINNE,92094,AIEG,aieg,1\nNAMUR,92094,ORES Namur,ores,5\n",
    )
    assert [
        finding.message for finding in checked(mini_copy, full_readings).findings.crosscheck
    ] == [
        "CWaPE Power BI elec, 92094/flawinne Namur: AIEG 1; data ores (explained: to_confirm)",
        "CWaPE Power BI gas, 92094/flawinne Namur: no GRD shown; data ores "
        "(explained: to_confirm, a designation does not guarantee a network)",
    ]


def test_report_is_the_same_with_or_without_the_full_readings(mini_copy: Path) -> None:
    """Every published file, REPORT.md included, comes out byte-identical in CI."""
    write_aliases(mini_copy, ("Flawinne", "92094"))
    write_powerbi(
        mini_copy,
        elec=b"WAVRE,25112,REW,rew,3\nFLAWINNE,92094,AIEG,aieg,1\nNAMUR,92094,ORES Namur,ores,5\n",
    )
    refresh(mini_copy)
    with_readings = outcome(mini_copy)
    shutil.rmtree(mini_copy / "curation" / powerbi.PRIVATE_DIR)
    without = outcome(mini_copy)
    assert with_readings.findings.crosscheck  # something to report
    assert with_readings.files == without.files


@pytest.mark.parametrize(
    "elec",
    [
        b"BAERLE-DUC,13002,Fluvius Kempen,fluvius-kempen,1\n",  # not a Walloon INS
        b"WAVRE,25112,Enexis,enexis,8\n",  # Enexis carries no electricity
        b"WAVRE,25112,Elia,elia,8\n",  # Elia is not a DSO
        b"WAVRE,25112,REW,nobody,8\n",  # not an operator
        b"WAVRE,25112,REW,rew,0\n",  # the count is positive
        b"WAVRE,25112,REW,rew,08\n",
    ],
)
def test_powerbi_reading_format(mini_copy: Path, elec: bytes) -> None:
    write_powerbi(mini_copy, elec=elec)
    assert messages(outcome(mini_copy), "curation") == [
        "cwape_powerbi_elec.csv:2: a Walloon INS, a commune label, a GRD label, "
        "the id of a DSO carrying elec and a positive count"
    ]


def test_a_malformed_reading_is_never_summarized(mini_copy: Path) -> None:
    write_powerbi(mini_copy, elec=b"WAVRE,25112,REW,rew,0\n")
    assert "curation" in error_rules(refresh(mini_copy))
    assert not (mini_copy / "curation" / powerbi.SUMMARY_FILE).exists()


@pytest.mark.parametrize(
    ("aliases", "elec", "message"),
    [
        # the label of another commune (like BEAUVECHAIN relabelled WAVRE)
        (
            (),
            b"WAVRE,25112,REW,rew,3\nWAVRE,92094,ORES Namur,ores,5\n",
            "cwape_powerbi_elec.csv:3: 'WAVRE' is not a name of 92094 (Namur) "
            "nor an alias of it in aliases.csv",
        ),
        # a section's label without an alias
        (
            (),
            b"WAVRE,25112,REW,rew,3\nFLAWINNE,92094,AIEG,aieg,1\n",
            "cwape_powerbi_elec.csv:3: 'FLAWINNE' is not a name of 92094 (Namur) "
            "nor an alias of it in aliases.csv",
        ),
        # an alias of another INS does not count
        (
            (("Flawinne", "25112"),),
            b"WAVRE,25112,REW,rew,3\nFLAWINNE,92094,AIEG,aieg,1\n",
            "cwape_powerbi_elec.csv:3: 'FLAWINNE' is not a name of 92094 (Namur) "
            "nor an alias of it in aliases.csv",
        ),
    ],
)
def test_powerbi_commune_label_must_name_its_ins(
    mini_copy: Path, aliases: tuple[tuple[str, str], ...], elec: bytes, message: str
) -> None:
    write_aliases(mini_copy, *aliases)
    write_powerbi(mini_copy, elec=elec)
    result = outcome(mini_copy)
    assert messages(result, "curation") == [message]
    assert result.findings.crosscheck == []  # a malformed reading is not compared


def test_powerbi_commune_label_by_any_name_or_alias(mini_copy: Path) -> None:
    """The name rule (case, accents, punctuation) on the FR, NL or DE name, or an alias."""
    write_aliases(mini_copy, ("Flawinne", "92094"))
    write_powerbi(
        mini_copy,
        elec=b"WAVRE,25112,REW,rew,3\nFLAWINNE,92094,AIEG,aieg,1\nNamen,92094,ORES Namur,ores,5\n",
        gas=b"WAVRE,25112,ORES Brabant wallon,ores,2\nn-a-m-u-r,92094,ORES Namur,ores,4\n",
    )
    assert messages(refresh(mini_copy), "curation") == []
    assert messages(outcome(mini_copy), "curation") == []


@pytest.mark.parametrize(
    ("elec", "message"),
    [
        # a RESA label kept as ores (like ATH relabelled RESA)
        (
            b"WAVRE,25112,REW,rew,3\nNAMUR,92094,RESA,ores,55\n",
            "cwape_powerbi_elec.csv:3: the GRD label 'RESA' is resa, not ores",
        ),
        # every "ORES ..." label is ores
        (
            b"WAVRE,25112,REW,rew,3\nNAMUR,92094,ORES Namur,aieg,55\n",
            "cwape_powerbi_elec.csv:3: the GRD label 'ORES Namur' is ores, not aieg",
        ),
        (
            b"WAVRE,25112,REW,ores,8\nNAMUR,92094,ORES Namur,ores,5\n",
            "cwape_powerbi_elec.csv:2: the GRD label 'REW' is rew, not ores",
        ),
    ],
)
def test_powerbi_grd_id_must_follow_its_label(mini_copy: Path, elec: bytes, message: str) -> None:
    write_powerbi(mini_copy, elec=elec)
    result = outcome(mini_copy)
    assert messages(result, "curation") == [message]
    assert result.findings.crosscheck == []


def test_powerbi_reading_must_be_sorted(mini_copy: Path) -> None:
    write_powerbi(mini_copy, elec=b"NAMUR,92094,ORES Namur,ores,5\nWAVRE,25112,REW,rew,3\n")
    assert "cwape_powerbi_elec.csv: rows are not sorted by ins, commune_label, grd_label" in [
        finding.message for finding in outcome(mini_copy).findings.errors
    ]


STALE_SUMMARY = (
    "curation/powerbi_checks.csv does not follow from the readings of curation/private/: "
    "run scripts/validate.py --refresh-powerbi-summary"
)


def test_the_summary_must_follow_the_full_readings(mini_copy: Path) -> None:
    """With the full readings present, a summary they do not give is an error; without
    them (CI), the committed summary is used as is."""
    write_powerbi(mini_copy)
    assert messages(outcome(mini_copy), "curation") == [STALE_SUMMARY]  # never refreshed
    refresh(mini_copy)
    assert messages(outcome(mini_copy), "curation") == []
    write_powerbi(mini_copy, elec=b"WAVRE,25112,ORES Brabant wallon,ores,8\n")  # a new reading
    assert messages(outcome(mini_copy), "curation") == [STALE_SUMMARY]
    shutil.rmtree(mini_copy / "curation" / powerbi.PRIVATE_DIR)
    result = outcome(mini_copy)
    assert result.findings.errors == []
    assert result.findings.crosscheck == []  # the committed summary: every row agreed


def test_refreshing_one_vector_keeps_the_other(mini_copy: Path) -> None:
    write_powerbi(mini_copy)
    refresh(mini_copy)
    both = summary_of(mini_copy)
    (mini_copy / "curation" / powerbi.PRIVATE_DIR / "cwape_powerbi_gas.csv").unlink()
    assert error_rules(refresh(mini_copy)) == set()
    assert summary_of(mini_copy) == both


def test_a_row_changed_since_the_summary_is_a_warning(mini_copy: Path) -> None:
    """Without the full readings, the summary cannot be refreshed: the comparison of a row
    whose value changed is dropped, with a warning (assemble.py no longer cites it)."""
    write_powerbi(mini_copy, gas=b"WAVRE,25112,RESA,resa,6\nNAMUR,92094,ORES Namur,ores,4\n")
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set={"gas_operator": "resa"})
    refresh(mini_copy)  # Wavre's gas compared as RESA (it agreed) ...
    shutil.rmtree(mini_copy / "curation" / powerbi.PRIVATE_DIR)
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set={"gas_operator": "ores"})
    result = outcome(mini_copy)  # ... then the row went back to ORES
    assert result.findings.errors == []
    assert result.findings.crosscheck == []
    assert [
        finding.message for finding in result.findings.warnings if "Power BI" in finding.message
    ] == [
        "CWaPE Power BI gas, 25112: the summary compared resa, the data now say ores: run "
        "scripts/validate.py --refresh-powerbi-summary (it needs the full readings of "
        "curation/private/)"
    ]


def test_a_summary_row_of_no_attribution_is_a_warning(mini_copy: Path) -> None:
    (mini_copy / "curation" / powerbi.SUMMARY_FILE).write_bytes(
        SUMMARY_HEADER + b"25112,,elec,rew,true,\n25112,old-section,elec,rew,true,\n"
    )
    result = outcome(mini_copy)
    assert result.findings.errors == []
    assert [finding.message for finding in result.findings.warnings] == [
        "powerbi_checks.csv:3: 25112/old-section is no longer a row of the data: run "
        "scripts/validate.py --refresh-powerbi-summary (it needs the full readings of "
        "curation/private/)"
    ]


@pytest.mark.parametrize(
    "row",
    [
        b"13002,baarle-hertog,elec,fluvius-kempen,true,\n",  # not a Walloon INS
        b"25112,,water,rew,true,\n",  # not a vector
        b"25112,,elec,none,true,\n",  # none is for gas only
        b"25112,,elec,enexis,true,\n",  # Enexis carries no electricity
        b"25112,,elec,rew,yes,\n",  # agrees is true or false
        b"25112,,elec,rew,true,REW 3\n",  # an agreeing row says nothing of the report
        b"25112,,elec,rew,false,\n",  # a disagreeing row says what the report showed
        b"25112,,elec,rew,false,ORES Brabant wallon\n",  # with its count
        b"25112,Old Section,elec,rew,true,\n",  # a section key is a slug
    ],
)
def test_powerbi_summary_format(mini_copy: Path, row: bytes) -> None:
    (mini_copy / "curation" / powerbi.SUMMARY_FILE).write_bytes(SUMMARY_HEADER + row)
    result = outcome(mini_copy)
    assert messages(result, "curation") == [
        "powerbi_checks.csv:2: a Walloon INS, an empty or slug section_key, a vector, the value "
        "compared (a DSO carrying the vector, or none for gas), agrees (true or false), and "
        "observed only when it disagrees ('none' or the GRD labels with their counts)"
    ]
    assert result.findings.crosscheck == []


def test_powerbi_summary_must_be_sorted(mini_copy: Path) -> None:
    (mini_copy / "curation" / powerbi.SUMMARY_FILE).write_bytes(
        SUMMARY_HEADER + b"25112,,gas,ores,true,\n25112,,elec,rew,true,\n"
    )
    assert [finding.message for finding in outcome(mini_copy).findings.errors] == [
        "powerbi_checks.csv: rows are not sorted by ins, section_key, vector"
    ]


def test_powerbi_summary_missing_is_a_warning_outside_fixture_mode(mini_copy: Path) -> None:
    """Never an error: the full readings are local, and even the summary is optional."""
    write_extracts(mini_copy)
    result = strict(mini_copy)
    assert "curation" not in error_rules(result)
    assert (
        "curation/powerbi_checks.csv missing: Walloon rows not cross-checked with the CWaPE "
        "Power BI"
    ) in [finding.message for finding in result.findings.warnings]
    (mini_copy / "curation" / powerbi.SUMMARY_FILE).write_bytes(
        SUMMARY_HEADER + b"25112,,gas,ores,true,\n"
    )
    warnings = [finding.message for finding in strict(mini_copy).findings.warnings]
    assert (
        "curation/powerbi_checks.csv has no elec row (cwape_powerbi_elec.csv not read): "
        "Walloon rows not cross-checked with the CWaPE Power BI"
    ) in warnings
    assert not any(
        "no gas row" in message or "powerbi_checks.csv missing" in message for message in warnings
    )
    assert not any("cwape_powerbi" in message and "missing" in message for message in warnings)


def test_cli_refresh_powerbi_summary(mini_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--fixture", "--data-dir", str(mini_copy), "--ignore-acceptance"]
    assert validate.main([*args, "--refresh-powerbi-summary"]) == 2
    assert "needs the full readings in curation/private/" in capsys.readouterr().err
    write_powerbi(mini_copy)
    assert validate.main(args) == 1  # the summary does not follow from the readings yet
    assert validate.main([*args, "--refresh-powerbi-summary"]) == 0
    assert validate.main(args) == 0
    shutil.rmtree(mini_copy / "curation" / powerbi.PRIVATE_DIR)
    assert validate.main(args) == 0


def test_spot_check_disagreement_explained(mini_copy: Path) -> None:
    mutate(
        mini_copy / "curation" / "spot_checks.csv",
        where={"ins": "25112"},
        set={"observed": "ores", "matches": "false"},
    )
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set={"valid_from": "2026-01-01"})
    assert [f.message for f in outcome(mini_copy).findings.crosscheck] == [
        "spot_checks.csv:2: cwape-power-bi on 2026-10-11 shows ores (elec) in 25112 "
        "(matches=false) (explained: valid_from 2026-01-01)"
    ]


# --- REPORT.md ------------------------------------------------------------------------------


def test_report_shows_the_acceptance_date_never_the_reviewer() -> None:
    ctx = context()
    notes = accepted(ctx.dataset.notes, accepted_by="Reviewer Name", accepted_on="2026-10-12")
    ctx = dataclasses.replace(ctx, dataset=dataclasses.replace(ctx.dataset, notes=notes))
    result = validate.build_and_check(
        ctx, draft=True, release=False, ignore_acceptance=False, as_of=ctx.date
    )
    text = result.files["REPORT.md"].decode("utf-8")
    assert "accepted 2026-10-12" in text
    assert "Reviewer" not in text


def test_report_flagged_row_without_a_note(mini_copy: Path) -> None:
    """operator_differs and propane_note need no note: the report says "-", not "missing"."""
    mutate(mini_copy / "assignments.csv", where={"ins": "25112"}, set={"flags": "propane_note"})
    text = outcome(mini_copy).files["REPORT.md"].decode("utf-8")
    assert "| 25112 | Wavre | - | propane_note | - | - | - |" in text
    assert "missing note" not in text


# --- CLI ------------------------------------------------------------------------------------


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert validate.main(["--fixture"]) == 1
    assert validate.main(["--fixture", "--ignore-acceptance"]) == 0
    assert "PASS: 0 errors, 0 warnings, 1 pending acceptances" in capsys.readouterr().out
    assert validate.main(["--data-dir", str(tmp_path), "--fixture"]) == 2
    with pytest.raises(SystemExit) as exit_info:
        validate.main(["--fixture", "--as-of", "yesterday"])
    assert exit_info.value.code == 2


def test_cli_release_never_ignores_acceptance() -> None:
    with pytest.raises(SystemExit) as exit_info:
        validate.main(["--fixture", "--release", "--ignore-acceptance"])
    assert exit_info.value.code == 2


def test_cli_writes_report_and_sources(tmp_path: Path) -> None:
    report_path, sources_path = tmp_path / "REPORT.md", tmp_path / "SOURCES.md"
    args = [
        "--fixture",
        "--ignore-acceptance",
        "--report",
        str(report_path),
        "--sources-md",
        str(sources_path),
    ]
    assert validate.main(args) == 0
    assert report_path.read_text(encoding="utf-8").startswith("# Data report — 2026.10.0-draft\n")
    sources = sources_path.read_text(encoding="utf-8")
    assert sources.index("## Legal references (R)") < sources.index("## Machine-readable data (M)")
    assert "`geo-statbel-postcodes-2025`" in sources
