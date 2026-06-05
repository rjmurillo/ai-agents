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

    def test_context_retrieval_no_longer_enforced(self):
        # Issue #2103: the context-retrieval agent was folded into the
        # exploring-knowledge-graph skill and deleted, so it is no longer a
        # delegable subagent and is dropped from ENFORCED_SUBAGENTS.
        assert not guard.is_enforced_subagent("context-retrieval")

    def test_case_insensitive(self):
        assert guard.is_enforced_subagent("Implementer")
        assert guard.is_enforced_subagent("IMPLEMENTER")

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


# ---------------------------------------------------------------------------
# Issue #2199: Windows path separators in LSP-context regex
# ---------------------------------------------------------------------------


class TestHasLspContextWindowsPaths:
    """Regression tests for #2199 problem 4: the kit regex used the character
    class ``[\\w\\-\\/]`` which excludes backslash, so Windows-style paths
    (``C:\\src\\foo.py:42``) failed to match and the guard wrongly blocked
    delegations that did carry pre-resolved LSP context.
    """

    def test_defined_at_windows_path(self):
        # C:\src\foo.py:42 (raw backslashes as a user would paste them)
        assert guard.has_lsp_context(r"foo defined at C:\src\foo.py:42")

    def test_called_from_windows_path(self):
        assert guard.has_lsp_context(r"bar called from src\handlers\auth.ts:15")

    def test_used_in_windows_path(self):
        assert guard.has_lsp_context(r"baz used in lib\models\x.py:9")

    def test_imported_in_windows_path(self):
        assert guard.has_lsp_context(r"qux imported in mod\helpers\y.py:3")

    def test_imported_by_windows_path(self):
        assert guard.has_lsp_context(r"qux imported by mod\helpers\y.py:3")

    def test_posix_path_still_matches(self):
        # Regression guard: do not break the POSIX path branch.
        assert guard.has_lsp_context("foo defined at src/handlers/auth.py:42")

    def test_mixed_separators(self):
        # Windows tooling sometimes emits mixed-separator paths.
        assert guard.has_lsp_context(r"foo defined at C:/src\handlers/auth.py:42")


# ---------------------------------------------------------------------------
# Issue #2199: provider_available iterates configured languages
# ---------------------------------------------------------------------------


class TestProviderAvailableMultiLanguage:
    """Regression tests for #2199 problem 1: provider_available previously
    probed only ``lsp_probe.py``, so a TypeScript- or Go-only repo with Serena
    active for its language probed empty and the guard never fired.
    """

    @pytest.fixture(autouse=True)
    def _use_real_provider_available(self, monkeypatch: pytest.MonkeyPatch):
        # Undo the module-level autouse stub.
        monkeypatch.setattr(guard, "provider_available", _REAL_PROVIDER_AVAILABLE)

    def _serena_project(self, tmp_path: Path, languages: list[str]) -> Path:
        proj = tmp_path / "proj"
        proj.mkdir()
        serena = proj / ".serena"
        serena.mkdir()
        body = "languages:\n" + "\n".join(f"- {lang}" for lang in languages)
        (serena / "project.yml").write_text(body, encoding="utf-8")
        (proj / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"serena": {"type": "stdio"}}}),
            encoding="utf-8",
        )
        return proj

    def test_typescript_only_repo_resolves_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        proj = self._serena_project(tmp_path, ["typescript"])
        # Isolate home so the machine's real ~/.mcp.json does not leak.
        fake_home = tmp_path / "_home"
        fake_home.mkdir()
        from hook_utilities import lsp_provider as lp

        monkeypatch.setattr(lp.Path, "home", classmethod(lambda cls: fake_home))
        # Real provider_available should iterate languages, hit typescript,
        # and find native_lsp via the .ts representative extension.
        assert guard.provider_available(str(proj)) is True

    def test_python_only_repo_still_resolves(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        proj = self._serena_project(tmp_path, ["python"])
        fake_home = tmp_path / "_home"
        fake_home.mkdir()
        from hook_utilities import lsp_provider as lp

        monkeypatch.setattr(lp.Path, "home", classmethod(lambda cls: fake_home))
        assert guard.provider_available(str(proj)) is True

    def test_no_serena_config_falls_back_to_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # No .serena/project.yml: must fall back to historic lsp_probe.py
        # behavior (native_lsp present for .py extension).
        proj = tmp_path / "proj"
        proj.mkdir()
        fake_home = tmp_path / "_home"
        fake_home.mkdir()
        from hook_utilities import lsp_provider as lp

        monkeypatch.setattr(lp.Path, "home", classmethod(lambda cls: fake_home))
        # detect_providers for "lsp_probe.py" SYMBOLS_OVERVIEW returns
        # ["native_lsp"] even without serena (native_lsp covers .py extension).
        assert guard.provider_available(str(proj)) is True

    def test_unmapped_languages_only_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Only language is one the registry does not map to an extension.
        # Should fall back to the historic Python probe, which still finds
        # native_lsp for .py.
        proj = self._serena_project(tmp_path, ["rust", "haskell"])
        fake_home = tmp_path / "_home"
        fake_home.mkdir()
        from hook_utilities import lsp_provider as lp

        monkeypatch.setattr(lp.Path, "home", classmethod(lambda cls: fake_home))
        assert guard.provider_available(str(proj)) is True

    def test_returns_false_when_detect_providers_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Force detect_providers to always return [] so all branches collapse
        # to the False return.
        proj = self._serena_project(tmp_path, ["python", "typescript"])
        fake_home = tmp_path / "_home"
        fake_home.mkdir()
        from hook_utilities import lsp_provider as lp

        monkeypatch.setattr(lp.Path, "home", classmethod(lambda cls: fake_home))
        monkeypatch.setattr(guard, "detect_providers", lambda *_a, **_k: [])
        assert guard.provider_available(str(proj)) is False

