"""An untouched cite fails when its one quoted line moves.

REQ-022 line 71 was already stale at the merge base. The quoted
assignment occurs once, and that line number changed. That is a finding.
A quote that keeps its line number stays debt.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.validation.citation_freshness_helpers import _git, _repo

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "citation_reverse_pass.py"
)
_NAME = "ledger.yml"
_QUOTE = 'fast_stage_ran = os.environ.get(FAST_STAGE_RAN_ENV) == "1"'
_BASE = "one\ntwo\nold comment about vendored install\n\n" + _QUOTE + "\n"
_SHIFTED = "one\ntwo\nold comment about vendored install\n\nspacer\n" + _QUOTE + "\n"
_SAME = "one\ntwo\nold comment about vendored install\n\n" + _QUOTE + "\nextra = 1\n"
_NO_QUOTE = "one\ntwo\nold comment about vendored install\nextra = 1\n"


def _cite(path: str) -> str:
    return f"The skip `{path}:3` reads\n`{_QUOTE}`.\n"


def _commit(root: Path, relpath: str, text: str, message: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "--", relpath)
    _git(root, "commit", "-q", "-m", message)


def _run_reverse(root: Path) -> tuple[int, str]:
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


def test_untouched_cite_fails_when_its_quote_moved(tmp_path: Path) -> None:
    """The quoted line occurs once, and its number changed."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, f"hooks/{_NAME}", _BASE, "cited")
    _commit(root, "docs/notes.md", _cite(_NAME), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, f"hooks/{_NAME}", _SHIFTED, "move quote")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "none of the cited anchors" in out


def test_untouched_cite_stays_debt_when_quote_keeps_its_line(tmp_path: Path) -> None:
    """A unique quote that stays on the same line does not block."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, f"hooks/{_NAME}", _BASE, "cited")
    _commit(root, "docs/notes.md", _cite(_NAME), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, f"hooks/{_NAME}", _SAME, "edit beside quote")

    code, out = _run_reverse(root)

    assert code == 0, out
    assert "already stale at the merge base" in out


def test_untouched_cite_without_a_relocated_quote_stays_debt(tmp_path: Path) -> None:
    """Base debt with no unique quote elsewhere does not block."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, f"hooks/{_NAME}", _BASE, "cited")
    _commit(root, "docs/notes.md", _cite(_NAME), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, f"hooks/{_NAME}", _NO_QUOTE, "edit without quote")

    code, out = _run_reverse(root)

    assert code == 0, out
    assert "already stale at the merge base" in out
