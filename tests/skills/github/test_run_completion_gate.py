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
import os
import subprocess
import sys
from pathlib import Path
from typing import cast
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

    The CWE-829 config trust check is stubbed to "trusted" here because
    tmp_path is not a git repository and these tests exercise dispatch,
    DSL, and schema logic, not the trust boundary. The trust boundary
    has its own dedicated tests (TestConfigTrustBoundary) that drive
    ``main`` against a real git repository with NO stubbing, which
    proves the wiring this fixture bypasses.
    """
    monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        _dispatcher,
        "_verify_config_trust",
        lambda *_a, **_k: _dispatcher.TrustCheck(_dispatcher.TRUST_TRUSTED, ""),
    )
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
        assert result["criteria"][0]["stdout_json"] == {
            "unresolved_count": 0,
            "fetched_pages_complete": True,
        }

    def test_writes_gate_evidence_file_before_merge_action(
        self, repo_root, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
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
        evidence_path = tmp_path / ".agents" / "pr-comments" / "PR-4377" / "gate.json"

        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=json.dumps({"unresolved_count": 0})),
        ):
            rc = _dispatcher.main(
                [
                    "--config", str(config_path),
                    "--pull-request", "4377",
                    "--evidence-path", str(evidence_path),
                ],
            )

        assert rc == 0
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["pull_request"] == 4377
        assert evidence["all_passed"] is True
        assert evidence["criteria"][0]["stdout_json"] == {"unresolved_count": 0}

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


class TestRepositoryConfigContract:
    """Keep the trusted repository config inside the safe evaluator subset."""

    def test_ready_criterion_expression_is_evaluable(self):
        # src/copilot-cli/commands/pr-review-config.yaml is the production
        # contract consumed by /pr-autofix before it enables auto-merge.
        config_path = (
            _REPO_ROOT
            / "src"
            / "copilot-cli"
            / "commands"
            / "pr-review-config.yaml"
        )
        config = _dispatcher.yaml.safe_load(
            config_path.read_text(encoding="utf-8"),
        )
        criterion = next(
            item
            for item in config["completion_criteria"]
            if item["name"] == "PR is ready to merge (CI green, no conflicts)"
        )
        data = {
            "CanMerge": True,
            "CIPassing": True,
            "fetched_pages_complete": True,
            "UnresolvedThreads": 0,
            "MergeStateStatus": "CLEAN",
            "UndisposedNonRequiredFailures": [],
        }

        assert _dispatcher._eval_pass_when_python(
            data,
            criterion["pass_when_python"],
        ) is True


class TestPassWhenPythonNegativeBranches:
    """Cover the AST-rejection paths in _eval_pass_when_python.

    These branches are security-relevant: they bound the expression surface
    accepted by the safe AST evaluator. AGENTS.md sets the security-critical
    coverage floor at 100%; missing these branches violates that floor.
    """

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match="must be a string"):
            _dispatcher._eval_pass_when_python({}, cast(str, 123))

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
            _dispatcher._format_command("echo {pr}", cast(int, "1; rm -rf /"))

    def test_bool_pr_number_rejected(self):
        # bools are int subclasses in Python; the guard rejects them
        # explicitly so a downstream caller cannot smuggle True/False.
        with pytest.raises(TypeError, match="pr_number must be int"):
            _dispatcher._format_command("echo {pr}", cast(int, True))


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

    def test_and_short_circuits_false_operand(self):
        assert _dispatcher._eval_pass_when_python(
            {"a": False},
            "lambda d: d.get('a') is True and d['unsupported'] == 1",
        ) is False

    def test_or_short_circuits_true_operand(self):
        assert _dispatcher._eval_pass_when_python(
            {"a": True},
            "lambda d: d.get('a') is True or d['unsupported'] == 1",
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


class TestMergeReadyFourConditionGate:
    """The pr-autofix ready-to-merge gate must preserve all blockers.

    CanMerge is necessary but not sufficient. The completion gate also checks
    required-check status, review-thread count, merge-state policy, and partial
    fetch integrity so a verifier regression cannot fail open.
    """

    # The exact predicate shipped in .claude/commands/pr-review-config.yaml
    # for the "PR is ready to merge" criterion. Kept verbatim so this test
    # exercises the real contract, not a paraphrase.
    _MERGE_READY_PASS_WHEN = (
        "lambda d: d.get('CanMerge') is True "
        "and d.get('CIPassing') is True "
        "and d.get('fetched_pages_complete') is True "
        "and d.get('UnresolvedThreads') == 0 "
        "and d.get('MergeStateStatus') in ('CLEAN', 'UNSTABLE')"
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

    def _run_gate(self, tmp_path: Path, capsys, verifier_data: dict) -> tuple[int, dict]:
        config_path = self._merge_ready_config(tmp_path)
        with patch.object(
            _dispatcher.subprocess, "run",
            return_value=_make_proc(stdout=json.dumps(verifier_data), returncode=0),
        ):
            rc = _dispatcher.main(
                ["--config", str(config_path), "--pull-request", "1", "--json"],
            )
        return rc, json.loads(capsys.readouterr().out)

    def test_clean_ready_pr_passes(self, repo_root, tmp_path, capsys):
        rc, result = self._run_gate(
            tmp_path,
            capsys,
            {
                "CanMerge": True,
                "CIPassing": True,
                "UnresolvedThreads": 0,
                "MergeStateStatus": "CLEAN",
                "fetched_pages_complete": True,
            },
        )
        assert rc == 0
        assert result["criteria"][0]["passed"] is True

    def test_unstable_ready_pr_passes(self, repo_root, tmp_path, capsys):
        rc, result = self._run_gate(
            tmp_path,
            capsys,
            {
                "CanMerge": True,
                "CIPassing": True,
                "UnresolvedThreads": 0,
                "MergeStateStatus": "UNSTABLE",
                "fetched_pages_complete": True,
            },
        )
        assert rc == 0
        assert result["criteria"][0]["passed"] is True

    @pytest.mark.parametrize(
        ("override", "reason"),
        [
            ({"CanMerge": False}, "CanMerge false"),
            ({"CIPassing": False}, "required checks failing"),
            ({"UnresolvedThreads": 1}, "unresolved thread"),
            ({"MergeStateStatus": "BLOCKED"}, "blocked merge state"),
            ({"MergeStateStatus": "BEHIND"}, "behind merge state"),
            ({"fetched_pages_complete": False}, "partial fetch"),
            ({"CanMerge": None}, "missing CanMerge"),
        ],
    )
    def test_any_missing_condition_fails_closed(
        self, repo_root, tmp_path, capsys, override, reason,
    ):
        data = {
            "CanMerge": True,
            "CIPassing": True,
            "UnresolvedThreads": 0,
            "MergeStateStatus": "CLEAN",
            "fetched_pages_complete": True,
        }
        data.update(override)

        rc, result = self._run_gate(tmp_path, capsys, data)

        assert rc == 1, reason
        assert result["criteria"][0]["passed"] is False


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

# ---------------------------------------------------------------------------
# CWE-829 config trust boundary (issue #5072)
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git hermetically: no user/system config, no signing, no hooks."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
         *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A real git repository standing in for the project root.

    Unlike ``repo_root``, this fixture does NOT stub
    ``_verify_config_trust``: tests using it drive ``main`` through the
    real trust check, proving the wiring end to end.
    """
    monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
    _git(tmp_path, "init", "-q")
    return tmp_path


