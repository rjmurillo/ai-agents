"""A shared token inside a range does not save rare names that moved out.

REQ-022 and TASK-029 kept stale fast-stage cites because one shared token
still sat inside the old range. The reverse pass must apply the same
rare-anchor rule the forward pass uses.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import _git, _repo, _run

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "citation_reverse_pass.py"
)
_CITED = "hooks/ledger.yml"
_BASE = "shared_gate\nskill_alpha_row\nshared_gate\nskill_beta_row\nshared_gate\n"
_MOVED = "shared_gate\nnotes\nshared_gate\nnotes\nshared_gate\nskill_alpha_row\nskill_beta_row\n"
_OUTSIDE = "shared_gate\nshared_gate\nshared_gate\nnotes\nskill_alpha_row\nskill_beta_row\n"


def _cite(path: str, span: str = "1-5") -> str:
    return f"See `{path}:{span}` for `shared_gate`, `skill_alpha_row`, and `skill_beta_row`.\n"


def _run_reverse(root: Path) -> tuple[int, str]:
    """Run the reverse pass CLI against one fixture repository."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--repo-root", str(root), "--base", "main"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _commit(root: Path, relpath: str, text: str, message: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def test_added_full_path_fails_when_rare_names_leave_the_range(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """REQ-022 shape: an added full-path cite names rows that now sit outside."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _CITED, _OUTSIDE, "cited")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, "docs/notes.md", _cite(_CITED, "1-3"), "cite")

    code, out = _run(root, capsys)

    assert code == 1, out
    assert "distinctive anchors" in out


def test_untouched_slashless_cite_fails_when_rare_names_move(
    tmp_path: Path,
) -> None:
    """TASK-029 shape: a kept slashless cite fails once its rare names move."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _CITED, _BASE, "cited")
    _commit(root, "docs/notes.md", _cite("ledger.yml"), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, _CITED, _MOVED, "move")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "distinctive anchors" in out


def test_stationary_first_line_still_fails_when_two_rare_names_move(
    tmp_path: Path,
) -> None:
    """An unchanged citation fails when the first boundary stays and two names leave."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _CITED, _BASE, "cited")
    _commit(root, "docs/notes.md", _cite(_CITED), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, _CITED, _MOVED, "move")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "skill_alpha_row" in out
    assert "skill_beta_row" in out


def test_rare_names_that_stay_inside_do_not_fail(tmp_path: Path) -> None:
    """A changed file whose rare names remain in range stays quiet."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _CITED, _BASE, "cited")
    _commit(root, "docs/notes.md", _cite(_CITED), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, _CITED, _BASE + "tail\n", "tail")

    code, out = _run_reverse(root)

    assert code == 0, out


def test_neighbor_rare_names_do_not_fail_a_valid_cite(tmp_path: Path) -> None:
    """A wrapped neighbor's rare names do not vote when this line's slice holds."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _CITED, _BASE + "rare_alpha\nrare_beta\n", "cited")
    note = f"Remember `rare_alpha` and `rare_beta`\nSee `{_CITED}:1-3` for `shared_gate`.\n"
    _commit(root, "docs/notes.md", note, "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, _CITED, _BASE + "rare_alpha\nrare_beta\ntail\n", "tail")

    code, out = _run_reverse(root)

    assert code == 0, out
