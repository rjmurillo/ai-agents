"""Codex live-evidence re-derivation (issue #5423 reopen).

The checked-in matrix (`MATRIX`) is a claim: codex-cli 0.156.0, probed live
on 2026-09-24, produced these capability statuses. This file is the check on
that claim. For every codex capability the matrix marks `VERIFIED`, it loads
the exact fixture the matrix's `detail` field cites and re-derives the same
verdict from it using only the in-tree parsers (`_codex_frames`,
`_capability_evidence`, `_harness_capability.classify_override`/
`classify_reviewer_isolation`), independent of `_capability_probes`'s
pipeline plumbing. `test_every_verified_codex_capability_is_reproduced_here`
is the closing assertion: the set of codex keys this file can re-derive as
VERIFIED must equal exactly the set the matrix marks VERIFIED, so a future
VERIFIED cell added without a derivation here fails loudly instead of
shipping unchecked.

Copilot's live-evidence re-derivation is
`test_harness_capability_live_evidence_copilot.py`, split out to stay under
this repository's 500-line file-size ceiling.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tests.eval._harness_capability_test_support import (
    FIXTURES,
    MATRIX,
    capability,
    codex_frames,
    evidence,
)

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind

CODEX_FIXTURES = FIXTURES / "codex-0.156.0"


def _frames(name: str):
    return codex_frames.parse_codex_frames((CODEX_FIXTURES / name).read_text(encoding="utf-8"))


def _codex_record():
    return next(record for record in capability.load_matrix(MATRIX) if record.harness == "codex")


# --- model_override / parent_child_override / effort_override ------------------
#
# All three cells cite the same evidence and the same underlying fact: in one
# `subagent-luna-high.trace.log` run, the parent's `response.created` frames
# report gpt-5.6-sol/medium throughout, and every `spawn_agent`-launched
# child's frames report gpt-6-luna/high instead.


def test_subagent_luna_high_parent_and_child_spans_disagree_on_model_and_effort() -> None:
    spans = codex_frames.response_spans(_frames("subagent-luna-high.trace.log"))
    parent_models = {span.model for span in spans if span.model == "gpt-5.6-sol"}
    child_models = {span.model for span in spans if span.model == "gpt-6-luna"}
    child_efforts = {span.effort for span in spans if span.model == "gpt-6-luna"}

    assert parent_models == {"gpt-5.6-sol"}
    assert child_models == {"gpt-6-luna"}
    assert child_efforts == {"high"}


def test_model_override_reproduces_verified_from_subagent_luna_high() -> None:
    frames = _frames("subagent-luna-high.trace.log")

    observed = evidence.observe_codex_model(frames, parent_value="gpt-5.6-sol")
    status = capability.classify_override(
        "gpt-6-luna", observed.observed, observed.evidence, parent_value="gpt-5.6-sol"
    )

    assert observed.evidence is EvidenceKind.BACKEND
    assert status is CapabilityStatus.VERIFIED


def test_effort_override_reproduces_verified_from_subagent_luna_high() -> None:
    frames = _frames("subagent-luna-high.trace.log")

    observed = evidence.observe_codex_effort(frames, parent_value="medium")
    status = capability.classify_override(
        "high", observed.observed, observed.evidence, parent_value="medium"
    )

    assert observed.evidence is EvidenceKind.BACKEND
    assert status is CapabilityStatus.VERIFIED


def test_parent_child_override_reproduces_verified_from_subagent_luna_high() -> None:
    """`parent_child_override` is the same fact as the two cells above,
    read from the same fixture: parent and child settings differ at the
    backend rather than the child inheriting either one.
    """
    frames = _frames("subagent-luna-high.trace.log")

    model = evidence.observe_codex_model(frames, parent_value="gpt-5.6-sol")
    effort = evidence.observe_codex_effort(frames, parent_value="medium")

    assert model.evidence is EvidenceKind.BACKEND and model.observed == "gpt-6-luna"
    assert effort.evidence is EvidenceKind.BACKEND and effort.observed == "high"
    assert (model.observed, effort.observed) != ("gpt-5.6-sol", "medium")


# --- subagent_support -------------------------------------------------------------


def test_subagent_support_reproduces_verified_from_subagent_luna_high() -> None:
    frames = _frames("subagent-luna-high.trace.log")
    spans = codex_frames.response_spans(frames)
    completed_models = {span.model for span in spans if span.completed is not None}
    spawn_models = [
        arguments.get("model")
        for name, arguments in codex_frames.function_calls(frames)
        if name == "spawn_agent" and isinstance(arguments.get("model"), str)
    ]

    assert spawn_models and all(model in completed_models for model in spawn_models)


# --- reviewer_isolation ------------------------------------------------------------


def test_reviewer_isolation_reproduces_verified_from_reviewer_isolation_log() -> None:
    """`fork_turns=none` isolates; the `fork_turns=all` positive control leaks.

    `message_texts` returns `['NONE', 'ZEBRA-7731', 'none=NONE
    all=ZEBRA-7731']` in frame order: the `fork_turns=none` reviewer's
    answer, then the `fork_turns=all` control's answer, then the parent's
    own summary.
    """
    frames = _frames("reviewer-isolation.trace.log")
    texts = codex_frames.message_texts(frames)
    none_reviewer_answer, all_control_answer = texts[0], texts[1]

    verdict = capability.classify_reviewer_isolation(
        none_reviewer_answer, ["ZEBRA-7731"], EvidenceKind.BACKEND
    )
    control_verdict = capability.classify_reviewer_isolation(
        all_control_answer, ["ZEBRA-7731"], EvidenceKind.BACKEND
    )

    assert verdict is CapabilityStatus.VERIFIED
    assert control_verdict is CapabilityStatus.UNVERIFIED, (
        "the fork_turns=all positive control must leak for this probe to discriminate at all"
    )


# --- single_agent ------------------------------------------------------------------


def test_single_agent_reproduces_verified_from_fresh_session_handoff() -> None:
    frames = _frames("fresh-session-handoff.trace.log")
    spawn_calls = [name for name, _ in codex_frames.function_calls(frames) if name == "spawn_agent"]

    assert spawn_calls == []


# --- fresh_session -------------------------------------------------------------------


def test_fresh_session_reproduces_verified_from_the_handoff_pair() -> None:
    plan_writer = json.loads(
        (CODEX_FIXTURES / "plan-writer.stdout.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    handoff = json.loads(
        (CODEX_FIXTURES / "fresh-session-handoff.stdout.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    frames = _frames("fresh-session-handoff.trace.log")
    spans = codex_frames.response_spans(frames)
    texts = codex_frames.message_texts(frames)

    assert plan_writer["type"] == "thread.started"
    assert handoff["type"] == "thread.started"
    assert plan_writer["thread_id"] != handoff["thread_id"]
    assert spans[0].previous_response_id is None
    assert "memory=NONE" in texts[-1]


# --- durable_artifact_handoff ----------------------------------------------------------


def test_durable_artifact_handoff_reproduces_verified_from_the_handoff_pair() -> None:
    writer_text = (CODEX_FIXTURES / "plan-writer.stdout.jsonl").read_text(encoding="utf-8")
    plan_writer_events = [json.loads(line) for line in writer_text.splitlines() if line.strip()]

    def _is_file_change_start(event: dict[str, Any]) -> bool:
        item = event.get("item", {})
        return event.get("type") == "item.started" and item.get("type") == "file_change"

    creation_command = next(event for event in plan_writer_events if _is_file_change_start(event))
    # The write itself carries only the path (`kind: "add"`); the writer
    # session's own verification command (`wc -l -c ... && sed -n '1,2p'
    # implementation-plan.md`) is what shows the exact byte content landed,
    # in a later `item.completed` `command_execution` event.
    wrote_the_token = any(
        event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "command_execution"
        and "TOKEN: PLAN-4417" in event["item"].get("aggregated_output", "")
        for event in plan_writer_events
    )
    read_back_text = codex_frames.message_texts(_frames("fresh-session-handoff.trace.log"))[-1]

    assert creation_command["item"]["changes"][0]["kind"] == "add"
    assert wrote_the_token, "the writer session's verification command never shows the TOKEN line"
    assert "plan=PLAN-4417" in read_back_text


# --- sol_ultra -----------------------------------------------------------------------


def test_sol_ultra_backend_effort_is_max_not_the_literal_ultra_request() -> None:
    frames = _frames("sol-6-ultra.trace.log")
    spans = codex_frames.response_spans(frames)

    assert {span.effort for span in spans} == {"max"}
    status = capability.classify_override("ultra", "max", EvidenceKind.BACKEND)
    assert status is CapabilityStatus.UNVERIFIED, (
        "an ultra request reporting back as max must never silently verify as 'ultra honored'"
    )


def test_sol_ultra_catalog_lists_ultra_for_gpt_6_sol_and_not_gpt_6_luna() -> None:
    """`models-catalog.json` is the real codex-cli 0.156.0 catalog: it names

    the exact models `sol-6-ultra.trace.log` requested, `gpt-6-sol` and
    `gpt-6-luna`, directly (`grep -n '"slug"' models-catalog.json` lists
    `gpt-6-sol, gpt-6-astra, gpt-6-luna, gpt-reserve, gpt-5.6-sol,
    gpt-5.6-terra, gpt-5.6-luna, gpt-5.5, codex-auto-review`), so this test
    asserts the matrix's `sol_ultra` claim against those exact slugs.
    """
    catalog = json.loads((CODEX_FIXTURES / "models-catalog.json").read_text(encoding="utf-8"))
    by_slug = {entry["slug"]: entry for entry in catalog["models"]}

    sol_efforts = {level["effort"] for level in by_slug["gpt-6-sol"]["supported_reasoning_levels"]}
    luna_efforts = {
        level["effort"] for level in by_slug["gpt-6-luna"]["supported_reasoning_levels"]
    }
    assert "ultra" in sol_efforts
    assert "ultra" not in luna_efforts


# --- concurrency_limit (UNVERIFIED, not VERIFIED) ---------------------------------


def test_concurrency_limit_peak_overlap_matches_the_checked_in_value() -> None:
    frames = _frames("concurrency-3-requested.trace.log")
    spans = codex_frames.response_spans(frames)

    peak = codex_frames.peak_overlap(spans, model="gpt-6-luna")

    record = _codex_record()
    concurrency = record.capabilities["concurrency_limit"]
    assert peak == concurrency.value == 2
    assert concurrency.status is CapabilityStatus.UNVERIFIED, (
        "3 was requested and only 2 overlapped, so this cell must stay short of VERIFIED"
    )


# --- Closing assertion: nothing VERIFIED escapes a derivation --------------------


#: Every codex capability key this file re-derives as VERIFIED above. Kept
#: as an explicit set, not inferred from test names, so a new test that
#: forgets to actually assert VERIFIED cannot silently widen this set.
_REPRODUCED_CODEX_VERIFIED_KEYS = frozenset(
    {
        "model_override",
        "effort_override",
        "parent_child_override",
        "subagent_support",
        "reviewer_isolation",
        "single_agent",
        "fresh_session",
        "durable_artifact_handoff",
    }
)


def test_every_verified_codex_capability_is_reproduced_here() -> None:
    record = _codex_record()
    matrix_verified = {
        key for key, cap in record.capabilities.items() if cap.status is CapabilityStatus.VERIFIED
    }

    assert matrix_verified == _REPRODUCED_CODEX_VERIFIED_KEYS


#: A fixture path a matrix `detail` field cites as evidence, for example
#: `codex-0.156.0/subagent-luna-high.trace.log` or
#: `copilot-1.0.89-byok-anthropic/child-model-override.wire.log`. `\b` after
#: the extension stops a greedy match from stopping at a shorter alternative
#: that happens to be a prefix of a longer one (`json` inside `jsonl`): `\b`
#: only holds at a word/non-word boundary, and `n`/`l` are both word
#: characters, so the engine is forced to keep matching through the `l`.
_FIXTURE_CITATION = re.compile(
    r"[\w.\-]+/[\w.\-]+\.(?:trace\.log|stdout\.jsonl|events\.jsonl|wire\.log|json|stderr\.txt)\b"
)


def test_checked_in_matrix_verified_cells_cite_real_evidence() -> None:
    """Every VERIFIED cell must carry backend evidence and cite a real fixture.

    Replaces the old all-`UNVERIFIED` pin (issue #5423 reopen): live probes
    against codex-cli 0.156.0 and copilot-cli 1.0.89 on 2026-09-24 produced
    real `VERIFIED` cells, so pinning "nothing is ever verified" would now
    be false. What still must hold is that a `VERIFIED` cell is never a bare
    assertion: it needs `BACKEND` evidence, a `probe_command`, a `date`, and
    a `detail` that names a fixture file this repository actually ships,
    which `tests/eval/test_harness_capability_live_evidence.py` then
    re-derives from that exact fixture.
    """
    for record in capability.load_matrix(MATRIX):
        for key, cap in record.capabilities.items():
            if cap.status is not CapabilityStatus.VERIFIED:
                continue
            assert cap.evidence is EvidenceKind.BACKEND, f"{record.harness}.{key}"
            assert cap.probe_command, f"{record.harness}.{key} has no probe_command"
            assert cap.date, f"{record.harness}.{key} has no date"
            names = _FIXTURE_CITATION.findall(cap.detail)
            assert names, f"{record.harness}.{key} detail names no fixture: {cap.detail!r}"
            for name in names:
                assert (FIXTURES / name).is_file(), (
                    f"{record.harness}.{key} cites missing fixture {name}"
                )
