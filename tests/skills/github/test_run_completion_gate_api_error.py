"""The gate's ``api_error`` signal and the evidence an unknown row leaves (ADR-120).

``get_unresolved_review_threads.py`` reports a failed ``gh`` call at exit 0, so the
gate reads that one field. It never reads ``fetched_pages_complete`` for this,
because a PR can set that field false with no API failure.
"""

from __future__ import annotations

import importlib.util
import json
from unittest.mock import patch

from tests.skills.github.session_refusal_helpers import (
    API_ERROR,
    GRAPHQL_REFUSED,
    INCOMPLETE_READ,
    REST_REFUSED,
    SCRIPT_PATH,
    VERIFIER_EXTERNAL_ERROR,
    VERIFIER_REFUSED,
    Session,
)


class TestApiErrorVerdict:
    def test_api_error_is_unanswered_in_a_refused_session(self, run_gate):
        """``get_unresolved_review_threads.py`` reports an API failure at exit 0."""
        session = Session({"a": API_ERROR, "b": VERIFIER_EXTERNAL_ERROR}, rest=REST_REFUSED)

        rc, result = run_gate(session)

        assert rc == 3
        assert result["verdict"] == "unknown"
        assert [row["status"] for row in result["criteria"]] == ["unknown", "unknown"]

    def test_pr_caused_incomplete_read_stays_failed_in_a_refused_session(self, run_gate):
        """A thread with over 100 comments sets the field, so it proves no API failure."""
        session = Session({"a": INCOMPLETE_READ}, rest=REST_REFUSED)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["verdict"] == "fail"
        assert result["criteria"][0]["status"] == "failed"
        assert session.gh_calls == []

    def test_graphql_refusal_leaves_an_api_error_failed(self, run_gate):
        """``api_error`` stands in for exit 3, which the narrow body does not cover."""
        session = Session({"a": API_ERROR}, graphql=GRAPHQL_REFUSED)

        rc, result = run_gate(session)

        assert rc == 1
        assert result["criteria"][0]["status"] == "failed"

    def test_api_error_stays_failed_in_a_served_session(self, run_gate):
        session = Session({"a": API_ERROR})

        rc, result = run_gate(session)

        assert rc == 1
        assert result["criteria"][0]["status"] == "failed"
        assert len(session.gh_calls) == 2


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
