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


@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    """Treat tmp_path as the repo root so validate_safe_path accepts configs.

    The dispatcher locks ``--config`` to paths under ``_PROJECT_ROOT`` to
    block path traversal (CWE-22). Tests need to write throwaway configs
    in tmp_path; monkeypatching the resolved root preserves the
    production guard while keeping the tests hermetic.
    """
    monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
    return tmp_path


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

    def test_quoted_string_with_space_stays_intact(self):
        # Per Gemini review: previous expr.split() broke on
        # ``"PR merged"``, splitting it into ``['"PR', 'merged"']``. The
        # shlex.split tokenizer keeps the literal as a single token.
        data = {"label": "PR merged"}
        assert _dispatcher._eval_pass_when(
            data, 'stdout-json.label == "PR merged"',
        ) is True

    def test_unbalanced_quotes_rejected(self):
        with pytest.raises(ValueError, match="tokenization failed"):
            _dispatcher._eval_pass_when(
                {"x": 1},
                'stdout-json.x == "unterminated',
            )

    def test_dangling_and_connective_rejected(self):
        # Per Copilot review: ``x == 1 AND`` (with no atom after AND)
        # silently passed before because the loop checked ``i < len``
        # only at the top.
        with pytest.raises(ValueError, match="dangling connective"):
            _dispatcher._eval_pass_when(
                {"x": 1},
                "stdout-json.x == 1 AND",
            )

    def test_dangling_or_connective_rejected(self):
        with pytest.raises(ValueError, match="dangling connective"):
            _dispatcher._eval_pass_when(
                {"x": 1},
                "stdout-json.x == 0 OR",
            )


# ---------------------------------------------------------------------------
# Dispatcher integration tests
# ---------------------------------------------------------------------------


class TestRunCompletionGate:
    """End-to-end main() exercises with mocked subprocess.run."""

    def test_all_pass_exits_zero(self, repo_root, tmp_path, capsys):
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

    def test_one_fail_exits_one(self, repo_root, tmp_path, capsys):
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
        self, repo_root, tmp_path, capsys,
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

    def test_command_error_passes_when_fail_open_true(self, repo_root, tmp_path, capsys):
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

    def test_malformed_json_fails_closed(self, repo_root, tmp_path, capsys):
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

    def test_non_zero_exit_treated_as_dispatch_error(
        self, repo_root, tmp_path, capsys,
    ):
        # Per Copilot review: a non-zero verifier exit is a dispatch
        # error, not a "the verifier ran fine, parse its stdout"
        # success path. Verifier output may be a stale snapshot; trust
        # the exit code first.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Crashy",
                    "verification": "command",
                    "command": "false",
                    "pass_when": "stdout-json.x == 0",
                    "fail_open": False,
                },
            ],
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(
                stdout=json.dumps({"x": 0}),
                stderr="something went wrong",
                returncode=3,
            ),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["passed"] is False
        assert "exited non-zero" in result["criteria"][0]["reason"]
        # Verifier output is preserved in the result for triage:
        assert result["criteria"][0]["stderr"] == "something went wrong"

    def test_broken_pass_when_fails_closed_even_when_fail_open_true(
        self, repo_root, tmp_path, capsys,
    ):
        # Per CodeRabbit review: a broken pass_when expression is a
        # config bug, not a verifier outage. fail_open MUST NOT mask
        # it; otherwise a typo in the gate definition silently greens
        # the gate.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Broken expr",
                    "verification": "command",
                    "command": "echo {}",
                    "pass_when": "stdout-json.x !@# 0",  # nonsense op
                    "fail_open": True,  # MUST be ignored for this case
                },
            ],
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=json.dumps({"x": 0})),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["passed"] is False
        assert "fails closed" in result["criteria"][0]["reason"]

    def test_verifier_stdout_preserved_in_result(
        self, repo_root, tmp_path, capsys,
    ):
        # Per CodeRabbit review: the result row must include the
        # verifier's stdout/stderr so the failing criterion can be
        # debugged from the gate output alone.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Verbose",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.unresolved_count == 99",
                },
            ],
        )
        verifier_out = json.dumps({"unresolved_count": 0})
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=verifier_out, returncode=0),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["stdout"] == verifier_out

    def test_missing_config_returns_two(self, repo_root, tmp_path):
        rc = _dispatcher.main(
            [
                "--config", str(tmp_path / "does-not-exist.yaml"),
                "--pull-request", "1234",
                "--json",
            ],
        )
        assert rc == 2

    def test_negative_pr_returns_two(self, repo_root, tmp_path):
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

    def test_pr_substitution(self, repo_root, tmp_path):
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

    def test_pass_when_python_escape_hatch(self, repo_root, tmp_path):
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


