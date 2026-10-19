"""The CSV dialect of the repository: UTF-8 without BOM, LF, comma, RFC 4180 quoting.

Reading is strict, so a file that a consumer would read differently never gets
through: a BOM, a CR, a missing final newline, a header that is not the expected
one, a short row, a non-NFC cell or a cell with padding or control characters is
an error. Writing is deterministic (`csv.QUOTE_MINIMAL`, `lineterminator="\\n"`,
bytes written as is), so two builds of the same rows are byte-identical.

The website's Jekyll reader does not strip a BOM and splits on commas, which is
why the dialect is fixed here and nowhere else.
"""

from __future__ import annotations

import csv
import io
import sys
import unicodedata
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path

Row = dict[str, str]

BOM = b"\xef\xbb\xbf"


class CsvError(ValueError):
    """A file breaks the dialect or its expected header."""


def check_text_bytes(data: bytes, name: str) -> str:
    """Decode a committed text file: UTF-8, no BOM, no CR, a final newline when not empty."""
    if data.startswith(BOM):
        raise CsvError(f"{name}: starts with a UTF-8 BOM")
    if b"\r" in data:
        raise CsvError(f"{name}: contains a CR (line endings must be LF)")
    if data and not data.endswith(b"\n"):
        raise CsvError(f"{name}: does not end with a newline")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CsvError(f"{name}: not valid UTF-8 ({exc.reason} at byte {exc.start})") from exc


def _cell_problem(value: str, *, raw: bool) -> str | None:
    """Why a cell breaks the hygiene rules, or None.

    `raw` cells (the inputs of tests/vectors.csv) keep their padding on purpose: they
    exercise the TRIM rule of the lookup. They may still not hold control characters,
    nor U+2028/U+2029: JavaScript's `.` stops at them, so the website's port of the
    CHANGES.md regexes would reject a line that Python accepts.
    """
    for char in value:
        category = unicodedata.category(char)
        if category in ("Cc", "Zl", "Zp") or (category == "Cf" and not raw):
            return f"control, format or line separator character U+{ord(char):04X}"
    if raw:
        return None
    if value != value.strip():
        return "leading or trailing whitespace"
    if not unicodedata.is_normalized("NFC", value):
        return "text is not in Unicode NFC form"
    return None


def parse_csv(
    data: bytes,
    *,
    name: str,
    header: Sequence[str] | None = None,
    raw_columns: Collection[str] = (),
) -> tuple[tuple[str, ...], list[Row]]:
    """Parse CSV bytes into (header, rows). With `header`, the header must match exactly."""
    text = check_text_bytes(data, name)
    if not text:
        raise CsvError(f"{name}: empty file (the header row is required)")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        parsed = list(reader)
    except csv.Error as exc:
        raise CsvError(f"{name}: line {reader.line_num}: {exc}") from exc
    found = tuple(parsed[0])
    if header is not None and found != tuple(header):
        raise CsvError(f"{name}: header is {','.join(found)!r}, expected {','.join(header)!r}")
    if len(set(found)) != len(found):
        raise CsvError(f"{name}: duplicate column in the header")
    for column in found:
        problem = _cell_problem(column, raw=False)
        if problem or not column:
            raise CsvError(f"{name}: header column {column!r}: {problem or 'empty name'}")
    rows: list[Row] = []
    for number, cells in enumerate(parsed[1:], start=2):
        if len(cells) != len(found):
            raise CsvError(f"{name}: line {number}: {len(cells)} fields, expected {len(found)}")
        for column, value in zip(found, cells, strict=True):
            problem = _cell_problem(value, raw=column in raw_columns)
            if problem:
                raise CsvError(f"{name}: line {number}, column {column}: {problem}")
        rows.append(dict(zip(found, cells, strict=True)))
    return found, rows


def read_csv(path: Path, header: Sequence[str], *, raw_columns: Collection[str] = ()) -> list[Row]:
    """Read a CSV file whose header must be exactly `header`."""
    _, rows = parse_csv(path.read_bytes(), name=path.name, header=header, raw_columns=raw_columns)
    return rows


def render_csv(header: Sequence[str], rows: Iterable[Mapping[str, str]]) -> bytes:
    """Render rows in the repository dialect. Every row must have every header column."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[column] for column in header])
    return buffer.getvalue().encode("utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    """Write bytes verbatim (never through a text layer that could add CRs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def utf8_console() -> None:
    """Print UTF-8 even on a Windows console (its code page cannot print "→" or "∅")."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Mapping[str, str]]) -> None:
    write_bytes(path, render_csv(header, rows))
