"""Content dates of published rows (`first_seen`, `changed_at`), by fingerprint.

A row's fingerprint is the sha256 of its data columns joined with U+001F. Only the
columns present in both the previous and the current header count, and the date
columns and `data_version` never do, so adding a column moves no date.

- No previous version, or a new key: first_seen = changed_at = the version date.
- Same fingerprint: both dates are kept as they were.
- Different fingerprint: first_seen is kept, changed_at = the version date.
- A key that disappeared is a removal (listed in CHANGES.md under the version).

The only date ever written is the version date: no clock, mtime or git date.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import schema

Row = dict[str, str]
Key = tuple[str, ...]


class DatesError(ValueError):
    """The previous version cannot be compared (bad dates, duplicate keys, time going back)."""


@dataclass(frozen=True)
class Change:
    kind: str  # added | changed | removed
    key: Key
    old: Mapping[str, str] | None
    new: Mapping[str, str] | None
    columns: tuple[str, ...] = ()  # changed columns, in header order

    @property
    def row(self) -> Mapping[str, str]:
        """The current row, or the removed one."""
        row = self.new if self.new is not None else self.old
        if row is None:
            raise ValueError("a change has an old row, a new row or both")
        return row


def fingerprint(row: Mapping[str, str], columns: Sequence[str]) -> str:
    return hashlib.sha256(
        "\x1f".join(row[column] for column in columns).encode("utf-8")
    ).hexdigest()


def compared_columns(
    data_columns: Sequence[str], previous_header: Sequence[str]
) -> tuple[str, ...]:
    """Data columns present in both headers, never a date column."""
    return tuple(
        column
        for column in data_columns
        if column in previous_header and column not in schema.DATE_COLUMNS
    )


def _keyed(
    rows: Sequence[Mapping[str, str]], key_columns: Sequence[str], label: str
) -> dict[Key, Mapping[str, str]]:
    keyed: dict[Key, Mapping[str, str]] = {}
    for row in rows:
        key = tuple(row[column] for column in key_columns)
        if key in keyed:
            raise DatesError(f"{label}: duplicate key {'|'.join(key)}")
        keyed[key] = row
    return keyed


def stamp(
    rows: Sequence[Mapping[str, str]],
    *,
    data_columns: Sequence[str],
    key_columns: Sequence[str],
    version_date: str,
    data_version: str,
    previous: tuple[Sequence[str], Sequence[Mapping[str, str]]] | None,
    label: str,
) -> tuple[list[Row], list[Change]]:
    """Rows with first_seen/changed_at/data_version added, and the changes since `previous`
    (header, rows of the previous published file). Changes are sorted by key."""
    current = _keyed(rows, key_columns, label)
    if previous is None:
        stamped = [
            {
                **row,
                "first_seen": version_date,
                "changed_at": version_date,
                "data_version": data_version,
            }
            for row in rows
        ]
        return stamped, []

    previous_header, previous_rows = previous
    for column in (*key_columns, "first_seen", "changed_at"):
        if column not in previous_header:
            raise DatesError(f"previous {label}: no column {column}")
    before = _keyed(previous_rows, key_columns, f"previous {label}")
    columns = compared_columns(data_columns, previous_header)

    stamped = []
    changes: list[Change] = []
    for key, row in current.items():
        old = before.get(key)
        if old is None:
            first_seen = changed_at = version_date
            changes.append(Change("added", key, None, row))
        else:
            first_seen, changed_at = old["first_seen"], old["changed_at"]
            if not (schema.is_date(first_seen) and schema.is_date(changed_at)):
                raise DatesError(f"previous {label} {'|'.join(key)}: invalid first_seen/changed_at")
            if not first_seen <= changed_at <= version_date:
                raise DatesError(
                    f"previous {label} {'|'.join(key)}: dates {first_seen}/{changed_at} "
                    f"are not ordered before the version date {version_date}"
                )
            if fingerprint(old, columns) != fingerprint(row, columns):
                changed_at = version_date
                differing = tuple(column for column in columns if old[column] != row[column])
                changes.append(Change("changed", key, old, row, differing))
        stamped.append(
            {
                **row,
                "first_seen": first_seen,
                "changed_at": changed_at,
                "data_version": data_version,
            }
        )
    changes.extend(
        Change("removed", key, old, None) for key, old in before.items() if key not in current
    )
    changes.sort(key=lambda change: change.key)
    return stamped, changes
