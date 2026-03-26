#!/usr/bin/env python3
"""Tests for hook contract validation.

Covers: script path extraction, settings parsing, per-entry validators,
cross-entry duplicate detection, output formatting, and CLI integration.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "validation"))

import hook_contracts  # noqa: E402

# ---------------------------------------------------------------------------
# extract_script_path
# ---------------------------------------------------------------------------


class TestExtractScriptPath:
    def test_simple_command(self):
        result = hook_contracts.extract_script_path("python3 -u .claude/hooks/PreToolUse/guard.py")
        assert result == ".claude/hooks/PreToolUse/guard.py"

    def test_no_flags(self):
        result = hook_contracts.extract_script_path("python3 .claude/hooks/stop.py")
        assert result == ".claude/hooks/stop.py"

    def test_multiple_flags(self):
        result = hook_contracts.extract_script_path("python3 -u -B .claude/hooks/hook.py")
        assert result == ".claude/hooks/hook.py"

    def test_no_python(self):
        result = hook_contracts.extract_script_path("pwsh script.ps1")
        assert result is None

    def test_empty_string(self):
        result = hook_contracts.extract_script_path("")
        assert result is None


# ---------------------------------------------------------------------------
# parse_settings
# ---------------------------------------------------------------------------


class TestParseSettings:
    def test_parses_basic_settings(self, tmp_path):
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 -u .claude/hooks/guard.py",
                                "timeout": 5,
                                "statusMessage": "Checking guard",
                            }
                        ],
                    }
                ]
            }
        }
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps(settings))

        _, entries = hook_contracts.parse_settings(settings_path)

        assert len(entries) == 1
        assert entries[0].hook_type == "PreToolUse"
        assert entries[0].script_path == ".claude/hooks/guard.py"
        assert entries[0].matcher == "Bash"
        assert entries[0].timeout == 5
        assert entries[0].status_message == "Checking guard"

    def test_skips_non_command_types(self, tmp_path):
        settings = {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "webhook",
                                "url": "https://example.com",
                            }
                        ],
                    }
                ]
            }
        }
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps(settings))

        _, entries = hook_contracts.parse_settings(settings_path)
        assert len(entries) == 0

    def test_parses_multiple_hook_types(self, tmp_path):
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 guard.py",
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 stop.py",
                            }
                        ],
                    }
                ],
            }
        }
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps(settings))

        _, entries = hook_contracts.parse_settings(settings_path)
        assert len(entries) == 2

    def test_no_hooks_section(self, tmp_path):
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"other": "config"}))

        _, entries = hook_contracts.parse_settings(settings_path)
        assert len(entries) == 0

    def test_group_without_matcher(self, tmp_path):
        settings = {
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 init.py",
                            }
                        ],
                    }
                ]
            }
        }
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps(settings))

        _, entries = hook_contracts.parse_settings(settings_path)
        assert len(entries) == 1
        assert entries[0].matcher is None


# ---------------------------------------------------------------------------
# validate_script_exists
# ---------------------------------------------------------------------------


class TestValidateScriptExists:
    def test_existing_script(self, tmp_path):
        script = tmp_path / ".claude" / "hooks" / "guard.py"
        script.parent.mkdir(parents=True)
        script.write_text("# hook")

        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path=".claude/hooks/guard.py",
            command="python3 .claude/hooks/guard.py",
        )
        assert hook_contracts.validate_script_exists(entry, tmp_path) is None

    def test_missing_script(self, tmp_path):
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path=".claude/hooks/missing.py",
            command="python3 .claude/hooks/missing.py",
        )
        violation = hook_contracts.validate_script_exists(entry, tmp_path)
        assert violation is not None
        assert violation.category == "missing_script"
        assert "missing.py" in violation.message


# ---------------------------------------------------------------------------
# validate_hook_type_known
# ---------------------------------------------------------------------------


class TestValidateHookTypeKnown:
    @pytest.mark.parametrize(
        "hook_type",
        [
            "PreToolUse",
            "PostToolUse",
            "Stop",
            "SubagentStop",
            "SessionStart",
            "UserPromptSubmit",
            "PermissionRequest",
        ],
    )
    def test_known_types(self, hook_type):
        entry = hook_contracts.HookEntry(
            hook_type=hook_type,
            script_path="hook.py",
            command="python3 hook.py",
        )
        assert hook_contracts.validate_hook_type_known(entry) is None

    def test_unknown_type(self):
        entry = hook_contracts.HookEntry(
            hook_type="BeforeStart",
            script_path="hook.py",
            command="python3 hook.py",
        )
        violation = hook_contracts.validate_hook_type_known(entry)
        assert violation is not None
        assert violation.category == "unknown_hook_type"


# ---------------------------------------------------------------------------
# validate_timeout
# ---------------------------------------------------------------------------


class TestValidateTimeout:
    def test_no_timeout(self):
        entry = hook_contracts.HookEntry(
            hook_type="Stop",
            script_path="hook.py",
            command="python3 hook.py",
        )
        assert hook_contracts.validate_timeout(entry) is None

    def test_valid_timeout(self):
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
            timeout=10,
        )
        assert hook_contracts.validate_timeout(entry) is None

    def test_timeout_too_low(self):
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
            timeout=0,
        )
        violation = hook_contracts.validate_timeout(entry)
        assert violation is not None
        assert violation.category == "timeout_range"

    def test_timeout_too_high(self):
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
            timeout=600,
        )
        violation = hook_contracts.validate_timeout(entry)
        assert violation is not None
        assert violation.category == "timeout_range"

    def test_boundary_min(self):
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
            timeout=1,
        )
        assert hook_contracts.validate_timeout(entry) is None

    def test_boundary_max(self):
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
            timeout=300,
        )
        assert hook_contracts.validate_timeout(entry) is None


# ---------------------------------------------------------------------------
# validate_exit_code_docs
# ---------------------------------------------------------------------------


class TestValidateExitCodeDocs:
    def test_blocking_hook_with_docs(self, tmp_path):
        script = tmp_path / "hook.py"
        script.write_text(
            textwrap.dedent('''\
            """Guard hook.

            Exit Codes:
                0 = Allow
                2 = Block
            """
        ''')
        )
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
        )
        assert hook_contracts.validate_exit_code_docs(entry, tmp_path) is None

    def test_blocking_hook_without_docs(self, tmp_path):
        script = tmp_path / "hook.py"
        script.write_text(
            textwrap.dedent('''\
            """Simple guard hook."""
            import sys
        ''')
        )
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
        )
        violation = hook_contracts.validate_exit_code_docs(entry, tmp_path)
        assert violation is not None
        assert violation.category == "missing_exit_docs"

    def test_non_blocking_hook_skips_check(self, tmp_path):
        script = tmp_path / "hook.py"
        script.write_text('"""No exit docs."""\n')
        entry = hook_contracts.HookEntry(
            hook_type="Stop",
            script_path="hook.py",
            command="python3 hook.py",
        )
        assert hook_contracts.validate_exit_code_docs(entry, tmp_path) is None

    def test_missing_script_skips(self, tmp_path):
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="missing.py",
            command="python3 missing.py",
        )
        assert hook_contracts.validate_exit_code_docs(entry, tmp_path) is None

    def test_block_keyword_in_docstring(self, tmp_path):
        script = tmp_path / "hook.py"
        script.write_text(
            textwrap.dedent('''\
            """Hook that can block operations."""
            import sys
        ''')
        )
        entry = hook_contracts.HookEntry(
            hook_type="PreToolUse",
            script_path="hook.py",
            command="python3 hook.py",
        )
        assert hook_contracts.validate_exit_code_docs(entry, tmp_path) is None


# ---------------------------------------------------------------------------
# validate_duplicate_entries
# ---------------------------------------------------------------------------


class TestValidateDuplicateEntries:
    def test_no_duplicates(self):
        entries = [
            hook_contracts.HookEntry(
                hook_type="PreToolUse",
                script_path="a.py",
                command="python3 a.py",
                matcher="Bash",
            ),
            hook_contracts.HookEntry(
                hook_type="PreToolUse",
                script_path="b.py",
                command="python3 b.py",
                matcher="Bash",
            ),
        ]
        violations = hook_contracts.validate_duplicate_entries(entries)
        assert len(violations) == 0

    def test_duplicate_detected(self):
        entries = [
            hook_contracts.HookEntry(
                hook_type="PreToolUse",
                script_path="a.py",
                command="python3 a.py",
                matcher="Bash",
            ),
            hook_contracts.HookEntry(
                hook_type="PreToolUse",
                script_path="a.py",
                command="python3 a.py",
                matcher="Bash",
            ),
        ]
        violations = hook_contracts.validate_duplicate_entries(entries)
        assert len(violations) == 1
        assert violations[0].category == "duplicate"

    def test_same_script_different_matcher_not_duplicate(self):
        entries = [
            hook_contracts.HookEntry(
                hook_type="PreToolUse",
                script_path="a.py",
                command="python3 a.py",
                matcher="Bash",
            ),
            hook_contracts.HookEntry(
                hook_type="PreToolUse",
                script_path="a.py",
                command="python3 a.py",
                matcher="^(Write|Edit)$",
            ),
        ]
        violations = hook_contracts.validate_duplicate_entries(entries)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# validate_all (integration)
# ---------------------------------------------------------------------------


class TestValidateAll:
    def _create_settings(self, tmp_path, hooks_config):
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({"hooks": hooks_config}))
        return settings_path

    def _create_script(self, tmp_path, script_path, content=""):
        full = tmp_path / script_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(
            content
            or textwrap.dedent('''\
            """Hook script.

            Exit Codes:
                0 = Allow
                2 = Block
            """
        ''')
        )
        return full

    def test_valid_setup(self, tmp_path):
        self._create_script(tmp_path, ".claude/hooks/guard.py")
        settings_path = self._create_settings(
            tmp_path,
            {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 .claude/hooks/guard.py",
                                "timeout": 5,
                            }
                        ],
                    }
                ],
            },
        )

        report = hook_contracts.validate_all(settings_path, tmp_path)
        assert report.is_valid
        assert len(report.entries) == 1

    def test_missing_script_violation(self, tmp_path):
        settings_path = self._create_settings(
            tmp_path,
            {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 .claude/hooks/missing.py",
                            }
                        ],
                    }
                ],
            },
        )

        report = hook_contracts.validate_all(settings_path, tmp_path)
        assert not report.is_valid
        categories = {v.category for v in report.violations}
        assert "missing_script" in categories

    def test_real_settings(self, project_root):
        """Validate the actual project settings.json against the codebase."""
        settings_path = project_root / ".claude" / "settings.json"
        if not settings_path.is_file():
            pytest.skip("No .claude/settings.json in project")

        report = hook_contracts.validate_all(settings_path, project_root)

        # All referenced scripts should exist
        missing = [v for v in report.violations if v.category == "missing_script"]
        assert len(missing) == 0, f"Missing scripts: {[v.script for v in missing]}"

        # No unknown hook types
        unknown = [v for v in report.violations if v.category == "unknown_hook_type"]
        assert len(unknown) == 0, f"Unknown hook types: {[v.hook_type for v in unknown]}"


# ---------------------------------------------------------------------------
# format_console
# ---------------------------------------------------------------------------


class TestFormatConsole:
    def test_valid_report(self):
        report = hook_contracts.ContractReport(
            entries=[
                hook_contracts.HookEntry(
                    hook_type="PreToolUse",
                    script_path="a.py",
                    command="python3 a.py",
                ),
            ],
        )
        output = hook_contracts.format_console(report)
        assert "valid" in output.lower()

    def test_report_with_violations(self):
        report = hook_contracts.ContractReport(
            entries=[],
            violations=[
                hook_contracts.Violation(
                    hook_type="PreToolUse",
                    script="missing.py",
                    category="missing_script",
                    message="Script not found: missing.py",
                ),
            ],
        )
        output = hook_contracts.format_console(report)
        assert "violation" in output.lower()
        assert "missing.py" in output


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_valid_report(self):
        report = hook_contracts.ContractReport(
            entries=[
                hook_contracts.HookEntry(
                    hook_type="Stop",
                    script_path="a.py",
                    command="python3 a.py",
                ),
            ],
        )
        data = json.loads(hook_contracts.format_json(report))
        assert data["status"] == "pass"
        assert data["entriesValidated"] == 1
        assert data["violationCount"] == 0

    def test_report_with_violations(self):
        report = hook_contracts.ContractReport(
            violations=[
                hook_contracts.Violation(
                    hook_type="PreToolUse",
                    script="x.py",
                    category="missing_script",
                    message="Not found",
                ),
            ],
        )
        data = json.loads(hook_contracts.format_json(report))
        assert data["status"] == "fail"
        assert data["violationCount"] == 1
        assert data["violations"][0]["category"] == "missing_script"


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------


class TestMain:
    def test_missing_path(self):
        exit_code = hook_contracts.main(["--path", "/nonexistent/path"])
        assert exit_code == 2

    def test_missing_settings(self, tmp_path):
        exit_code = hook_contracts.main(["--path", str(tmp_path)])
        assert exit_code == 2

    def test_invalid_json(self, tmp_path):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("{invalid json}")
        exit_code = hook_contracts.main(["--path", str(tmp_path)])
        assert exit_code == 2

    def test_valid_settings_returns_zero(self, tmp_path):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(json.dumps({"hooks": {}}))
        exit_code = hook_contracts.main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_ci_mode_returns_one_on_violations(self, tmp_path):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 missing.py",
                            }
                        ],
                    }
                ],
            }
        }
        (settings_dir / "settings.json").write_text(json.dumps(settings))
        exit_code = hook_contracts.main(
            [
                "--path",
                str(tmp_path),
                "--ci",
            ]
        )
        assert exit_code == 1

    def test_non_ci_returns_zero_on_violations(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 missing.py",
                            }
                        ],
                    }
                ],
            }
        }
        (settings_dir / "settings.json").write_text(json.dumps(settings))
        exit_code = hook_contracts.main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_json_output_format(self, tmp_path, capsys):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(json.dumps({"hooks": {}}))
        hook_contracts.main(
            [
                "--path",
                str(tmp_path),
                "--format",
                "json",
            ]
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "pass"

    def test_custom_settings_path(self, tmp_path):
        custom = tmp_path / "custom.json"
        custom.write_text(json.dumps({"hooks": {}}))
        exit_code = hook_contracts.main(
            [
                "--path",
                str(tmp_path),
                "--settings",
                str(custom),
            ]
        )
        assert exit_code == 0
