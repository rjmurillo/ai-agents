# ADR Debate Log: ADR-101 Enforcement Planes, Requirement 2 Split (Amendment D23)

## Summary
- **Rounds**: 2
- **Outcome**: Consensus
- **Final Status**: accepted (amendment to ADR-101, owner decision D23, 2026-10-01)

Method note: the six seats were written as six independent positions by one reviewing agent in one thread, not as six spawned agents. The cap of three subagents made a six-process panel unavailable. Treat the positions as one reviewer's adversarial passes, and treat the owner's own review as the external check.

Scope: the amendment diff to `.project-toolkit/architecture/ADR-101-enforcement-planes.md` plus contradictions it leaves elsewhere in that file.

## Round 1 Summary

### Evidence checked first-hand
- `gh api repos/rjmurillo/ai-agents/environments` returns three environments (`bot-secrets`, `copilot`, `vendor-provenance`), each with `deployment_branch_policy` null. Confirmed.
- `gh api repos/rjmurillo/ai-agents/rulesets/11104075` returns nine required contexts, all `integration_id` 15368. Confirmed.
- `git grep -E '^\s+environment:' -- .github/workflows` returns 18 stanzas. 16 name `bot-secrets`, one `vendor-provenance`, one `npm` (`publish.yml:81`). The draft's count was right but hid that `npm` is not a listed environment.
- `git grep workflow_run: -- .github` returns nothing. Confirmed.
- `.github/workflows/enforcement-closure.yml:28` uses `pull_request_target`. Confirmed.
- `scripts/ci/adr101_publisher.py` does not exist in this tree. The draft's "covered by" outran the evidence.
- PR #6103 is MERGED. The spike file and the serena memory both exist.

### Key Issues Addressed
- Line 217 still said "Independently signed execution evidence remains the third option." That contradicts the withdrawal.
- Line 191 said only the first half "is closable by a signer". (2a) is closed by an identity pin, not a signer.
- Lines 33, 193 and 438 said the App "closes" or "covers" (2a) with no code and no pin in existence.
- Line 437 put the publisher pin in Phase 0 and line 438 put (2a) in Phase 1, with no statement of how they fit.
- Line 193 left a gap: a pinned context made required while (2b) is open reads as a verified verdict. The execute conclusion is a candidate-authored integer (line 229).
- Line 102 hid that `npm` is absent from the environments API.

### Major Changes Made
- Line 217: replaced "third option" with a statement that signing authenticates the signer and not the result.
- Line 191: "closable by a signer" became "closable by an identity pin".
- Lines 33, 193, 438: "closes/covered" became "designed to close", "Not yet built", "a design and no code".
- Line 193: added that (2a) supplies conjuncts two and three, conjunct one stays open under (2b), the pinned context is added beside existing required contexts and replaces none, and no check name or summary says "verified".
- Line 438: added "Phase 0 carries the ruleset pin and Phase 1 builds the publisher."
- Line 102: split the 18 stanzas into 16, 1 and 1, and named `npm` as unlisted.

### Agent Positions
| Agent | Position |
|-------|----------|
| architect | Block. Line 217 contradicts the split and Phase 0 versus Phase 1 placement is ambiguous at lines 437 and 438. |
| critic | Block. "Covered" and "closes" claim a build that does not exist (`scripts/ci/adr101_publisher.py` absent). Line 102 count hides `npm`. |
| independent-thinker | Disagree. Line 191 "closable by a signer" is the wrong frame for (2a). Challenged whether (2b) deserves any design sketch before measurement. Kept it, since it is labeled unvalidated with an exit condition. |
| security | Block. A pinned required context with an open (2b) lets a green read as verified, and the draft does not forbid the label or substitution for existing contexts. |
| analyst | Accept with fixes. All four first-hand facts hold. Flagged the `npm` omission and the missing-build overclaim. |
| high-level-advisor | Accept with fixes. Scope is right: split, withdraw, correct, no new phase. Do not widen into designing (2b). |

## Round 2 Summary

### Key Issues Addressed
- Re-read lines 33, 102, 191 to 195, 217, 223, 227, 438 after the edits. Grep for `only option`, `third option`, `Phase 1 therefore` returns only the quoted withdrawn phrases at lines 33, 217 and 223, each marked as withdrawn.
- Em and en dash grep over the ADR returns nothing. No banned word in the added text. ADR length is 489 lines, under 500.
- Remaining residual, not an objection: lines 229 and 233 to 243 still use "attestation" for requirement 2's digest, which is the (2a) evidence digest and is consistent with the split.

### Agent Positions
| Agent | Position |
|-------|----------|
| architect | Accept. Phase 0 pin and Phase 1 build are now stated together. |
| critic | Accept. Claims now match the tree: design, no code. |
| independent-thinker | Disagree and Commit. Still thinks the (2b) sketch is premature. It is labeled unvalidated and gated by an exit condition, so it does no harm. |
| security | Accept. The "verified" label ban and the beside-not-instead rule close the objection. |
| analyst | Accept. Evidence matches live reads. |
| high-level-advisor | Accept. Terminal. No further scope. |

### Next Steps
Owner creates the App, the `adr101-publisher` environment with a `main` branch policy, the secret and variables, then writes the ruleset pin. Issue #5245 tracks (2b) as research.
