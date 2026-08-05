"""Tests for auto_merge_guard.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("auto_merge_guard")


def _thread_context(auto_merge: dict | None = None, resolved: bool = False) -> dict:
    return {
        "node": {
            "id": "PRRT_final",
            "isResolved": resolved,
            "pullRequest": {
                "id": "PR_node",
                "number": 4377,
                "autoMergeRequest": auto_merge,
                "repository": {
                    "name": "ai-agents",
                    "owner": {"login": "rjmurillo"},
                },
            },
        },
    }


def _threads(*ids: str, has_next: bool = False, cursor: str | None = None) -> dict:
    return {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": cursor,
                    },
                    "nodes": [
                        {"id": thread_id, "isResolved": False}
                        for thread_id in ids
                    ],
                },
            },
        },
    }


def _disabled() -> dict:
    return {
        "disablePullRequestAutoMerge": {
            "pullRequest": {
                "id": "PR_node",
                "number": 4377,
                "autoMergeRequest": None,
            },
        },
    }


class TestAutoMergeGuard:
    def test_disables_armed_auto_merge_before_final_thread_resolution(self):
        calls: list[str] = []

        def fake_graphql(query: str, variables: dict):
            if "node(id: $threadId)" in query:
                calls.append("context")
                return _thread_context(
                    {"enabledAt": "2026-08-04T01:40:00Z", "mergeMethod": "SQUASH"},
                )
            if "reviewThreads(first: 100" in query:
                calls.append("count")
                return _threads("PRRT_final")
            if "disablePullRequestAutoMerge" in query:
                calls.append("disable")
                return _disabled()
            raise AssertionError(query[:80])

        with patch("auto_merge_guard.gh_graphql", side_effect=fake_graphql):
            result = _mod.guard_auto_merge_before_final_thread_resolution("PRRT_final")

        assert calls == ["context", "count", "disable"]
        assert result["action"] == "DISABLED"
        assert result["auto_merge_was_armed"] is True
        assert result["unresolved_count"] == 1
        assert result["merge_method"] == "SQUASH"

    def test_does_not_disable_when_more_than_one_thread_is_unresolved(self):
        calls: list[str] = []

        def fake_graphql(query: str, variables: dict):
            if "node(id: $threadId)" in query:
                calls.append("context")
                return _thread_context(
                    {"enabledAt": "2026-08-04T01:40:00Z", "mergeMethod": "SQUASH"},
                )
            if "reviewThreads(first: 100" in query:
                calls.append("count")
                return _threads("PRRT_final", "PRRT_other")
            if "disablePullRequestAutoMerge" in query:
                calls.append("disable")
                return _disabled()
            raise AssertionError(query[:80])

        with patch("auto_merge_guard.gh_graphql", side_effect=fake_graphql):
            result = _mod.guard_auto_merge_before_final_thread_resolution("PRRT_final")

        assert calls == ["context", "count"]
        assert result["action"] == "NOOP"
        assert result["reason"] == "not_final_thread"
        assert result["unresolved_count"] == 2

    def test_does_not_disable_when_final_thread_has_no_armed_auto_merge(self):
        calls: list[str] = []

        def fake_graphql(query: str, variables: dict):
            if "node(id: $threadId)" in query:
                calls.append("context")
                return _thread_context(None)
            if "reviewThreads(first: 100" in query:
                calls.append("count")
                return _threads("PRRT_final")
            if "disablePullRequestAutoMerge" in query:
                calls.append("disable")
                return _disabled()
            raise AssertionError(query[:80])

        with patch("auto_merge_guard.gh_graphql", side_effect=fake_graphql):
            result = _mod.guard_auto_merge_before_final_thread_resolution("PRRT_final")

        assert calls == ["context", "count"]
        assert result["action"] == "NOOP"
        assert result["reason"] == "auto_merge_not_armed"
        assert result["auto_merge_was_armed"] is False

    def test_rejects_incomplete_unresolved_thread_pagination(self):
        def fake_graphql(query: str, variables: dict):
            if "node(id: $threadId)" in query:
                return _thread_context(
                    {"enabledAt": "2026-08-04T01:40:00Z", "mergeMethod": "SQUASH"},
                )
            if "reviewThreads(first: 100" in query:
                return _threads("PRRT_final", has_next=True, cursor=None)
            raise AssertionError(query[:80])

        with patch("auto_merge_guard.gh_graphql", side_effect=fake_graphql):
            with pytest.raises(RuntimeError, match="could not prove"):
                _mod.guard_auto_merge_before_final_thread_resolution("PRRT_final")

    def test_rejects_if_final_thread_identity_changes(self):
        def fake_graphql(query: str, variables: dict):
            if "node(id: $threadId)" in query:
                return _thread_context(
                    {"enabledAt": "2026-08-04T01:40:00Z", "mergeMethod": "SQUASH"},
                )
            if "reviewThreads(first: 100" in query:
                return _threads("PRRT_other")
            raise AssertionError(query[:80])

        with patch("auto_merge_guard.gh_graphql", side_effect=fake_graphql):
            with pytest.raises(RuntimeError, match="changed before resolution"):
                _mod.guard_auto_merge_before_final_thread_resolution("PRRT_final")