# ---------------------------------------------------------------------------
# Negative branch coverage: rejection paths in the dispatcher.
# These exercise branches that the production-code review identified as
# reachable but untested. Each test covers one branch so that a future
# regression localizes the failure.
# ---------------------------------------------------------------------------


class TestPassWhenDslNegativeBranches:
    """Cover error-path branches of the pass_when DSL evaluator."""

    def test_empty_expression_raises(self):
        with pytest.raises(ValueError):
            _dispatcher._eval_pass_when({}, "")

    def test_missing_connective_between_atoms_raises(self):
        # "a == 0 b == 1" lacks AND/OR between the two atoms; the parser
        # should reject rather than silently accept.
        with pytest.raises(ValueError):
            _dispatcher._eval_pass_when(
                {"a": 0, "b": 1},
                "stdout-json.a == 0 stdout-json.b == 1",
            )


class TestPassWhenPythonNegativeBranches:
    """Cover the eval-rejection paths in _eval_pass_when_python.

    These branches are security-relevant: they bound the surface that
    the eval call will accept. AGENTS.md sets the security-critical
    coverage floor at 100%; missing these branches violates that floor.
    """

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match="must be a string"):
            _dispatcher._eval_pass_when_python({}, 123)  # type: ignore[arg-type]

    def test_non_lambda_rejected(self):
        with pytest.raises(ValueError, match="must be a lambda"):
            _dispatcher._eval_pass_when_python({}, "1 + 1")

    def test_multiline_rejected(self):
        with pytest.raises(ValueError, match="single line"):
            _dispatcher._eval_pass_when_python(
                {}, "lambda d: d\n.get('x')",
            )

    def test_not_a_lambda_body_rejected(self):
        # A bare expression (no lambda) is rejected before any AST walk.
        with pytest.raises(ValueError, match="must be a lambda"):
            _dispatcher._eval_pass_when_python({}, "d.get('x') is True")

    def test_invalid_python_syntax_rejected(self):
        with pytest.raises(ValueError, match="not valid Python"):
            _dispatcher._eval_pass_when_python({}, "lambda d: d.get(")

    def test_multi_argument_lambda_rejected(self):
        # A second parameter is outside the one-positional-arg contract.
        with pytest.raises(ValueError, match="exactly one positional argument"):
            _dispatcher._eval_pass_when_python(
                {}, "lambda d, e: d.get('x') is True",
            )


