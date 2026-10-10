"""Distinct doc paths keep distinct changed-line keys."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import by_symbol, commit, example, gate_diff, make_repo, mod

FILLER = "Plain prose line.\n" * 30


@pytest.mark.skipif(os.sep == "\\", reason="a backslash is a path separator on Windows")
def test_backslash_name_does_not_collide_with_slash_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"docs/a/b.md": FILLER, "docs/a\\b.md": FILLER})
    (repo / "docs/a/b.md").write_text(example("GhostSlash") + FILLER)
    (repo / "docs/a\\b.md").write_text(FILLER + example("GhostBack"))
    commit(repo)

    code, data = gate_diff(repo, tmp_path)

    found = by_symbol(data)
    assert found["GhostSlash"]["in_diff"] is True
    assert found["GhostBack"]["in_diff"] is True
    assert code != 0


@pytest.mark.skipif(os.sep == "\\", reason="a backslash is a path separator on Windows")
def test_norm_path_keeps_a_literal_backslash_on_posix() -> None:
    assert mod._norm_path("docs/a\\b.md") == "docs/a\\b.md"
    assert mod._norm_path("./docs//a/b.md") == "docs/a/b.md"
