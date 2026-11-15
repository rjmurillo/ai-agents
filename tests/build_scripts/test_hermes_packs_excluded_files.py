"""Tests for the Hermes ``excludedFiles`` table in the pack build (issue #7357).

A file named there ships in no pack, the pack count drops by exactly that file,
and an entry that matches nothing fails the build. Parsing and the check itself
are in ``test_hermes_pack_checks.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import hermes_pack_config as cfg  # noqa: E402
import hermes_packs  # noqa: E402
from _hermes_pack_helpers import make_config, make_repo  # noqa: E402


def test_build_pack_skips_an_excluded_file_and_keeps_its_siblings(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config(excludedFiles={"alpha/scripts/run.py": "needs a missing skill"})

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})

    assert "skills/alpha/scripts/run.py" not in files
    assert "skills/alpha/references/r.md" in files
    assert "skills/alpha/SKILL.md" in files


def test_plan_tree_drops_one_file_per_excluded_file_from_the_pack_count(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    before = hermes_packs.plan_tree(repo, make_config())
    after = hermes_packs.plan_tree(
        repo, make_config(excludedFiles={"alpha/scripts/run.py": "needs a missing skill"})
    )

    assert set(before) - set(after) == {"project-toolkit-one/skills/alpha/scripts/run.py"}
    assert set(after) - set(before) == set()


def test_plan_tree_fails_when_an_excluded_file_matches_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config(excludedFiles={"alpha/scripts/gone.py": "why"})

    with pytest.raises(cfg.HermesPackError, match="matches no file"):
        hermes_packs.plan_tree(repo, config)