class TestDispatcherCriterionRejectionPaths:
    """Reachable production branches in _evaluate_criterion that the
    earlier tests did not cover.
    """

    def test_unsupported_verification_kind(self, repo_root, tmp_path, capsys):
        # Schema bug: verification kind unknown. Per CodeRabbit review
        # feedback, malformed criteria are config errors (exit 2), not
        # gate failures (exit 1). Distinguishes a typo from a verifier
        # legitimately reporting a problem.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Bogus",
                    "verification": "magic",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.x == 0",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )
        assert rc == 2
        assert "unsupported verification" in capsys.readouterr().err

    def test_missing_command_field(self, repo_root, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "No-cmd",
                    "verification": "command",
                    "pass_when": "stdout-json.x == 0",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )
        assert rc == 2
        assert "command must be a non-empty string" in capsys.readouterr().err

    def test_missing_pass_when_expression(self, repo_root, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "No-expr",
                    "verification": "command",
                    "command": "echo ignored",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )
        assert rc == 2
        assert "missing pass_when" in capsys.readouterr().err

    def test_pass_when_and_pass_when_python_both_set_rejected(
        self, repo_root, tmp_path, capsys,
    ):
        # Per Copilot review: both-set is ambiguous because the
        # dispatcher silently picks pass_when_python first. Reject at
        # schema time so the ambiguity never reaches runtime.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Both",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.x == 0",
                    "pass_when_python": "lambda d: d['x'] == 0",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )
        assert rc == 2
        assert "mutually exclusive" in capsys.readouterr().err

    def test_timeout_fails_closed_when_fail_open_false(
        self, repo_root, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Slow",
                    "verification": "command",
                    "command": "sleep 9999",
                    "pass_when": "stdout-json.x == 0",
                    "fail_open": False,
                },
            ],
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd=["sleep"], timeout=1),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["passed"] is False
        assert "command failed to run" in result["criteria"][0]["reason"]

    def test_timeout_passes_when_fail_open_true(
        self, repo_root, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Lenient",
                    "verification": "command",
                    "command": "sleep 9999",
                    "pass_when": "stdout-json.x == 0",
                    "fail_open": True,
                },
            ],
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd=["sleep"], timeout=1),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 0


class TestDispatcherMainRejectionPaths:
    """Reachable branches in main() that earlier tests did not cover."""

    def test_empty_completion_criteria_returns_two(
        self, repo_root, tmp_path, capsys,
    ):
        config_path = _write_config(tmp_path, [])
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "No completion_criteria" in capsys.readouterr().err

    def test_malformed_criterion_not_a_mapping(
        self, repo_root, tmp_path, capsys,
    ):
        # YAML parses "- foo" as a list element of type str, not dict.
        # CodeRabbit review feedback: a non-mapping criterion is a
        # config bug, not a gate result. Exit 2.
        config_path = tmp_path / "pr-review-config.yaml"
        config_path.write_text(
            "completion_criteria:\n  - 'this is a string, not a mapping'\n",
            encoding="utf-8",
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )
        assert rc == 2
        assert "not a mapping" in capsys.readouterr().err

    def test_completion_criteria_not_a_list_rejected(
        self, repo_root, tmp_path, capsys,
    ):
        # Per CodeRabbit: a dict in this slot would be silently iterated
        # as keys. Reject explicitly.
        config_path = tmp_path / "pr-review-config.yaml"
        config_path.write_text(
            "completion_criteria:\n  some_key: some_value\n",
            encoding="utf-8",
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "must be a list" in capsys.readouterr().err

    def test_unreadable_config_returns_two(
        self, repo_root, tmp_path, capsys,
    ):
        # Per CodeRabbit: yaml.YAMLError must be caught and exit 2.
        config_path = tmp_path / "pr-review-config.yaml"
        config_path.write_text(
            "this is not: valid: yaml: at: all:\n  - [unbalanced",
            encoding="utf-8",
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "Failed to load config" in capsys.readouterr().err

    def test_path_traversal_rejected(self, tmp_path):
        # No repo_root fixture: --config points outside the production
        # _PROJECT_ROOT (which is the actual repo root); the dispatcher
        # MUST reject with exit 2 before reading the file.
        outside = tmp_path / "evil.yaml"
        outside.write_text("completion_criteria: []\n", encoding="utf-8")
        rc = _dispatcher.main(
            ["--config", str(outside), "--pull-request", "1"],
        )
        assert rc == 2


class TestFormatCommandTypeGuard:
    """The integer assertion in _format_command bounds CWE-78 risk."""

    def test_string_pr_number_rejected(self):
        with pytest.raises(TypeError, match="pr_number must be int"):
            _dispatcher._format_command("echo {pr}", "1; rm -rf /")  # type: ignore[arg-type]

    def test_bool_pr_number_rejected(self):
        # bools are int subclasses in Python; the guard rejects them
        # explicitly so a downstream caller cannot smuggle True/False.
        with pytest.raises(TypeError, match="pr_number must be int"):
            _dispatcher._format_command("echo {pr}", True)  # type: ignore[arg-type]


class TestSchemaTypeChecks:
    """Per Copilot review: tighten value-type checks in
    _validate_criterion_schema so YAML quirks (lists where strings are
    expected, ``"yes"`` instead of ``true``) surface as ConfigError
    rather than crashing later in the dispatch path.
    """

    def test_command_as_list_rejected(self, repo_root, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Listy",
                    "verification": "command",
                    "command": ["echo", "ignored"],
                    "pass_when": "stdout-json.x == 0",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "command must be a non-empty string" in capsys.readouterr().err

    def test_fail_open_string_yes_rejected(self, repo_root, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Trickier",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.x == 0",
                    "fail_open": "yes",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "fail_open must be a boolean" in capsys.readouterr().err

    def test_pass_when_as_list_rejected(self, repo_root, tmp_path, capsys):
        # Per Copilot review: pass_when must also be type-checked, not
        # just present. A list-valued pass_when (YAML indentation) would
        # crash the DSL tokenizer later.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Listy",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": ["stdout-json.x == 0"],
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "pass_when must be a non-empty string" in capsys.readouterr().err

    def test_missing_name_rejected(self, repo_root, tmp_path, capsys):
        # Per Copilot review: name was previously defaulted to <unnamed>
        # which could silently slip past. The dispatcher now mirrors the
        # validator and requires it explicitly.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.x == 0",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "missing required field: name" in capsys.readouterr().err

    def test_missing_verification_rejected(self, repo_root, tmp_path, capsys):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "No-verification",
                    "command": "echo ignored",
                    "pass_when": "stdout-json.x == 0",
                },
            ],
        )
        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )
        assert rc == 2
        assert "missing required field: verification" in capsys.readouterr().err