def _commit_as_trusted(repo: Path, *paths: Path) -> None:
    """Commit paths and point refs/remotes/origin/main at the result."""
    _git(repo, "add", *[str(p.relative_to(repo)) for p in paths])
    _git(repo, "commit", "-q", "-m", "trusted config")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def _marker_criterion(tmp_path: Path, marker: Path) -> list[dict]:
    """A criterion whose command PROVABLY executed: it writes a marker file.

    The marker is the isolating assertion for the negative controls: if
    the dispatcher executes the command, the marker exists; a halt that
    happened only after execution cannot hide.
    """
    verifier = tmp_path / "verifier.py"
    verifier.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran')\n"
        "print(json.dumps({'ok': True}))\n",
        encoding="utf-8",
    )
    return [
        {
            "name": "MarkerCriterion",
            "verification": "command",
            "command": f"{sys.executable} {verifier}",
            "pass_when": "stdout-json.ok == true",
        },
    ]


class TestConfigTrustBoundary:
    """The dispatcher must not execute a config that diverges from the
    trusted ref (CWE-829). No subprocess stubbing: real git, real
    dispatch, marker files proving execution or its absence.
    """

    def test_identical_config_proceeds_and_executes(
        self, git_repo, tmp_path, capsys,
    ):
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(git_repo, config_path)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )

        assert rc == 0
        assert marker.exists(), "trusted config must dispatch normally"
        payload = json.loads(capsys.readouterr().out)
        assert payload["config_trust"] == {
            "status": "trusted",
            "trusted_ref": "origin/main",
            "approved": False,
        }

    def test_tampered_config_halts_without_executing_command(
        self, git_repo, tmp_path, capsys,
    ):
        # Trusted copy holds a benign criterion; the PR tree rewrites the
        # command. The marker file is the negative control: it must NOT
        # appear, proving the tampered command never ran.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Benign",
                    "verification": "command",
                    "command": "echo benign",
                    "pass_when": "stdout-json.ok == true",
                },
            ],
        )
        _commit_as_trusted(git_repo, config_path)
        marker = tmp_path / "pwned.txt"
        _write_config(tmp_path, _marker_criterion(tmp_path, marker))

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), (
            "tampered completion_criteria.command must never execute"
        )
        err = capsys.readouterr().err
        assert "HALT" in err
        assert "diverged" in err
        assert "MarkerCriterion" in err, "the halt must surface the diff"
        assert "--approve-untrusted-config" in err

    def test_whitespace_only_change_halts(self, git_repo, tmp_path, capsys):
        # Byte identity is the contract: even a trailing newline halts.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(git_repo, config_path)
        config_path.write_bytes(config_path.read_bytes() + b"\n")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()
        assert "diverged" in capsys.readouterr().err

    def test_bidi_controls_in_surfaced_diff_are_escaped(
        self, git_repo, tmp_path, capsys,
    ):
        # Trojan Source (CVE-2021-42574): a bidi control such as U+202E
        # in the tampered content could make the terminal render a
        # different command than the one approval would execute, and a
        # zero-width character such as U+200B (also category Cf) can
        # hide inside a command or filename invisibly. The surfaced
        # diff must show visible escapes, never the raw characters.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(git_repo, config_path)
        config_path.write_text(
            config_path.read_text(encoding="utf-8")
            + "\n\u202eevil\u200bhidden\x1b[31mansi",
            encoding="utf-8",
        )

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()
        err = capsys.readouterr().err
        assert "\u202e" not in err
        assert "\\u202e" in err
        assert "\u200b" not in err
        assert "\\u200b" in err
        assert "\x1b" not in err
        assert "\\u001b" in err

    def test_config_in_nested_repository_fails_closed(
        self, git_repo, tmp_path, capsys,
    ):
        # A PR can vendor a nested repository (initialized submodule or
        # committed checkout) whose origin/main the ATTACKER controls.
        # A config inside it is byte-identical to that attacker-owned
        # trusted ref, so trust must anchor at the project root's work
        # tree and refuse a config from any other one (exit 3, never
        # approvable).
        nested = tmp_path / "vendor"
        nested.mkdir()
        _git(nested, "init", "-q")
        marker = tmp_path / "ran.txt"
        config_path = _write_config(nested, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(nested, config_path)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 3
        assert not marker.exists()
        err = capsys.readouterr().err
        assert "different git work tree" in err

    def test_symlinked_config_is_rejected_without_reading_target(
        self, git_repo, tmp_path, capsys,
    ):
        # CWE-59/CWE-200: validate_safe_path resolves symlinks, so a
        # PR-committed symlink at the config path would redirect the
        # trust check to its target, and a local-only target (untracked
        # .env, .git/config) would be printed in full by the
        # missing-base approval diff. The gate must reject the symlink
        # before reading; the secret must never reach stderr.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(git_repo, config_path)
        secret = tmp_path / ".env"
        secret.write_text("SECRET_TOKEN=hunter2\n", encoding="utf-8")
        config_path.unlink()
        try:
            config_path.symlink_to(secret)
        except OSError:
            pytest.skip("filesystem does not support symlinks")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()
        err = capsys.readouterr().err
        assert "symlink" in err
        assert "hunter2" not in err

    def test_symlinked_parent_directory_is_rejected(
        self, git_repo, tmp_path, capsys,
    ):
        # Parent-directory variant of the same redirect: the final
        # component is a regular file but a directory on the path is a
        # PR-controlled symlink.
        target_dir = tmp_path / "real"
        target_dir.mkdir()
        local_only = target_dir / "pr-review-config.yaml"
        local_only.write_text("LOCAL_ONLY: yes\n", encoding="utf-8")
        link_dir = tmp_path / "linkdir"
        try:
            link_dir.symlink_to(target_dir, target_is_directory=True)
        except OSError:
            pytest.skip("filesystem does not support symlinks")

        rc = _dispatcher.main(
            [
                "--config", str(link_dir / "pr-review-config.yaml"),
                "--pull-request", "1",
            ],
        )

        assert rc == 2
        err = capsys.readouterr().err
        assert "symlink" in err
        assert "LOCAL_ONLY" not in err

    def test_config_missing_from_trusted_ref_halts(
        self, git_repo, tmp_path, capsys,
    ):
        # origin/main exists but never carried the config: fail closed,
        # because tampering is indistinguishable from a new file.
        dummy = tmp_path / "README.md"
        dummy.write_text("x", encoding="utf-8")
        _commit_as_trusted(git_repo, dummy)
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()
        err = capsys.readouterr().err
        assert "missing-base" in err
        # missing-base is approvable, so the halt must surface the exact
        # command a human would be approving, as a full-file addition
        # diff (there is no trusted copy to diff against). The config's
        # command string names verifier.py; its appearance on stderr
        # proves the approvable content was shown, not just an absence
        # message.
        assert "verifier.py" in err
        assert "(working tree)" in err

    def test_trusted_ref_absent_fails_closed(self, git_repo, tmp_path, capsys):
        # A repo with commits but no origin/main: verification is
        # impossible, so the gate halts with the external-error code.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _git(git_repo, "add", str(config_path.relative_to(git_repo)))
        _git(git_repo, "commit", "-q", "-m", "no origin ref")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 3
        assert not marker.exists()
        assert "git-error" in capsys.readouterr().err

    def test_not_a_git_repo_fails_closed(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 3
        assert not marker.exists()
        assert "git-error" in capsys.readouterr().err

    def test_approval_flag_executes_diverged_config_with_warning(
        self, git_repo, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Benign",
                    "verification": "command",
                    "command": "echo benign",
                    "pass_when": "stdout-json.ok == true",
                },
            ],
        )
        _commit_as_trusted(git_repo, config_path)
        marker = tmp_path / "approved.txt"
        _write_config(tmp_path, _marker_criterion(tmp_path, marker))

        rc = _dispatcher.main(
            [
                "--config", str(config_path),
                "--pull-request", "1",
                "--json",
                "--approve-untrusted-config",
            ],
        )

        assert rc == 0
        assert marker.exists(), "explicit approval must allow dispatch"
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        payload = json.loads(captured.out)
        assert payload["config_trust"]["status"] == "diverged"
        assert payload["config_trust"]["approved"] is True

    def test_approval_flag_covers_missing_base(self, git_repo, tmp_path, capsys):
        dummy = tmp_path / "README.md"
        dummy.write_text("x", encoding="utf-8")
        _commit_as_trusted(git_repo, dummy)
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))

        rc = _dispatcher.main(
            [
                "--config", str(config_path),
                "--pull-request", "1",
                "--approve-untrusted-config",
            ],
        )

        assert rc == 0
        assert marker.exists()
        assert "WARNING" in capsys.readouterr().err

    def test_malformed_trusted_ref_rejected_before_git_runs(
        self, git_repo, tmp_path, capsys,
    ):
        # A ref starting with "-" could be parsed as a git option
        # (argument injection); it must be rejected up front.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(git_repo, config_path)

        rc = _dispatcher.main(
            [
                "--config", str(config_path),
                "--pull-request", "1",
                "--trusted-ref=--upload-pack=/bin/true",
            ],
        )

        assert rc == 2
        assert not marker.exists()
        assert "malformed --trusted-ref" in capsys.readouterr().err

    def test_custom_trusted_ref_is_honored(self, git_repo, tmp_path):
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _git(git_repo, "add", str(config_path.relative_to(git_repo)))
        _git(git_repo, "commit", "-q", "-m", "trusted on a custom ref")
        _git(git_repo, "update-ref", "refs/remotes/upstream/release", "HEAD")

        rc = _dispatcher.main(
            [
                "--config", str(config_path),
                "--pull-request", "1",
                "--trusted-ref", "upstream/release",
            ],
        )

        assert rc == 0
        assert marker.exists()


