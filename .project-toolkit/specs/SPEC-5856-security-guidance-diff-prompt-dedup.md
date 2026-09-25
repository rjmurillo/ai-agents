# SPEC: Security-Guidance Diff Prompt Deduplication Investigation

**Issue**: [#5856](https://github.com/rjmurillo/ai-agents/issues/5856)
**Status**: Accepted for investigation
**Created**: 2026-09-24
**Plugin under test**: `security-guidance@claude-plugins-official` 2.0.8, marketplace commit `55b58ec6e5649104f926ba7558b567dc8d33c5ff`

## Problem

Local recurring-context reports flag large repeated blocks in session transcripts.
The issue maps most of them to security-guidance review prompts.
Each review prompt inlines a capped unified diff.
The question is whether an exact artifact reference can replace that inline diff.
Any replacement must keep review correctness, provenance, and fail-safe behavior.

## First principles

1. The reviewer model must see every `+` and `-` line it reviews.
   A reference only moves bytes from the prompt to a tool result.
   It saves tokens only when the reviewer skips reading the artifact.
2. A reference adds a resolution step.
   That step can fail, go stale, or resolve the wrong content.
   Each failure mode needs a verified inline fallback.
3. The cheapest repeat is the one that never runs.
   Identical diffs reviewed twice cost two reviews, not two prompts.

## Requirements

| ID | Requirement | Verification |
|----|-------------|--------------|
| REQ-1 | Map every prompt producer, repeat path, retry, and session boundary with file and line references. | Report call graph section |
| REQ-2 | Record plugin version, marketplace commit, and SHA-256 of each traced source file. | Report provenance section |
| REQ-3 | Audit local child-review transcripts without copying code content. Output hashes, sizes, paths, cap state, and usage only. | `sg_prompt_audit.py` tests, no-leak test |
| REQ-4 | Model a content-addressed artifact reference with identity, retention, access, and mismatch rules. | `sg_diff_reference.py` tests |
| REQ-5 | Missing, unreadable, stale, cross-repository, and tampered references fall back to the exact inline prompt. | Negative tests assert byte equality with the inline prompt |
| REQ-6 | Referenced and inline reviews expose identical `+` and `-` line multisets per file. | Semantics equivalence tests |
| REQ-7 | The authoritative-diff warning stays intact when the checkout differs. | Checkout mismatch fixture test |
| REQ-8 | Measure prompt bytes, tokens, latency, failures, and findings for inline and referenced reviews on fixtures. | `sg_reference_ab.py` live run, results in report |
| REQ-9 | Name the canonical owner and record adopt, defer, or reject. Any implementation is a separate follow-up in that owner. | Report decision section |

## Non-goals

- No edit to the installed plugin.
- No hook, skill, or runtime wiring of the reference model.
- No change to security heuristics or review failure handling.
- No overlap with #5851 raw tool-output containment.

## Plan

| Task | Output | Depends on |
|------|--------|------------|
| T1 | `scripts/metrics/sg_prompt_audit.py` plus tests and synthetic transcript fixtures | none |
| T2 | `scripts/metrics/sg_diff_reference.py` plus tests for REQ-4 to REQ-7 | none |
| T3 | `scripts/metrics/sg_reference_ab.py` plus mocked tests | T2 |
| T4 | Run T1 on local transcripts and T3 against the Anthropic API | T1, T3 |
| T5 | Report at `.project-toolkit/analysis/security-guidance-diff-prompt-dedup-5856.md` | T4 |

### Risks

| Risk | Mitigation |
|------|------------|
| Audit output leaks proprietary code | Emit hashes, sizes, and paths only. A test asserts no fixture content appears in output. |
| Live A/B differs from the plugin harness | Reuse the plugin system prompt and schema verbatim. Record the gap in the report. |
| Model nondeterminism hides equivalence | Run each fixture and mode several times and compare finding sets per run. |
