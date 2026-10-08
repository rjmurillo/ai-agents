#!/usr/bin/env python3
"""Tests for the trusted-context gate on the authenticated smoke (issue #2231 item 3, REQ-047).

The gate keeps the secret-bearing smoke from running attacker-controlled code.
These tests cover the authorized path and every denial reason. The CLI argv
contract (stdout decision, exit code) lives in
``test_assert_trusted_smoke_context_cli.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "validation"
    / "assert_trusted_smoke_context.py"
)
_spec = importlib.util.spec_from_file_location("assert_trusted_smoke_context", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

_REPO = "rjmurillo/ai-agents"
_REF = "refs/heads/main"


_PR_REF = "refs/pull/7/merge"
_FORK = "attacker/ai-agents"


def _decide(event: str, repository: str = _REPO, ref: str = _REF, **kwargs: str | None):
    return gate.is_trusted(event, repository, _REPO, ref, _REF, **kwargs)


@pytest.mark.parametrize(
    ("event", "repository", "ref", "head_repository"),
    [
        ("workflow_dispatch", _REPO, _REF, None),
        ("pull_request", _REPO, _PR_REF, _REPO),
        ("workflow_dispatch", _REPO.upper(), _REF, None),
        ("pull_request", _REPO, _PR_REF, _REPO.upper()),
    ],
    ids=["dispatch", "same-repo-pr", "repo-case-insensitive", "head-case-insensitive"],
)
def test_trusted_context_is_accepted(
    event: str, repository: str, ref: str, head_repository: str | None
) -> None:
    trusted, reason = _decide(event, repository, ref, head_repository=head_repository)

    assert trusted is True
    assert "trusted context" in reason


@pytest.mark.parametrize(
    ("event", "repository", "ref", "head_repository", "expected_reason"),
    [
        ("pull_request", _REPO, _PR_REF, _FORK, "fork"),
        ("pull_request", _REPO, _PR_REF, None, "head repository"),
        ("pull_request", _REPO, _PR_REF, "", "head repository"),
        ("pull_request", _REPO, _PR_REF, "   ", "head repository"),
        ("workflow_dispatch", _REPO, "refs/heads/feature", _REPO, "not the trusted ref"),
        ("workflow_dispatch", _REPO, "refs/heads/feature", None, "not the trusted ref"),
        ("schedule", _REPO, _REF, None, "not a trusted trigger"),
        ("workflow_dispatch", _FORK, _REF, None, "not the trusted repo"),
        ("pull_request", _FORK, _PR_REF, _FORK, "not the trusted repo"),
        ("push", _REPO, _REF, _REPO, ""),
    ],
    ids=[
        "fork-pr",
        "pr-head-missing",
        "pr-head-empty",
        "pr-head-blank",
        "dispatch-wrong-ref-with-head",
        "dispatch-wrong-ref",
        "schedule",
        "fork-dispatch",
        "pr-in-fork",
        "unknown-event",
    ],
)
def test_untrusted_context_is_denied(
    event: str, repository: str, ref: str, head_repository: str | None, expected_reason: str
) -> None:
    trusted, reason = _decide(event, repository, ref, head_repository=head_repository)

    assert trusted is False
    assert expected_reason in reason
