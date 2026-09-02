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
import yaml

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
_PR_REVIEW_CONFIG_PATH = _REPO_ROOT / ".claude" / "commands" / "pr-review-config.yaml"
_MERGE_READY_CRITERION = "PR is ready to merge (CI green, no conflicts)"


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


def _shipped_merge_ready_predicate() -> str:
    """The `pass_when_python` string for the merge-ready criterion, as shipped.

    Read from `.claude/commands/pr-review-config.yaml` rather than transcribed.
    A transcribed copy is a paraphrase the moment the config moves, and the
    tests then certify a predicate nobody runs: the hand-copied version this
    replaced had already lost the `UndisposedNonRequiredFailures` clause, so
    every case below exercised a four-condition gate while pr-autofix ran a
    five-condition one.
    """
    config = yaml.safe_load(_PR_REVIEW_CONFIG_PATH.read_text(encoding="utf-8"))
    for criterion in config["completion_criteria"]:
        if criterion.get("name") == _MERGE_READY_CRITERION:
            return criterion["pass_when_python"]
    raise AssertionError(
        f"no criterion named {_MERGE_READY_CRITERION!r} in "
        f"{_PR_REVIEW_CONFIG_PATH}; the gate this suite tests has been renamed "
        f"or removed",
    )


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

    Both CWE-829 trust checks (the config file and the files its
    commands name) are stubbed to "trusted" here because tmp_path is not
    a git repository and these tests exercise dispatch, DSL, and schema
    logic, not the trust boundary. Each boundary has its own dedicated
    tests (TestConfigTrustBoundary, TestCommandTrustBoundary) that drive
    ``main`` against a real git repository with NO stubbing, which
    proves the wiring this fixture bypasses.
    """
    monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        _dispatcher,
        "_verify_config_trust",
        lambda *_a, **_k: _dispatcher.TrustCheck(_dispatcher.TRUST_TRUSTED, ""),
    )
    monkeypatch.setattr(
        _dispatcher,
        "_verify_command_trust",
        lambda *_a, **_k: _dispatcher.CommandTrustCheck(
            _dispatcher.COMMAND_TRUST_TRUSTED, [], [], [], [], "",
        ),
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

    def test_ready_criterion_expression_is_evaluable(self, monkeypatch, capsys):
        # .claude/commands/pr-review-config.yaml is the live configuration
        # consumed by /pr-autofix before it enables auto-merge. Drive main()
        # through every production criterion so this contract covers config
        # loading, dispatch, and the final process verdict, not just the private
        # expression helper.
        config_path = _REPO_ROOT / ".claude" / "commands" / "pr-review-config.yaml"
        monkeypatch.setattr(
            _dispatcher,
            "_verify_config_trust",
            lambda *_a, **_k: _dispatcher.TrustCheck(
                _dispatcher.TRUST_TRUSTED,
                "",
            ),
        )
        # _verify_command_trust makes its own real `git` subprocess calls
        # (rev-parse, ls-files, ls-tree, cat-file) to verify the verifier
        # scripts named by the config's criteria. Those calls would
        # otherwise consume entries from `responses` below, which are
        # canned JSON meant for the criterion dispatch that follows this
        # check. The command-trust boundary itself has dedicated coverage
        # in TestCommandTrustBoundary; this test's scope is criterion
        # evaluation and dispatch, so mock it trusted the same way the
        # config check above is mocked trusted.
        monkeypatch.setattr(
            _dispatcher,
            "_verify_command_trust",
            lambda *_a, **_k: _dispatcher.CommandTrustCheck(
                _dispatcher.COMMAND_TRUST_TRUSTED,
                [],
                [],
                [],
                [],
                "",
            ),
        )
        responses = [
            _make_proc(
                stdout=json.dumps(
                    {"unresolved_count": 0, "fetched_pages_complete": True},
                ),
            ),
            _make_proc(
                stdout=json.dumps(
                    {
                        "active_suppressed_count": 0,
                        "unknown_suppressed_count": 0,
                        "fetched_pages_complete": True,
                    },
                ),
            ),
            _make_proc(
                stdout=json.dumps(
                    {
                        "unreachable_count": 0,
                        "invalid_count": 0,
                        "ambiguous_count": 0,
                        "fetched_pages_complete": True,
                    },
                ),
            ),
            _make_proc(
                stdout=json.dumps(
                    {
                        "CanMerge": True,
                        "CIPassing": True,
                        "fetched_pages_complete": True,
                        "UnresolvedThreads": 0,
                        "MergeStateStatus": "CLEAN",
                        "UndisposedNonRequiredFailures": [],
                    },
                ),
            ),
            _make_proc(stdout=json.dumps({"merged": False})),
        ]

        with patch.object(
            _dispatcher.subprocess,
            "run",
            side_effect=responses,
        ) as dispatched:
            rc = _dispatcher.main(
                [
                    "--config",
                    str(config_path),
                    "--pull-request",
                    "5147",
                    "--json",
                ],
            )

        assert rc == 0
        assert dispatched.call_count == len(responses)
        result = json.loads(capsys.readouterr().out)
        assert result["all_passed"] is True
        ready = next(
            item
            for item in result["criteria"]
            if item["name"] == "PR is ready to merge (CI green, no conflicts)"
        )
        assert ready["passed"] is True


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

    _MERGE_READY_PASS_WHEN = _shipped_merge_ready_predicate()

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

    @staticmethod
    def _ready_payload(merge_state: str = "CLEAN") -> dict:
        """A merge-ready verifier verdict, every gate condition satisfied."""
        return {
            "CanMerge": True,
            "CIPassing": True,
            "UnresolvedThreads": 0,
            "MergeStateStatus": merge_state,
            "fetched_pages_complete": True,
            "UndisposedNonRequiredFailures": [],
        }

    @pytest.mark.parametrize("merge_state", ["CLEAN", "HAS_HOOKS", "UNSTABLE"])
    def test_every_supported_merge_state_passes(
        self, repo_root, tmp_path, capsys, merge_state,
    ):
        """The three states `test_pr_merge_ready.py` routes to T1 clear the gate.

        `HAS_HOOKS` is here because the producer's `_SUPPORTED_MERGE_STATES`
        allowlists it while this gate's tuple did not, so a green `HAS_HOOKS`
        PR reached the auto-merge tier and then failed a mandatory gate with no
        work left to do (issue #4899 review round). The two sets have to move
        together; `TestSupportedStatesClearTheCompletionGate` in
        `tests/test_test_pr_merge_ready.py` drives the real producer verdict
        into this real predicate and fails when they drift apart.
        """
        rc, result = self._run_gate(tmp_path, capsys, self._ready_payload(merge_state))

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
            ({"MergeStateStatus": "DIRTY"}, "conflicted merge state"),
            ({"MergeStateStatus": "UNKNOWN"}, "unsupported merge state"),
            (
                {"MergeStateStatus": "A_STATE_GITHUB_ADDS_LATER"},
                "merge state GitHub has not defined yet",
            ),
            ({"fetched_pages_complete": False}, "partial fetch"),
            ({"CanMerge": None}, "missing CanMerge"),
            (
                {"UndisposedNonRequiredFailures": ["flaky-lint"]},
                "undisposed non-required failure",
            ),
        ],
    )
    def test_any_missing_condition_fails_closed(
        self, repo_root, tmp_path, capsys, override, reason,
    ):
        data = self._ready_payload()
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

    The cwd moves into the work tree because that is where the gate runs
    in production: relative command paths resolve against the cwd, and
    ``_verify_command_trust`` refuses to classify them when the cwd sits
    outside the tree it is verifying.
    """
    monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _commit_as_trusted(repo: Path, *paths: Path) -> None:
    """Commit paths and point refs/remotes/origin/main at the result."""
    _git(repo, "add", *[str(p.relative_to(repo)) for p in paths])
    _git(repo, "commit", "-q", "-m", "trusted config")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def _verifier_path(tmp_path: Path) -> Path:
    """The script `_marker_criterion` writes and its command names.

    The command trust boundary byte-compares every work-tree file an
    argv names, so any test that expects dispatch must commit this file
    to the trusted ref alongside the config.
    """
    return tmp_path / "verifier.py"


def _marker_criterion(tmp_path: Path, marker: Path) -> list[dict]:
    """A criterion whose command PROVABLY executed: it writes a marker file.

    The marker is the isolating assertion for the negative controls: if
    the dispatcher executes the command, the marker exists; a halt that
    happened only after execution cannot hide.
    """
    verifier = _verifier_path(tmp_path)
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
        _commit_as_trusted(git_repo, config_path, _verifier_path(tmp_path))

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
        assert payload["command_trust"]["status"] == "trusted"
        assert payload["command_trust"]["checked_files"] == ["verifier.py"]
        assert payload["command_trust"]["untrusted_files"] == []

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
        _git(git_repo, "add", str(_verifier_path(tmp_path).relative_to(git_repo)))
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
        verifier = _verifier_path(tmp_path)
        _commit_as_trusted(git_repo, config_path, verifier)
        _git(git_repo, "config", "core.autocrlf", "true")
        # A CRLF checkout converts every text file, not just the config,
        # so the verifier the command names gets the same treatment.
        for path in (config_path, verifier):
            lf_bytes = path.read_bytes()
            assert b"\r\n" not in lf_bytes
            path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))

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
        _commit_as_trusted(git_repo, config_path, _verifier_path(tmp_path))

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


