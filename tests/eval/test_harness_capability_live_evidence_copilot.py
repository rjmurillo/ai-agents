"""Copilot live-evidence re-derivation (issue #5423 BYOK scope addition).

Split from `test_harness_capability_live_evidence.py` (codex) to stay under
this repository's 500-line file-size ceiling; see that file's module
docstring for the shared contract. Every GitHub-routed Copilot call on
2026-09-24 returned HTTP 402 (monthly quota exceeded), so every VERIFIED
copilot cell here was probed through the documented BYOK Anthropic path
instead (`copilot-1.0.89-byok-anthropic/*`); GitHub-routed Sol, Luna, and
Terra models remain unobserved, which is also why every #5422 arm stays
`UNVERIFIED` between codex and copilot (see
`test_harness_capability_arm_models.py::test_no_arm_matches_codex_against_the_checked_in_copilot_record`).
"""

from __future__ import annotations

import json
import subprocess

from tests.eval._harness_capability_test_support import (
    FIXTURES,
    MATRIX,
    capability,
    copilot_wire,
    evidence,
    probes,
    runtime_harness,
    topology,
)

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind

BYOK_FIXTURES = FIXTURES / "copilot-1.0.89-byok-anthropic"
LEGACY_FIXTURES = FIXTURES / "copilot-1.0.89"