class TestVerifyConfigTrustErrorBranches:
    """Unit coverage for _verify_config_trust branches that need fault
    injection (100% coverage requirement for security-critical code).
    """

    def test_git_timeout_reports_git_error(self, tmp_path, monkeypatch):
        def _boom(args, cwd):
            raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=30)

        monkeypatch.setattr(_dispatcher, "_run_git", _boom)
        config = tmp_path / "c.yaml"
        config.write_text("{}", encoding="utf-8")

        result = _dispatcher._verify_config_trust(config, "origin/main", b"{}")

        assert result.status == _dispatcher.TRUST_GIT_ERROR
        assert "trust verification failed" in result.detail

    def test_git_binary_missing_reports_git_error(self, tmp_path, monkeypatch):
        def _boom(args, cwd):
            raise FileNotFoundError("git")

        monkeypatch.setattr(_dispatcher, "_run_git", _boom)
        config = tmp_path / "c.yaml"
        config.write_text("{}", encoding="utf-8")

        result = _dispatcher._verify_config_trust(config, "origin/main", b"{}")

        assert result.status == _dispatcher.TRUST_GIT_ERROR

    def test_config_outside_toplevel_reports_git_error(
        self, tmp_path, monkeypatch,
    ):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()

        def _fake(args, cwd):
            if args[:2] == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout=str(elsewhere).encode() + b"\n", stderr=b"",
                )
            raise AssertionError(f"unexpected git call: {args}")

        monkeypatch.setattr(_dispatcher, "_run_git", _fake)
        config = tmp_path / "c.yaml"
        config.write_text("{}", encoding="utf-8")

        result = _dispatcher._verify_config_trust(config, "origin/main", b"{}")

        assert result.status == _dispatcher.TRUST_GIT_ERROR
        assert "outside git work tree" in result.detail

    def test_cat_file_filters_failure_reports_git_error(
        self, tmp_path, monkeypatch,
    ):
        def _fake(args, cwd):
            if args[:2] == ["cat-file", "--filters"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=128, stdout=b"", stderr=b"boom",
                )
            if args[:2] == ["rev-parse", "--symbolic-full-name"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout=b"refs/remotes/origin/main\n", stderr=b"",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout=str(tmp_path).encode() + b"\n", stderr=b"",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _fake)
        config = tmp_path / "c.yaml"
        config.write_text("{}", encoding="utf-8")

        result = _dispatcher._verify_config_trust(config, "origin/main", b"{}")

        assert result.status == _dispatcher.TRUST_GIT_ERROR
        assert "cat-file --filters" in result.detail

    def test_ls_tree_failure_is_git_error_not_missing_base(
        self, tmp_path, monkeypatch,
    ):
        # cat-file -e exits 128 for BOTH an absent path and an
        # object-store error, which would have made verification
        # failures approvable as missing-base. The existence check now
        # uses ls-tree; a nonzero exit there must be the non-approvable
        # git-error (exit 3), never missing-base.
        def _fake(args, cwd):
            if args[:1] == ["ls-tree"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=128, stdout=b"",
                    stderr=b"fatal: object store corrupt",
                )
            if args[:2] == ["rev-parse", "--symbolic-full-name"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout=b"refs/remotes/origin/main\n", stderr=b"",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout=str(tmp_path).encode() + b"\n", stderr=b"",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _fake)
        config = tmp_path / "c.yaml"
        config.write_text("{}", encoding="utf-8")

        result = _dispatcher._verify_config_trust(config, "origin/main", b"{}")

        assert result.status == _dispatcher.TRUST_GIT_ERROR
        assert result.status != _dispatcher.TRUST_MISSING_BASE
        assert "ls-tree" in result.detail


