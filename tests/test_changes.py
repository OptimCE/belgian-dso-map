"""CHANGES.md: strict grammar, cumulative prepend, entry lines with commune labels."""

from __future__ import annotations

from pathlib import Path

import pytest

import changes
from dates import Change

CANONICAL = (
    "# Changes\n"
    "\n"
    "## 2026.11.0 — 2026-11-02\n"
    "- changed dso_lookup 5020|92094|flawinne — Flawinne (Namur); elec_operator: aieg→ores\n"
    "- removed dso_lookup 1301|25112| — Wavre\n"
    "- added notes gesves-exchange\n"
    "\n"
    "## 2026.10.0 — 2026-10-12\n"
    "- initial release\n"
)


def lookup_row(**values: str) -> dict[str, str]:
    row = {
        "postcode": "5020",
        "ins": "92094",
        "commune_fr": "Namur",
        "section_key": "flawinne",
        "section_fr": "Flawinne",
        "elec_operator": "aieg",
        "flags": "transition|operator_differs|to_confirm",
        "valid_from": "",
    }
    row.update(values)
    return row


def test_round_trip() -> None:
    sections = changes.parse_changes(CANONICAL)
    assert [(s.version, s.date, len(s.entries)) for s in sections] == [
        ("2026.11.0", "2026-11-02", 3),
        ("2026.10.0", "2026-10-12", 1),
    ]
    assert changes.render_changes(sections) == CANONICAL


def test_prepend_keeps_every_previous_section() -> None:
    newer = changes.Section("2026.12.0", "2026-12-07", (changes.NO_CHANGES,))
    text = changes.prepend(CANONICAL, newer)
    assert text.startswith("# Changes\n\n## 2026.12.0 — 2026-12-07\n- no changes\n\n## 2026.11.0")
    assert text.endswith(CANONICAL.removeprefix("# Changes\n"))
    with pytest.raises(changes.ChangesError, match="not newer"):
        changes.prepend(
            CANONICAL, changes.Section("2026.11.0", "2026-11-02", (changes.NO_CHANGES,))
        )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# CHANGES\n", "line 1"),
        ("# Changes\n- initial release\n", "before any version"),
        ("# Changes\n\n## 2026.10.0 — 2026-10-12\n", "no entries"),
        ("# Changes\n\n## 2026.10.0 - 2026-10-12\n- initial release\n", "not a heading"),
        (
            "# Changes\n\n## 2026.10.0 — 2026-10-12\n- removed: 5020,92094,x (2026-10-12)\n",
            "not a heading",
        ),
        ("# Changes\n\n## 2026.10.0 — 2026-10-12\n- initial release \n", "not a heading"),
        ("# Changes\n\n## 2026.10.0 — 2026-10-12\n- added dso_lookup a b\n", "not a heading"),
        (
            "# Changes\n\n## 2026.10.0 — 2026-10-12\n- initial release\n\n"
            "## 2026.11.0 — 2026-11-02\n- no changes\n",
            "newest first",
        ),
        ("# Changes\n\n## 2026.10.0 — 2026-02-30\n- initial release\n", "invalid date"),
        ("# Changes\n\n## 2026.13.0 — 2026-12-01\n- initial release\n", "not YYYY.MM.N"),
        ("# Changes\n\n## 2026.10.01 — 2026-10-12\n- initial release\n", "not YYYY.MM.N"),
        (
            "# Changes\n\n## 2026.11.0 — 2026-10-02\n- no changes\n\n"
            "## 2026.10.0 — 2026-10-12\n- initial release\n",
            "dated before",
        ),
    ],
)
def test_rejects_lines_outside_the_grammar(text: str, message: str) -> None:
    with pytest.raises(changes.ChangesError, match=message):
        changes.parse_changes(text)


def test_changed_lookup_entry_has_the_section_label_and_the_details() -> None:
    old = lookup_row()
    new = lookup_row(elec_operator="ores", flags="", valid_from="2026-07-01")
    change = Change(
        "changed", ("5020", "92094", "flawinne"), old, new, ("elec_operator", "flags", "valid_from")
    )
    line = changes.entry(change, "dso_lookup")
    assert line == (
        "- changed dso_lookup 5020|92094|flawinne — Flawinne (Namur); elec_operator: aieg→ores; "
        "flags: -transition -operator_differs -to_confirm; valid_from: ∅→2026-07-01"
    )
    assert changes.ENTRY_RE.fullmatch(line)


def test_commune_level_key_ends_with_a_pipe() -> None:
    row = lookup_row(
        postcode="1301", ins="25112", commune_fr="Wavre", section_key="", section_fr=""
    )
    line = changes.entry(Change("removed", ("1301", "25112", ""), row, None), "dso_lookup")
    assert line == "- removed dso_lookup 1301|25112| — Wavre"
    assert changes.ENTRY_RE.fullmatch(line)


def test_other_files_list_the_changed_columns() -> None:
    old = {"id": "ores", "name": "ORES", "website": "https://a"}
    new = {"id": "ores", "name": "ORES", "website": "https://b"}
    line = changes.entry(Change("changed", ("ores",), old, new, ("website",)), "operators")
    assert line == "- changed operators ores — ORES; website"
    note = changes.entry(Change("added", ("gesves",), None, {"key": "gesves"}), "notes")
    assert note == "- added notes gesves"
    assert changes.ENTRY_RE.fullmatch(note)


def test_new_section_orders_files_then_keys() -> None:
    added = Change("added", ("b",), None, {"key": "b"})
    removed = Change(
        "removed",
        ("1301", "25112", ""),
        lookup_row(postcode="1301", section_key="", section_fr=""),
        None,
    )
    section = changes.new_section(
        "2026.11.0", "2026-11-02", {"notes": [added], "dso_lookup": [removed]}, initial=False
    )
    assert section.entries == ("- removed dso_lookup 1301|25112| — Namur", "- added notes b")
    assert changes.new_section("2026.10.0", "2026-10-12", {}, initial=True).entries == (
        "- initial release",
    )
    assert changes.new_section("2026.10.1", "2026-10-13", {}, initial=False).entries == (
        "- no changes",
    )


def test_cli_prints_the_newest_section(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "CHANGES.md"
    path.write_bytes(CANONICAL.encode("utf-8"))
    assert changes.main(["--latest", str(path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("## 2026.11.0 — 2026-11-02\n- changed")
    assert "2026.10.0" not in out


def test_cli_refuses_an_invalid_version(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "CHANGES.md"
    path.write_bytes("# Changes\n\n## 2026.13.0 — 2026-12-01\n- initial release\n".encode())
    assert changes.main(["--latest", str(path)]) == 2
    assert "not YYYY.MM.N" in capsys.readouterr().err
