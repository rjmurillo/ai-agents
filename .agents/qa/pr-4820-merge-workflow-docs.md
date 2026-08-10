---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10026-merge-workflow-docs.json
qaCommit: dac8dfa0f57d2953793ec7601fba7c6cbf0149a6
---
# Test Report: Serial Auto-Merge Protocol

## Scope

Documentation-only change for issue #4820:

- `.agents/SESSION-PROTOCOL.md`
- `.agents/governance/GOTCHAS.md`
- `.agents/critique/SESSION-PROTOCOL-merge-workflow-debate-log.md`

## Live evidence

| Claim | Verified result |
|-------|-----------------|
| Strict branch freshness | Ruleset 11104075 returned `strict: false` |
| No merge queue | Ruleset 11104075 returned zero `merge_queue` rules |
| Single armed PR | PR #4792 was the only open PR with auto-merge enabled |
| Parallel update cost | 41 branches triggered 820 queued/in-progress runs |
| Rollback | 41 auto-merge requests disabled; 818 runs cancelled |
| Trunk removed | PR #4814 and issues #4815/#4818 closed; remote branches deleted |

## Procedure under test

The protocol requires one front PR at a time:

1. Disable every other auto-merge request and verify zero remain.
2. Record main SHA.
3. Update only the front PR and run one CI matrix.
4. Recheck main SHA before enabling squash auto-merge.
5. Wait until `MERGED`.
6. Inspect push workflows on the new main commit before advancing.

The protocol states that strict-off leaves a TOCTOU window between the final
SHA check and GitHub's merge. It accepts that residual risk to avoid the
measured O(N²) cost, prohibits concurrent landing sessions, and limits blast
radius to one merge by halting after any red main push.

## Review

The decision changed materially during review, so the six-role panel re-ran on
the final strict-off serial design. Final votes:

| Reviewer | Vote |
|----------|------|
| Architect | ACCEPT |
| Critic | ACCEPT |
| Independent Thinker | ACCEPT |
| Security | ACCEPT |
| Analyst | ACCEPT |
| High-Level Advisor | ACCEPT |

No P0 or P1 findings remain. The debate log records the TOCTOU, one-front
enforcement, 422 recovery, cost-model, and main-health findings and fixes.

## Documentation checks

- live ruleset and PR state read through GitHub API
- commands are copy-pasteable and use repository-derived variables
- `git diff --check`: passed
- prohibited dash scan: zero
- session JSON and QA binding: passed
- `pre_pr.py`: passed after final marker update

## Verdict

PASS. The documentation matches the chosen non-strict serial workflow, states
the residual race honestly, and encodes the controls needed to prevent another
parallel CI explosion.