class TestTrustBoundaryHardening:
    """Findings from the PR #5089 security review: self-referential
    trusted refs, TOCTOU, EOL normalization, and parser crash classes.
    """

    def test_head_as_trusted_ref_fails_closed(self, git_repo, tmp_path, capsys):
        # F2: `--trusted-ref HEAD` would make the PR's own tampered config
        # "trusted". HEAD is not a remote-tracking ref, so it must be
        # refused before any dispatch.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _git(git_repo, "add", str(config_path.relative_to(git_repo)))
        _git(git_repo, "commit", "-q", "-m", "attacker controls HEAD")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1",
             "--trusted-ref", "HEAD"],
        )

        assert rc == 3
        assert not marker.exists(), "HEAD-anchored trust must never dispatch"
        err = capsys.readouterr().err
        assert "remote-tracking" in err

    def test_local_branch_as_trusted_ref_fails_closed(
        self, git_repo, tmp_path, capsys,
    ):
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _git(git_repo, "add", str(config_path.relative_to(git_repo)))
        _git(git_repo, "commit", "-q", "-m", "local branch is PR-movable")
        _git(git_repo, "branch", "pr-branch")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1",
             "--trusted-ref", "pr-branch"],
        )

        assert rc == 3
        assert not marker.exists()
        assert "remote-tracking" in capsys.readouterr().err

    def test_eol_only_difference_under_autocrlf_stays_trusted(
        self, git_repo, tmp_path,
    ):
        # F4: a consumer repo with core.autocrlf=true checks the config out
        # with CRLF while the trusted blob stores LF. The comparison uses
        # `git cat-file --filters`, so an EOL-only difference is not a
        # divergence and the gate does not train operators to bypass.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(git_repo, config_path)
        _git(git_repo, "config", "core.autocrlf", "true")
        lf_bytes = config_path.read_bytes()
        assert b"\r\n" not in lf_bytes
        config_path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 0
        assert marker.exists()

    def test_content_tamper_under_autocrlf_still_halts(
        self, git_repo, tmp_path,
    ):
        # Negative control for the EOL allowance: CRLF conversion plus a
        # real content change must still halt without executing.
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Benign",
                    "verification": "command",
                    "command": "echo benign",
                    "pass_when": "stdout-json.ok == true",
                },
            ],
        )
        _commit_as_trusted(git_repo, config_path)
        _git(git_repo, "config", "core.autocrlf", "true")
        marker = tmp_path / "pwned.txt"
        _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        crlf = config_path.read_bytes().replace(b"\n", b"\r\n")
        config_path.write_bytes(crlf)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()

    def test_deeply_nested_config_fails_config_not_crash(
        self, repo_root, tmp_path, capsys,
    ):
        # F6: RecursionError is not a yaml.YAMLError subclass; a nesting
        # bomb must exit 2 (config error), not escape as a traceback with
        # exit 1 ("a criterion failed").
        config_path = tmp_path / "pr-review-config.yaml"
        config_path.write_bytes(b"[" * 200000 + b"]" * 200000)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert "Failed to load config" in capsys.readouterr().err

    def test_config_is_read_exactly_once(self, git_repo, tmp_path, monkeypatch):
        # F3 (CWE-367): the bytes that were trust-verified must be the
        # bytes that are parsed and dispatched. One read, one buffer.
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _commit_as_trusted(git_repo, config_path)

        reads: list[Path] = []
        original_read_bytes = Path.read_bytes

        def _counting_read_bytes(self: Path) -> bytes:
            if self == config_path:
                reads.append(self)
            return original_read_bytes(self)

        monkeypatch.setattr(Path, "read_bytes", _counting_read_bytes)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 0
        assert len(reads) == 1, (
            f"config read {len(reads)} times; a second read reopens the "
            f"TOCTOU window between verification and dispatch"
        )


