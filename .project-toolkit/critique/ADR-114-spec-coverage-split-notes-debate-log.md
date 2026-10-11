# ADR Debate Log: ADR-114 Note After the Spec Coverage Split

## Summary

- **Rounds**: 1
- **Panel**: reduced (architect and critic). The change is one dated note and touches no executable enforcement.
- **Outcome**: Consensus after revision
- **Final Status**: ADR-114 stays `proposed`. It gains one dated amendment. No decision text changes.

## Context

Issue #6182 asked for a deterministic `Validate Spec Coverage` check. The owner made three choices. The model review moves to its own workflow behind an approval environment (D1). A linked spec with no acceptance checkbox section fails (D2). The deterministic workflow stays on `advisory_agent_workflows` (D3).

ADR-114 names `ai-spec-validation.yml` as a model caller gated by `agent-claude`. After the change, `ai-spec-review.yml` is that caller. PR #6274 set the form: dated notes, not rewritten decisions.

The owner set aside the alternatives before this panel sat. One was keeping the model call with a fallback when a credential fails. Another was deleting the model review from CI. The panel reviewed the note, not that choice.

The first draft was one paragraph. Both seats read it before the workflow files existed in the worktree, so they judged it against the spec.

## Agent Positions

| Agent | Position | Key findings |
|-------|----------|--------------|
| architect | accept with changes | State why a deterministic FAIL stays non-blocking. Say the list holds six entries, one ungated. Name job `review-spec`. Say the workflow counts are unchanged. Cover Decision 9. Cite #6182 and SPEC-6182. |
| critic | accept with changes | The Decision 2 row, the Decision 5 count, the Decision 9 reason, the Decision 11 `BOT_PAT` reader list, and the Decision 8 rationale all go stale. Rollback needs a step. Say `review-spec` can still fail on approval or outage. |

## Resolutions

- **Decision 2 row and job name**: the note maps the row to `ai-spec-review.yml`, job `review-spec`.
- **Counts**: the note says the Context and Decision 2 counts are unchanged, and why.
- **Decision 5**: the note says six entries, five gated, one listed without a gate by owner decision D3.
- **Decision 8**: the note says a deterministic FAIL stays non-blocking by owner decision D3. It says `review-spec` can fail on approval, timeout, or outage, and that its listing covers those.
- **Decision 9**: the note says `merge_group` stays out of both workflows. Queue use of the deterministic check is out of scope.
- **Decision 11 `BOT_PAT`**: the note says `validate-spec` reads no secret.
- **Rollback**: the note adds a revert step.
- **Line 150 doc table (critic)**: deferred with reason. That table lists the docs the original change edited. It is history, and the amendment covers the current facts.
- **PR number (architect)**: deferred with reason. The pull request does not exist when the note is written. The pull request body links the note.

## Post-implementation check

A later `/review` decision-rigor seat checked the tree at commit c4ccde79b, and again at cc2a4487d. `review-spec` exists behind `agent-claude`. `validate-spec` declares no environment. Both workflows are listed. That review also found the `debounce` job still on `bot-secrets`. The change removed that environment, and the note says so.

## Decision

Both seats accepted with changes. Every finding is resolved or deferred above. The amendment records facts that changed after the decision. It does not change the decision.