def _write_marker_script(script: Path, marker: Path) -> Path:
    """Write a verifier that PROVES execution by creating ``marker``."""
    script.write_text(
        "import json, pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran')\n"
        "print(json.dumps({'ok': True}))\n",
        encoding="utf-8",
    )
    return script


def _benign_script(script: Path) -> Path:
    """Write a verifier that passes and leaves no trace."""
    script.write_text(
        "import json\nprint(json.dumps({'ok': True}))\n", encoding="utf-8",
    )
    return script


def _script_criterion(name: str, script: Path, *extra_args: str) -> dict:
    return {
        "name": name,
        "verification": "command",
        "command": " ".join([sys.executable, str(script), *extra_args]),
        "pass_when": "stdout-json.ok == true",
    }


class TestCommandTrustBoundary:
    """The dispatcher must not execute a verifier file that differs from
    the trusted ref, even when the config itself is byte-identical
    (CWE-829 / CWE-494, issue #5099). No subprocess stubbing: real git,
    real dispatch, marker files proving execution or its absence.
    """

    def test_untouched_verifier_and_data_file_dispatch(
        self, git_repo, tmp_path, capsys,
    ):
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        data = tmp_path / "fixture.json"
        data.write_text("{}", encoding="utf-8")
        config_path = _write_config(
            tmp_path, [_script_criterion("Ok", script, str(data))],
        )
        _commit_as_trusted(git_repo, config_path, script, data)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )

        assert rc == 0
        assert marker.exists(), "trusted verifier files must dispatch"
        payload = json.loads(capsys.readouterr().out)
        assert payload["command_trust"]["status"] == "trusted"
        assert payload["command_trust"]["checked_files"] == [
            "verify.py", "fixture.json",
        ]
        assert payload["command_trust"]["untrusted_files"] == []

    def test_modified_verifier_script_halts_without_executing(
        self, git_repo, tmp_path, capsys,
    ):
        # The exact attack from issue #5099: the config is left untouched
        # (so config_trust stays "trusted") while the verifier script the
        # config names is rewritten. The marker is the negative control.
        script = _benign_script(tmp_path / "verify.py")
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(git_repo, config_path, script)

        marker = tmp_path / "pwned.txt"
        _write_marker_script(script, marker)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), (
            "a rewritten verifier script must never execute"
        )
        err = capsys.readouterr().err
        assert "HALT" in err
        assert "verify.py" in err
        assert "--approve-untrusted-config" in err

    def test_verifier_added_by_the_pr_and_absent_at_base_halts(
        self, git_repo, tmp_path, capsys,
    ):
        # A tracked verifier the base branch does not have is PR-supplied
        # code with nothing to compare against: untrusted, not "no
        # opinion". The PR commit lands after the trusted ref is set, so
        # origin/main does not carry the script.
        marker = tmp_path / "pwned.txt"
        script = _write_marker_script(tmp_path / "new_verify.py", marker)
        config_path = _write_config(tmp_path, [_script_criterion("New", script)])
        _commit_as_trusted(git_repo, config_path)
        _git(git_repo, "add", str(script.relative_to(git_repo)))
        _git(git_repo, "commit", "-q", "-m", "PR adds a verifier")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()
        assert "new_verify.py" in capsys.readouterr().err

    def test_untracked_operator_file_is_recorded_not_compared(
        self, git_repo, tmp_path, capsys,
    ):
        # A file the operator writes during the review, such as a local
        # scratch fixture. It is untracked, so it has no trusted-ref copy;
        # comparing it would halt every real run.
        #
        # This used to cite the shipped --dispositions-file as the example.
        # PR #5481 committed .agents/pr-checks/dispositions.json, so that
        # path is tracked now and is compared like any other tracked file.
        # The carve-out this test pins is unchanged; only the example moved.
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        dispositions = tmp_path / "dispositions.json"
        config_path = _write_config(
            tmp_path, [_script_criterion("Ok", script, str(dispositions))],
        )
        _commit_as_trusted(git_repo, config_path, script)
        dispositions.write_text("{}", encoding="utf-8")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )

        assert rc == 0
        assert marker.exists(), "an untracked operator file must not halt"
        payload = json.loads(capsys.readouterr().out)
        assert payload["command_trust"]["status"] == "trusted"
        assert payload["command_trust"]["checked_files"] == ["verify.py"]
        assert payload["command_trust"]["skipped_untracked_files"] == [
            "dispositions.json",
        ]

    def test_a_tracked_option_value_is_compared_like_any_other_path(
        self, git_repo, tmp_path, capsys,
    ):
        """Positive control for the pair above: tracked means compared.

        `_classify_argv_token` skips a token only when it is empty or
        starts with a hyphen. There is no option-position tracking, so an
        option VALUE naming an existing in-tree file is classified by what
        is on disk, exactly like a bare path argument. The test above shows
        the untracked half; without this one, a classifier that skipped
        every option value by position would satisfy it and nothing would
        notice.

        This is the mechanism by which the shipped `--dispositions-file`
        value is verified, which the `--command-trust` documentation now
        states.
        """
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        registry = tmp_path / "dispositions.json"
        registry.write_text("{}", encoding="utf-8")
        config_path = _write_config(
            tmp_path, [_script_criterion("Ok", script, str(registry))],
        )
        _commit_as_trusted(git_repo, config_path, script, registry)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command_trust"]["status"] == "trusted"
        assert payload["command_trust"]["checked_files"] == [
            "verify.py",
            "dispositions.json",
        ], "a tracked option value must be compared, not skipped by position"
        assert payload["command_trust"]["skipped_untracked_files"] == []

    def test_a_tampered_tracked_option_value_halts_the_gate(
        self, git_repo, tmp_path,
    ):
        """The half that matters: comparison without a halt is decoration.

        A registry that can wave a red check through has to stop the gate
        when a PR edits it, not merely appear in `checked_files`.
        """
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        registry = tmp_path / "dispositions.json"
        registry.write_text("{}", encoding="utf-8")
        config_path = _write_config(
            tmp_path, [_script_criterion("Ok", script, str(registry))],
        )
        _commit_as_trusted(git_repo, config_path, script, registry)
        registry.write_text('{"some-check": {"disposition": "known-flaky"}}',
                            encoding="utf-8")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), "no criterion may run on an edited registry"

    def test_untracked_script_does_not_mask_a_tampered_tracked_one(
        self, git_repo, tmp_path,
    ):
        # Negative control for the untracked carve-out: skipping an
        # untracked path must not stop a tracked, tampered script from
        # halting the gate.
        script = _benign_script(tmp_path / "verify.py")
        scratch = tmp_path / "scratch.json"
        config_path = _write_config(
            tmp_path, [_script_criterion("Ok", script, str(scratch))],
        )
        _commit_as_trusted(git_repo, config_path, script)
        scratch.write_text("{}", encoding="utf-8")
        marker = tmp_path / "pwned.txt"
        _write_marker_script(script, marker)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()

    def test_no_criterion_runs_when_a_later_one_is_untrusted(
        self, git_repo, tmp_path,
    ):
        # FR-3.1: every trust check precedes every dispatch. A trusted
        # first criterion must not run when a later one is untrusted.
        first_marker = tmp_path / "first.txt"
        first = _write_marker_script(tmp_path / "first.py", first_marker)
        second = _benign_script(tmp_path / "second.py")
        config_path = _write_config(
            tmp_path,
            [
                _script_criterion("First", first),
                _script_criterion("Second", second),
            ],
        )
        _commit_as_trusted(git_repo, config_path, first, second)

        second_marker = tmp_path / "pwned.txt"
        _write_marker_script(second, second_marker)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not second_marker.exists()
        assert not first_marker.exists(), (
            "a trusted criterion must not dispatch when a later one halts"
        )

    def test_approval_flag_allows_modified_verifier_with_warning(
        self, git_repo, tmp_path, capsys,
    ):
        script = _benign_script(tmp_path / "verify.py")
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(git_repo, config_path, script)
        marker = tmp_path / "approved.txt"
        _write_marker_script(script, marker)

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
        assert payload["command_trust"]["status"] == "untrusted"
        assert payload["command_trust"]["untrusted_files"] == ["verify.py"]
        assert payload["command_trust"]["approved"] is True

    def test_git_error_during_file_verification_is_not_approvable(
        self, git_repo, tmp_path, monkeypatch, capsys,
    ):
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(git_repo, config_path, script)

        original = _dispatcher._run_git

        def _fail_verifier_lookup(args, cwd):
            if args[0] == "ls-tree" and args[-1] == ":(literal)verify.py":
                return subprocess.CompletedProcess(
                    args=args, returncode=128, stdout=b"",
                    stderr=b"fatal: object store is broken",
                )
            return original(args, cwd)

        monkeypatch.setattr(_dispatcher, "_run_git", _fail_verifier_lookup)

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
        assert (
            "does not apply when verification is impossible"
            in capsys.readouterr().err
        )

    def test_script_outside_the_work_tree_is_recorded_not_checked(
        self, git_repo, tmp_path, tmp_path_factory, capsys,
    ):
        # An installed-plugin script lives outside the consumer's work
        # tree. A PR to that repository cannot rewrite it and it has no
        # trusted-ref copy, so it is recorded and skipped, not halted on.
        plugin_root = tmp_path_factory.mktemp("installed-plugin")
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(plugin_root / "verify.py", marker)
        config_path = _write_config(
            tmp_path, [_script_criterion("Plugin", script)],
        )
        _commit_as_trusted(git_repo, config_path)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )

        assert rc == 0
        assert marker.exists()
        payload = json.loads(capsys.readouterr().out)
        assert payload["command_trust"]["status"] == "trusted"
        assert payload["command_trust"]["checked_files"] == []
        assert str(script.resolve()) in (
            payload["command_trust"]["skipped_external_files"]
        )

    def test_interpreter_and_flags_are_not_compared(
        self, git_repo, tmp_path, capsys,
    ):
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        config_path = _write_config(
            tmp_path,
            [_script_criterion("Flags", script, "--pull-request", "{pr}")],
        )
        _commit_as_trusted(git_repo, config_path, script)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "77", "--json"],
        )

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        checked = payload["command_trust"]["checked_files"]
        assert checked == ["verify.py"], (
            "only the work-tree script is compared; the interpreter, the "
            "flag, and the substituted PR number are not paths to verify"
        )
        assert "77" not in checked
        assert "--pull-request" not in checked

    def test_repo_local_symlink_escaping_the_work_tree_halts(
        self, git_repo, tmp_path, tmp_path_factory, capsys,
    ):
        # CWE-59: a PR-committed symlink lets the argv name a repo-local
        # path whose content has no trusted-ref copy. Fail closed.
        outside = tmp_path_factory.mktemp("outside")
        marker = tmp_path / "pwned.txt"
        target = _write_marker_script(outside / "target.py", marker)
        link = tmp_path / "verify.py"
        link.symlink_to(target)
        config_path = _write_config(tmp_path, [_script_criterion("Linked", link)])
        _commit_as_trusted(git_repo, config_path, link)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()
        assert str(link) in capsys.readouterr().err

    def test_unparseable_command_line_exits_config_error(
        self, git_repo, tmp_path, capsys,
    ):
        config_path = _write_config(
            tmp_path,
            [
                {
                    "name": "Unbalanced",
                    "verification": "command",
                    "command": 'echo "unterminated',
                    "pass_when": "stdout-json.ok == true",
                },
            ],
        )
        _commit_as_trusted(git_repo, config_path)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert "not a parseable command line" in capsys.readouterr().err