class TestConfigLoaderBranches:
    """Unit coverage for the split read/parse loader (100% requirement)."""

    def test_unreadable_existing_config_reports_config_error(
        self, tmp_path, monkeypatch,
    ):
        config = tmp_path / "c.yaml"
        config.write_text("{}", encoding="utf-8")

        def _boom(self: Path) -> bytes:
            raise OSError("io broke")

        monkeypatch.setattr(Path, "read_bytes", _boom)
        with pytest.raises(_dispatcher.ConfigError, match="Cannot read config"):
            _dispatcher._read_config_bytes(config)

    def test_missing_pyyaml_reports_config_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_dispatcher, "_HAVE_YAML", False)
        with pytest.raises(_dispatcher.ConfigError, match="PyYAML is required"):
            _dispatcher._load_config_bytes(b"{}", tmp_path / "c.yaml")

    def test_non_utf8_config_reports_config_error(self, tmp_path):
        with pytest.raises(_dispatcher.ConfigError, match="not valid UTF-8"):
            _dispatcher._load_config_bytes(b"\xff\xfe\x00A", tmp_path / "c.yaml")

    def test_non_mapping_root_reports_config_error(self, tmp_path):
        with pytest.raises(_dispatcher.ConfigError, match="must be a mapping"):
            _dispatcher._load_config_bytes(b"[1, 2]", tmp_path / "c.yaml")