def _events(name: str) -> list[dict[str, object]]:
    text = (BYOK_FIXTURES / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _wire_text(name: str) -> str:
    return (BYOK_FIXTURES / name).read_text(encoding="utf-8")


def _final_answer(events: list[dict[str, object]]) -> str:
    """Return the last top-level (no `agentId`) assistant turn with real content.

    A turn that only carries tool requests (`content == ""`) is not the
    answer; the last content-bearing turn is, mirroring
    `_capability_evidence._assistant_values`'s own content requirement.
    """
    answers = [
        event["data"]["content"]
        for event in events
        if event.get("type") == "assistant.message"
        and not event.get("agentId")
        and event["data"].get("content")
    ]
    return answers[-1]


def _copilot_record():
    return next(record for record in capability.load_matrix(MATRIX) if record.harness == "copilot")


# --- model_override / parent_child_override / subagent_support -------------------
#
# All three read the same run: a parent on claude-haiku-4-5 launches one task
# child explicitly overridden to claude-sonnet-4-6.


def test_client_label_diverges_from_the_wire_response_model() -> None:
    """The finding this whole BYOK scope addition exists to prove.

    `assistant.message.data.model` reports the requested alias
    (`claude-haiku-4-5`); the provider's own wire response for the same
    `apiCallId`/`id` reports the dated id it actually used
    (`claude-haiku-4-5-20251001`).
    """
    events = _events("child-model-override.events.jsonl")
    responses = copilot_wire.parse_wire_responses(_wire_text("child-model-override.wire.log"))
    parent_answer = next(
        event
        for event in events
        if event.get("type") == "assistant.message"
        and not event.get("agentId")
        and event["data"].get("content")
    )
    matching_response = next(
        response for response in responses if response.id == parent_answer["data"]["apiCallId"]
    )

    assert parent_answer["data"]["model"] == "claude-haiku-4-5"
    assert matching_response.model == "claude-haiku-4-5-20251001"
    assert parent_answer["data"]["model"] != matching_response.model


def test_model_override_reproduces_verified_from_child_model_override() -> None:
    events = _events("child-model-override.events.jsonl")
    responses = copilot_wire.parse_wire_responses(_wire_text("child-model-override.wire.log"))

    observed = evidence.observe_copilot_model(events, responses)
    status = capability.classify_override(
        "claude-sonnet-4-6",
        observed.observed,
        observed.evidence,
        parent_value="claude-haiku-4-5-20251001",
    )

    assert observed.evidence is EvidenceKind.BACKEND
    assert observed.observed == "claude-sonnet-4-6"
    assert status is CapabilityStatus.VERIFIED


def test_parent_child_override_child_launch_names_the_override_source() -> None:
    """`subagent.started.data.taskModelSource == "task_argument"`: the child's

    model came from the tool call, not session inheritance, which is the
    other half of `parent_child_override`'s evidence alongside the wire
    response divergence in `test_model_override_reproduces_verified_...`.
    """
    events = _events("child-model-override.events.jsonl")
    started = next(event for event in events if event.get("type") == "subagent.started")

    assert started["data"]["model"] == "claude-sonnet-4-6"
    assert started["data"]["taskModelSource"] == "task_argument"


def test_subagent_support_reproduces_verified_from_child_model_override() -> None:
    events = _events("child-model-override.events.jsonl")
    responses = copilot_wire.parse_wire_responses(_wire_text("child-model-override.wire.log"))
    child_answer = next(
        event
        for event in events
        if event.get("type") == "assistant.message"
        and event.get("agentId")
        and event["data"].get("content")
    )

    assert topology.subagent_lifecycle_events(events), "no subagent.* event at all"
    assert any(response.id == child_answer["data"]["apiCallId"] for response in responses), (
        "the child's answer has no matching provider wire response"
    )


# --- effort_override (UNVERIFIED, client_echo) ------------------------------------


def test_effort_override_reproduces_client_echo_never_backend() -> None:
    low = copilot_wire.parse_wire_requests(_wire_text("child-model-override.wire.log"))
    high = copilot_wire.parse_wire_requests(_wire_text("effort-high.wire.log"))

    low_observed = evidence.observe_copilot_effort(low)
    high_observed = evidence.observe_copilot_effort(high)

    assert low_observed.observed == "1024" and low_observed.evidence is EvidenceKind.CLIENT_ECHO
    assert high_observed.observed == "4096" and high_observed.evidence is EvidenceKind.CLIENT_ECHO
    status = capability.classify_override("high", high_observed.observed, high_observed.evidence)
    assert status is CapabilityStatus.UNVERIFIED, "CLIENT_ECHO evidence must never verify"


# --- concurrency_limit (UNVERIFIED, client_echo) ------------------------------------


def test_concurrency_limit_reproduces_the_checked_in_client_echo_value() -> None:
    """`subagent.*` lifecycle events are client-emitted, not backend evidence.

    Copilot's Anthropic wire log carries no request id on requests (unlike
    the response `Request-ID` header `_copilot_wire` reads), so a child's
    provider call cannot be paired into a backend span the way codex's
    `response.created`/`.completed` frames can. `topology.max_concurrent_children`
    still reproduces the observed count of 3 from the client's own
    `subagent.started`/`.completed` events, but that count is `client_echo`
    evidence, never `BACKEND`, so it cannot reach `VERIFIED`
    (`_harness_capability.classify_override`/`validate_record` both require
    `BACKEND` for `VERIFIED`; nothing in `_capability_probes` routes
    copilot's `concurrency_limit` through a probe that could claim
    otherwise, see `test_no_copilot_probe_path_can_verify_concurrency`).
    """
    events = _events("concurrency-3-requested.events.jsonl")

    assert topology.subagent_launch_count(events) == 3
    peak = topology.max_concurrent_children(events)

    record = _copilot_record()
    concurrency = record.capabilities["concurrency_limit"]
    assert peak == concurrency.value == 3
    assert concurrency.status is CapabilityStatus.UNVERIFIED
    assert concurrency.evidence is EvidenceKind.CLIENT_ECHO


def test_no_copilot_probe_path_can_verify_concurrency() -> None:
    """Structural guard: copilot has no trusted `concurrency_limit` request

    flag at all (`copilot --help`, 1.0.89, lists none), so
    `probes.probe_concurrency` can never reach copilot's `subagent.*`
    events for that capability; the trust gate refuses it first, the same
    way it refuses the old `--max-concurrency` placeholder.
    """
    assert ("copilot", "concurrency_limit") not in probes.TRUSTED_REQUEST_TEMPLATES


# --- reviewer_isolation ------------------------------------------------------------


def test_reviewer_isolation_reproduces_verified_from_reviewer_isolation_events() -> None:
    events = _events("reviewer-isolation.events.jsonl")
    child_answers = [
        event["data"]["content"]
        for event in events
        if event.get("type") == "assistant.message"
        and event.get("agentId")
        and event["data"].get("content")
    ]
    reviewer_answer, control_answer = child_answers[0], child_answers[1]

    verdict = capability.classify_reviewer_isolation(
        reviewer_answer, ["ZEBRA-7731"], EvidenceKind.BACKEND
    )
    control_verdict = capability.classify_reviewer_isolation(
        control_answer, ["ZEBRA-7731"], EvidenceKind.BACKEND
    )

    assert reviewer_answer == "NONE"
    assert control_answer == "ZEBRA-7731"
    assert verdict is CapabilityStatus.VERIFIED
    assert control_verdict is CapabilityStatus.UNVERIFIED


# --- single_agent ------------------------------------------------------------------


def test_single_agent_reproduces_verified_from_excluded_task_tool() -> None:
    events = _events("excluded-task-tool.events.jsonl")
    answer = next(
        event["data"]["content"] for event in events if event.get("type") == "assistant.message"
    )

    assert topology.subagent_lifecycle_events(events) == []
    assert answer == "NO_TASK_TOOL"


# --- fresh_session / durable_artifact_handoff ---------------------------------------


def test_fresh_session_reproduces_verified_from_the_handoff_pair() -> None:
    plan_writer = _events("plan-writer.events.jsonl")
    handoff = _events("fresh-session-handoff.events.jsonl")
    plan_writer_result = next(event for event in plan_writer if event.get("type") == "result")
    handoff_result = next(event for event in handoff if event.get("type") == "result")
    answer = _final_answer(handoff)

    assert plan_writer_result["sessionId"] != handoff_result["sessionId"]
    assert "memory=NONE" in answer


def test_durable_artifact_handoff_reproduces_verified_from_the_handoff_pair() -> None:
    plan_writer = _events("plan-writer.events.jsonl")
    creation = next(
        tool_request
        for event in plan_writer
        if event.get("type") == "assistant.message"
        for tool_request in event["data"].get("toolRequests", [])
        if tool_request.get("name") == "create"
    )
    handoff_answer = _final_answer(_events("fresh-session-handoff.events.jsonl"))

    assert creation["arguments"]["file_text"] == "TOKEN: PLAN-4417"
    assert "plan=PLAN-4417" in handoff_answer


# --- sol_ultra (UNSUPPORTED) -------------------------------------------------------


def test_sol_ultra_reproduces_unsupported_from_the_cli_rejection() -> None:
    stderr = (LEGACY_FIXTURES / "reasoning-effort-ultra.stderr.txt").read_text(encoding="utf-8")

    assert "invalid value 'ultra'" in stderr
    record = _copilot_record()
    assert record.capabilities["sol_ultra"].status is CapabilityStatus.UNSUPPORTED


# --- Arm eligibility: no #5422 arm matches without a shared Sol model ------------


def test_build_report_matches_no_arm_between_codex_and_copilot() -> None:
    records = capability.load_matrix(MATRIX)
    report = capability.build_report(records)

    matched = {
        row["arm"]: eligibility
        for row in report["arm_eligibility"]
        for harness, eligibility in row["eligibility"].items()
        if eligibility == capability.ArmEligibility.ELIGIBLE_MATCHED.value
    }

    assert matched == {}, (
        f"copilot has no Sol/Luna/Terra model; no arm should read as matched: {matched}"
    )


# --- Checked-in versions match what probe_version would actually return --------


def test_checked_in_versions_are_the_first_line_probe_version_would_return(tmp_path) -> None:
    """`probe_version` returns the first non-empty line; the matrix's `version`

    field must be exactly that, not the whole multi-line output copilot
    prints (`"GitHub Copilot CLI 1.0.89-1.\\nRun 'copilot update' to check
    for updates.\\n"`).
    """

    def fake_runner(argv, **_kwargs):
        args = [str(value) for value in argv]
        text = (
            "GitHub Copilot CLI 1.0.89-1.\nRun 'copilot update' to check for updates.\n"
            if args[0] == "copilot"
            else "codex-cli 0.156.0\n"
        )
        return subprocess.CompletedProcess(args, 0, text, "")

    codex_version = runtime_harness.probe_version(
        "codex", "codex", tmp_path / "codex", fake_runner, 5.0
    )
    copilot_version = runtime_harness.probe_version(
        "copilot", "copilot", tmp_path / "copilot", fake_runner, 5.0
    )

    codex_record = next(
        record for record in capability.load_matrix(MATRIX) if record.harness == "codex"
    )
    assert codex_version == codex_record.version == "codex-cli 0.156.0"
    assert copilot_version == _copilot_record().version == "GitHub Copilot CLI 1.0.89-1."


# --- Closing assertion: nothing VERIFIED escapes a derivation --------------------


_REPRODUCED_COPILOT_VERIFIED_KEYS = frozenset(
    {
        "model_override",
        "subagent_support",
        "parent_child_override",
        "reviewer_isolation",
        "single_agent",
        "fresh_session",
        "durable_artifact_handoff",
    }
)


def test_every_verified_copilot_capability_is_reproduced_here() -> None:
    record = _copilot_record()
    matrix_verified = {
        key for key, cap in record.capabilities.items() if cap.status is CapabilityStatus.VERIFIED
    }

    assert matrix_verified == _REPRODUCED_COPILOT_VERIFIED_KEYS