class TestCommandTrustBypassRegressions:
    """Executed bypasses found by adversarial security review of PR #5146.

    Every test here reproduces a path the reviewer actually ran to get
    code execution with ``command_trust: trusted``. Each keeps the
    marker-file negative control, so a regression shows up as the
    payload running, not merely as a changed status string.
    """

    def test_pathspec_magic_filename_cannot_evade_the_tracked_check(
        self, git_repo, tmp_path, capsys,
    ):
        # F-2: git reads pathspec magic from a leading ":" even after
        # "--", so a tracked file named ":(glob)evil.py" never matched
        # its own path, came back absent, and was classified untracked,
        # which SKIPS verification entirely.
        marker = tmp_path / "pwned.txt"
        script = _write_marker_script(tmp_path / ":(glob)evil.py", marker)
        config_path = _write_config(tmp_path, [_script_criterion("Magic", script)])
        _commit_as_trusted(git_repo, config_path)
        _git(git_repo, "add", "--", ":(literal):(glob)evil.py")
        _git(git_repo, "commit", "-q", "-m", "PR adds a magic-named payload")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), (
            "a pathspec-magic filename must not skip verification"
        )
        assert ":(glob)evil.py" in capsys.readouterr().err

    def test_tracked_pathspec_magic_filename_is_verified_not_skipped(
        self, git_repo, tmp_path, capsys,
    ):
        # Positive control for the fix: the same adversarial filename,
        # unmodified since the trusted ref, must be CHECKED (not merely
        # skipped into a passing run) and must dispatch.
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / ":(glob)ok.py", marker)
        config_path = _write_config(tmp_path, [_script_criterion("Magic", script)])
        _git(git_repo, "add", "--", ":(literal)pr-review-config.yaml")
        _git(git_repo, "add", "--", ":(literal):(glob)ok.py")
        _git(git_repo, "commit", "-q", "-m", "trusted")
        _git(git_repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )

        assert rc == 0
        assert marker.exists()
        payload = json.loads(capsys.readouterr().out)
        assert ":(glob)ok.py" in payload["command_trust"]["checked_files"], (
            "the adversarial filename must be verified, not skipped"
        )
        assert payload["command_trust"]["skipped_untracked_files"] == []

    def test_intra_work_tree_symlink_halts(self, git_repo, tmp_path, capsys):
        # F-3: a symlink whose target stays INSIDE the work tree used to
        # pass through as a normal path, and the resolved target was
        # compared instead of the path the config named. The reviewer
        # pointed a config-named verifier at a different, untouched,
        # trusted script and got command_trust: trusted.
        marker = tmp_path / "pwned.txt"
        real = _write_marker_script(tmp_path / "payload.py", marker)
        link = tmp_path / "verify.py"
        link.symlink_to(real)
        config_path = _write_config(tmp_path, [_script_criterion("Linked", link)])
        _commit_as_trusted(git_repo, config_path, real, link)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), (
            "an in-tree symlink must not execute unverified"
        )
        assert "verify.py" in capsys.readouterr().err

    def test_symlinked_parent_directory_halts(self, git_repo, tmp_path):
        # Same hazard one level up: the named file is ordinary but a
        # parent component is a link, so the resolved path differs from
        # the path the config named.
        marker = tmp_path / "pwned.txt"
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        _write_marker_script(real_dir / "verify.py", marker)
        (tmp_path / "linked").symlink_to(real_dir, target_is_directory=True)
        config_path = _write_config(
            tmp_path, [_script_criterion("Dir", tmp_path / "linked" / "verify.py")],
        )
        _commit_as_trusted(
            git_repo, config_path, real_dir / "verify.py", tmp_path / "linked",
        )

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists()

    def test_nested_repository_path_halts_instead_of_skipping(
        self, git_repo, tmp_path, capsys,
    ):
        # F-4: git ls-files does not descend into a gitlink, so every
        # file inside a submodule reads as untracked in the superproject
        # and was skipped rather than verified.
        marker = tmp_path / "pwned.txt"
        nested = tmp_path / "vendored"
        nested.mkdir()
        script = _write_marker_script(nested / "verify.py", marker)
        config_path = _write_config(tmp_path, [_script_criterion("Nested", script)])
        _commit_as_trusted(git_repo, config_path)
        _git(nested, "init", "-q")
        _git(nested, "add", "verify.py")
        _git(nested, "commit", "-q", "-m", "payload in a nested repo")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), (
            "a nested-repository path must not skip verification"
        )
        assert "vendored/verify.py" in capsys.readouterr().err

    def test_cwd_outside_the_work_tree_fails_closed(
        self, git_repo, tmp_path, tmp_path_factory, monkeypatch, capsys,
    ):
        # F-5: relative argv resolves against the cwd, so running the
        # gate from a different tree silently routed work-tree scripts
        # into the external carve-out and skipped them.
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(git_repo, config_path, script)
        monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 3
        assert not marker.exists()
        assert "outside the git work tree" in capsys.readouterr().err

    def test_transitive_import_of_a_work_tree_module_is_verified(
        self, git_repo, tmp_path, capsys,
    ):
        # F-1: every shipped verifier imports github_core.api from the
        # work tree's plugin lib directory at module load, so a PR could
        # rewrite that module and get execution with every named script
        # byte-identical to the trusted ref.
        lib = tmp_path / "lib" / "helperpkg"
        lib.mkdir(parents=True)
        (lib / "__init__.py").write_text("", encoding="utf-8")
        helper = lib / "api.py"
        helper.write_text("VALUE = 'clean'\n", encoding="utf-8")
        script = tmp_path / "verify.py"
        script.write_text(
            "import json, sys, pathlib\n"
            f"sys.path.insert(0, {str(tmp_path / 'lib')!r})\n"
            "from helperpkg.api import VALUE\n"
            "print(json.dumps({'ok': True}))\n",
            encoding="utf-8",
        )
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(
            git_repo, config_path, script, helper, lib / "__init__.py",
        )

        marker = tmp_path / "pwned.txt"
        helper.write_text(
            f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n"
            "VALUE = 'evil'\n",
            encoding="utf-8",
        )

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), (
            "a rewritten imported module must never be loaded"
        )
        assert "lib/helperpkg/api.py" in capsys.readouterr().err

    def test_relative_import_inside_a_package_is_verified(
        self, git_repo, tmp_path, capsys,
    ):
        # The shipped github_core.api reaches its siblings with
        # "from .log_safety import ...". An absolute-only resolver walks
        # the closure, reports success, and silently leaves most of the
        # library unverified.
        pkg = tmp_path / "lib" / "helperpkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "api.py").write_text(
            "from .sibling import VALUE\n", encoding="utf-8",
        )
        sibling = pkg / "sibling.py"
        sibling.write_text("VALUE = 'clean'\n", encoding="utf-8")
        script = tmp_path / "verify.py"
        script.write_text(
            "import json, sys\n"
            f"sys.path.insert(0, {str(tmp_path / 'lib')!r})\n"
            "from helperpkg.api import VALUE\n"
            "print(json.dumps({'ok': True}))\n",
            encoding="utf-8",
        )
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(
            git_repo, config_path, script,
            pkg / "__init__.py", pkg / "api.py", sibling,
        )

        marker = tmp_path / "pwned.txt"
        sibling.write_text(
            f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n"
            "VALUE = 'evil'\n",
            encoding="utf-8",
        )

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 2
        assert not marker.exists(), (
            "a relative-imported module must never be loaded unverified"
        )
        assert "lib/helperpkg/sibling.py" in capsys.readouterr().err

    def test_relative_import_cannot_climb_out_of_the_work_tree(self, tmp_path):
        # A crafted "from ..... import x" must not resolve above the
        # work tree, where there is no trusted-ref copy to compare.
        script = tmp_path / "deep" / "pkg" / "mod.py"
        script.parent.mkdir(parents=True)
        script.write_text("", encoding="utf-8")

        assert _dispatcher._relative_import_root(script, 9, tmp_path) == []
        assert _dispatcher._relative_import_root(script, 1, tmp_path) == [
            script.parent,
        ]

    def test_unrelated_sibling_change_does_not_halt(
        self, git_repo, tmp_path, capsys,
    ):
        # The import closure must stay narrower than a directory rule:
        # editing a sibling script nothing imports must not halt, or
        # operators learn to pass --approve-untrusted-config by reflex.
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        sibling = _benign_script(tmp_path / "unrelated.py")
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(git_repo, config_path, script, sibling)
        sibling.write_text("# edited by this PR\n", encoding="utf-8")

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1", "--json"],
        )

        assert rc == 0
        assert marker.exists()
        payload = json.loads(capsys.readouterr().out)
        assert "unrelated.py" not in payload["command_trust"]["checked_files"]


