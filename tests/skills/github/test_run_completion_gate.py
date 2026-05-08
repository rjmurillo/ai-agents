"""Tests for the dispatchable /pr-review completion gate.

Covers run_completion_gate.py at .claude/skills/github/scripts/pr/.

Each test case constructs a synthetic config and stubs subprocess.run so
the criterion's command does not actually shell out. We assert on:

  * exit code (0 if all pass, 1 if any fail, 2 on usage)
  * per-criterion verdicts visible in --json output
  * fail_open semantics: command error -> pass when fail_open=true,
    fail when fail_open=false
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = (
    _REPO_ROOT
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "run_completion_gate.py"
)


def _import_dispatcher():
    """Import the dispatcher module from its file path."""
    spec = importlib.util.spec_from_file_location(
        "run_completion_gate", _SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_completion_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


_dispatcher = _import_dispatcher()


def _make_proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _write_config(tmp_path: Path, criteria: list[dict]) -> Path:
    """Write a minimal config YAML with only completion_criteria.

    Uses JSON syntax (which is valid YAML) so PyYAML parses it without
    needing block-style indentation gymnastics in the test source.
    """
    config = {"completion_criteria": criteria}
    path = tmp_path / "pr-review-config.yaml"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# pass_when DSL unit tests
# ---------------------------------------------------------------------------


class TestPassWhenDsl:
    """Direct exercise of the pass_when expression evaluator."""

    def test_simple_int_eq_passes(self):
        data = {"unresolved_count": 0}
        assert _dispatcher._eval_pass_when(
            data, "stdout-json.unresolved_count == 0",
        ) is True

    def test_simple_int_eq_fails(self):
        data = {"unresolved_count": 3}
        assert _dispatcher._eval_pass_when(
            data, "stdout-json.unresolved_count == 0",
        ) is False

    def test_bool_eq_true(self):
        data = {"fetched_pages_complete": True}
        assert _dispatcher._eval_pass_when(
            data, "stdout-json.fetched_pages_complete == true",
        ) is True

    def test_bool_eq_false_with_false_literal(self):
        data = {"merged": False}
        assert _dispatcher._eval_pass_when(
            data, "stdout-json.merged == false",
        ) is True

    def test_neq_operator(self):
        data = {"state": "OPEN"}
        assert _dispatcher._eval_pass_when(
            data, 'stdout-json.state != "CLOSED"',
        ) is True

    def test_and_composition_both_true(self):
        data = {"unresolved_count": 0, "fetched_pages_complete": True}
        expr = (
            "stdout-json.unresolved_count == 0 "
            "AND stdout-json.fetched_pages_complete == true"
        )
        assert _dispatcher._eval_pass_when(data, expr) is True

    def test_and_composition_one_false(self):
        data = {"unresolved_count": 0, "fetched_pages_complete": False}
        expr = (
            "stdout-json.unresolved_count == 0 "
            "AND stdout-json.fetched_pages_complete == true"
        )
        assert _dispatcher._eval_pass_when(data, expr) is False

    def test_or_composition_one_true(self):
        data = {"unresolved_count": 5, "ignore_threads": True}
        expr = (
            "stdout-json.unresolved_count == 0 "
            "OR stdout-json.ignore_threads == true"
        )
        assert _dispatcher._eval_pass_when(data, expr) is True

    def test_missing_path_returns_none(self):
        data: dict = {}
        # null literal compares equal to a missing path
        assert _dispatcher._eval_pass_when(
            data, "stdout-json.nope == null",
        ) is True

    def test_unsupported_op_raises(self):
        data = {"x": 1}
        with pytest.raises(ValueError):
            _dispatcher._eval_pass_when(data, "stdout-json.x > 0")

    def test_dotted_nested_path(self):
        data = {"outer": {"inner": 42}}
        assert _dispatcher._eval_pass_when(
            data, "stdout-json.outer.inner == 42",
        ) is True


# ---------------------------------------------------------------------------
# Dispatcher integration tests
# ---------------------------------------------------------------------------


class TestRunCompletionGate:
    """End-to-end main() exercises with mocked subprocess.run."""

    def test_all_pass_exits_zero(self, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "All threads resolved",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": (
                        "stdout-json.unresolved_count == 0 "
                        "AND stdout-json.fetched_pages_complete == true"
                    ),
                    "fail_open": False,
                },
                {
                    "name": "Not merged",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.merged == false",
                    "fail_open": False,
                },
            ],
        )

        responses = [
            _make_proc(
                stdout=json.dumps(
                    {"unresolved_count": 0, "fetched_pages_complete": True},
                ),
            ),
            _make_proc(stdout=json.dumps({"merged": False})),
        ]

        with patch.object(
            _dispatcher.subprocess, "run", side_effect=responses,
        ):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "1234",
                    "--json",
                ],
            )

        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["all_passed"] is True
        assert all(c["passed"] for c in result["criteria"])

    def test_one_fail_exits_one(self, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "All threads resolved",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.unresolved_count == 0",
                    "fail_open": False,
                },
            ],
        )

        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(
                stdout=json.dumps({"unresolved_count": 3}),
            ),
        ):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "1234",
                    "--json",
                ],
            )

        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["all_passed"] is False
        assert result["criteria"][0]["passed"] is False
        assert "pass_when evaluated false" in result["criteria"][0]["reason"]

    def test_command_error_fails_closed_when_fail_open_false(
        self, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Strict",
                    "verification": "command",
                    "command": "this-command-does-not-exist",
                    "pass_when": "stdout-json.x == 0",
                    "fail_open": False,
                },
            ],
        )

        with patch.object(
            _dispatcher.subprocess, "run",
            side_effect=FileNotFoundError("nope"),
        ):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "1234",
                    "--json",
                ],
            )

        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["passed"] is False
        assert "command failed to run" in result["criteria"][0]["reason"]

    def test_command_error_passes_when_fail_open_true(self, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Lenient",
                    "verification": "command",
                    "command": "this-command-does-not-exist",
                    "pass_when": "stdout-json.x == 0",
                    "fail_open": True,
                },
            ],
        )

        with patch.object(
            _dispatcher.subprocess, "run",
            side_effect=FileNotFoundError("nope"),
        ):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "1234",
                    "--json",
                ],
            )

        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["passed"] is True

    def test_malformed_json_fails_closed(self, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Bad output",
                    "verification": "command",
                    "command": "echo not-json",
                    "pass_when": "stdout-json.x == 0",
                    "fail_open": False,
                },
            ],
        )

        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout="not-json", returncode=0),
        ):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "1234",
                    "--json",
                ],
            )

        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["passed"] is False
        assert "not a JSON object" in result["criteria"][0]["reason"]

    def test_missing_config_returns_two(self, tmp_path):
        rc = _dispatcher.main(
            [
                "--config", str(tmp_path / "does-not-exist.yaml"),
                "--pull-request", "1234",
                "--json",
            ],
        )
        assert rc == 2

    def test_negative_pr_returns_two(self, tmp_path):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "x",
                    "verification": "command",
                    "command": "echo {}",
                    "pass_when": "stdout-json.x == 0",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "-1"],
        )
        assert rc == 2

    def test_pr_substitution(self, tmp_path):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "echo PR",
                    "verification": "command",
                    "command": 'echo {"pr": {pr}}',
                    "pass_when": "stdout-json.pr == 1234",
                    "fail_open": False,
                },
            ],
        )

        captured: dict = {}

        def fake_run(argv, **_kw):
            captured["argv"] = argv
            return _make_proc(stdout=json.dumps({"pr": 1234}))

        with patch.object(_dispatcher.subprocess, "run", side_effect=fake_run):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "1234",
                    "--json",
                ],
            )

        assert rc == 0
        # The {pr} placeholder must have been substituted before tokenizing.
        assert "1234" in " ".join(captured["argv"])

    def test_pass_when_python_escape_hatch(self, tmp_path):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Python hatch",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when_python": "lambda d: d.get('x', 0) > 0",
                    "fail_open": False,
                },
            ],
        )

        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=json.dumps({"x": 7})),
        ):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "1",
                    "--json",
                ],
            )

        assert rc == 0
