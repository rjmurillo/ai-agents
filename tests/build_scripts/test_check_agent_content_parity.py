"""Tests for build/scripts/check_agent_content_parity.py (Issue #4082).

The gate compares .claude/agents/ and src/claude/ byte-for-byte and fails
when any shared file differs or when a file is present in one tree but absent
from the other (excluding known tree-specific files).

Tests:
- Positive: identical trees pass (exit 0).
- Negative: content mismatch fails (exit 1).
- Negative: file missing from src/claude fails (exit 1).
- Negative: file missing from .claude/agents fails (exit 1).
- Edge: exempt files do not trigger failures.
- Negative: a returning .claude/agents/CLAUDE.md stub fails (issue #5493).
- Edge: JSON output format is parseable and accurate.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "build" / "scripts" / "check_agent_content_parity.py"

_spec = importlib.util.spec_from_file_location("check_agent_content_parity", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["check_agent_content_parity"] = _mod
_spec.loader.exec_module(_mod)

main = _mod.main
ALLOWED_ONLY_IN_CLAUDE = _mod.ALLOWED_ONLY_IN_CLAUDE
ALLOWED_ONLY_IN_SRC = _mod.ALLOWED_ONLY_IN_SRC


def _make_trees(tmp_path: Path) -> tuple[Path, Path]:
    """Return (claude_dir, src_dir) - both empty dirs inside tmp_path."""
    claude = tmp_path / ".claude" / "agents"
    src = tmp_path / "src" / "claude"
    claude.mkdir(parents=True)
    src.mkdir(parents=True)
    # pyproject.toml required by _find_repo_root
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    return claude, src


# ---------------------------------------------------------------------------
# Positive: trees are identical -> exit 0
# ---------------------------------------------------------------------------

def test_identical_trees_pass(tmp_path: Path) -> None:
    claude, src = _make_trees(tmp_path)
    content = b"# Agent\n\nSome content.\n"
    (claude / "analyst.md").write_bytes(content)
    (src / "analyst.md").write_bytes(content)

    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 0


def test_empty_trees_pass(tmp_path: Path) -> None:
    _make_trees(tmp_path)
    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 0


def test_check_flag_is_not_supported(tmp_path: Path) -> None:
    _make_trees(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(["--repo-root", str(tmp_path), "--check"])

    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Negative: drift -> exit 1
# ---------------------------------------------------------------------------

def test_content_mismatch_fails(tmp_path: Path) -> None:
    claude, src = _make_trees(tmp_path)
    (claude / "analyst.md").write_bytes(b"# Agent v2\n")
    (src / "analyst.md").write_bytes(b"# Agent v1\n")

    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 1


def test_missing_from_src_fails(tmp_path: Path) -> None:
    claude, src = _make_trees(tmp_path)
    (claude / "new-agent.md").write_bytes(b"# New agent\n")
    # src/claude/new-agent.md absent

    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 1


def test_missing_from_claude_fails(tmp_path: Path) -> None:
    claude, src = _make_trees(tmp_path)
    (src / "new-agent.md").write_bytes(b"# New agent\n")
    # .claude/agents/new-agent.md absent

    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 1


# ---------------------------------------------------------------------------
# Edge: exempt files do not cause failures
# ---------------------------------------------------------------------------

def test_allowed_only_in_claude_no_failure(tmp_path: Path) -> None:
    if not ALLOWED_ONLY_IN_CLAUDE:
        pytest.skip(
            "ALLOWED_ONLY_IN_CLAUDE is empty since issue #5493. An empty set "
            "would make this loop iterate zero times and pass vacuously; "
            "test_claude_md_stub_is_not_exempt pins the contract instead."
        )
    claude, src = _make_trees(tmp_path)
    for name in ALLOWED_ONLY_IN_CLAUDE:
        (claude / name).write_bytes(b"# Claude-only\n")
    # Nothing in src

    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 0


def test_allowed_only_in_src_no_failure(tmp_path: Path) -> None:
    claude, src = _make_trees(tmp_path)
    for name in ALLOWED_ONLY_IN_SRC:
        (src / name).write_bytes(b"# Src-only\n")
    # Nothing in claude

    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 0


# ---------------------------------------------------------------------------
# Negative: the claude-mem stub is no longer exempt (issue #5493)
# ---------------------------------------------------------------------------

def test_claude_md_stub_is_not_exempt(tmp_path: Path) -> None:
    """A returning .claude/agents/CLAUDE.md fails, it is not skipped.

    Issue #5493 removed "CLAUDE.md" from ALLOWED_ONLY_IN_CLAUDE so the
    claude-mem stub cannot come back silently. This pins that removal
    directly rather than through the now-empty exemption set.
    """
    claude, _src = _make_trees(tmp_path)
    (claude / "CLAUDE.md").write_bytes(
        b"<claude-mem-context>\n*No recent activity*\n</claude-mem-context>\n"
    )

    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 1


# ---------------------------------------------------------------------------
# Edge: JSON output is parseable and correct
# ---------------------------------------------------------------------------

def test_json_output_on_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    claude, src = _make_trees(tmp_path)
    (claude / "analyst.md").write_bytes(b"# Agent v2\n")
    (src / "analyst.md").write_bytes(b"# Agent v1\n")

    rc = main(["--repo-root", str(tmp_path), "--format", "json"])
    assert rc == 1

    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["total_issues"] == 1
    assert "analyst.md" in report["diffs"]
    assert report["missing_from_src"] == []
    assert report["missing_from_claude"] == []


def test_json_output_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    claude, src = _make_trees(tmp_path)
    content = b"# Agent\n"
    (claude / "qa.md").write_bytes(content)
    (src / "qa.md").write_bytes(content)

    rc = main(["--repo-root", str(tmp_path), "--format", "json"])
    assert rc == 0

    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["total_issues"] == 0
    assert report["diffs"] == []


# ---------------------------------------------------------------------------
# Edge: missing directory errors out cleanly (exit 2)
# ---------------------------------------------------------------------------

def test_missing_claude_dir_returns_2(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    # Neither .claude/agents nor src/claude exist
    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 2


# ---------------------------------------------------------------------------
# Load-bearing proof: gate passes on current repo (all 15 diffs are fixed)
# ---------------------------------------------------------------------------

def test_current_repo_trees_are_in_parity() -> None:
    """The gate must pass against the real repo trees after the sync fix.

    If this test fails, the sync of the 15 drifted files in Issue #4082 did
    not complete or a new drift was introduced.
    """
    rc = main(["--repo-root", str(_REPO_ROOT)])
    assert rc == 0, (
        "check_agent_content_parity reported drift in the live repo. "
        "Run build/scripts/check_agent_content_parity.py to see which files differ."
    )