class TestClassifyArgvToken:
    """Unit coverage for argv classification (100% branch requirement for
    security-critical code).
    """

    def test_flags_and_empty_tokens_are_skipped(self, tmp_path):
        for token in ("--pull-request", "-v", ""):
            assert _dispatcher._classify_argv_token(token, tmp_path) == (
                _dispatcher._ARGV_SKIP, "",
            )

    def test_bare_interpreter_name_is_not_a_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert _dispatcher._classify_argv_token("python3", tmp_path) == (
            _dispatcher._ARGV_SKIP, "",
        )

    def test_directory_inside_work_tree_is_skipped(self, tmp_path):
        (tmp_path / "sub").mkdir()
        assert _dispatcher._classify_argv_token(
            str(tmp_path / "sub"), tmp_path,
        ) == (_dispatcher._ARGV_SKIP, "")

    def test_relative_token_resolves_against_cwd(self, tmp_path, monkeypatch):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "verify.py").write_text("x", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        assert _dispatcher._classify_argv_token("pkg/verify.py", tmp_path) == (
            _dispatcher._ARGV_VERIFY, "pkg/verify.py",
        )

    def test_lexical_parent_escape_is_not_treated_as_inside(
        self, tmp_path, tmp_path_factory,
    ):
        # Path.relative_to is lexical, so "<root>/../x" would otherwise
        # pass containment; normpath collapses it first.
        outside = tmp_path_factory.mktemp("outside")
        target = outside / "verify.py"
        target.write_text("x", encoding="utf-8")

        kind, value = _dispatcher._classify_argv_token(
            str(tmp_path / ".." / outside.name / "verify.py"), tmp_path,
        )

        assert kind == _dispatcher._ARGV_EXTERNAL
        assert value == str(target.resolve())

    def test_escaping_symlink_missed_by_the_precheck_still_fails_closed(
        self, tmp_path, tmp_path_factory, monkeypatch,
    ):
        # Defense in depth: if the symlink pre-check misses a link (for
        # example one created between the check and the resolve), the
        # containment comparison must still refuse it.
        outside = tmp_path_factory.mktemp("outside")
        target = outside / "real.py"
        target.write_text("x", encoding="utf-8")
        link = tmp_path / "verify.py"
        link.symlink_to(target)
        monkeypatch.setattr(
            _dispatcher, "_first_symlinked_component", lambda *_a: None,
        )

        assert _dispatcher._classify_argv_token(str(link), tmp_path) == (
            _dispatcher._ARGV_ESCAPES, str(link),
        )

    def test_nonexistent_path_outside_work_tree_is_skipped(self, tmp_path):
        assert _dispatcher._classify_argv_token(
            "/nonexistent/x.py", tmp_path,
        ) == (_dispatcher._ARGV_SKIP, "")

    def test_unresolvable_repo_local_path_fails_closed(
        self, tmp_path, monkeypatch,
    ):
        def _boom(self, strict=False):
            raise OSError("symlink loop")

        monkeypatch.setattr(Path, "resolve", _boom)
        token = str(tmp_path / "loop.py")

        assert _dispatcher._classify_argv_token(token, tmp_path) == (
            _dispatcher._ARGV_ESCAPES, token,
        )

    def test_unresolvable_external_path_is_skipped(self, tmp_path, monkeypatch):
        def _boom(self, strict=False):
            raise OSError("symlink loop")

        monkeypatch.setattr(Path, "resolve", _boom)

        assert _dispatcher._classify_argv_token(
            "/elsewhere/x.py", tmp_path,
        ) == (_dispatcher._ARGV_SKIP, "")


class TestImportClosureBranches:
    """Unit coverage for the closure helpers, including the defensive
    branches the end-to-end tests cannot reach (100% requirement for
    security-critical code).
    """

    def test_unparseable_source_yields_no_imports(self):
        assert _dispatcher._imported_module_names(b"def (:\n") == []

    def test_source_with_null_byte_yields_no_imports(self):
        # ast.parse raises ValueError, not SyntaxError, on embedded nulls.
        assert _dispatcher._imported_module_names(b"x = '\x00'\n") == []

    def test_absolute_and_relative_imports_are_reported_with_levels(self):
        found = _dispatcher._imported_module_names(
            b"import os\nfrom pkg import a\nfrom . import b\nfrom ..up import c\n",
        )

        assert (0, "os") in found
        assert (0, "pkg") in found and (0, "pkg.a") in found
        assert (1, "b") in found
        assert (2, "up") in found and (2, "up.c") in found

    def test_import_roots_stop_at_the_work_tree(self, tmp_path):
        (tmp_path / "lib").mkdir()
        script = tmp_path / "skills" / "pr" / "verify.py"
        script.parent.mkdir(parents=True)
        script.write_text("", encoding="utf-8")

        roots = _dispatcher._import_roots(script, tmp_path)

        assert roots[0] == script.parent
        assert tmp_path / "lib" in roots
        assert roots[-1] == tmp_path
        assert all(_dispatcher._is_within(r, tmp_path) for r in roots)

    def test_package_init_resolves_when_module_file_is_absent(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        assert _dispatcher._resolve_module_file("pkg", [tmp_path], tmp_path) == (
            "pkg/__init__.py"
        )

    def test_empty_dotted_name_resolves_to_nothing(self, tmp_path):
        assert _dispatcher._resolve_module_file("", [tmp_path], tmp_path) is None

    def test_stdlib_name_resolves_to_nothing(self, tmp_path):
        assert _dispatcher._resolve_module_file("json", [tmp_path], tmp_path) is None

    def test_symlinked_module_is_not_resolved_as_a_closure_member(
        self, tmp_path, tmp_path_factory,
    ):
        # A module reached through a symlink must not be silently
        # verified at its target; _classify_argv_token fails those
        # closed and the closure simply declines to follow one.
        outside = tmp_path_factory.mktemp("outside")
        target = outside / "real.py"
        target.write_text("", encoding="utf-8")
        (tmp_path / "mod.py").symlink_to(target)

        assert _dispatcher._resolve_module_file("mod", [tmp_path], tmp_path) is None

    def test_unreadable_script_is_skipped_by_the_closure(self, tmp_path, monkeypatch):
        (tmp_path / "verify.py").write_text("import os\n", encoding="utf-8")

        def _boom(self: Path) -> bytes:
            raise OSError("io broke")

        monkeypatch.setattr(Path, "read_bytes", _boom)

        assert _dispatcher._expand_import_closure(["verify.py"], tmp_path) == [
            "verify.py",
        ]

    def test_non_python_named_file_is_not_walked(self, tmp_path):
        assert _dispatcher._expand_import_closure(["data.json"], tmp_path) == [
            "data.json",
        ]


class TestFirstSymlinkedComponentBranches:
    """Unit coverage for the shared symlink-component helper."""

    def test_unstattable_component_fails_closed(self, tmp_path, monkeypatch):
        def _boom(self: Path) -> bool:
            raise OSError("stat broke")

        monkeypatch.setattr(Path, "is_symlink", _boom)

        # The first component at or below the root is the root itself,
        # and an unstattable component is reported rather than skipped.
        assert _dispatcher._first_symlinked_component(
            tmp_path / "x.py", tmp_path,
        ) == tmp_path

    def test_component_above_the_root_is_ignored(self, tmp_path, tmp_path_factory):
        # A symlink above the work tree is the operator's environment,
        # not PR content, and must not false-halt the gate.
        outside = tmp_path_factory.mktemp("outside")
        real = outside / "real"
        real.mkdir()
        link = outside / "linked"
        link.symlink_to(real, target_is_directory=True)

        assert _dispatcher._first_symlinked_component(link / "x.py", tmp_path) is None


class TestNestedRepositoryProbeBranches:
    """Unit coverage for the submodule / nested-repository probe."""

    def test_missing_parent_directory_is_not_nested(self, tmp_path):
        assert _dispatcher._is_in_nested_repository("gone/x.py", tmp_path) is False

    def test_git_failure_fails_closed(self, tmp_path, monkeypatch):
        (tmp_path / "sub").mkdir()
        monkeypatch.setattr(
            _dispatcher,
            "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args=args, returncode=128, stdout=b"", stderr=b"boom",
            ),
        )

        assert _dispatcher._is_in_nested_repository("sub/x.py", tmp_path) is True

    def test_same_toplevel_is_not_nested(self, tmp_path, monkeypatch):
        (tmp_path / "sub").mkdir()
        monkeypatch.setattr(
            _dispatcher,
            "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout=str(tmp_path).encode() + b"\n", stderr=b"",
            ),
        )

        assert _dispatcher._is_in_nested_repository("sub/x.py", tmp_path) is False

    def test_unresolvable_toplevel_fails_closed(self, tmp_path, monkeypatch):
        (tmp_path / "sub").mkdir()
        monkeypatch.setattr(
            _dispatcher,
            "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args=args, returncode=0, stdout=b"/elsewhere\n", stderr=b"",
            ),
        )

        def _boom(self: Path, strict: bool = False) -> Path:
            raise OSError("resolve broke")

        monkeypatch.setattr(Path, "resolve", _boom)

        assert _dispatcher._is_in_nested_repository("sub/x.py", tmp_path) is True


