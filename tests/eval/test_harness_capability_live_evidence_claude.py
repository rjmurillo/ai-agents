"""Claude live-evidence re-derivation (issue #5426).

The checked-in matrix claims that claude 2.1.309, probed live on 2026-10-23 on the operator's
subscription login, produced these capability statuses. For every claude capability the matrix
marks `VERIFIED`, this file loads the fixtures the matrix `detail` cites and re-derives the
verdict from the raw stream events with plain `json`, independent of `_routing_claude`.
`test_every_verified_claude_capability_is_reproduced_here` is the closing assertion: the keys
re-derived here must equal the keys the matrix marks `VERIFIED`.

The generic check that every `VERIFIED` cell cites a fixture that exists is
`test_checked_in_matrix_verified_cells_cite_real_evidence` in the Codex sibling file.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.eval._harness_capability_test_support import FIXTURES, MATRIX, capability

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind
CLAUDE_FIXTURES = FIXTURES / "claude-2.1.309"
OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"
PRIVATE = "ZEBRA-7731"


def _events(name: str) -> list[dict[str, Any]]:
    text = (CLAUDE_FIXTURES / f"{name}.stdout.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _init(name: str) -> dict[str, Any]:
    return next(e for e in _events(name) if e.get("subtype") == "init")


def _last_result(name: str) -> dict[str, Any]:
    return [e for e in _events(name) if e["type"] == "result"][-1]


def _models(name: str, *, child: bool) -> set[str]:
    """Models named on assistant messages, split by whether a parent tool call spawned them."""
    return {
        e["message"]["model"]
        for e in _events(name)
        if e["type"] == "assistant" and bool(e.get("parent_tool_use_id")) is child
    }


def _tool_uses(name: str, tool: str) -> list[dict[str, Any]]:
    blocks = (
        block
        for e in _events(name)
        if e["type"] == "assistant"
        for block in e["message"]["content"]
    )
    return [b for b in blocks if b["type"] == "tool_use" and b["name"] == tool]


def _claude_record() -> Any:
    return next(r for r in capability.load_matrix(MATRIX) if r.harness == "claude")


def _all_fixture_names() -> list[str]:
    return sorted(
        p.name.removesuffix(".stdout.jsonl") for p in CLAUDE_FIXTURES.glob("*.stdout.jsonl")
    )


# --- model_override / parent_child_override --------------------------------------


@pytest.mark.parametrize(
    ("name", "requested"),
    [("plan-writer", OPUS), ("fresh-reader", SONNET), ("effort-low", HAIKU)],
)
def test_a_top_level_run_is_served_the_model_it_requested(name: str, requested: str) -> None:
    assert _models(name, child=False) == {requested}
    verdict = capability.classify_override(requested, requested, EvidenceKind.BACKEND)
    assert verdict is CapabilityStatus.VERIFIED


def test_model_override_reproduces_verified_from_the_child_that_differs_from_the_parent() -> None:
    parent = _models("subagent-haiku-child", child=False)
    child = _models("subagent-haiku-child", child=True)

    assert parent == {OPUS} and child == {HAIKU}
    verdict = capability.classify_override(HAIKU, HAIKU, EvidenceKind.BACKEND, parent_value=OPUS)
    assert verdict is CapabilityStatus.VERIFIED
    assert set(_last_result("subagent-haiku-child")["modelUsage"]) == {OPUS, HAIKU}


def test_an_inherited_child_model_would_not_verify() -> None:
    verdict = capability.classify_override(HAIKU, OPUS, EvidenceKind.BACKEND, parent_value=OPUS)

    assert verdict is CapabilityStatus.UNVERIFIED


# --- subagent_support / single_agent -----------------------------------------------


def test_subagent_support_reproduces_verified_from_the_agent_call_and_child_messages() -> None:
    calls = _tool_uses("subagent-haiku-child", "Agent")
    stats = _last_result("subagent-haiku-child")["subagent_stats"]

    assert [c["input"]["subagent_type"] for c in calls] == ["worker"]
    assert (stats["spawned"], stats["completed"], stats["by_type"]) == (1, 1, {"worker": 1})
    assert "Task" in _init("subagent-haiku-child")["tools"]


@pytest.mark.parametrize("name", ["plan-writer", "fresh-reader"])
def test_single_agent_reproduces_verified_because_the_agent_tool_is_absent(name: str) -> None:
    tools = _init(name)["tools"]

    assert "Task" not in tools and "Agent" not in tools
    assert _last_result(name)["subagent_stats"]["spawned"] == 0
    assert not _tool_uses(name, "Agent")


def test_the_fresh_reader_itself_reported_no_agent_tool() -> None:
    assert "C=NO_AGENT_TOOL" in _last_result("fresh-reader")["result"]


# --- reviewer_isolation -------------------------------------------------------------


def _child_prompts_and_answers(name: str) -> list[tuple[str, str]]:
    """(prompt the parent wrote, answer the child gave), in call order."""
    events = _events(name)
    prompts = [c["input"]["prompt"] for c in _tool_uses(name, "Agent")]
    answers = [
        block["text"]
        for e in events
        if e["type"] == "assistant" and e.get("parent_tool_use_id")
        for block in e["message"]["content"]
        if block["type"] == "text"
    ]
    return list(zip(prompts, answers, strict=True))


def test_reviewer_isolation_reproduces_verified_from_the_none_and_all_pair() -> None:
    (none_prompt, none_answer), (all_prompt, all_answer) = _child_prompts_and_answers(
        "reviewer-isolation"
    )

    assert (none_answer, all_answer) == ("NONE", PRIVATE)
    isolated = capability.classify_reviewer_isolation(none_prompt, [PRIVATE], EvidenceKind.BACKEND)
    leaked = capability.classify_reviewer_isolation(all_prompt, [PRIVATE], EvidenceKind.BACKEND)
    assert isolated is CapabilityStatus.VERIFIED
    assert leaked is CapabilityStatus.UNVERIFIED


# --- fresh_session / durable_artifact_handoff -----------------------------------------


def test_fresh_session_reproduces_verified_from_two_sessions_that_share_no_context() -> None:
    writer_session = _init("plan-writer")["session_id"]
    reader_session = _init("fresh-reader")["session_id"]

    assert writer_session != reader_session
    assert _last_result("fresh-reader")["result"].startswith("A=NONE")


def test_durable_artifact_handoff_reproduces_verified_from_the_write_and_the_read() -> None:
    (write,) = _tool_uses("plan-writer", "Write")
    (read,) = _tool_uses("fresh-reader", "Read")

    assert write["input"]["file_path"].endswith("/implementation-plan.md")
    assert write["input"]["content"] == "TOKEN: PLAN-4417\n"
    assert read["input"]["file_path"] == write["input"]["file_path"]
    assert "B=PLAN-4417" in _last_result("fresh-reader")["result"]


# --- concurrency_limit ------------------------------------------------------------------


def _refusals(name: str) -> list[str]:
    texts: list[str] = []
    for e in _events(name):
        content = e["message"]["content"] if e["type"] == "user" else []
        texts += [
            str(b.get("content", ""))
            for b in content
            if isinstance(b, dict) and b.get("is_error") is True
        ]
    return [t for t in texts if "Concurrent subagent limit reached" in t]


def test_concurrency_limit_reproduces_verified_from_the_refused_spawn() -> None:
    stats = _last_result("concurrency-cap3")["subagent_stats"]
    refusals = _refusals("concurrency-cap3")

    assert stats["refused"]["concurrency_limit"] == 1
    assert len(refusals) == 1 and "You can run 3 subagents at once" in refusals[0]
    assert _claude_record().capabilities["concurrency_limit"].value == 3


def test_without_the_cap_the_same_request_is_not_refused() -> None:
    stats = _last_result("concurrency-uncapped")["subagent_stats"]

    assert stats["spawned"] == 5 and stats["refused"]["concurrency_limit"] == 0
    assert _refusals("concurrency-uncapped") == []


# --- context_reset_observability ------------------------------------------------------------


def test_context_reset_observability_reproduces_verified_from_compact_boundaries() -> None:
    events = _events("compaction")
    boundaries = [e for e in events if e.get("subtype") == "compact_boundary"]
    results = [e["compact_result"] for e in events if e.get("compact_result")]

    assert len(boundaries) == 4 and {b["compact_metadata"]["trigger"] for b in boundaries} == {
        "auto"
    }
    assert results == ["success"] * 4
    assert all(
        b["compact_metadata"]["post_tokens"] < b["compact_metadata"]["pre_tokens"]
        for b in boundaries
    )


def test_a_single_oversized_prompt_does_not_compact() -> None:
    events = _events("compaction-single-prompt")

    assert not [e for e in events if e.get("subtype") == "compact_boundary"]
    assert [e["compact_error"] for e in events if e.get("compact_error")] == ["too_few_groups"]


# --- effort_override stays UNVERIFIED ------------------------------------------------------------


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_no_stream_names_a_reasoning_effort() -> None:
    names = {
        key
        for fixture in _all_fixture_names()
        for event in _events(fixture)
        for key in _keys(event)
        if "effort" in key.lower()
    }

    assert names == {"per_turn_effort_active"}


def test_effort_override_cell_is_unverified_and_labeled_behavioral() -> None:
    cell = _claude_record().capabilities["effort_override"]

    assert cell.status is CapabilityStatus.UNVERIFIED and cell.evidence is EvidenceKind.BEHAVIORAL
    assert capability.classify_override("low", None, EvidenceKind.BACKEND) is (
        CapabilityStatus.UNVERIFIED
    )


def _thinking(name: str) -> int:
    return _last_result(name)["usage"]["output_tokens_details"]["thinking_tokens"]


@pytest.mark.parametrize("model", ["opus", "sonnet", "haiku"])
def test_the_matrix_counts_are_the_thinking_tokens_in_the_fixtures(model: str) -> None:
    recorded = _claude_record().effort_behavioral.thinking_tokens[f"claude-{model}-5-5"]

    assert recorded == {
        level: _thinking(f"effort-{model}-{level}") for level in ("low", "medium", "high")
    }


def test_the_nine_measured_counts_give_opus_verified_and_sonnet_and_haiku_not() -> None:
    record = _claude_record()
    evidence = record.effort_behavioral

    def verdict(model: str) -> Any:
        return capability.classify_behavioral_effort(evidence, record.version, [model])

    assert verdict("claude-opus-5-5") is CapabilityStatus.VERIFIED
    assert verdict("claude-sonnet-5-5") is CapabilityStatus.UNVERIFIED
    assert verdict("claude-haiku-5-5") is CapabilityStatus.UNVERIFIED
    assert evidence.cli_version == record.version


def test_a_lower_effort_used_fewer_thinking_tokens_but_that_is_not_the_served_value() -> None:
    def thinking(name: str) -> int:
        return _last_result(name)["usage"]["output_tokens_details"]["thinking_tokens"]

    assert thinking("effort-low") < thinking("effort-max")


def test_an_unknown_effort_ran_at_the_default_and_exited_clean() -> None:
    assert _last_result("effort-ultra-ignored")["is_error"] is False
    stderr = (CLAUDE_FIXTURES / "effort-ultra-ignored.stderr.txt").read_text(encoding="utf-8")
    assert "Unknown --effort value 'ultra'" in stderr


# --- billing, ambient context, permission mode ---


@pytest.mark.parametrize("name", _all_fixture_names())
def test_every_capture_ran_on_the_subscription_login(name: str) -> None:
    init = _init(name)

    assert init["apiKeySource"] == "none"
    assert init["claude_code_version"] == "2.1.309"


@pytest.mark.parametrize("name", _all_fixture_names())
def test_no_capture_loaded_skills_mcp_servers_or_non_builtin_plugins(name: str) -> None:
    init = _init(name)

    assert init["skills"] == [] and init["mcp_servers"] == [] and init["slash_commands"] == []
    assert all(p["source"].endswith("@builtin") for p in init.get("plugins", []))


def test_restricted_confines_file_tools_but_an_allowed_python_call_escapes() -> None:
    result = _last_result("restricted-writes")

    assert result["result"].startswith("inside=ran outside=denied pyoutside=ran ls=denied")
    assert [d["tool_name"] for d in result["permission_denials"]] == ["Write", "Bash"]


def test_accept_edits_alone_wrote_outside_the_workdir() -> None:
    assert _last_result("acceptedits-outside-write")["result"] == "ran"


def test_the_claude_sandbox_setting_failed_closed_on_the_probe_host() -> None:
    texts = [
        str(block.get("content", ""))
        for e in _events("sandbox-unavailable")
        if e["type"] == "user"
        for block in e["message"]["content"]
    ]

    assert texts and all("nested userns is capability-restricted" in t for t in texts)


# --- closing assertion ---


_REPRODUCED_CLAUDE_VERIFIED_KEYS = frozenset(
    {
        "model_override",
        "parent_child_override",
        "subagent_support",
        "single_agent",
        "reviewer_isolation",
        "fresh_session",
        "durable_artifact_handoff",
        "concurrency_limit",
        "context_reset_observability",
    }
)


def test_every_verified_claude_capability_is_reproduced_here() -> None:
    matrix_verified = {
        key
        for key, cap in _claude_record().capabilities.items()
        if cap.status is CapabilityStatus.VERIFIED
    }

    assert matrix_verified == _REPRODUCED_CLAUDE_VERIFIED_KEYS
