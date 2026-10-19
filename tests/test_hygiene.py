"""Committed text files: UTF-8, no BOM, LF only, a final newline; CSV headers as specified."""

from __future__ import annotations

from pathlib import Path

import pytest

import csvio
import schema
from helpers import MINI, ROOT

SKIPPED_DIRS = {
    ".git",
    ".venv",
    ".build",
    ".cache",
    ".claude",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "private",  # curation/private/: the full Power BI readings, git-ignored (local only)
}
TEXT_SUFFIXES = {".csv", ".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".py"}
TEXT_NAMES = {"LICENSE", "LICENSE-CODE", "SHA256SUMS", ".gitattributes", ".gitignore"}


def committed_text_files() -> list[Path]:
    files = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in SKIPPED_DIRS for part in relative.parts) or not path.is_file():
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:
            files.append(path)
    return files


def test_the_walk_finds_the_repository_files() -> None:
    names = {path.relative_to(ROOT).as_posix() for path in committed_text_files()}
    assert {
        "README.md",
        "release.json",
        "data/operators.csv",
        "tests/vectors.csv",
        "scripts/build.py",
    } <= names


@pytest.mark.parametrize(
    "path", committed_text_files(), ids=lambda path: path.relative_to(ROOT).as_posix()
)
def test_text_file_is_lf_utf8_without_bom(path: Path) -> None:
    csvio.check_text_bytes(path.read_bytes(), str(path.relative_to(ROOT)))


@pytest.mark.parametrize("data_dir", [ROOT / "data", MINI], ids=["data", "mini"])
def test_data_files_have_the_contract_headers(data_dir: Path) -> None:
    dataset = schema.load_dataset(data_dir)
    assert set(dataset.hashes) == set(schema.DATA_FILES)


def test_vectors_files_have_the_contract_header() -> None:
    for path in (ROOT / "tests" / "vectors.csv", MINI / "vectors.csv"):
        csvio.read_csv(path, schema.VECTORS_HEADER, raw_columns=schema.VECTOR_INPUT_COLUMNS)


def test_curation_files_have_their_headers() -> None:
    csvio.read_csv(MINI / "curation" / "spot_checks.csv", schema.SPOT_CHECKS_HEADER)
    worksheets = sorted((ROOT / "curation").glob("*_designations.csv"))
    for path in [*worksheets, MINI / "curation" / "wal_designations.csv"]:
        csvio.read_csv(path, schema.WORKSHEET_HEADER)


def test_fixture_notes_are_never_accepted() -> None:
    """The fixture builds as a draft only. data/notes.csv is not checked: filling its
    accepted_by/accepted_on is Eric's release step, and a test must not block it."""
    notes = csvio.read_csv(MINI / "notes.csv", schema.NOTES_HEADER)
    assert all(not note["accepted_by"] and not note["accepted_on"] for note in notes)
