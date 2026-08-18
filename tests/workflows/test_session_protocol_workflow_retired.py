"""Durable regression: the session-protocol CI workflow stays retired.

The mandatory committed session-log gate was retired because it duplicated
signal that git history, PR/CI review, and Copilot session data already carry.
This test pins the removal so a future edit cannot silently reintroduce the
workflow, a reference to it, or a required-status-check context tied to it.

Scope: this asserts absence only. The real validator
(``scripts/validate_session_json.py``) and the historical
``.agents/sessions/*.json`` records stay in place and are out of scope here.
"""

from __future__ import annotations

from pathlib import Path

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
RETIRED_WORKFLOW = WORKFLOW_DIR / "ai-session-protocol.yml"


def test_retired_workflow_file_is_absent() -> None:
    assert not RETIRED_WORKFLOW.exists(), (
        "ai-session-protocol.yml was retired; it must not be reintroduced. "
        f"Found: {RETIRED_WORKFLOW}"
    )


def test_no_workflow_references_session_protocol() -> None:
    offenders: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        if "ai-session-protocol" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == [], (
        "No workflow may reference the retired ai-session-protocol workflow. "
        f"Offending files: {offenders}"
    )


def test_no_session_protocol_required_context() -> None:
    # Canonical contract: scripts/ci/ruleset_required_contexts.py::REQUIRED_CONTEXTS.
    # Verified 2026-08-16 to contain no session-protocol context, so removing the
    # workflow does not break the required-status-check registry.
    offenders = [ctx for ctx in REQUIRED_CONTEXTS if "Session Protocol" in ctx]
    assert offenders == [], (
        "The required-status-check registry must not gate on a session-protocol "
        f"context. Offending contexts: {offenders}"
    )