class TestVerifyWorktreeFileTrustBranches:
    """Fault injection for the per-file comparison helper."""

    def test_cat_file_failure_reports_error(self, tmp_path, monkeypatch):
        def _fake(args, cwd):
            if args[0] == "ls-tree":
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout=b"blob deadbeef\tv.py\n", stderr=b"",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=128, stdout=b"", stderr=b"boom",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _fake)

        is_trusted, error = _dispatcher._verify_worktree_file_trust(
            "v.py", tmp_path, "origin/main",
        )

        assert is_trusted is False
        assert "cat-file" in error

    def test_unreadable_worktree_file_reports_error(self, tmp_path, monkeypatch):
        def _fake(args, cwd):
            if args[0] == "ls-tree":
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout=b"blob deadbeef\tv.py\n", stderr=b"",
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=b"trusted", stderr=b"",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _fake)

        is_trusted, error = _dispatcher._verify_worktree_file_trust(
            "v.py", tmp_path, "origin/main",
        )

        assert is_trusted is False
        assert "cannot read work-tree file" in error


class TestVerifyCommandTrustErrorBranches:
    """Unit coverage for the aggregate verifier's failure paths."""

    def test_not_a_git_work_tree_reports_git_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(
            _dispatcher,
            "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args=args, returncode=128, stdout=b"",
                stderr=b"not a git repository",
            ),
        )

        result = _dispatcher._verify_command_trust([], 1, "origin/main")

        assert result.status == _dispatcher.COMMAND_TRUST_GIT_ERROR
        assert "not inside a git work tree" in result.detail

    def test_git_timeout_reports_git_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)

        def _boom(args, cwd):
            raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=30)

        monkeypatch.setattr(_dispatcher, "_run_git", _boom)

        result = _dispatcher._verify_command_trust([], 1, "origin/main")

        assert result.status == _dispatcher.COMMAND_TRUST_GIT_ERROR
        assert "command trust verification failed" in result.detail

    def test_schema_violation_raises_config_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_dispatcher, "_PROJECT_ROOT", tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            _dispatcher,
            "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout=str(tmp_path).encode() + b"\n", stderr=b"",
            ),
        )

        with pytest.raises(_dispatcher.ConfigError, match="verification kind"):
            _dispatcher._verify_command_trust(
                [{"name": "X", "verification": "manual"}], 1, "origin/main",
            )

    def test_tracked_probe_failure_halts_as_git_error(
        self, git_repo, tmp_path, monkeypatch, capsys,
    ):
        marker = tmp_path / "ran.txt"
        script = _write_marker_script(tmp_path / "verify.py", marker)
        config_path = _write_config(tmp_path, [_script_criterion("Ok", script)])
        _commit_as_trusted(git_repo, config_path, script)

        original = _dispatcher._run_git

        def _fail_ls_files(args, cwd):
            if args[0] == "ls-files":
                return subprocess.CompletedProcess(
                    args=args, returncode=128, stdout=b"",
                    stderr=b"fatal: index is corrupt",
                )
            return original(args, cwd)

        monkeypatch.setattr(_dispatcher, "_run_git", _fail_ls_files)

        rc = _dispatcher.main(
            ["--config", str(config_path), "--pull-request", "1"],
        )

        assert rc == 3
        assert not marker.exists(), (
            "an unusable tracked-file probe must fail closed, not skip"
        )
        assert "cannot be verified" in capsys.readouterr().err


class TestTrackedSubset:
    """Unit coverage for the batched tracked-file probe."""

    def test_empty_input_runs_no_git(self, tmp_path, monkeypatch):
        def _unexpected(args, cwd):
            raise AssertionError(f"git must not run for an empty set: {args}")

        monkeypatch.setattr(_dispatcher, "_run_git", _unexpected)

        assert _dispatcher._tracked_subset([], tmp_path) == (set(), "")

    def test_returns_only_the_tracked_paths(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            _dispatcher,
            "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args=args, returncode=0, stdout=b"a.py\x00", stderr=b"",
            ),
        )

        tracked, error = _dispatcher._tracked_subset(
            ["a.py", "b.json"], tmp_path,
        )

        assert tracked == {"a.py"}
        assert error == ""

    def test_probe_failure_reports_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            _dispatcher,
            "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args=args, returncode=128, stdout=b"", stderr=b"index corrupt",
            ),
        )

        tracked, error = _dispatcher._tracked_subset(["a.py"], tmp_path)

        assert tracked == set()
        assert "git ls-files failed" in error


def _own_plugin_root(monkeypatch, root: Path) -> None:
    """Declare `root` the plugin that ships the dispatcher under test.

    Install trust requires the declared root to CONTAIN this dispatcher, so a
    host variable naming a foreign co-installed plugin cannot trust that
    plugin's config (CWE-829, reproduced in Copilot review on PR #5329).

    These unit tests import the canonical script from the repository, so its
    real ``__file__`` is nowhere near their ``tmp_path`` roots. Rebinding the
    module constant states the arrangement each case assumes: "this
    dispatcher is the one shipped inside that plugin". It does NOT weaken the
    condition, because the condition is exercised for real elsewhere:
    ``_install_plugin`` in tests/test_run_completion_gate_install.py copies
    the script into the plugin root, so every CLI case satisfies it
    genuinely, and a dedicated case there drives a foreign root end to end.
    """
    monkeypatch.setattr(
        _dispatcher,
        "_DISPATCHER_PATH",
        root.resolve() / "skills" / "github" / "scripts" / "pr"
        / "run_completion_gate.py",
    )


def _git_work_tree(path: Path) -> Path:
    """Create `path` as a real git work tree and return it.

    _install_trusted_root fails closed when `git rev-parse --show-toplevel`
    reports nothing, so a bare `.git` directory is not enough: git answers
    "fatal: not a git repository" for one. Verified before relying on it.
    """
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return path


