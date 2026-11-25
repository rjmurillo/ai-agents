# ADR Debate Log: amendments for the deleted agent-* environment workflows

## Summary

- **Rounds**: 3 of 10
- **Outcome**: Consensus after round 3 changes. Both seats returned ACCEPT-WITH-CHANGES and the changes were applied.
- **Final Status**: unchanged for every ADR. ADR-057, ADR-059, and ADR-101 stay accepted.
- **Scope**: ADR-057 (dated amendment and past tense for the `/spec` CI leg), ADR-101 (secret-reachability and `statuses: write` history, folded into the existing 2026-10-11 amendment), ADR-059 (one re-anchored citation).
- **Panel**: reduced panel, architect and critic.
- **Why reduced**: the edits are history and citation fallout. No decision text changes. No executable enforcement and no rule that other gates read changes.
- **Owner decision, 2026-11-25**: approved the amendment route, the reduced panel, past tense, sentence-case starts, and dated amendments. No ratchet baseline may rise.
- **Base**: `e74b842786`, deletion commit `3f145f26fd`. The ADR edits and this log are in commit `2fff4607a4`.

On 2026-11-25 the owner deleted every GitHub Actions job gated by an `agent-*` environment. Eleven workflows were deleted and two lost their agent-gated jobs. ADR-057 and ADR-101 cited the deleted files by path, which raised the `cited-paths-exist` ratchet from 57 to 59. ADR-059 cited a config range that moved. The size-cap ratchet holds ADR-101 at 500 lines, so its amendment adds no lines.

## Gates before the panel

- **Claims ledgers**: `ADR-057-claims-ledger.md`, `ADR-101-claims-ledger.md`, `ADR-059-claims-ledger.md` in this directory. Every row ran against the working tree. One row is NOT RUN: the owner statement about the latest 100 deployments, which the amendments attribute to the owner.
- **Documentation accuracy**: `doc_accuracy.py` phases 1 to 3 on an isolated copy of the three ADRs and two mapped sources: 13 claims, 0 findings, gate PASS. A whole-repository run was UNAVAILABLE: it timed out at 550 seconds in phase 1. Phase 4 ran as one Sonnet agent over all three files, not one per file group. It returned PASS on 9 of 9 claims.
- **Self-consistency**: VERIFIED. The amendment's blanket sentence covers the present-tense lines the panel named in ADR-057, and the panel's tense edits were applied to them as well.
- **Refuting seat**: one haiku analyst agent, told to refute only the ledgers. Result: `FACTUAL FINDINGS: none`. It could not re-run the three `git` rows because its tools have no git access. The author re-ran those rows and they hold.
- **Phase 4 extra findings**: ADR-101 line 265 count claims, a stale comment in `.github/scripts/measure_workflow_coalescing.py`, and the `adr101-publisher.yml` app-token `checks: write`. All three were applied.

## Round 1

Reviewed a citation-only first patch (backticked path replaced by "the deleted X workflow"). Critic verdict: REVISE. Architect verdict: ACCEPT-WITH-CHANGES.

### Accepted

- Lowercase sentence starts in ADR-101 lines 272 and 274.
- Present tense for deleted files in ADR-057 lines 92, 239, 267, 300.
- ADR-057 needed a dated amendment: the `/spec` CI leg is gone and nothing runs the eval in CI.
- ADR-101 claimed `ai-spec-validation.yml` holds `COPILOT_GITHUB_TOKEN`. The file reads no secret.
- ADR-101 cited the deleted claude workflow as the `statuses: write` holder. No workflow grants it now.
- The "verified at HEAD" comment in ADR-101 line 274 was false for a deleted file.

## Round 2

Reviewed the amended ADRs, the amendments, and the ledgers. Critic verdict: REVISE. Architect verdict: ACCEPT-WITH-CHANGES.

### Accepted

- ADR-101:276 called `ai-spec-validation.yml` the live `BOT_PAT` case "today". It reads no secret and `BOT_PAT` appears nowhere under `.github`. Now past tense with a pointer to the amendment.
- The ADR-101 amendment omitted `BOT_PAT`. It now says `BOT_PAT` is not referenced and that the older counts describe the tree when written.
- ADR-057 lines 135, 137, 218, 257, 269, 281, and 282 moved to past tense. Line 269 said "already ships".
- The ledger row that cited "150 passed" could not show the FAIL-on-regression claim. It now runs `test_regression_fails_gate`.
- "Approval was never given" and "the environments remain" were stated as fact. Both are now attributed to the owner.

## Round 3

Reviewed the Round 2 response. Critic verdict: ACCEPT-WITH-CHANGES. Architect verdict: ACCEPT-WITH-CHANGES.

### Accepted

- ADR-101:265 "One workflow grants `statuses: write`" now reads as history with a pointer to the amendment.
- ADR-101:284 named `post-pr-retrospective.yml` in backticks. It now names the workflow in prose with the deletion date.
- ADR-057:308 said the `/spec` leg "stays advisory". Now past tense with the deletion date.
- The ADR-101 amendment now says it records what workflows reference, not whether repository-level secrets still exist. This answers the critic's point that reading is not reachability.
- The `BOT_PAT` uses described for the dependabot workflow and P0, at ADR-101 lines 108, 110, 130, and 418, are named in the amendment as the tree when written. The dependabot workflow reads `GITHUB_TOKEN` now, and that was already true before this change.
- Ledger headers now cite head `7cfb378901` and deletion commit `3f145f26fd`. The deletion rows use `git show` on that commit instead of a moving remote ref. The "reads no secret" row now also matches `secrets[` and `secrets: inherit`.

### Not changed

- ADR-114 sets the approval and non-blocking policy that created the `agent-*` environments. It is not edited here. Its decisions describe a mechanism that no job uses now. The owner decides whether to amend or supersede it.
- The older `BOT_PAT` sentences in ADR-101 keep their wording. The dated amendment marks them as history. Rewriting them is a separate decision.

## Method note

The round 3 changes were applied after both seats accepted and were not sent to a fourth round. Both seats named only changes that the author could apply as written, and the ratchets (`check_adr_lifecycle.py`, 153 violations, none outside the baseline) pass after them.

## Post-review correction

After round 3, the `/review` skill ran its own axes over the whole branch. Its analyst axis found one overstatement in the ADR-101 amendment: it said no file under `.github` reads `ANTHROPIC_API_KEY`, but the `ai-review` composite action takes it as an input and `generate_spec_report.py` names it in message text. No workflow passes the secret. The author reworded the amendment to say that, without adding lines. The panel did not review this one-clause correction. The `check_adr_lifecycle.py` ratchet passes with no baseline change.
