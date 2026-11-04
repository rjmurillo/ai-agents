"""Contract pins for the gate's refused-session probe (ADR-120)."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.github_core.api import _GRAPHQL_BLOCKED_MESSAGE, _TRANSPORT_BLOCKED_MESSAGE
from tests.gh_auth_refusal_fixtures import PROXY_GRAPHQL_403, PROXY_REST_403
from tests.skills.github.session_refusal_helpers import (
    PASSING,
    REPO_ROOT,
    REST_REFUSED,
    SCRIPT_PATH,
    VERIFIER_REFUSED,
    Session,
    dispatcher,
    proc,
)


class TestProbeContract:
    def test_probe_argv_holds_no_runtime_value(self):
        """Fixed argv keeps PR-controlled input out of the probe."""
        probes = dispatcher._SESSION_REFUSAL_PROBES
        assert all(isinstance(probe.argv, tuple) for probe in probes)
        assert all(probe.argv[:2] == ("gh", "api") for probe in probes)

    def test_patterns_match_the_captured_proxy_bodies(self):
        rest, graphql = dispatcher._SESSION_REFUSAL_PROBES
        assert rest.refusal.search(PROXY_REST_403)
        assert not rest.refusal.search(PROXY_GRAPHQL_403)
        assert graphql.refusal.search(PROXY_GRAPHQL_403)
        assert not graphql.refusal.search(PROXY_REST_403)

    def test_graphql_probe_sends_the_query_check_gh_auth_sends(self):
        """Different text could be answered differently by a query allowlist."""
        _, graphql = dispatcher._SESSION_REFUSAL_PROBES
        api_source = (REPO_ROOT / "scripts/github_core/api.py").read_text(encoding="utf-8")
        assert f'"{graphql.argv[-1]}"' in api_source


_ALLOWED_BEFORE_PREFLIGHT = {"build_parser", "parse_args", "error_and_exit", "print"}


def _calls_before_preflight(script: Path) -> set[str]:
    """Names called in ``main`` before ``assert_gh_authenticated``, in source order."""
    tree = ast.parse(script.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = sorted(
        (node for node in ast.walk(main) if isinstance(node, ast.Call)),
        key=lambda node: (node.lineno, node.col_offset),
    )
    names = [
        call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "?")
        for call in calls
    ]
    return set(names[: names.index("assert_gh_authenticated")])


class TestDecisionEightInvariant:
    """ADR-120 Decision 8: a refusal is session-wide, so no verifier may read PR
    data before the ``gh`` preflight. A verifier that did could steer its own exit."""

    def test_every_shipped_verifier_calls_the_preflight_first(self):
        config_path = REPO_ROOT / "src/claude/skills/pr-review/pr-review-config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        scripts = [
            re.search(r"/skills/github/scripts/pr/(\w+\.py)", criterion["command"]).group(1)
            for criterion in config["completion_criteria"]
        ]

        assert len(scripts) == 5
        for script in scripts:
            before = _calls_before_preflight(SCRIPT_PATH.parent / script)
            assert before <= _ALLOWED_BEFORE_PREFLIGHT, script

    def test_a_broken_verifier_reads_unknown_in_a_refused_session(self, run_gate):
        """Accepted trade-off: it never passes, and the hand check still runs."""
        broken = proc(stderr="Plugin lib directory not found", returncode=2)
        session = Session({"a": broken}, rest=REST_REFUSED)

        rc, result = run_gate(session)

        assert rc == 3
        assert result["criteria"][0]["passed"] is False

    def test_reworded_proxy_body_leaves_the_row_failed(self, run_gate):
        reworded = proc(stderr="gh: Access denied by session policy. (HTTP 403)", returncode=1)
        session = Session({"a": VERIFIER_REFUSED}, rest=reworded, graphql=reworded)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["criteria"][0]["status"] == "failed"


class TestApiErrorSource:
    """ADR-120: only a raised ``gh`` call may set ``api_error``."""

    @staticmethod
    def _fetch(answers):
        path = SCRIPT_PATH.parent / "get_unresolved_review_threads.py"
        spec = importlib.util.spec_from_file_location("unresolved_for_api_error", path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "gh_graphql", side_effect=answers):
            return module.fetch_unresolved_threads_paginated("o", "r", 1, 1)

    def test_raised_call_sets_api_error(self):
        _, complete, api_error = self._fetch(RuntimeError("HTTP 403"))

        assert (complete, api_error) == (False, True)

    def test_missing_cursor_does_not_set_api_error(self):
        page = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}}
        answer = {"repository": {"pullRequest": {"reviewThreads": page}}}

        _, complete, api_error = self._fetch([answer])

        assert (complete, api_error) == (False, False)

    def test_complete_read_does_not_set_api_error(self):
        page = {"nodes": [], "pageInfo": {"hasNextPage": False}}
        answer = {"repository": {"pullRequest": {"reviewThreads": page}}}

        _, complete, api_error = self._fetch([answer])

        assert (complete, api_error) == (True, False)


class TestUnknownEvidence:
    def test_reason_says_the_criterion_was_not_verified(self, run_gate):
        session = Session({"a": VERIFIER_REFUSED}, rest=REST_REFUSED)

        _, result = run_gate(session)

        assert result["criteria"][0]["reason"].startswith("session refuses GitHub")

    def test_evidence_file_records_the_verdict(self, run_gate, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        session = Session({"a": VERIFIER_REFUSED}, rest=REST_REFUSED)
        evidence = tmp_path / "gate-evidence.json"

        rc, _ = run_gate(session, extra_args=["--evidence-path", str(evidence)])

        recorded = json.loads(evidence.read_text(encoding="utf-8"))
        assert rc == 3
        assert recorded["verdict"] == "unknown"
        assert recorded["unknown_criteria"] == ["a"]


class TestTrustHaltStaysDistinct:
    def test_trust_halt_exit_three_prints_no_payload(self, run_gate, monkeypatch):
        """Payload presence is how a caller tells the two exit 3 results apart."""
        monkeypatch.setattr(
            dispatcher,
            "_verify_command_trust",
            lambda *_a, **_k: dispatcher.CommandTrustCheck(
                dispatcher.COMMAND_TRUST_GIT_ERROR, [], [], [], [], "git failed"
            ),
        )
        session = Session({"a": PASSING})

        rc, out = run_gate(session, as_json=False)

        assert rc == 3
        assert out == ""
        assert "HALT:" in run_gate.stderr
        assert "UNKNOWN:" not in run_gate.stderr
        assert session.gh_calls == []


class TestRefusalMessage:
    def test_app_connection_is_not_the_expected_fix(self):
        assert "that is the environment fix" not in _TRANSPORT_BLOCKED_MESSAGE
        assert "supported path" in _TRANSPORT_BLOCKED_MESSAGE

    def test_graphql_message_stays_distinct(self):
        assert "repository REST call was served" in _GRAPHQL_BLOCKED_MESSAGE