class TestPassWhenPythonBroadException:
    """Per CodeRabbit: a pass_when_python lambda body can raise anything
    (ZeroDivisionError, IndexError, custom exceptions). The dispatcher
    must catch all of them and fail closed.
    """

    def test_zero_division_in_lambda_fails_closed(
        self, repo_root, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Divides",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when_python": "lambda d: 1 / 0",
                    "fail_open": True,  # MUST be ignored (config bug)
                },
            ],
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=json.dumps({"x": 0})),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["criteria"][0]["passed"] is False
        assert "fails closed" in result["criteria"][0]["reason"]

    def test_index_error_in_lambda_fails_closed(
        self, repo_root, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "OutOfBounds",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when_python": "lambda d: d['items'][5] == 'x'",
                    "fail_open": True,
                },
            ],
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=json.dumps({"items": []})),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert "fails closed" in result["criteria"][0]["reason"]


class TestPassWhenPythonAstSafeSubset:
    """The pass_when_python evaluator walks a whitelisted AST subset and
    never calls ``eval`` (issue #2303 hardening). These tests pin the
    accepted operators and prove the rejected ones fail closed.
    """

    def test_is_true_comparison(self):
        assert _dispatcher._eval_pass_when_python(
            {"CanMerge": True}, "lambda d: d.get('CanMerge') is True",
        ) is True

    def test_is_true_comparison_false_when_value_not_true(self):
        # ``is True`` must be identity-strict: a truthy non-True value
        # (e.g. the string "yes") does NOT satisfy ``is True``.
        assert _dispatcher._eval_pass_when_python(
            {"CanMerge": "yes"}, "lambda d: d.get('CanMerge') is True",
        ) is False

    def test_and_composition(self):
        data = {"CanMerge": True, "fetched_pages_complete": True}
        assert _dispatcher._eval_pass_when_python(
            data,
            "lambda d: d.get('CanMerge') is True "
            "and d.get('fetched_pages_complete') is True",
        ) is True

    def test_or_composition(self):
        assert _dispatcher._eval_pass_when_python(
            {"a": False, "b": True},
            "lambda d: d.get('a') is True or d.get('b') is True",
        ) is True

    def test_not_operator(self):
        assert _dispatcher._eval_pass_when_python(
            {"merged": False}, "lambda d: not d.get('merged') is True",
        ) is True

    def test_get_with_default(self):
        assert _dispatcher._eval_pass_when_python(
            {}, "lambda d: d.get('missing', 0) == 0",
        ) is True

    def test_in_membership_against_tuple(self):
        assert _dispatcher._eval_pass_when_python(
            {"state": "CLEAN"},
            "lambda d: d.get('state') in ('CLEAN', 'UNSTABLE')",
        ) is True

    def test_numeric_comparison(self):
        assert _dispatcher._eval_pass_when_python(
            {"x": 7}, "lambda d: d.get('x', 0) > 0",
        ) is True

    def test_attribute_call_other_than_get_rejected(self):
        # ``d.keys()`` is a method call but not the permitted ``get``.
        with pytest.raises(ValueError, match="get"):
            _dispatcher._eval_pass_when_python(
                {"x": 1}, "lambda d: d.keys() is not None",
            )

    def test_arbitrary_name_rejected(self):
        # A free name (not the lambda param) must not resolve.
        with pytest.raises(ValueError, match="unknown name"):
            _dispatcher._eval_pass_when_python(
                {}, "lambda d: __import__ is None",
            )

    def test_subscript_rejected_fails_closed(self):
        # ``d['k']`` uses ast.Subscript, outside the whitelist; the
        # evaluator raises rather than executing it.
        with pytest.raises(ValueError, match="unsupported expression node"):
            _dispatcher._eval_pass_when_python(
                {"k": 1}, "lambda d: d['k'] == 1",
            )

    def test_binop_rejected_before_evaluation(self):
        # ``1 / 0`` is an ast.BinOp; rejected by the node whitelist before
        # any ZeroDivisionError can occur. Proves no arithmetic runs.
        with pytest.raises(ValueError, match="unsupported expression node"):
            _dispatcher._eval_pass_when_python({}, "lambda d: 1 / 0 == 0")

    def test_call_to_builtin_rejected(self):
        # A bare builtin call (len) is not <param>.get(...); rejected.
        with pytest.raises(ValueError):
            _dispatcher._eval_pass_when_python(
                {"x": [1]}, "lambda d: len(d.get('x')) == 1",
            )

    def test_get_with_too_many_args_rejected(self):
        with pytest.raises(ValueError, match="one or two positional"):
            _dispatcher._eval_pass_when_python(
                {}, "lambda d: d.get('a', 0, 9) == 0",
            )


