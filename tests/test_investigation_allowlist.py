"""Tests for scripts.modules.investigation_allowlist module."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from scripts.modules.investigation_allowlist import (
    get_investigation_allowlist,
    get_investigation_allowlist_display,
)
from scripts.modules.investigation_allowlist import (
    test_file_matches_allowlist as file_matches_allowlist,
)


class TestGetInvestigationAllowlist:
    def test_returns_non_empty_list(self) -> None:
        result = get_investigation_allowlist()
        assert len(result) > 0

    def test_patterns_are_anchored(self) -> None:
        for pattern in get_investigation_allowlist():
            assert pattern.startswith("^"), f"Pattern not anchored: {pattern}"


class TestGetInvestigationAllowlistDisplay:
    def test_returns_non_empty_list(self) -> None:
        result = get_investigation_allowlist_display()
        assert len(result) > 0

    def test_same_count_as_allowlist(self) -> None:
        assert len(get_investigation_allowlist()) == len(get_investigation_allowlist_display())


class TestFileMatchesAllowlist:
    def test_matches_sessions_path(self) -> None:
        assert file_matches_allowlist(".agents/sessions/log.json") is True

    def test_matches_analysis_path(self) -> None:
        assert file_matches_allowlist(".agents/analysis/report.md") is True

    def test_matches_serena_memories(self) -> None:
        assert file_matches_allowlist(".serena/memories/test.md") is True

    def test_rejects_source_code(self) -> None:
        assert file_matches_allowlist("src/main.py") is False

    def test_rejects_scripts(self) -> None:
        assert file_matches_allowlist("scripts/build.py") is False

    def test_normalizes_backslashes(self) -> None:
        assert file_matches_allowlist(".agents\\sessions\\log.json") is True

    def test_matches_architecture_review(self) -> None:
        assert file_matches_allowlist(".agents/architecture/REVIEW-001.md") is True

    def test_rejects_architecture_adr(self) -> None:
        assert file_matches_allowlist(".agents/architecture/ADR-001.md") is False


@lru_cache(maxsize=1)
def _load_session_skill_module() -> ModuleType:
    """Load the packaged session-skill eligibility script by path.

    The script ships to installed-plugin trees, so it keeps a verbatim copy
    of the allowlist instead of importing the repo-relative module. This
    loader lets the parity test compare the two in-repo. The result is cached
    so the script executes once across the whole test class.
    """
    script = (
        Path(__file__).resolve().parents[1]
        / ".claude"
        / "skills"
        / "session"
        / "scripts"
        / "test_investigation_eligibility.py"
    )
    assert script.is_file(), f"session-skill eligibility script missing: {script}"
    spec = importlib.util.spec_from_file_location("_session_eligibility", script)
    assert spec is not None and spec.loader is not None, (
        f"could not build import spec for {script}"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSessionSkillAllowlistParity:
    """Lock the session-skill allowlist copy to the canonical module (#2966).

    The session skill cannot import scripts.modules.investigation_allowlist at
    runtime because it is packaged into plugin trees where scripts/ is absent.
    These tests fail CI if the verbatim copy drifts from the module, which is
    the DRY gap the ADR-034 amendment deferred.
    """

    def test_patterns_match_module(self) -> None:
        skill = _load_session_skill_module()
        assert list(skill._ALLOWLIST_PATTERNS) == get_investigation_allowlist()

    def test_display_matches_module(self) -> None:
        skill = _load_session_skill_module()
        assert list(skill._ALLOWLIST_DISPLAY) == get_investigation_allowlist_display()

    def test_match_behavior_matches_module(self) -> None:
        skill = _load_session_skill_module()
        samples = [
            ".agents/sessions/log.json",
            ".agents/memory/episodes/ep.json",
            ".serena/memories/note.md",
            ".agents/architecture/REVIEW-1.md",
            ".agents/architecture/ADR-1.md",
            "src/main.py",
            "scripts/build.py",
        ]
        for path in samples:
            assert skill._file_matches_allowlist(path) == file_matches_allowlist(path), path