class TestInstallTrustedRoot:
    """Unit coverage for _install_trusted_root (issue #5112, Option 1).

    The subprocess-level behavior lives in
    tests/test_run_completion_gate_install.py, which exercises the real
    installed-plugin layout. These cover the helper's individual
    conditions, including the ones that arrangement cannot isolate.

    _PROJECT_ROOT is resolved at import time to this repository, so a
    tmp_path root is outside it, which is exactly condition 3's
    "not at or under the project root".
    """

    def _config_in(self, root, name="pr-review-config.yaml"):
        root.mkdir(parents=True, exist_ok=True)
        config = root / name
        config.write_text("completion_criteria: []\n", encoding="utf-8")
        return config

    def test_unset_environment_install_trusts_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        config = self._config_in(tmp_path / "plugin")

        assert _dispatcher._install_trusted_root(str(config)) is None

    @pytest.mark.parametrize(
        "env_var", ["CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"],
    )
    def test_either_host_variable_install_trusts(
        self, tmp_path, monkeypatch, env_var,
    ):
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        root = tmp_path / "plugin"
        config = self._config_in(root / "commands")
        monkeypatch.setenv(env_var, str(root))
        _own_plugin_root(monkeypatch, root)

        assert _dispatcher._install_trusted_root(str(config)).root == root.resolve()

    def test_empty_and_whitespace_values_are_ignored(self, tmp_path, monkeypatch):
        """An exported-but-empty variable is not a declaration.

        Hosts and CI commonly export a variable with no value; treating
        that as a plugin root would resolve Path("") to the cwd.
        """
        root = tmp_path / "plugin"
        config = self._config_in(root / "commands")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", "   ")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "")

        assert _dispatcher._install_trusted_root(str(config)) is None

    def test_surrounding_whitespace_is_stripped_from_a_real_root(
        self, tmp_path, monkeypatch,
    ):
        """Discriminating twin for the case above.

        The case above cannot observe the strip(): whitespace-only survives
        it as a relative path that is not a directory, so the value is
        dropped either way and the assertion holds against an unstripped
        implementation. Mutation confirmed it, removing .strip() left the
        whole file green.

        A real root with stray spaces is the input the two implementations
        disagree on. Unstripped, Path("  /abs/root") is RELATIVE (its first
        component is the spaces), so it resolves under the cwd, is not a
        directory, and nothing is trusted.
        """
        root = tmp_path / "plugin"
        config = self._config_in(root / "commands")
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", f"  {root}  ")
        _own_plugin_root(monkeypatch, root)

        assert _dispatcher._install_trusted_root(str(config)).root == root.resolve()

    def test_a_root_that_is_not_a_directory_is_ignored(self, tmp_path, monkeypatch):
        """A declared root must be a directory, not merely a path.

        The config is placed INSIDE the declared root so containment
        (condition 4) cannot be what refuses this. Without the is_dir()
        check a plain FILE would install-trust a config named beneath it:
        Path.resolve() does not require existence, so the containment test
        happily succeeds against a path that cannot hold a file at all.
        An earlier version of this case put the config elsewhere, so
        containment refused it and the is_dir() check went unobserved;
        mutation confirmed removing is_dir() left the file green.
        """
        not_a_dir = tmp_path / "plugin-root-is-a-file"
        not_a_dir.write_text("", encoding="utf-8")
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(not_a_dir))

        assert _dispatcher._install_trusted_root(
            str(not_a_dir / "pr-review-config.yaml"),
        ) is None

    def test_a_root_inside_the_project_root_is_refused(self, monkeypatch):
        """Condition 3: the PR-controlled in-repo fallback never widens.

        Uses the live project root, so this asserts the real containment
        the gate applies rather than a stand-in.
        """
        in_repo_root = _dispatcher._PROJECT_ROOT / ".claude"
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(in_repo_root))
        config = in_repo_root / "commands" / "pr-review-config.yaml"

        assert _dispatcher._install_trusted_root(str(config)) is None

    def test_an_ancestor_of_the_project_root_is_refused(self, monkeypatch):
        """Condition 3 is disjointness, not one-way containment.

        The bypass Copilot found on PR #5329. Testing only "the root is not
        below the project" passes a root that is an ANCESTOR of the project,
        while every PR-controlled file in the repo is inside that root, so
        condition 4 passes too and a config the checked-out PR wrote becomes
        install-trusted, skipping byte-identity verification (CWE-829).

        Reproduced before the fix with the live project root: declared root
        /home/user install-trusted
        /home/user/ai-agents/.claude/commands/pr-review-config.yaml.
        """
        project_root = _dispatcher._PROJECT_ROOT.resolve()
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(project_root.parent))
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        pr_controlled = project_root / ".claude" / "commands" / "pr-review-config.yaml"

        assert _dispatcher._install_trusted_root(str(pr_controlled)) is None

    def test_the_project_root_itself_is_refused(self, monkeypatch):
        """_is_within is true for root == root, so the repo itself is out."""
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_dispatcher._PROJECT_ROOT))
        config = _dispatcher._PROJECT_ROOT / "pyproject.toml"

        assert _dispatcher._install_trusted_root(str(config)) is None

    def test_a_config_outside_the_declared_root_is_refused(
        self, tmp_path, monkeypatch,
    ):
        """Condition 4: declaring a root does not bless every path."""
        root = tmp_path / "plugin"
        root.mkdir(parents=True)
        elsewhere = self._config_in(tmp_path / "elsewhere")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))

        assert _dispatcher._install_trusted_root(str(elsewhere)) is None

    def test_a_symlink_escaping_the_root_is_refused(self, tmp_path, monkeypatch):
        """Condition 4 resolves before containment (CWE-59)."""
        root = tmp_path / "plugin"
        (root / "commands").mkdir(parents=True)
        target = self._config_in(tmp_path / "outside")
        link = root / "commands" / "linked.yaml"
        link.symlink_to(target)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)

        assert _dispatcher._install_trusted_root(str(link)) is None

    def test_a_symlink_within_the_root_is_still_trusted(self, tmp_path, monkeypatch):
        """The refusal is about escaping, not about links as such.

        A link whose target is also install-controlled stays inside the
        operator's own directory, so nothing PR-controlled is reached.
        """
        root = tmp_path / "plugin"
        target = self._config_in(root / "real")
        (root / "commands").mkdir(parents=True)
        link = root / "commands" / "linked.yaml"
        link.symlink_to(target)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)

        assert _dispatcher._install_trusted_root(str(link)).root == root.resolve()

    def test_copilot_root_is_consulted_before_claude_root(
        self, tmp_path, monkeypatch,
    ):
        """Order matches resolve_pr_review_config's own precedence.

        That command reads
        ${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}, so when
        both are set and only one contains the config, the Copilot root
        is the one that decides.
        """
        copilot_root = tmp_path / "copilot"
        claude_root = tmp_path / "claude"
        claude_root.mkdir(parents=True)
        config = self._config_in(copilot_root / "commands")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(copilot_root))
        _own_plugin_root(monkeypatch, copilot_root)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude_root))

        assert _dispatcher._install_trusted_root(str(config)).root == copilot_root.resolve()

    def test_a_relative_config_resolves_against_the_cwd(
        self, tmp_path, monkeypatch,
    ):
        """--config may be relative; the gate resolves it against the cwd.

        The cwd is a real work tree, because _install_trusted_root fails
        closed when git cannot report a toplevel. A relative arg is only
        install-trustable when it traverses OUT of that work tree and into
        the declared root, which is what the host does when it passes the
        bundled config by a path relative to the consumer repository.
        """
        consumer = _git_work_tree(tmp_path / "consumer")
        root = tmp_path / "plugin"
        self._config_in(root / "commands")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.chdir(consumer)

        approved = _dispatcher._install_trusted_root(
            "../plugin/commands/pr-review-config.yaml",
        )

        assert approved.root == root.resolve()

    def test_a_relative_config_inside_the_work_tree_is_refused(
        self, tmp_path, monkeypatch,
    ):
        """Discriminating control for the case above.

        Same cwd, same declared root, same relative syntax; only the
        traversal differs. This one stays inside the consumer work tree, so
        it is PR-controlled and must keep the byte-identity check. Without
        it the case above would pass for any relative path at all.
        """
        consumer = _git_work_tree(tmp_path / "consumer")
        root = tmp_path / "plugin"
        self._config_in(root / "commands")
        self._config_in(consumer / "commands")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.chdir(consumer)

        assert _dispatcher._install_trusted_root(
            "commands/pr-review-config.yaml",
        ) is None


