"""Tests for scripts/validation/check_orchestrator_citations.py.

The check (Issue #1966) fails when a backtick path citation in
`.claude/commands/pr-quality/all.md` points to a file that does not exist,
so a stale module citation in orchestrator prose is caught locally instead
of misleading the next reader.

Tests build temporary file trees rather than the live repo, to keep the
result independent of the repository's state on any given day.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_orchestrator_citations.py"

_TARGET = ".claude/commands/pr-quality/all.md"


def _load_module():
    """Load the script as a module under a stable name."""
    spec = importlib.util.spec_from_file_location(
        "check_orchestrator_citations",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


coc = _load_module()


def _write_file(repo: Path, relpath: str, content: str) -> Path:
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# --- extract_path_citations (pure) ----------------------------------------


def test_extract_picks_up_path_with_symbol_suffix() -> None:
    text = "Merge logic (canonical: `.claude/lib/ai_review_common/verdict.py:merge_verdicts`)."
    assert coc.extract_path_citations(text) == [".claude/lib/ai_review_common/verdict.py"]


def test_extract_picks_up_bare_path() -> None:
    text = "See `scripts/validation/pr_description.py` for the pattern."
    assert coc.extract_path_citations(text) == ["scripts/validation/pr_description.py"]


@pytest.mark.parametrize(
    "noise",
    [
        "`git branch --show-current`",
        "`/pr-quality:security $ARGUMENTS`",
        "`main`",
        "`VERDICT: TOKEN`",
        "`CRITICAL_FAIL`",
    ],
)
def test_extract_ignores_non_path_tokens(noise: str) -> None:
    """Slash commands, bare words, and verdict tokens are not path citations."""
    assert coc.extract_path_citations(noise) == []


# --- check_file / collect_broken_citations --------------------------------


def test_resolving_citation_passes(tmp_path: Path) -> None:
    """A cited path that exists on disk yields no broken citation."""
    _write_file(tmp_path, "scripts/real.py", "x = 1\n")
    _write_file(tmp_path, _TARGET, "Logic in `scripts/real.py:run`.\n")
    assert coc.collect_broken_citations(tmp_path) == []


def test_broken_citation_detected(tmp_path: Path) -> None:
    """A cited path that does not exist is reported as broken."""
    _write_file(tmp_path, _TARGET, "Logic in `scripts/gone.py:run`.\n")
    broken = coc.collect_broken_citations(tmp_path)
    assert len(broken) == 1
    assert broken[0].path == "scripts/gone.py"
    assert broken[0].source == _TARGET


def test_symbol_suffix_stripped_before_resolving(tmp_path: Path) -> None:
    """The file resolves even though the citation carries a :symbol suffix."""
    _write_file(tmp_path, "scripts/real.py", "x = 1\n")
    _write_file(tmp_path, _TARGET, "`scripts/real.py:some_func` owns it.\n")
    assert coc.collect_broken_citations(tmp_path) == []


def test_absent_target_file_is_benign(tmp_path: Path) -> None:
    """A missing orchestrator command file yields no broken citations."""
    assert coc.collect_broken_citations(tmp_path) == []


# --- main / exit codes (ADR-035) ------------------------------------------


def test_main_returns_zero_when_all_resolve(tmp_path: Path) -> None:
    _write_file(tmp_path, "scripts/real.py", "x = 1\n")
    _write_file(tmp_path, _TARGET, "`scripts/real.py:run` here.\n")
    assert coc.main(["--repo-root", str(tmp_path)]) == 0


def test_main_returns_one_on_broken_citation(tmp_path: Path) -> None:
    _write_file(tmp_path, _TARGET, "`scripts/gone.py:run` here.\n")
    assert coc.main(["--repo-root", str(tmp_path)]) == 1


def test_main_returns_two_when_repo_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert coc.main(["--repo-root", str(missing)]) == 2


def test_live_repo_citations_resolve() -> None:
    """The committed all.md citations must resolve against the live repo."""
    assert coc.collect_broken_citations(REPO_ROOT) == []
