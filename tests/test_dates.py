"""first_seen / changed_at by fingerprint, and versions that only move forward."""

from __future__ import annotations

import pytest

import build
import dates

COLUMNS = ("id", "value")
KEY = ("id",)
D1, D2 = "2026-10-12", "2026-11-02"


def stamp(
    rows: list[dict[str, str]],
    previous: tuple[tuple[str, ...], list[dict[str, str]]] | None,
    date: str = D2,
):
    return dates.stamp(
        rows,
        data_columns=COLUMNS,
        key_columns=KEY,
        version_date=date,
        data_version="2026.11.0",
        previous=previous,
        label="t.csv",
    )


def published(*rows: tuple[str, str, str, str]) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    header = (*COLUMNS, "first_seen", "changed_at", "data_version")
    return header, [
        {"id": i, "value": v, "first_seen": f, "changed_at": c, "data_version": "2026.10.0"}
        for i, v, f, c in rows
    ]


def test_first_version_dates_every_row_with_the_version_date() -> None:
    stamped, changes = stamp([{"id": "a", "value": "1"}], None)
    assert stamped == [
        {"id": "a", "value": "1", "first_seen": D2, "changed_at": D2, "data_version": "2026.11.0"}
    ]
    assert changes == []


def test_unchanged_row_keeps_both_dates() -> None:
    stamped, changes = stamp([{"id": "a", "value": "1"}], published(("a", "1", "2026-01-05", D1)))
    assert (stamped[0]["first_seen"], stamped[0]["changed_at"]) == ("2026-01-05", D1)
    assert changes == []


def test_changed_row_keeps_first_seen_and_moves_changed_at() -> None:
    old = published(("a", "1", "2026-01-05", D1))
    stamped, changes = stamp([{"id": "a", "value": "2"}], old)
    assert (stamped[0]["first_seen"], stamped[0]["changed_at"]) == ("2026-01-05", D2)
    assert [(change.kind, change.key, change.columns) for change in changes] == [
        ("changed", ("a",), ("value",))
    ]


def test_new_and_removed_keys() -> None:
    stamped, changes = stamp([{"id": "b", "value": "1"}], published(("a", "1", D1, D1)))
    assert (stamped[0]["first_seen"], stamped[0]["changed_at"]) == (D2, D2)
    # sorted by key, whatever the kind
    assert [(change.kind, change.key) for change in changes] == [
        ("removed", ("a",)),
        ("added", ("b",)),
    ]
    assert changes[0].row["value"] == "1"


def test_an_added_column_moves_no_date() -> None:
    header, rows = published(("a", "1", D1, D1))
    narrow_header = tuple(column for column in header if column != "value")
    narrow_rows = [{key: value for key, value in row.items() if key != "value"} for row in rows]
    stamped, changes = stamp([{"id": "a", "value": "new column"}], (narrow_header, narrow_rows))
    assert stamped[0]["changed_at"] == D1
    assert changes == []


def test_data_version_and_dates_are_not_fingerprinted() -> None:
    assert dates.compared_columns(
        ("id", "first_seen", "changed_at", "data_version"), ("id", "first_seen")
    ) == ("id",)
    old = published(("a", "1", D1, D1))
    old[1][0]["data_version"] = "2026.10.0-draft"
    _, changes = stamp([{"id": "a", "value": "1"}], old)
    assert changes == []


def test_fingerprint_separates_columns() -> None:
    assert dates.fingerprint({"a": "x", "b": "yz"}, ("a", "b")) != dates.fingerprint(
        {"a": "xy", "b": "z"}, ("a", "b")
    )


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("a", "1", D1, "2026-12-01"), "not ordered"),
        (("a", "1", D2, D1), "not ordered"),
        (("a", "1", "2026-13-01", D1), "invalid"),
    ],
)
def test_previous_dates_must_be_ordered_before_the_version(
    row: tuple[str, str, str, str], message: str
) -> None:
    with pytest.raises(dates.DatesError, match=message):
        stamp([{"id": "a", "value": "1"}], published(row))


def test_duplicate_keys_are_refused() -> None:
    with pytest.raises(dates.DatesError, match="duplicate"):
        stamp([{"id": "a", "value": "1"}, {"id": "a", "value": "2"}], None)
    with pytest.raises(dates.DatesError, match="duplicate"):
        stamp([], published(("a", "1", D1, D1), ("a", "2", D1, D1)))


def test_previous_without_date_columns_is_refused() -> None:
    with pytest.raises(dates.DatesError, match="first_seen"):
        stamp([], (("id", "value"), []))


# --- version sequence -----------------------------------------------------------------------


def previous(version: str, date: str) -> build.Previous:
    return build.Previous("prev", build.Release(version, date, ""), {}, "# Changes\n")


def test_versions_and_dates_only_move_forward() -> None:
    build.check_sequence(
        "2026.11.0", D2, previous("2026.10.0", D1), release=True, named_previous="2026.10.0"
    )
    with pytest.raises(build.BuildError, match="not newer"):
        build.check_sequence(
            "2026.10.0", D2, previous("2026.10.0", D1), release=False, named_previous=None
        )
    with pytest.raises(build.BuildError, match="not newer"):
        build.check_sequence(
            "2026.10.1", D2, previous("2026.11.0", D1), release=False, named_previous=None
        )
    with pytest.raises(build.BuildError, match="before"):
        build.check_sequence(
            "2026.11.0", D1, previous("2026.10.0", D2), release=False, named_previous=None
        )


def test_a_release_never_follows_a_draft_and_names_its_previous() -> None:
    with pytest.raises(build.BuildError, match="draft"):
        build.check_sequence(
            "2026.11.0", D2, previous("2026.10.0-draft", D1), release=True, named_previous=None
        )
    build.check_sequence(
        "2026.11.0", D2, previous("2026.10.0-draft", D1), release=False, named_previous=None
    )
    with pytest.raises(build.BuildError, match="names previous"):
        build.check_sequence(
            "2026.11.0", D2, previous("2026.10.0", D1), release=True, named_previous="2026.09.0"
        )
    with pytest.raises(build.BuildError, match="not found"):
        build.check_sequence("2026.11.0", D2, None, release=True, named_previous="2026.10.0")