class TestEnforceConfigTrustInstallTrusted:
    """_enforce_config_trust short-circuits only on an install-trusted root."""

    def test_install_root_skips_config_verification_but_not_the_ref_check(
        self, tmp_path, monkeypatch,
    ):
        """Byte verification is skipped; ref validation is NOT.

        This case previously asserted that _run_git must never be called for
        an install-trusted config, and stubbed it to raise. That contract was
        wrong and the assertion enforced the wrong thing: the trust ANCHOR
        still has to resolve to a remote-tracking ref, which takes a git
        call, and skipping it let `--trusted-ref HEAD` make command trust
        compare PR-modified verifiers against the PR's own commit (Copilot
        review, PR #5329). What is skipped is _verify_config_trust's
        byte-identity comparison, and only that.
        """
        calls: list[list[str]] = []

        def _fake_git(args, cwd):
            calls.append(args)
            return subprocess.CompletedProcess(
                args, 0, b"refs/remotes/origin/main\n", b"",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _fake_git)

        trust, halt = _dispatcher._enforce_config_trust(
            tmp_path / "pr-review-config.yaml",
            "origin/main",
            False,
            b"completion_criteria: []\n",
            _dispatcher.InstallTrust(
                tmp_path, tmp_path / "pr-review-config.yaml", tmp_path,
            ),
        )

        assert halt is None
        assert trust.status == _dispatcher.TRUST_INSTALL_TRUSTED
        assert "install-trusted" in trust.detail
        # Exactly one git call, and it is the anchor check. `cat-file`
        # would mean byte verification ran, which install trust exists to
        # skip; asserting the call list catches either drift.
        assert calls == [["rev-parse", "--symbolic-full-name", "origin/main"]], calls

    def test_install_root_refuses_a_local_ref(self, tmp_path, monkeypatch):
        """HEAD passes the regex, so only the remote-tracking check stops it.

        The reproduction behind this: with the ref unvalidated, command
        trust compared a PR-modified verifier against the PR's own HEAD,
        declared it trusted, and executed it. Exit 3, matching
        TRUST_GIT_ERROR, so --approve-untrusted-config cannot override it.
        """
        def _fake_git(args, cwd):
            return subprocess.CompletedProcess(args, 0, b"refs/heads/main\n", b"")

        monkeypatch.setattr(_dispatcher, "_run_git", _fake_git)

        trust, halt = _dispatcher._enforce_config_trust(
            tmp_path / "pr-review-config.yaml",
            "HEAD",
            True,  # approval must NOT rescue this
            b"completion_criteria: []\n",
            _dispatcher.InstallTrust(
                tmp_path, tmp_path / "pr-review-config.yaml", tmp_path,
            ),
        )

        assert halt == 3, halt
        assert trust.status == _dispatcher.TRUST_GIT_ERROR
        assert "remote-tracking" in trust.detail

    def test_install_root_refuses_an_option_shaped_ref(self, tmp_path, monkeypatch):
        """The regex guard now runs ahead of the short-circuit.

        Discriminating twin for the case above: this one is stopped by the
        regex and never reaches git, so _run_git raising proves the order.
        """
        def _explode(*args, **kwargs):
            raise AssertionError("a malformed ref must not reach git")

        monkeypatch.setattr(_dispatcher, "_run_git", _explode)

        trust, halt = _dispatcher._enforce_config_trust(
            tmp_path / "pr-review-config.yaml",
            "--upload-pack=touch /tmp/pwned",
            False,
            b"completion_criteria: []\n",
            _dispatcher.InstallTrust(
                tmp_path, tmp_path / "pr-review-config.yaml", tmp_path,
            ),
        )

        assert halt == 2, halt
        assert trust.status == _dispatcher.TRUST_MALFORMED_REF

    def test_without_install_root_verification_still_runs(self, tmp_path, monkeypatch):
        """Negative control: the short-circuit is gated on the argument.

        Without it the malformed-ref check is reached and returns exit 2,
        proving the branch above is not simply always taken.
        """
        trust, halt = _dispatcher._enforce_config_trust(
            tmp_path / "pr-review-config.yaml",
            "--not-a-ref",
            False,
            b"completion_criteria: []\n",
            None,
        )

        assert halt == 2
        assert trust.status == _dispatcher.TRUST_MALFORMED_REF


class TestWorkTreeProbeFailure:
    """A failed work-tree probe is exit 3, and a git hang is caught.

    Copilot review, PR #5329. Two distinct defects behind one finding:

    1. ``subprocess.TimeoutExpired`` is NOT an ``OSError`` (its MRO is
       TimeoutExpired -> SubprocessError -> Exception), and ``_run_git``
       passes ``timeout=_GIT_TIMEOUT_SECONDS``, so an ``except OSError``
       alone let a 30-second git hang escape as an unhandled traceback.
       The module's two other guarded ``_run_git`` callers already catch
       the pair.
    2. A probe failure was collapsed into "no install trust" and fell
       through to containment, exiting 2 and naming the config path as
       the problem when the path was fine.

    Driven through ``main()`` so the assertion is on the integer the
    process exits with, not on a helper's return value (testing.md MUST 8).
    """

    def _plugin_root(self, tmp_path, monkeypatch):
        root = tmp_path / "plugin"
        (root / "commands").mkdir(parents=True)
        config = root / "commands" / "pr-review-config.yaml"
        config.write_text(
            "completion_criteria:\n"
            "  - name: c\n"
            "    verification: command\n"
            '    command: "true"\n'
            '    pass_when: "exit_code == 0"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        return config

    def test_a_git_timeout_exits_3_instead_of_raising(
        self, tmp_path, monkeypatch, capsys,
    ):
        config = self._plugin_root(tmp_path, monkeypatch)

        def _hang(args, cwd):
            raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=30)

        monkeypatch.setattr(_dispatcher, "_run_git", _hang)

        code = _dispatcher.main(
            ["--pull-request", "1", "--config", str(config)],
        )

        assert code == 3, code
        err = capsys.readouterr().err
        assert "could not run git" in err, err
        assert "Refusing to load config from unsafe path" not in err, err

    def test_a_symlink_loop_in_the_work_tree_path_exits_3(
        self, tmp_path, monkeypatch, capsys,
    ):
        """RuntimeError from resolve() must not escape as a traceback.

        CPython 3.10, 3.11 and 3.12 raise ``RuntimeError("Symlink loop
        from ...")`` out of ``Path.resolve()``; 3.14 returns the unresolved
        path instead. ``RuntimeError`` is not an ``OSError``, so the earlier
        ``except OSError`` guard let it escape on exactly the interpreters
        the hook-portability floor targets, and a local run on 3.14 could
        never reveal that (Copilot review, PR #5329).

        The exception is injected rather than produced with real symlinks,
        because on the interpreter this suite runs under no real loop raises
        it. That is the point: the defect is invisible to a same-version
        reproduction, so the test has to model the other versions' contract.
        """
        config = self._plugin_root(tmp_path, monkeypatch)

        real_resolve = Path.resolve

        # Exact match, not a substring: tmp_path contains "loop" because
        # this test is NAMED for one, and a substring trigger fired on the
        # config path instead of the work tree.
        looped = "/looped-work-tree"

        def _looping(self, *a, **kw):
            if str(self) == looped:
                raise RuntimeError(f"Symlink loop from {self!r}")
            return real_resolve(self, *a, **kw)

        monkeypatch.setattr(Path, "resolve", _looping)
        monkeypatch.setattr(
            _dispatcher, "_run_git",
            lambda args, cwd: subprocess.CompletedProcess(
                args, 0, looped.encode() + b"\n", b"",
            ),
        )

        code = _dispatcher.main(
            ["--pull-request", "1", "--config", str(config)],
        )

        assert code == 3, code
        assert "does not resolve" in capsys.readouterr().err

    def test_a_missing_git_binary_exits_3(self, tmp_path, monkeypatch, capsys):
        config = self._plugin_root(tmp_path, monkeypatch)

        def _absent(args, cwd):
            raise FileNotFoundError(2, "No such file or directory: 'git'")

        monkeypatch.setattr(_dispatcher, "_run_git", _absent)

        code = _dispatcher.main(
            ["--pull-request", "1", "--config", str(config)],
        )

        assert code == 3, code
        assert "could not run git" in capsys.readouterr().err

    def test_an_anchor_probe_timeout_exits_3_not_1(self, tmp_path, monkeypatch, capsys):
        """A git failure DURING anchor validation is exit 3, not a traceback.

        The work-tree probe is already guarded, so this covers the SECOND git
        call on the install-trusted path, inside
        ``_require_remote_tracking_ref``. ``_verify_config_trust`` happens to
        call that helper inside its own try, but the install-trusted caller
        invokes it directly, so a timeout or a missing binary escaped as a
        traceback and exit 1 instead of the documented non-overridable exit 3
        (Copilot review, PR #5329). The catch now lives in the shared helper,
        which is what keeps the two callers from disagreeing about it.
        """
        config = self._plugin_root(tmp_path, monkeypatch)
        calls: list[list[str]] = []

        def _hang_on_anchor(args, cwd):
            calls.append(args)
            if args[:2] == ["rev-parse", "--symbolic-full-name"]:
                raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=30)
            # The work-tree probe succeeds, so install trust is granted and
            # execution reaches the anchor check. Without this the case would
            # exit 3 from the earlier probe and prove nothing about the second.
            # It must report a tree DISJOINT from tmp_path/"plugin"; returning
            # tmp_path itself makes the declared root a subdirectory of the
            # work tree, which condition 3 refuses, and the case then dies at
            # containment having never reached the anchor call.
            return subprocess.CompletedProcess(
                args, 0, str(tmp_path / "consumer").encode() + b"\n", b"",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _hang_on_anchor)

        code = _dispatcher.main(
            ["--pull-request", "1", "--config", str(config)],
        )

        assert code == 3, code
        assert "could not resolve trusted ref" in capsys.readouterr().err
        # Proof the anchor call was actually reached, so a future change that
        # short-circuits earlier fails here rather than passing vacuously.
        assert ["rev-parse", "--symbolic-full-name", "origin/main"] in calls, calls

    def test_a_config_problem_still_exits_2(self, tmp_path, monkeypatch, capsys):
        """Discriminating control: 3 must not swallow the config code.

        Same declared root, same working git; only the config is wrong (it
        is outside both the root and the project). Without this, a mutant
        that returned 3 unconditionally would pass every case above.
        """
        self._plugin_root(tmp_path, monkeypatch)
        outside = tmp_path / "outside" / "pr-review-config.yaml"
        outside.parent.mkdir(parents=True)
        outside.write_text("completion_criteria: []\n", encoding="utf-8")

        code = _dispatcher.main(
            ["--pull-request", "1", "--config", str(outside)],
        )

        assert code == 2, code
        assert "Refusing to load config from unsafe path" in capsys.readouterr().err


