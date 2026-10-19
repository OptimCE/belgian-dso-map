"""Shared helpers of the test suite: the mini fixture, in-memory builds, CSV edits."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

import build
import csvio
import validate

ROOT = Path(__file__).resolve().parent.parent
MINI = ROOT / "tests" / "fixtures" / "mini"

Row = dict[str, str]


def make_args(data_dir: Path = MINI, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "data_dir": data_dir,
        "fixture": True,
        "vectors": None,
        "previous": None,
        "previous_ref": None,
        "version": None,
        "date": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def context(data_dir: Path = MINI, *, release: bool = False, **overrides: object) -> build.Context:
    return build.load_context(make_args(data_dir, **overrides), release=release)


def outcome(
    data_dir: Path = MINI,
    *,
    draft: bool = True,
    release: bool = False,
    ignore_acceptance: bool = True,
    as_of: str | None = None,
    **overrides: object,
) -> validate.Outcome:
    ctx = context(data_dir, release=release, **overrides)
    return validate.build_and_check(
        ctx,
        draft=draft,
        release=release,
        ignore_acceptance=ignore_acceptance,
        as_of=as_of or ctx.date,
    )


def edit_csv(path: Path, change: Callable[[list[Row]], list[Row] | None]) -> None:
    """Rewrite a CSV after `change` edits its rows in place (or returns new rows)."""
    header, rows = csvio.parse_csv(
        path.read_bytes(),
        name=path.name,
        raw_columns=("postcode", "ins", "section_key", "post_name", "ean"),
    )
    result = change(rows)
    csvio.write_csv(path, header, rows if result is None else result)


def row_of(rows: list[Row], **match: str) -> Row:
    found = [row for row in rows if all(row[key] == value for key, value in match.items())]
    assert len(found) == 1, (match, found)
    return found[0]


def error_rules(result: validate.Outcome) -> set[str]:
    return {finding.rule for finding in result.findings.errors}


def warning_rules(result: validate.Outcome) -> set[str]:
    return {finding.rule for finding in result.findings.warnings}
