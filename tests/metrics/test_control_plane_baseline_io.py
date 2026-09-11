"""IO-boundary tests for control_plane_baseline.py (CodeRabbit review, PR #5725).

Split from test_control_plane_baseline.py to keep that file at the 500-line
taste-lint ratchet (see its module docstring). Covers three review findings:
malformed-shape JSON degrading to an exclusion instead of an AttributeError,
``_git_output`` converting a timeout to ``RuntimeError``, and ``_safe_open``
narrowing a pre-existing report file's mode via ``fchmod``.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.metrics import control_plane_baseline as cpb


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- JSON structure validation (thread: "Validate JSON structure before
# dimension extraction") -----------------------------------------------------


def test_negative_claude_hooks_non_object_root_excludes_instead_of_raising(
    tmp_path: Path,
) -> None:
    _write(tmp_path, ".claude/settings.json", "[1, 2, 3]")
    exclusions: list[dict[str, str]] = []
    result = cpb.canonical(tmp_path, exclusions)
    assert result["hooks_by_event"] == {}
    assert any(
        e["dimension"] == "canonical.hooks" and "root is not a JSON object" in e["reason"]
        for e in exclusions
    )


def test_negative_claude_hooks_non_object_hooks_key_excludes(tmp_path: Path) -> None:
    _write(tmp_path, ".claude/settings.json", '{"hooks": "not-an-object"}')
    exclusions: list[dict[str, str]] = []
    result = cpb.canonical(tmp_path, exclusions)
    assert result["hooks_by_event"] == {}
    assert any(
        e["dimension"] == "canonical.hooks" and "'hooks' is not an object" in e["reason"]
        for e in exclusions
    )


def test_negative_claude_hooks_non_list_matcher_excludes_that_event_only(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        ".claude/settings.json",
        '{"hooks": {"SessionStart": "not-a-list", "Stop": [{"hooks": [{"a": 1}]}]}}',
    )
    exclusions: list[dict[str, str]] = []
    result = cpb.canonical(tmp_path, exclusions)
    assert result["hooks_by_event"] == {"Stop": 1}
    assert any(
        e["dimension"] == "canonical.hooks" and "hooks.SessionStart is not a list" in e["reason"]
        for e in exclusions
    )


def test_negative_accepted_tasks_non_object_root_returns_none_with_reason(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "scripts/eval/examples/harness-capability-matrix.json", "[1, 2]")
    exclusions: list[dict[str, str]] = []
    assert cpb.accepted_tasks(tmp_path, exclusions) is None
    assert any(
        e["dimension"] == "accepted_tasks" and "root is not a JSON object" in e["reason"]
        for e in exclusions
    )


def test_negative_accepted_tasks_non_list_harnesses_returns_none_with_reason(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/eval/examples/harness-capability-matrix.json",
        '{"harnesses": {"not": "a list"}}',
    )
    exclusions: list[dict[str, str]] = []
    assert cpb.accepted_tasks(tmp_path, exclusions) is None
    assert any(
        e["dimension"] == "accepted_tasks" and "'harnesses' is not a list" in e["reason"]
        for e in exclusions
    )


def test_negative_accepted_tasks_non_object_harness_entry_skips_and_excludes(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/eval/examples/harness-capability-matrix.json",
        '{"harnesses": ["not-an-object", {"capabilities": {"x": {"status": "VERIFIED"}}}]}',
    )
    exclusions: list[dict[str, str]] = []
    result = cpb.accepted_tasks(tmp_path, exclusions)
    assert result == {"verified": 1, "unverified": 0, "other": 0, "total": 1}
    assert any(
        e["dimension"] == "accepted_tasks" and "harness entry is not an object" in e["reason"]
        for e in exclusions
    )


def test_negative_accepted_tasks_non_object_capabilities_skips_and_excludes(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "scripts/eval/examples/harness-capability-matrix.json",
        '{"harnesses": [{"capabilities": "not-an-object"}]}',
    )
    exclusions: list[dict[str, str]] = []
    result = cpb.accepted_tasks(tmp_path, exclusions)
    assert result == {"verified": 0, "unverified": 0, "other": 0, "total": 0}
    assert any(
        e["dimension"] == "accepted_tasks" and "capabilities is not an object" in e["reason"]
        for e in exclusions
    )


# --- Git subprocess timeout (thread: "Handle Git timeout and decoding
# failures") -----------------------------------------------------------------


def test_negative_git_output_timeout_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git status", timeout=30)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    with pytest.raises(RuntimeError, match="timed out after 30 seconds"):
        cpb._git_output(tmp_path, ["status", "--porcelain"])


# --- Owner-only mode on a pre-existing file (thread: "Enforce owner-only
# mode for existing report files") -------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits; os.fchmod is POSIX-only")
def test_negative_safe_open_narrows_preexisting_broader_mode(tmp_path: Path) -> None:
    target = tmp_path / "existing.json"
    target.write_text("stale\n", encoding="utf-8")
    target.chmod(0o644)
    assert stat.S_IMODE(target.stat().st_mode) == 0o644, "chmod before open did not land"
    fd = cpb._safe_open(target)
    try:
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    finally:
        os.close(fd)
