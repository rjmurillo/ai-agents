"""Verify all hooks and skill scripts use the standard plugin path resolution pattern.

ADR-047 requires that:
1. Every file importing from hook_utilities or github_core uses CLAUDE_PLUGIN_ROOT
   for path resolution (not early exit).
2. No hook uses sys.exit(0) gated on CLAUDE_PLUGIN_ROOT (the plugin IS the system).
3. Skill scripts that previously skipped on missing .agents/ now create directories.
4. All files with CLAUDE_PLUGIN_ROOT validate the lib directory exists before importing.

This test prevents regression to the "skip in plugin mode" anti-pattern
and ensures the standard boilerplate includes path validation per ADR-047.
"""

from __future__ import annotations

import ast
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

# The required validation: lib directory must exist before importing
LIB_DIR_VALIDATION_PATTERNS = (
    "os.path.isdir(_lib_dir)",
    "os.path.isdir(_LIB_DIR)",
    "os.path.isdir(lib_dir)",
)

# Files that delegate plugin-path resolution to a shared bootstrap helper.
# Importing the helper satisfies the CLAUDE_PLUGIN_ROOT and lib-validation
# requirements transitively; the canonical resolution lives in the helper.
#
# The exemption is granted only when AST analysis confirms BOTH:
#   1. an actual ``ImportFrom`` node with module == "_bootstrap" that
#      imports ``ensure_plugin_paths``, and
#   2. an actual ``Call`` node whose ``func`` resolves to
#      ``ensure_plugin_paths`` (or ``_bootstrap.ensure_plugin_paths``).
#
# A docstring or comment that merely mentions the import string and the
# call string would have satisfied a substring-only check; the AST-based
# check rejects that because text inside string literals is not parsed
# as code.
_BOOTSTRAP_MODULE = "_bootstrap"
_BOOTSTRAP_FUNC = "ensure_plugin_paths"


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


def _has_lib_dir_validation(content: str) -> bool:
    """Check if file validates lib directory exists before importing."""
    return any(pattern in content for pattern in LIB_DIR_VALIDATION_PATTERNS)


def _delegates_to_shared_bootstrap(content: str) -> bool:
    """Check if the file delegates plugin-path resolution to ``_bootstrap``.

    Uses AST analysis (not substring matching) so a docstring or comment
    that happens to contain the import or call text cannot grant the
    exemption. A file qualifies only when its parsed AST contains:

    1. ``from _bootstrap import ... ensure_plugin_paths ...`` AND
    2. an actual call to ``ensure_plugin_paths()`` (bare name) or
       ``_bootstrap.ensure_plugin_paths()`` (attribute form).

    A SyntaxError or any AST traversal failure conservatively denies
    the exemption: a file the test cannot parse has not proven
    delegation, so it must satisfy the inline-pattern checks instead.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    has_import = False
    has_call = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _BOOTSTRAP_MODULE:
            for alias in node.names:
                if alias.name == _BOOTSTRAP_FUNC:
                    has_import = True
                    break
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == _BOOTSTRAP_FUNC:
                has_call = True
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == _BOOTSTRAP_FUNC
                and isinstance(func.value, ast.Name)
                and func.value.id == _BOOTSTRAP_MODULE
            ):
                has_call = True
        if has_import and has_call:
            return True
    return False


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
        """Hooks importing from lib must use CLAUDE_PLUGIN_ROOT for path resolution.

        Files that delegate to the shared ``_bootstrap`` helper satisfy
        this transitively (the helper itself contains the canonical
        resolution).
        """
        violations = []
        for hook_path in hook_files:
            content = hook_path.read_text(encoding="utf-8")
            if not _has_lib_import(content):
                continue
            if PLUGIN_PATH_PATTERN in content:
                continue
            if _delegates_to_shared_bootstrap(content):
                continue
            rel = hook_path.relative_to(REPO_ROOT)
            violations.append(str(rel))

        assert not violations, (
            "Hooks importing from lib but missing CLAUDE_PLUGIN_ROOT resolution:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_hooks_validate_lib_dir_exists(self, hook_files: list[Path]) -> None:
        """Hooks with CLAUDE_PLUGIN_ROOT must validate lib directory exists (ADR-047)."""
        violations = []
        for hook_path in hook_files:
            content = hook_path.read_text(encoding="utf-8")
            if PLUGIN_PATH_PATTERN in content and not _has_lib_dir_validation(content):
                rel = hook_path.relative_to(REPO_ROOT)
                violations.append(str(rel))

        assert not violations, (
            "Hooks with CLAUDE_PLUGIN_ROOT but missing lib dir validation:\n"
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

    def test_skill_scripts_validate_lib_dir_exists(
        self, skill_scripts_with_lib_imports: list[Path],
    ) -> None:
        """Skill scripts with CLAUDE_PLUGIN_ROOT must validate lib dir exists (ADR-047)."""
        violations = []
        for script_path in skill_scripts_with_lib_imports:
            content = script_path.read_text(encoding="utf-8")
            if PLUGIN_PATH_PATTERN in content and not _has_lib_dir_validation(content):
                rel = script_path.relative_to(REPO_ROOT)
                violations.append(str(rel))

        assert not violations, (
            "Skill scripts with CLAUDE_PLUGIN_ROOT but missing lib dir validation:\n"
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
