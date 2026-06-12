"""Tests for pre-push ruff command selection (issue #2574)."""

from __future__ import annotations

from pathlib import Path

_PRE_PUSH = Path(__file__).resolve().parents[1] / ".githooks" / "pre-push"


def _ruff_section() -> str:
    text = _PRE_PUSH.read_text(encoding="utf-8")
    start = text.index("# 6. Python lint (ruff)")
    end = text.index("# 7. Python type check", start)
    return text[start:end]


def test_prefers_uv_managed_ruff_before_path_ruff() -> None:
    section = _ruff_section()

    uv_index = section.index("uv run --frozen --extra dev ruff --version")
    path_index = section.index("elif command -v ruff")
    assert uv_index < path_index


def test_runs_ruff_check_through_resolved_command() -> None:
    section = _ruff_section()

    assert '"${RUFF_CMD[@]}" check -- "${PY_FILES[@]}"' in section
    assert 'record_pass "Python lint/ruff (${#PY_FILES[@]} files via ${RUFF_SOURCE})"' in section


def test_fails_loudly_when_no_ruff_command_resolves() -> None:
    section = _ruff_section()

    assert 'record_fail "Python lint/ruff (no ruff available)"' in section
    assert "uv cannot provision the pinned Python" in section
