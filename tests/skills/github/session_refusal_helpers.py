"""Shared setup for the completion gate's refused-session tests (issue #5232).

Fakes ``subprocess.run`` by argv, so each verifier and each ``gh`` probe answers
independently. The proxy bodies are the ones captured from a live session.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from scripts.github_core.api import _TRANSPORT_BLOCKED_MESSAGE
from tests.gh_auth_refusal_fixtures import PROXY_GRAPHQL_403, PROXY_REST_403

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "src/claude/skills/github/scripts/pr/run_completion_gate.py"
_MODULE_NAME = "run_completion_gate_session_refusal"


def _import_dispatcher():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


dispatcher = _import_dispatcher()


def proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


SERVED = proc(stdout="{}")
REST_REFUSED = proc(stderr=PROXY_REST_403, returncode=1)
GRAPHQL_REFUSED = proc(stderr=PROXY_GRAPHQL_403, returncode=1)
VERIFIER_REFUSED = proc(stderr=_TRANSPORT_BLOCKED_MESSAGE, returncode=2)
VERIFIER_EXTERNAL_ERROR = proc(stderr="HTTP 503", returncode=3)
VERIFIER_NOT_READY = proc(stdout=json.dumps({"CanMerge": False}), returncode=1)
PASSING = proc(stdout=json.dumps({"count": 0}))
FAILING = proc(stdout=json.dumps({"count": 3}))
API_ERROR = proc(
    stdout=json.dumps({"count": 3, "fetched_pages_complete": False, "api_error": True})
)
INCOMPLETE_READ = proc(
    stdout=json.dumps({"count": 3, "fetched_pages_complete": False, "api_error": False})
)


class Session:
    """Answers verifiers by name and ``gh`` probes by endpoint."""

    def __init__(self, verifiers: dict, rest=SERVED, graphql=SERVED) -> None:
        self._verifiers = verifiers
        self._rest = rest
        self._graphql = graphql
        self._gh_calls: list[list[str]] = []

    @property
    def verifiers(self) -> dict:
        return self._verifiers

    @property
    def gh_calls(self) -> list[list[str]]:
        return self._gh_calls

    def __call__(self, argv, **_kwargs):
        if argv[0] != "gh":
            return self._verifiers[argv[0]]
        self._gh_calls.append(list(argv))
        answer = self._graphql if "graphql" in argv else self._rest
        if isinstance(answer, BaseException):
            raise answer
        return answer


class GateRunner:
    """Runs ``main`` against a fake session and keeps the last stderr."""

    def __init__(self, tmp_path: Path, monkeypatch, capsys) -> None:
        self._tmp_path = tmp_path
        self._monkeypatch = monkeypatch
        self._capsys = capsys
        self._stderr = ""

    @property
    def stderr(self) -> str:
        return self._stderr

    def __call__(
        self,
        session: Session,
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
        config = self._tmp_path / "pr-review-config.yaml"
        config.write_text(json.dumps({"completion_criteria": criteria}), encoding="utf-8")
        self._monkeypatch.setattr(dispatcher.subprocess, "run", session)
        argv = ["--config", str(config), "--pull-request", "7", *extra_args]
        rc = dispatcher.main([*argv, "--json"] if as_json else argv)
        captured = self._capsys.readouterr()
        self._stderr = captured.err
        return rc, json.loads(captured.out) if as_json else captured.out


def make_gate_runner(tmp_path: Path, monkeypatch, capsys) -> GateRunner:
    """Build the ``run_gate`` fixture's runner, with both trust checks stubbed."""
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setattr(dispatcher, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        dispatcher,
        "_verify_config_trust",
        lambda *_a, **_k: dispatcher.TrustCheck(dispatcher.TRUST_TRUSTED, ""),
    )
    monkeypatch.setattr(
        dispatcher,
        "_verify_command_trust",
        lambda *_a, **_k: dispatcher.CommandTrustCheck(
            dispatcher.COMMAND_TRUST_TRUSTED, [], [], [], [], ""
        ),
    )

    return GateRunner(tmp_path, monkeypatch, capsys)