class TestVerifyRefCommitBranch:
    """The ^{commit} verify after the symbolic check: defense in depth for
    a remote-tracking ref that resolves symbolically but not to a commit.
    """

    def test_symbolic_ok_but_verify_fails_reports_git_error(
        self, tmp_path, monkeypatch,
    ):
        def _fake(args, cwd):
            if args[:2] == ["rev-parse", "--symbolic-full-name"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout=b"refs/remotes/origin/main\n", stderr=b"",
                )
            if args[:2] == ["rev-parse", "--verify"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=1, stdout=b"", stderr=b"",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout=str(tmp_path).encode() + b"\n", stderr=b"",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _fake)
        config = tmp_path / "c.yaml"
        config.write_text("{}", encoding="utf-8")

        result = _dispatcher._verify_config_trust(config, "origin/main", b"{}")

        assert result.status == _dispatcher.TRUST_GIT_ERROR
        assert "not found" in result.detail


class TestApprovalDoesNotCoverGitError:
    """PR #5089 agent-safety finding: on git-error there is no trustworthy
    diff to inspect, so explicit approval must not unlock dispatch.
    """

    def test_approval_flag_rejected_when_not_a_git_repo(
        self, tmp_path, monkeypatch, capsys,
    ):
        monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))

        rc = _dispatcher.main(
            [
                "--config", str(config_path),
                "--pull-request", "1",
                "--approve-untrusted-config",
            ],
        )

        assert rc == 3
        assert not marker.exists(), (
            "approval must not unlock dispatch when verification is impossible"
        )
        err = capsys.readouterr().err
        assert "does not apply when verification is impossible" in err

    def test_approval_flag_rejected_when_trusted_ref_absent(
        self, git_repo, tmp_path, capsys,
    ):
        marker = tmp_path / "ran.txt"
        config_path = _write_config(tmp_path, _marker_criterion(tmp_path, marker))
        _git(git_repo, "add", str(config_path.relative_to(git_repo)))
        _git(git_repo, "commit", "-q", "-m", "no origin ref")

        rc = _dispatcher.main(
            [
                "--config", str(config_path),
                "--pull-request", "1",
                "--approve-untrusted-config",
            ],
        )

        assert rc == 3
        assert not marker.exists()
