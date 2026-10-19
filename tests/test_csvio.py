"""The CSV dialect: UTF-8 without BOM, LF, comma, RFC 4180, strict cells."""

from __future__ import annotations

from pathlib import Path

import pytest

import csvio

HEADER = ("id", "text")
NBSP = chr(0xA0)
BOM_CHAR = chr(0xFEFF)
COMBINING_ACUTE = chr(0x301)
LINE_SEPARATOR = chr(0x2028)  # JavaScript's `.` stops here, Python's does not
PARAGRAPH_SEPARATOR = chr(0x2029)


def test_render_is_lf_without_bom_and_quotes_only_when_needed() -> None:
    data = csvio.render_csv(HEADER, [{"id": "a", "text": "plain"}, {"id": "b", "text": "x,y"}])
    assert data == b'id,text\na,plain\nb,"x,y"\n'
    assert not data.startswith(csvio.BOM)
    assert b"\r" not in data


@pytest.mark.parametrize(
    "value",
    ["comma, inside", 'say "hi"', "pipe|list", "Gelbressée", "d'Électricité", "Namür"],
)
def test_round_trip(value: str) -> None:
    rows = [{"id": "x", "text": value}]
    header, parsed = csvio.parse_csv(csvio.render_csv(HEADER, rows), name="t.csv", header=HEADER)
    assert header == HEADER
    assert parsed == rows


def test_write_csv_writes_the_rendered_bytes(tmp_path: Path) -> None:
    path = tmp_path / "out" / "t.csv"
    csvio.write_csv(path, HEADER, [{"id": "a", "text": "x"}])
    assert path.read_bytes() == b"id,text\na,x\n"
    assert csvio.read_csv(path, HEADER) == [{"id": "a", "text": "x"}]


def test_header_only_file_has_no_rows() -> None:
    assert csvio.parse_csv(b"id,text\n", name="t.csv", header=HEADER) == (HEADER, [])


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (csvio.BOM + b"id,text\n", "BOM"),
        (b"id,text\r\na,b\r\n", "CR"),
        (b"id,text\na,b", "newline"),
        (b"", "empty"),
        (b"id,other\n", "header"),
        (b"id,text\na\n", "fields"),
        (b"id,text\na,b,c\n", "fields"),
        (b"id,text\n\n", "fields"),
        (b"id,id\n", "header"),
        (b"id,text\na, padded\n", "whitespace"),
        (b"id,text\na,padded \n", "whitespace"),
        (b'id,text\na,"two\nlines"\n', "control"),
        (b"id,text\na,bell\x07\n", "control"),
        (f"id,text\na,line{LINE_SEPARATOR}break\n".encode(), "separator"),
        (f"id,text\na,paragraph{PARAGRAPH_SEPARATOR}break\n".encode(), "separator"),
        (b"id,text\na,\xff\n", "UTF-8"),
        (b'id,text\na,"unclosed\n', "line"),
    ],
)
def test_rejects(data: bytes, message: str) -> None:
    with pytest.raises(csvio.CsvError, match=message):
        csvio.parse_csv(data, name="t.csv", header=HEADER)


def test_rejects_non_nfc_text() -> None:
    decomposed = "Gelbresse" + COMBINING_ACUTE + "e"
    with pytest.raises(csvio.CsvError, match="NFC"):
        csvio.parse_csv(f"id,text\na,{decomposed}\n".encode(), name="t.csv", header=HEADER)


@pytest.mark.parametrize("value", [NBSP + "x", "x" + BOM_CHAR, BOM_CHAR + "x"])
def test_rejects_invisible_padding_in_strict_cells(value: str) -> None:
    with pytest.raises(csvio.CsvError):
        csvio.parse_csv(f"id,text\na,{value}\n".encode(), name="t.csv", header=HEADER)


@pytest.mark.parametrize("value", [" 5020 ", NBSP + "5020", BOM_CHAR + "1000", ""])
def test_raw_columns_keep_their_padding(value: str) -> None:
    rows = [{"id": "a", "text": value}]
    _, parsed = csvio.parse_csv(
        csvio.render_csv(HEADER, rows), name="t.csv", header=HEADER, raw_columns=("text",)
    )
    assert parsed == rows


@pytest.mark.parametrize("value", ["\tx", "x" + LINE_SEPARATOR, PARAGRAPH_SEPARATOR + "x"])
def test_raw_columns_still_refuse_control_characters(value: str) -> None:
    with pytest.raises(csvio.CsvError, match="control"):
        csvio.parse_csv(
            f"id,text\na,{value}\n".encode(), name="t.csv", header=HEADER, raw_columns=("text",)
        )


def test_duplicate_header_column_without_an_expected_header() -> None:
    with pytest.raises(csvio.CsvError, match="duplicate column"):
        csvio.parse_csv(b"id,id\na,b\n", name="t.csv")


def test_header_is_optional_when_reading_any_table() -> None:
    header, rows = csvio.parse_csv(b"x,y\n1,2\n", name="t.csv")
    assert header == ("x", "y")
    assert rows == [{"x": "1", "y": "2"}]
