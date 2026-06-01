#!/usr/bin/env python3
"""Tests for the invoke_lsp_pre_delegation_guard PreToolUse hook (ADR-062).

Covers: enforced-subagent detection, LSP-context detection, provider-conditioned
blocking, LSP_GATE_MODE=warn, exit codes (0=allow, 2=block), the SKIP_LSP_GATE
kill switch, and EVERY fail-open path (tty, empty stdin, malformed JSON, missing
tool_input, non-dict tool_input, wrong tool_name, exempt subagent, short prompt,
context-present, no-provider-available, exception). Includes subprocess
stdin-feeding tests and a runpy entry-point test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = str(REPO_ROOT / ".claude" / "hooks" / "PreToolUse")
HOOK_PATH = Path(HOOK_DIR) / "invoke_lsp_pre_delegation_guard.py"
sys.path.insert(0, HOOK_DIR)

import invoke_lsp_pre_delegation_guard as guard  # noqa: E402

# Capture the real provider_available before any autouse stub patches it, so
# TestProviderAvailable can exercise the genuine body (lines that call
# detect_providers) for coverage.
_REAL_PROVIDER_AVAILABLE = guard.provider_available

# A prompt long enough to clear the 200-char floor, with no LSP CONTEXT marker.
LONG_PROMPT_NO_CONTEXT = (
    "Implement the new feature in the codebase. " * 8
)  # > 200 chars
# A prompt long enough, WITH an LSP CONTEXT marker.
LONG_PROMPT_WITH_CONTEXT = (
    "## LSP CONTEXT (pre-resolved)\n- foo: defined at a.py:42\n"
    + ("Do the work. " * 20)
)


def _stdin_json(**fields: object) -> str:
    return json.dumps(fields)


@pytest.fixture(autouse=True)
def _clear_gate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no ambient SKIP_LSP_GATE / LSP_GATE_MODE leaks into a test."""
    monkeypatch.delenv("SKIP_LSP_GATE", raising=False)
    monkeypatch.delenv("LSP_GATE_MODE", raising=False)


@pytest.fixture(autouse=True)
def _allow_project_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: not a consumer repo, so the guard does not early-allow on that."""
    monkeypatch.setattr(guard, "skip_if_consumer_repo", lambda _name: False)


@pytest.fixture(autouse=True)
def _provider_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: a provider is available (so the block path is reachable)."""
    monkeypatch.setattr(guard, "provider_available", lambda _pd: True)


# ---------------------------------------------------------------------------
# Unit tests for is_enforced_subagent
# ---------------------------------------------------------------------------


class TestIsEnforcedSubagent:
    def test_implementer_enforced(self):
        assert guard.is_enforced_subagent("implementer")

    def test_context_retrieval_enforced(self):
        assert guard.is_enforced_subagent("context-retrieval")

    def test_case_insensitive(self):
        assert guard.is_enforced_subagent("Implementer")
        assert guard.is_enforced_subagent("CONTEXT-RETRIEVAL")

    def test_whitespace_trimmed(self):
        assert guard.is_enforced_subagent("  implementer  ")

    def test_reviewer_exempt(self):
        assert not guard.is_enforced_subagent("architect")
        assert not guard.is_enforced_subagent("qa")
        assert not guard.is_enforced_subagent("security")
        assert not guard.is_enforced_subagent("critic")

    def test_unknown_exempt(self):
        assert not guard.is_enforced_subagent("totally-unknown-agent")

    def test_empty_exempt(self):
        assert not guard.is_enforced_subagent("")


# ---------------------------------------------------------------------------
# Unit tests for has_lsp_context (faithful port of kit hasLspContext)
# ---------------------------------------------------------------------------


class TestHasLspContext:
    def test_lsp_context_marker(self):
        assert guard.has_lsp_context("here is the ## LSP CONTEXT block")

    def test_symbol_map_marker(self):
        assert guard.has_lsp_context("See the Symbol Map below")

    def test_defined_at(self):
        assert guard.has_lsp_context("foo defined at path/to/file.py:42")

    def test_called_from(self):
        assert guard.has_lsp_context("bar called from src/a.ts:15")

    def test_used_in(self):
        assert guard.has_lsp_context("baz used in lib/x.py:9")

    def test_imported_in(self):
        assert guard.has_lsp_context("qux imported in mod/y.py:3")

    def test_imported_by(self):
        assert guard.has_lsp_context("qux imported by mod/y.py:3")

    def test_case_insensitive(self):
        assert guard.has_lsp_context("lsp context")

    def test_absent(self):
        assert not guard.has_lsp_context("just implement the feature please")


# ---------------------------------------------------------------------------
# Unit tests for provider_available (real lib, not the autouse stub)
# ---------------------------------------------------------------------------


class TestProviderAvailable:
    @pytest.fixture(autouse=True)
    def _use_real_provider_available(self, monkeypatch: pytest.MonkeyPatch):
        # Undo the module-level autouse stub so the real body (which calls
        # detect_providers) executes and is covered.
        monkeypatch.setattr(
            guard,
            "provider_available",
            guard.provider_available.__wrapped__
            if hasattr(guard.provider_available, "__wrapped__")
            else _REAL_PROVIDER_AVAILABLE,
        )

    def test_true_for_code_repo(self):
        # The real implementation against this repo's .serena/project.yml.
        assert guard.provider_available(str(REPO_ROOT)) is True

    def test_false_for_non_code_target(self, monkeypatch: pytest.MonkeyPatch):
        # Force detect_providers to return [] so the bool(providers) -> False
        # branch is exercised through the real provider_available body.
        monkeypatch.setattr(guard, "detect_providers", lambda *_a, **_k: [])
        assert guard.provider_available(str(REPO_ROOT)) is False


# ---------------------------------------------------------------------------
# Unit tests for build_guidance
# ---------------------------------------------------------------------------


class TestBuildGuidance:
    def test_names_subagent_and_section(self):
        msg = guard.build_guidance("implementer")
        assert "implementer" in msg
        assert "LSP CONTEXT" in msg
        assert "BLOCKED" in msg

    def test_no_dashes(self):
        # Universal rule: no em-dash (U+2014) or en-dash (U+2013) in authored
        # text. Reference the codepoints by escape so this file stays clean.
        msg = guard.build_guidance("implementer")
        assert "\u2014" not in msg  # em dash
        assert "\u2013" not in msg  # en dash


# ---------------------------------------------------------------------------
# main(): fail-open paths
# ---------------------------------------------------------------------------


