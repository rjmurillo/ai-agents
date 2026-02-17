"""Verify all hooks and skill scripts use the standard plugin path resolution pattern.

ADR-047 requires that:
1. Every file importing from hook_utilities or github_core uses CLAUDE_PLUGIN_ROOT
   for path resolution (not early exit).
2. No hook uses sys.exit(0) gated on CLAUDE_PLUGIN_ROOT (the plugin IS the system).
3. Skill scripts that previously skipped on missing .agents/ now create directories.

This test prevents regression to the "skip in plugin mode" anti-pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

# Patterns that indicate lib imports requiring plugin path resolution
LIB_IMPORT_MARKERS = (
    "from hook_utilities",
    "from github_core",
)

# The anti-pattern: early exit in plugin mode
PLUGIN_SKIP_PATTERN = 'if os.environ.get("CLAUDE_PLUGIN_ROOT"):\n    sys.exit(0)'

# The required pattern: CLAUDE_PLUGIN_ROOT used for path resolution
PLUGIN_PATH_PATTERN = 'os.environ.get("CLAUDE_PLUGIN_ROOT")'


def _collect_python_files(directory: Path) -> list[Path]:
    """Collect all .py files recursively, excluding __pycache__ and tests."""
    return [
        p
        for p in directory.rglob("*.py")
        if "__pycache__" not in str(p) and "tests" not in str(p)
    ]


def _has_lib_import(content: str) -> bool:
    """Check if file imports from the shared lib (hook_utilities or github_core)."""
    return any(marker in content for marker in LIB_IMPORT_MARKERS)


class TestPluginPathResolution:
    """Verify hooks use CLAUDE_PLUGIN_ROOT for path resolution, not early exit."""

    @pytest.fixture
    def hook_files(self) -> list[Path]:
        return _collect_python_files(HOOKS_DIR)

    def test_no_plugin_mode_early_exit_in_hooks(self, hook_files: list[Path]) -> None:
        """No hook should sys.exit(0) when CLAUDE_PLUGIN_ROOT is set (ADR-047)."""
        violations = []
        for hook_path in hook_files:
            content = hook_path.read_text(encoding="utf-8")
            if PLUGIN_SKIP_PATTERN in content:
                rel = hook_path.relative_to(REPO_ROOT)
                violations.append(str(rel))

        assert not violations, (
            "Hooks with plugin-mode early exit (violates ADR-047):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_hooks_with_lib_imports_use_plugin_root(
        self, hook_files: list[Path],
    ) -> None:
        """Hooks importing from lib must use CLAUDE_PLUGIN_ROOT for path resolution."""
        violations = []
        for hook_path in hook_files:
            content = hook_path.read_text(encoding="utf-8")
            if _has_lib_import(content) and PLUGIN_PATH_PATTERN not in content:
                rel = hook_path.relative_to(REPO_ROOT)
                violations.append(str(rel))

        assert not violations, (
            "Hooks importing from lib but missing CLAUDE_PLUGIN_ROOT resolution:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestSkillPluginPathResolution:
    """Verify skill scripts use CLAUDE_PLUGIN_ROOT for import resolution."""

    @pytest.fixture
    def skill_scripts_with_lib_imports(self) -> list[Path]:
        scripts = _collect_python_files(SKILLS_DIR)
        return [s for s in scripts if _has_lib_import(s.read_text(encoding="utf-8"))]

    def test_skill_scripts_use_plugin_root(
        self, skill_scripts_with_lib_imports: list[Path],
    ) -> None:
        """Skill scripts importing from lib must use CLAUDE_PLUGIN_ROOT."""
        violations = []
        for script_path in skill_scripts_with_lib_imports:
            content = script_path.read_text(encoding="utf-8")
            if PLUGIN_PATH_PATTERN not in content:
                rel = script_path.relative_to(REPO_ROOT)
                violations.append(str(rel))

        assert not violations, (
            "Skill scripts importing from lib but missing CLAUDE_PLUGIN_ROOT:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_skip_on_missing_agents_dir(self) -> None:
        """No skill script should skip when .agents/ is missing (ADR-047)."""
        skip_pattern = '[SKIP] .agents/ not found'
        violations = []
        for script_path in _collect_python_files(SKILLS_DIR):
            content = script_path.read_text(encoding="utf-8")
            if skip_pattern in content:
                rel = script_path.relative_to(REPO_ROOT)
                violations.append(str(rel))

        assert not violations, (
            "Scripts that skip on missing .agents/ (should create instead):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
