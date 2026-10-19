"""CHANGES.md: the cumulative log of published versions, and its strict grammar.

    # Changes

    ## 2026.11.0 — 2026-11-02
    - changed dso_lookup 5020|92094|flawinne — Flawinne (Namur); elec_operator: aieg→ores
    - removed dso_lookup 5024|92094|gelbressee — Gelbressée (Namur)
    - added notes gesves-exchange

    ## 2026.10.0 — 2026-10-12
    - initial release

Lines are the title, blank lines, version headings (newest first) and entries. The
dso_lookup key is `postcode|ins|section_key` (a trailing `|` when there is no
section); a removal is dated by its version heading. parse_changes() is the
reference parser: the website ports its regexes and rejects any other line.

Usage: python scripts/changes.py --latest dist/CHANGES.md   (newest section, for release notes)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import csvio
import schema
from dates import Change

TITLE = "# Changes"
HEADING_RE = re.compile(r"## ([0-9]{4}\.[0-9]{2}\.[0-9]+) — ([0-9]{4}-[0-9]{2}-[0-9]{2})")
ENTRY_RE = re.compile(
    r"- (added|changed|removed) (dso_lookup|operators|notes|sources) (\S+)( — .*)?"
)
INITIAL_RELEASE = "- initial release"
NO_CHANGES = "- no changes"
FILES = ("dso_lookup", "operators", "notes", "sources")
EMPTY = "∅"


class ChangesError(ValueError):
    """CHANGES.md breaks the grammar."""


@dataclass(frozen=True)
class Section:
    version: str
    date: str
    entries: tuple[str, ...]

    @property
    def heading(self) -> str:
        return f"## {self.version} — {self.date}"


def parse_changes(text: str) -> list[Section]:
    """Sections newest first. ChangesError on any line outside the grammar."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != TITLE:
        raise ChangesError(f"line 1: expected {TITLE!r}")
    sections: list[Section] = []
    current: tuple[str, str, list[str]] | None = None
    for number, line in enumerate(lines[1:], start=2):
        heading = HEADING_RE.fullmatch(line)
        if line == "":
            continue
        if heading:
            if current:
                sections.append(Section(current[0], current[1], tuple(current[2])))
            current = (heading.group(1), heading.group(2), [])
        elif ENTRY_RE.fullmatch(line) or line in (INITIAL_RELEASE, NO_CHANGES):
            if current is None:
                raise ChangesError(f"line {number}: entry before any version heading")
            current[2].append(line)
        else:
            raise ChangesError(f"line {number}: not a heading or an entry: {line!r}")
    if current:
        sections.append(Section(current[0], current[1], tuple(current[2])))
    for section in sections:
        if not section.entries:
            raise ChangesError(f"{section.heading}: no entries")
        if not schema.is_date(section.date):
            raise ChangesError(f"{section.heading}: invalid date")
        try:
            schema.version_key(section.version)  # the heading regex lets month 13 through
        except ValueError as exc:
            raise ChangesError(f"{section.heading}: {exc}") from exc
    for newer, older in pairwise(sections):
        if schema.version_key(newer.version) <= schema.version_key(older.version):
            raise ChangesError(f"{newer.heading}: versions must be listed newest first")
        if newer.date < older.date:
            raise ChangesError(f"{newer.heading}: dated before {older.version}")
    return sections


def render_changes(sections: Sequence[Section]) -> str:
    blocks = ["\n".join((section.heading, *section.entries)) for section in sections]
    return "\n\n".join((TITLE, *blocks)) + "\n"


# --- Entries ------------------------------------------------------------------------------


def _value(value: str) -> str:
    return value or EMPTY


def _lookup_label(row: Mapping[str, str]) -> str:
    if row["section_key"]:
        return f"{row['section_fr']} ({row['commune_fr']})"
    return row["commune_fr"]


def _lookup_details(change: Change) -> list[str]:
    old, new = change.old or {}, change.new or {}
    details = []
    for column in change.columns:
        before, after = old[column], new[column]
        if column in ("flags", "source_ids"):
            old_items, new_items = schema.split_list(before), schema.split_list(after)
            moves = [f"-{item}" for item in old_items if item not in new_items]
            moves += [f"+{item}" for item in new_items if item not in old_items]
            details.append(f"{column}: {' '.join(moves) or 'reordered'}")
        else:
            details.append(f"{column}: {_value(before)}→{_value(after)}")
    return details


def entry(change: Change, file: str) -> str:
    """One entry line: `- <kind> <file> <key> — <label; details>`."""
    row = change.row
    if file == "dso_lookup":
        key = "|".join(change.key)
        parts = [_lookup_label(row)]
        if change.kind == "changed":
            parts += _lookup_details(change)
    else:
        key = change.key[0]
        label = {"operators": "name", "sources": "publisher"}.get(file)
        parts = [row[label]] if label else []
        if change.kind == "changed":
            parts.append(", ".join(change.columns))
    tail = "; ".join(part for part in parts if part)
    line = f"- {change.kind} {file} {key}"
    return f"{line} — {tail}" if tail else line


def new_section(
    version: str, date: str, changes: Mapping[str, Sequence[Change]], *, initial: bool
) -> Section:
    """The section of a new version: entries grouped by file (FILES order), sorted by key."""
    if initial:
        return Section(version, date, (INITIAL_RELEASE,))
    entries = tuple(entry(change, file) for file in FILES for change in changes.get(file, ()))
    return Section(version, date, entries or (NO_CHANGES,))


def prepend(previous_text: str | None, section: Section) -> str:
    """The cumulative CHANGES.md: the new section first, then every previous one."""
    previous = parse_changes(previous_text) if previous_text is not None else []
    if previous and schema.version_key(previous[0].version) >= schema.version_key(section.version):
        raise ChangesError(f"{section.version} is not newer than {previous[0].version}")
    return render_changes([section, *previous])


def main(argv: Sequence[str] | None = None) -> int:
    csvio.utf8_console()
    parser = argparse.ArgumentParser(description="Print the newest section of a CHANGES.md.")
    parser.add_argument("--latest", type=Path, required=True, metavar="CHANGES_MD")
    args = parser.parse_args(argv)
    try:
        sections = parse_changes(args.latest.read_text(encoding="utf-8"))
    except (OSError, ChangesError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not sections:
        print("error: no version in this file", file=sys.stderr)
        return 1
    print(render_changes(sections[:1]).split("\n", 2)[2], end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
