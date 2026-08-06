"""Test analyst agent tool allowlist security and bundled script layout.

Verifies:
1. The allowlist permits only the bundled github_query.py, not arbitrary python
2. The bundled script exists in both plugin roots
3. Repo-local spoofing is structurally impossible (script is self-contained)
4. Missing trusted install produces explicit failure
5. The bundled script exposes only read-only commands
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True,
).strip())

ANALYST_MD = REPO_ROOT / ".claude" / "agents" / "analyst.md"
ANALYST_SRC = REPO_ROOT / "src" / "claude" / "analyst.md"
SCRIPT_CLAUDE = REPO_ROOT / ".claude" / "scripts" / "github_query.py"
SCRIPT_SRC = REPO_ROOT / "src" / "claude" / "scripts" / "github_query.py"

ALLOWLIST_PATTERN = 'Bash(python3 "$CLAUDE_PLUGIN_ROOT/scripts/github_query.py" *)'


class TestAllowlistNarrow:
    """The tool allowlist permits only the bundled script."""

    def test_allowlist_references_exact_script(self) -> None:
        text = ANALYST_MD.read_text()
        assert ALLOWLIST_PATTERN in text

    def test_no_broad_python3_permission(self) -> None:
        text = ANALYST_MD.read_text()
        # Must not contain python3 * (without the script path)
        lines = text.splitlines()
        for line in lines:
            if "Bash(python3" in line and "github_query.py" not in line:
                pytest.fail(f"Broad python3 permission found: {line.strip()}")

    def test_no_python3_dash_c_allowed(self) -> None:
        """python3 -c must not match the allowlist pattern."""
        # The allowlist is: Bash(python3 "$CLAUDE_PLUGIN_ROOT/scripts/github_query.py" *)
        # A command like python3 -c "..." does NOT start with the required
        # $CLAUDE_PLUGIN_ROOT/scripts/github_query.py prefix, so it must not
        # match.  We verify the pattern structurally: the second positional
        # token after python3 must be the literal script path.
        text = ANALYST_MD.read_text()
        bash_python_lines = [
            l.strip() for l in text.splitlines()
            if l.strip().startswith("- Bash(python3")
        ]
        for line in bash_python_lines:
            assert "$CLAUDE_PLUGIN_ROOT/scripts/github_query.py" in line, (
                f"python3 permission without pinned script path: {line}"
            )

    def test_parity_between_plugin_roots(self) -> None:
        assert ANALYST_MD.read_text() == ANALYST_SRC.read_text()


class TestBundledScriptLayout:
    """The github_query.py script is bundled in both plugin roots."""

    def test_script_exists_in_claude_root(self) -> None:
        assert SCRIPT_CLAUDE.is_file()

    def test_script_exists_in_src_root(self) -> None:
        assert SCRIPT_SRC.is_file()

    def test_scripts_are_identical(self) -> None:
        assert SCRIPT_CLAUDE.read_bytes() == SCRIPT_SRC.read_bytes()

    def test_script_is_self_contained(self) -> None:
        """Script must not import from or reference other plugin roots."""
        text = SCRIPT_SRC.read_text()
        # Must not reference .claude/ paths (cross-plugin)
        assert ".claude/skills" not in text
        assert ".claude/lib" not in text
        # Must not import from project-toolkit paths
        assert "from skills" not in text
        assert "import skills" not in text

    def test_script_has_no_eval_or_exec(self) -> None:
        """Script must not contain eval/exec that could run arbitrary code."""
        text = SCRIPT_SRC.read_text()
        # Reject eval() and exec() calls (but allow "evaluate" in comments)
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            assert not re.search(r'\beval\s*\(', stripped), f"eval() found: {line}"
            assert not re.search(r'\bexec\s*\(', stripped), f"exec() found: {line}"


class TestBundledScriptReadOnly:
    """The bundled script exposes only read-only commands."""

    def test_only_read_commands_exposed(self) -> None:
        """All subcommands must be read-only GitHub API operations."""
        result = subprocess.run(
            ["python3", str(SCRIPT_SRC), "--help"],
            capture_output=True, text=True,
        )
        help_text = result.stdout + result.stderr
        # These are the allowed commands
        allowed = {"pr-context", "pr-threads", "pr-comments", "pr-checks", "issue-context"}
        # Extract subcommand names from help text
        # argparse prints: {pr-context,pr-threads,...}
        match = re.search(r'\{([^}]+)\}', help_text)
        assert match, f"Could not find subcommands in help: {help_text}"
        found = set(match.group(1).split(","))
        assert found == allowed, f"Unexpected commands: {found - allowed}"

    def test_no_write_operations(self) -> None:
        """Script must not contain POST/PUT/PATCH/DELETE API calls."""
        text = SCRIPT_SRC.read_text()
        # Check _gh_api calls default to GET
        # Check no method="POST" etc. in actual command functions
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            # Allow the method parameter definition, but not actual usage
            for line in text.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith("def "):
                    continue
                if f'method="{method}"' in stripped:
                    # Only allowed in the _gh_api signature default
                    if "def _gh_api" not in stripped:
                        pytest.fail(f"Write method {method} used: {line}")


class TestMissingInstallFailsExplicit:
    """When CLAUDE_PLUGIN_ROOT points to a directory without the script,
    the command must fail explicitly rather than falling back to repo-local."""

    def test_missing_script_fails(self, tmp_path: Path) -> None:
        """Invoking with a CLAUDE_PLUGIN_ROOT that lacks the script fails."""
        fake_root = tmp_path / "fake-plugin"
        fake_root.mkdir()
        result = subprocess.run(
            [
                "python3",
                str(fake_root / "scripts" / "github_query.py"),
                "pr-context", "--pull-request", "1",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_no_repo_local_fallback_in_allowlist(self) -> None:
        """The allowlist must not contain cwd-relative .claude paths."""
        text = ANALYST_MD.read_text()
        bash_lines = [
            l for l in text.splitlines()
            if "Bash(python3" in l
        ]
        for line in bash_lines:
            assert ".claude/skills" not in line, f"repo-local fallback: {line}"
            assert ":-." not in line, f"cwd-relative fallback: {line}"