class TestInstalledRuntimePrerequisites:
    """What a consumer whose environment lacks PyYAML actually gets.

    Copilot review, PR #5329: the shipped skill runs ``uv run python`` from
    the consumer's cwd and the plugin declares no dependencies, so a clean
    consumer environment may not carry PyYAML. That is a PRE-EXISTING
    condition (this gate has always parsed YAML), but this PR is what makes
    installed dispatch reachable at all, so the prerequisite becomes visible
    here for the first time.

    Packaging the dependency, or replacing the parser, is a plugin-wide
    decision and is deliberately not made in this PR. What IS pinned is that
    the failure is clean: exit 2 with an actionable message, not a traceback
    (exit 1) and not a silently skipped criterion. A gate that cannot parse
    its config must not look like a gate that passed.
    """

    def test_missing_pyyaml_exits_2_with_an_actionable_message(
        self, tmp_path, monkeypatch, capsys,
    ):
        root = tmp_path / "plugin"
        (root / "commands").mkdir(parents=True)
        config = root / "commands" / "pr-review-config.yaml"
        config.write_text("completion_criteria: []\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        _own_plugin_root(monkeypatch, root)

        def _fake_git(args, cwd):
            if args[:2] == ["rev-parse", "--symbolic-full-name"]:
                return subprocess.CompletedProcess(
                    args, 0, b"refs/remotes/origin/main\n", b"",
                )
            return subprocess.CompletedProcess(
                args, 0, str(tmp_path / "consumer").encode() + b"\n", b"",
            )

        monkeypatch.setattr(_dispatcher, "_run_git", _fake_git)
        monkeypatch.setattr(_dispatcher, "_HAVE_YAML", False)

        code = _dispatcher.main(
            ["--pull-request", "1", "--config", str(config)],
        )

        # 2, not 1: a config that cannot be parsed is a config error under
        # ADR-035. Exit 1 is reserved for "a criterion failed", and reporting
        # an unparseable config that way would read as a real gate verdict.
        assert code == 2, code
        err = capsys.readouterr().err
        assert "PyYAML is required" in err, err
        # Actionable AND correctly targeted. Naming the interpreter is the
        # point: the shipped skill runs this through `uv run python`, so a
        # bare `pip install` can modify an environment the next run never
        # consults. Raised by Copilot on PR #5331.
        assert sys.executable in err, err
        assert "uv run --with pyyaml" in err, err


class TestInstallTrustedPathConsistency:
    """The path install-trust approves must be the path that is read.

    Found by Semgrep's dangerous-subprocess-use-tainted-env-args on
    PR #5329. validate_safe_path builds its result as
    (resolved_base / path).resolve(), so handing it the environment-
    declared root as the base made that root a component of the path
    READ, not merely the boundary it is CHECKED against. For a relative
    --config the two resolutions disagree, and the file authorized by
    _install_trusted_root (cwd-anchored) is not the file loaded
    (root-anchored). _resolve_and_read_config now reuses the approved
    path instead.
    """

    def test_a_relative_config_reads_the_cwd_anchored_file(
        self, tmp_path, monkeypatch,
    ):
        """Two files share a relative name; the cwd-anchored one wins.

        Without the fix, validate_safe_path anchored the relative arg on
        the plugin root and loaded the decoy instead.
        """
        consumer = _git_work_tree(tmp_path / "consumer")
        root = tmp_path / "inst" / "plugin"
        rel = "../inst/plugin/pr-review-config.yaml"

        # The file the cwd-anchored resolution names, and the one
        # _install_trusted_root approves: consumer/../inst/plugin/<name>.
        approved = root / "pr-review-config.yaml"
        approved.parent.mkdir(parents=True)
        approved.write_text(
            "completion_criteria:\n  - name: approved\n", encoding="utf-8",
        )
        # The file the ROOT-anchored resolution names for the same arg:
        # tmp/inst/plugin/../inst/plugin/<name> is tmp/inst/inst/plugin/<name>.
        # The asymmetric nesting is what makes the two resolutions differ;
        # with the root and the cwd at the same depth they coincide and the
        # case cannot discriminate. Note this decoy sits OUTSIDE the root
        # that install trust was granted for, which is the defect exactly.
        decoy = tmp_path / "inst" / "inst" / "plugin" / "pr-review-config.yaml"
        decoy.parent.mkdir(parents=True)
        decoy.write_text(
            "completion_criteria:\n  - name: decoy\n", encoding="utf-8",
        )

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.chdir(consumer)

        resolved = _dispatcher._resolve_and_read_config(rel)

        assert resolved.exit_code is None, resolved.exit_code
        assert resolved.install.root == root.resolve()
        assert resolved.path == approved.resolve()
        assert b"approved" in resolved.raw
        assert b"decoy" not in resolved.raw

    def test_the_approved_path_is_the_path_read(self, tmp_path, monkeypatch):
        """The config is resolved ONCE, and the read reuses that result.

        Simulates the CWE-367 swap Copilot reported: a repo-controlled
        symlink changed between the containment decision and the read
        resolves inside the root for the decision and outside it for the
        read, with byte verification still skipped.

        The swap is injected at the only place a second resolution could
        happen, ``_absolute_config_candidate``. Call one is the decision,
        inside ``_install_trusted_root``. Any call two is the re-resolution
        the fix removed, and it gets the decoy. With the fix there is no
        call two, so the decoy is unreachable no matter what it points at.

        Written after mutation showed the earlier cases could not tell the
        two apart: re-resolving returns the same path in a non-adversarial
        fixture, so every one of them passed against the unfixed code.
        """
        root = tmp_path / "plugin"
        approved = root / "commands" / "pr-review-config.yaml"
        approved.parent.mkdir(parents=True)
        approved.write_text(
            "completion_criteria:\n  - name: approved\n", encoding="utf-8",
        )
        decoy = tmp_path / "decoy.yaml"
        decoy.write_text(
            "completion_criteria:\n  - name: decoy\n", encoding="utf-8",
        )

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)

        real = _dispatcher._absolute_config_candidate
        calls: list[str] = []

        def _swapping(config_arg):
            calls.append(config_arg)
            if len(calls) == 1:
                return real(config_arg)
            return decoy

        monkeypatch.setattr(_dispatcher, "_absolute_config_candidate", _swapping)

        resolved = _dispatcher._resolve_and_read_config(str(approved))

        assert resolved.exit_code is None, resolved.exit_code
        assert len(calls) == 1, f"resolved {len(calls)} times, expected 1"
        assert resolved.path == approved.resolve()
        assert b"approved" in resolved.raw
        assert b"decoy" not in resolved.raw

    def test_the_environment_root_cannot_redirect_an_absolute_config(
        self, tmp_path, monkeypatch,
    ):
        """An absolute --config is unaffected by the root, as before."""
        root = tmp_path / "plugin"
        config = root / "commands" / "pr-review-config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            "completion_criteria:\n  - name: absolute\n", encoding="utf-8",
        )
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)

        resolved = _dispatcher._resolve_and_read_config(
            str(config),
        )

        assert resolved.exit_code is None, resolved.exit_code
        assert resolved.install.root == root.resolve()
        assert resolved.path == config.resolve()
        assert b"absolute" in resolved.raw

    def test_a_config_outside_the_root_still_falls_back_to_containment(
        self, tmp_path, monkeypatch,
    ):
        """Negative control: the install branch is not always taken."""
        root = tmp_path / "plugin"
        root.mkdir(parents=True)
        outside = tmp_path / "outside" / "pr-review-config.yaml"
        outside.parent.mkdir(parents=True)
        outside.write_text("completion_criteria: []\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
        _own_plugin_root(monkeypatch, root)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)

        resolved = _dispatcher._resolve_and_read_config(
            str(outside),
        )

        assert resolved.install is None
        assert resolved.path is None
        assert resolved.raw is None
        # 2, not 3: the work tree resolved fine and the CONFIG is the
        # problem. The exit-3 branch is a different failure and has its
        # own cases; asserting the code here keeps the two from merging.
        assert resolved.exit_code == 2, resolved.exit_code
