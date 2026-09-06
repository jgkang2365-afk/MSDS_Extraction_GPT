"""Isolated imports and disposable real-PDF storage for rebaseline tests."""

from pathlib import Path
import shutil
import sys
from uuid import uuid4

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture
def pdf_tmp():
    """A worktree-local directory for one synthetic-PDF test, always removed."""
    root = REPOSITORY_ROOT / ".rebaseline-test-tmp"
    root.mkdir(exist_ok=True)
    child = root / uuid4().hex
    child.mkdir()
    try:
        yield child
    finally:
        shutil.rmtree(child, ignore_errors=True)
        try:
            root.rmdir()
        except OSError:
            pass
