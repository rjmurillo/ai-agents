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

    def test_non_callable_result_rejected(self):
        # A lambda that yields a non-callable value (defensive guard for
        # a future expression form that does not produce a function).
        # `lambda d: 1` is callable, so we exercise the guard via the
        # boolean coercion: the function must be a callable in the
        # is-checked sense. We force the result to a non-callable by
        # supplying a degenerate expression that startswith "lambda" but
        # whose body is parsed as something other than a function.
        # Python forbids that at parse-time, so this branch is reached
        # only via the ``isinstance(expr, str)`` + ``startswith`` path.
        # The only way to exercise the ``not callable(func)`` line is to
        # call _eval_pass_when_python with an expression that compiles
        # but produces a non-callable. None such exists for ``lambda``,
        # so we confirm the guard via direct unit-style exercise: feed
        # a value that bypasses the startswith check by patching it.
        with patch.object(
            _dispatcher, "eval", return_value=42, create=True,
        ):
            with pytest.raises(ValueError, match="did not yield a callable"):
                _dispatcher._eval_pass_when_python({}, "lambda d: True")


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
        assert "missing command" in capsys.readouterr().err

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
