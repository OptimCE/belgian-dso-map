from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from helpers import MINI


@pytest.fixture
def mini_copy(tmp_path: Path) -> Path:
    """A writable copy of the mini fixture (with its curation/ and vectors.csv)."""
    target = tmp_path / "mini"
    shutil.copytree(MINI, target)
    return target
