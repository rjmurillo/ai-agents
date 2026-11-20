"""An untouched citation that was stale at the merge base stays debt.

PR #7482 was blocked by ADR-109 line 96. That line cited ADR-107 line 663.
The quoted bullet already sat at line 725 on main, so the citation was
wrong before the branch. The branch added three lines above the bullet.
It never touched line 96. The reverse pass blocked anyway and printed
"0 already stale". These cases pin the fix: debt is counted, not blocked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.validation.citation_freshness_helpers import TARGET, _git, _repo

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "citation_reverse_pass.py"
)
_NAME = "ledger.yml"
_QUOTE = 'fast_stage_ran = os.environ.get(FAST_STAGE_RAN_ENV) == "1"'
_BASE = "one\ntwo\nold comment about vendored install\n\n" + _QUOTE + "\n"
_SHIFTED = "one\ntwo\nold comment about vendored install\n\nspacer\n" + _QUOTE + "\n"
_SAME = "one\ntwo\nold comment about vendored install\n\n" + _QUOTE + "\nextra = 1\n"
_NO_QUOTE = "one\ntwo\nold comment about vendored install\nextra = 1\n"
_ONE_STALE = "; 1 already stale at the merge base (not blocking)"
_DOC = "docs/guide.md"


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


def _stale_cite_on_feature(tmp_path: Path, head_text: str) -> Path:
    """Main cites line 3 of a file whose quote sits at line 5: stale at base."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, f"hooks/{_NAME}", _BASE, "cited")
    _commit(root, "docs/notes.md", _cite(_NAME), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, f"hooks/{_NAME}", head_text, "edit cited file")
    return root


def test_untouched_stale_cite_stays_debt_when_its_quote_shifts(tmp_path: Path) -> None:
    """The PR #7482 shape: lines shift under a cite that was already wrong."""
    root = _stale_cite_on_feature(tmp_path, _SHIFTED)

    code, out = _run_reverse(root)

    assert code == 0, out
    assert _ONE_STALE in out


def test_untouched_stale_cite_stays_debt_when_quote_keeps_its_line(tmp_path: Path) -> None:
    """A unique quote that stays on the same line does not block."""
    root = _stale_cite_on_feature(tmp_path, _SAME)

    code, out = _run_reverse(root)

    assert code == 0, out
    assert _ONE_STALE in out


def test_untouched_stale_cite_stays_debt_when_quote_is_deleted(tmp_path: Path) -> None:
    """Base debt with no quote left at HEAD does not block."""
    root = _stale_cite_on_feature(tmp_path, _NO_QUOTE)

    code, out = _run_reverse(root)

    assert code == 0, out
    assert _ONE_STALE in out


def test_edited_stale_cite_still_blocks_after_a_shift(tmp_path: Path) -> None:
    """A citing line the branch edits owns its citation, even inherited drift."""
    root = _stale_cite_on_feature(tmp_path, _SHIFTED)
    _commit(root, "docs/notes.md", "The fast-stage" + _cite(_NAME)[3:], "reword")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "docs/notes.md:1" in out
    assert "none of the cited anchors" in out
    assert "; 0 already stale at the merge base" in out


_CLUSTER = "alpha_line_aaaa\nbeta_line_bbbb\ngamma_line_cccc\ndelta_line_dddd\n"
_PAD = "# pad one\n# pad two\n# pad three\n"


def test_four_moved_lines_under_a_stale_untouched_range_stay_debt(tmp_path: Path) -> None:
    """A range already wrong at the base does not block when its lines shift.

    Intended: the owner accepted that eval case C1-01 is no longer caught
    (decision D1, 2026-11-20). Do not restore a moved-cluster exception.
    """
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, TARGET, _CLUSTER, "cited")
    _commit(root, _DOC, f"See `{TARGET}:1-4` (`not_in_file_zzzz`).\n", "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, TARGET, _PAD + _CLUSTER, "shift")

    code, output = _run_reverse(root)

    assert code == 0, output
    assert "; 1 already stale at the merge base (not blocking)" in output


def test_shift_blocks_the_valid_cite_and_counts_the_stale_one(tmp_path: Path) -> None:
    """One shift breaks a valid cite and moves a stale one; only the first blocks."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, TARGET, _CLUSTER, "cited")
    valid = f"Read `{TARGET}:2` for `beta_line_bbbb`.\n"
    stale = f"Read `{TARGET}:1` for `delta_line_dddd`.\n"
    _commit(root, _DOC, valid + stale, "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, TARGET, _PAD + _CLUSTER, "shift")

    code, output = _run_reverse(root)

    assert code == 1, output
    assert f"{_DOC}:1: {TARGET}:2" in output
    assert f"{_DOC}:2:" not in output
    assert "; 1 already stale at the merge base (not blocking)" in output