class TestMergeReadyFalseFailRegression:
    """Issue #2303 regression: the completion gate must return success when
    test_pr_merge_ready.py reports CanMerge=True and fetched_pages_complete,
    using the production pass_when_python predicate verbatim. Before the fix
    the gate re-checked ``MergeStateStatus in ('CLEAN', 'UNSTABLE')`` and
    false-failed a mergeable BLOCKED PR (observed on PR #2283).
    """

    # The exact predicate shipped in .claude/commands/pr-review-config.yaml
    # for the "PR is ready to merge" criterion. Kept verbatim so this test
    # exercises the real contract, not a paraphrase.
    _MERGE_READY_PASS_WHEN = (
        "lambda d: d.get('CanMerge') is True "
        "and d.get('fetched_pages_complete') is True"
    )

    def _merge_ready_config(self, tmp_path: Path) -> Path:
        return _write_config(
            tmp_path,
            [
                {
                    "name": "PR is ready to merge (CI green, no conflicts)",
                    "verification": "command",
                    "command": "echo ignored",
                    "pass_when_python": self._MERGE_READY_PASS_WHEN,
                    "fail_open": False,
                },
            ],
        )

    def test_can_merge_true_blocked_state_passes(
        self, repo_root, tmp_path, capsys,
    ):
        # The false-fail case: a BLOCKED-but-mergeable PR. CanMerge=True is
        # the upstream verdict; the gate must honor it without re-deriving
        # the MergeStateStatus rule. CIPassing/UnresolvedThreads are present
        # in real output but are NOT re-checked here by design.
        config_path = self._merge_ready_config(tmp_path)
        verifier_out = json.dumps(
            {
                "CanMerge": True,
                "CIPassing": True,
                "UnresolvedThreads": 0,
                "MergeStateStatus": "BLOCKED",
                "fetched_pages_complete": True,
            },
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=verifier_out, returncode=0),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "2283", "--json"],
            )
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["all_passed"] is True
        assert result["criteria"][0]["passed"] is True

    def test_can_merge_true_clean_state_passes(
        self, repo_root, tmp_path, capsys,
    ):
        config_path = self._merge_ready_config(tmp_path)
        verifier_out = json.dumps(
            {"CanMerge": True, "MergeStateStatus": "CLEAN",
             "fetched_pages_complete": True},
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=verifier_out, returncode=0),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["criteria"][0]["passed"] is True

    def test_can_merge_false_still_fails(self, repo_root, tmp_path, capsys):
        # Negative control: when the upstream script says CanMerge=False the
        # gate must still fail. Trusting CanMerge does not weaken the gate.
        config_path = self._merge_ready_config(tmp_path)
        verifier_out = json.dumps(
            {"CanMerge": False, "fetched_pages_complete": True},
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=verifier_out, returncode=0),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        assert json.loads(capsys.readouterr().out)["criteria"][0]["passed"] is False

    def test_partial_fetch_fails_closed_even_when_can_merge_true(
        self, repo_root, tmp_path, capsys,
    ):
        # Data-integrity guard: a truncated GraphQL page (fetched_pages_
        # complete=False) can hide a failing required check, so the gate
        # fails closed regardless of CanMerge.
        config_path = self._merge_ready_config(tmp_path)
        verifier_out = json.dumps(
            {"CanMerge": True, "fetched_pages_complete": False},
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=verifier_out, returncode=0),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        assert json.loads(capsys.readouterr().out)["criteria"][0]["passed"] is False

    def test_missing_can_merge_field_fails_closed(
        self, repo_root, tmp_path, capsys,
    ):
        # Edge: a verifier that omits CanMerge entirely. ``d.get('CanMerge')``
        # returns None, ``None is True`` is False, gate fails closed.
        config_path = self._merge_ready_config(tmp_path)
        verifier_out = json.dumps({"fetched_pages_complete": True})
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=verifier_out, returncode=0),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        assert rc == 1
        assert json.loads(capsys.readouterr().out)["criteria"][0]["passed"] is False


class TestTableModeShowsEvidence:
    """Per CodeRabbit: the non-JSON path also needs to surface the
    verifier's command and stdout/stderr so an operator triaging from
    the terminal output has the same evidence the JSON consumer sees.
    """

    def test_failing_row_shows_command_and_output(
        self, repo_root, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "ShowMe",
                    "verification": "command",
                    "command": "echo evidence",
                    "pass_when": "stdout-json.unresolved_count == 99",
                },
            ],
        )
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(
                stdout=json.dumps({"unresolved_count": 0}),
                stderr="warning from verifier",
                returncode=0,
            ),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1"],
            )
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL   ShowMe" in out
        assert "command:" in out
        assert "stdout:" in out
        assert "warning from verifier" in out
