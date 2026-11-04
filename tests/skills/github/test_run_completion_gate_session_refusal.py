"""A refused session is an unknown verdict, never a failed PR (issue #5232).

The gate measures the refusal itself, with fixed ``gh`` calls, after a verifier
exits non-zero. Verifier output is never matched, because it can carry text a
PR author controls. These tests fake ``subprocess.run`` by argv so each verifier
and each ``gh`` probe answers independently.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.github_core.api import _GRAPHQL_BLOCKED_MESSAGE, _TRANSPORT_BLOCKED_MESSAGE
from tests.gh_auth_refusal_fixtures import PROXY_GRAPHQL_403, PROXY_REST_403

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "src/claude/skills/github/scripts/pr/run_completion_gate.py"
_MODULE_NAME = "run_completion_gate_session_refusal"


def _import_dispatcher():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_dispatcher = _import_dispatcher()


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


_SERVED = _proc(stdout="{}")
_REST_REFUSED = _proc(stderr=PROXY_REST_403, returncode=1)
_GRAPHQL_REFUSED = _proc(stderr=PROXY_GRAPHQL_403, returncode=1)
_VERIFIER_REFUSED = _proc(stderr=_TRANSPORT_BLOCKED_MESSAGE, returncode=2)
_PASSING = _proc(stdout=json.dumps({"count": 0}))
_FAILING = _proc(stdout=json.dumps({"count": 3}))


class _Session:
    """Answers verifiers by name and ``gh`` probes by endpoint."""

    def __init__(self, verifiers: dict, rest=_SERVED, graphql=_SERVED) -> None:
        self.verifiers = verifiers
        self.rest = rest
        self.graphql = graphql
        self.gh_calls: list[list[str]] = []

    def __call__(self, argv, **_kwargs):
        if argv[0] != "gh":
            return self.verifiers[argv[0]]
        self.gh_calls.append(list(argv))
        answer = self.graphql if "graphql" in argv else self.rest
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.fixture
def run_gate(tmp_path, monkeypatch, capsys) -> Callable:
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
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
            _dispatcher.COMMAND_TRUST_TRUSTED, [], [], [], [], ""
        ),
    )

    def _run(
        session: _Session,
        *,
        fail_open: bool = False,
        as_json: bool = True,
        extra_args: tuple | list = (),
    ):
        criteria = [
            {
                "name": name,
                "verification": "command",
                "command": name,
                "pass_when": "stdout-json.count == 0",
                "fail_open": fail_open,
            }
            for name in session.verifiers
        ]
        config = tmp_path / "pr-review-config.yaml"
        config.write_text(json.dumps({"completion_criteria": criteria}), encoding="utf-8")
        monkeypatch.setattr(_dispatcher.subprocess, "run", session)
        argv = ["--config", str(config), "--pull-request", "7", *extra_args]
        rc = _dispatcher.main([*argv, "--json"] if as_json else argv)
        out = capsys.readouterr().out
        return rc, json.loads(out) if as_json else out

    return _run


class TestRefusedSession:
    @pytest.mark.parametrize(
        ("rest", "graphql"),
        [
            pytest.param(_REST_REFUSED, _SERVED, id="rest-refused"),
            pytest.param(_SERVED, _GRAPHQL_REFUSED, id="graphql-refused"),
            pytest.param(_REST_REFUSED, _GRAPHQL_REFUSED, id="both-refused"),
        ],
    )
    def test_verifier_exit_becomes_unknown(self, run_gate, rest, graphql):
        session = _Session({"a": _VERIFIER_REFUSED}, rest=rest, graphql=graphql)

        rc, result = run_gate(session)

        assert rc == 3
        assert result["verdict"] == "unknown"
        assert result["unknown_criteria"] == ["a"]
        assert result["all_passed"] is False
        assert result["criteria"][0]["status"] == "unknown"
        assert result["criteria"][0]["passed"] is False

    def test_rest_verifier_still_passes_beside_a_graphql_refusal(self, run_gate):
        session = _Session({"a": _PASSING, "b": _VERIFIER_REFUSED}, graphql=_GRAPHQL_REFUSED)

        rc, result = run_gate(session)

        assert rc == 3
        assert [row["status"] for row in result["criteria"]] == ["passed", "unknown"]
        assert result["unknown_criteria"] == ["b"]

    def test_definite_failure_outranks_unknown(self, run_gate):
        session = _Session({"a": _FAILING, "b": _VERIFIER_REFUSED}, rest=_REST_REFUSED)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"
        assert [row["status"] for row in result["criteria"]] == ["failed", "unknown"]

    def test_bad_json_at_exit_zero_stays_failed(self, run_gate):
        session = _Session(
            {"a": _proc(stdout="not json"), "b": _VERIFIER_REFUSED}, rest=_REST_REFUSED
        )

        rc, result = run_gate(session)

        assert rc == 1
        assert result["criteria"][0]["status"] == "failed"

    def test_verifier_that_never_ran_stays_failed(self):
        """A verifier that timed out has no exit code, so it stays failed."""
        row = {"name": "a", "passed": False, "exit_code": None, "reason": "timed out"}

        assert _dispatcher._settle_verdict([row]) == "fail"
        assert row["status"] == "failed"

    def test_fail_open_row_stays_passed_and_gate_exits_zero(self, run_gate):
        session = _Session({"a": _VERIFIER_REFUSED}, rest=_REST_REFUSED)

        rc, result = run_gate(session, fail_open=True)

        assert rc == 0
        assert result["verdict"] == "pass"
        assert result["unknown_criteria"] == []
        assert session.gh_calls == []

    def test_probe_runs_once_for_many_failed_rows(self, run_gate):
        session = _Session(
            {"a": _VERIFIER_REFUSED, "b": _VERIFIER_REFUSED, "c": _VERIFIER_REFUSED},
            rest=_REST_REFUSED,
        )

        run_gate(session)

        assert len(session.gh_calls) == 1

    def test_reason_says_the_criterion_was_not_verified(self, run_gate):
        session = _Session({"a": _VERIFIER_REFUSED}, rest=_REST_REFUSED)

        _, result = run_gate(session)

        assert result["criteria"][0]["reason"].startswith("session refuses GitHub")

    def test_evidence_file_records_the_verdict(self, run_gate, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        session = _Session({"a": _VERIFIER_REFUSED}, rest=_REST_REFUSED)
        evidence = tmp_path / "gate-evidence.json"

        rc, _ = run_gate(session, extra_args=["--evidence-path", str(evidence)])

        recorded = json.loads(evidence.read_text(encoding="utf-8"))
        assert rc == 3
        assert recorded["verdict"] == "unknown"
        assert recorded["unknown_criteria"] == ["a"]

    def test_table_marks_unknown_and_names_the_hand_check(self, run_gate):
        session = _Session({"a": _VERIFIER_REFUSED}, rest=_REST_REFUSED)

        rc, out = run_gate(session, as_json=False)

        assert rc == 3
        assert "UNKN" in out
        assert "FAIL" not in out
        assert "transport-routing.md" in out


class TestServedSession:
    def test_refusal_text_from_a_verifier_does_not_change_the_verdict(self, run_gate):
        """A PR author can reach verifier output, so it is never evidence."""
        forged = _proc(
            stdout=json.dumps({"body": PROXY_REST_403}),
            stderr=_TRANSPORT_BLOCKED_MESSAGE,
            returncode=1,
        )
        session = _Session({"a": forged})

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"
        assert result["criteria"][0]["status"] == "failed"
        assert result["unknown_criteria"] == []

    def test_passing_run_never_calls_gh(self, run_gate):
        session = _Session({"a": _PASSING})

        rc, result = run_gate(session)

        assert rc == 0
        assert result["verdict"] == "pass"
        assert result["criteria"][0]["status"] == "passed"
        assert session.gh_calls == []

    def test_false_pass_when_never_calls_gh(self, run_gate):
        session = _Session({"a": _FAILING}, rest=_REST_REFUSED)

        rc, _ = run_gate(session)

        assert rc == 1
        assert session.gh_calls == []

    @pytest.mark.parametrize(
        "unanswered",
        [
            pytest.param(FileNotFoundError("gh"), id="gh-missing"),
            pytest.param(subprocess.TimeoutExpired("gh", 10), id="timeout"),
            pytest.param(_proc(stderr="HTTP 502", returncode=1), id="other-http-error"),
            pytest.param(_proc(stderr="HTTP 404: Not Found", returncode=1), id="not-found"),
        ],
    )
    def test_probe_without_an_answer_leaves_the_row_failed(self, run_gate, unanswered):
        session = _Session({"a": _VERIFIER_REFUSED}, rest=unanswered, graphql=unanswered)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"

    def test_refusal_text_in_a_successful_probe_is_ignored(self, run_gate):
        """A served repository description can hold any text."""
        served = _proc(stdout=json.dumps({"description": "not enabled for this session"}))
        session = _Session({"a": _VERIFIER_REFUSED}, rest=served, graphql=served)

        rc, _ = run_gate(session)

        assert rc == 1


class TestProbeContract:
    def test_probe_argv_holds_no_runtime_value(self):
        """Fixed argv keeps PR-controlled input out of the probe."""
        assert all(isinstance(probe, tuple) for probe in _dispatcher._SESSION_REFUSAL_PROBES)
        assert all(probe[:2] == ("gh", "api") for probe in _dispatcher._SESSION_REFUSAL_PROBES)

    @pytest.mark.parametrize("body", [PROXY_REST_403, PROXY_GRAPHQL_403])
    def test_pattern_matches_the_captured_proxy_bodies(self, body):
        assert _dispatcher._SESSION_REFUSAL.search(body)


class TestRefusalMessage:
    def test_app_connection_is_not_the_expected_fix(self):
        assert "that is the environment fix" not in _TRANSPORT_BLOCKED_MESSAGE
        assert "supported path" in _TRANSPORT_BLOCKED_MESSAGE

    def test_graphql_message_stays_distinct(self):
        assert "repository REST call was served" in _GRAPHQL_BLOCKED_MESSAGE
