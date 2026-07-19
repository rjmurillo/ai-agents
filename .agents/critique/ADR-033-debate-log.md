# ADR-033 Amendment Debate Log: Gates 2/3/4 Hook Retirement

Date: 2026-07-19
Refs: #3194, #3246, #3248
Protocol: six-agent adr-review (architect, critic, independent-thinker, security, analyst, high-level-advisor)
Subject: Amendment recording the already-shipped retirement of `invoke_routing_gates.py` (Gates 2 QA, 3 Critic, 4 ADR Existence), deleted in PR #3246.

## Verdicts

| Reviewer | Verdict | Summary |
|----------|---------|---------|
| architect | ACCEPT | Recording an already-shipped retirement keeps the ADR coherent. Keeping status Accepted (not Superseded) is correct because Gate 1 and the Retrospective gate remain under this ADR's authority. |
| critic | ACCEPT | All key claims independently verifiable from the tree: file deleted, skill-first guard covers the same raw commands, no orphaned references to the Python path. Flagged that the Gate Types table did not visually mark Gates 2/3/4 as retired. |
| independent-thinker | DISAGREE-AND-COMMIT | Retirement reasoning is sound. Flagged that the original "advisory intent re-homed to .githooks" wording overstated reality: pre-push has only a non-blocking ADR reminder, no QA-validation or critic-review gate. |
| security | ACCEPT | Honest disclosure that Gates 2/3/4 no longer block at PreToolUse. The most security-relevant intent (ADR existence) is still enforced by the separate adr-review guard (fail-closed). QA and critic were process-quality, not security, controls. No posture degradation. |
| analyst | ACCEPT | Verified all six material claims at file-read level, including that no live code path references `invoke_routing_gates` (only historical docs and session logs). |
| high-level-advisor | ACCEPT | Correct level of ceremony. A maintainer grepping `invoke_routing_gates` lands here and understands why Gates 2/3/4 are gone. Ship it. |

Consensus: 5 ACCEPT, 1 DISAGREE-AND-COMMIT, 0 BLOCK. Proceed.

## Concerns raised and resolved before commit

1. Gate Types table not marked retired (critic). RESOLVED: the Enforcement column for QA Validation, Critic Review, and ADR Existence now reads "Retired 2026-07-19 (see Amendment)" instead of "JSON deny", so a reader who skips the amendment is not misled.
2. "Where the advisory intent went" overstated .githooks enforcement (independent-thinker). RESOLVED: rewrote the section to state plainly that the retired hook enforced nothing, that ADR review is covered by the adr-review guard (blocking) plus a non-blocking pre-push reminder plus CI spec validation, and that QA and critic checks are left advisory to CI and code review by design rather than claimed as active .githooks gates.

## Ground-truth verification (this session)

- `.claude/hooks/invoke_routing_gates.py` absent on main; deleted by #3246.
- `invoke_skill_first_guard.py` maps `pr create` to `new_pr.py` and `pr merge` to `merge_pr.py` (lines 79 to 99), so it denies the raw commands the retired matcher needed.
- Surviving guards confirmed present: `invoke_session_log_guard.py`, `invoke_retrospective_gate.py` (docstring: "Block git push without retrospective evidence per ADR-033"), `invoke_adr_review_guard.py`.
- No live code reference to `invoke_routing_gates` remains; only historical docs, session logs, and episode memory.
