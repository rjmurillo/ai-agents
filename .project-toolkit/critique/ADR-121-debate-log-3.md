# ADR Debate Log: ADR-121 One Resolver Launches Every Shipped Plugin-Root Shell Command (debate 3)

## Summary

- **Rounds**: 2 of 10
- **Prior debate logs**: `.project-toolkit/critique/ADR-121-debate-log.md` and `.project-toolkit/critique/ADR-121-debate-log-2.md`
- **Outcome**: Consensus, with P2 findings applied
- **Final Status**: proposed
- **Panel**: a reduced panel of two seats, architect and critic. The edit records rollout state and fixes one printed pattern. It changes no decision, no executable enforcement, and no rule that another gate reads.
- **Trigger**: rollout steps 4 and 5 merged in part (PRs #7337 to #7342). The ADR needed a status section and a corrected assignment-site pattern.

## Round 1 Summary

### Key Issues Addressed

- The first draft flipped `status` to `accepted`. The critic ran `check_adr_lifecycle.py` and found that `cited-paths-exist` went from 57 to 60 once the record was `accepted`. The record stays `proposed`.
- The draft named a fixture F6 and a figure of 120,423 bytes for `autoplan`. The critic measured: `autoplan` is fixture F4, F6 is `code-review`, and the figure has no source in the repo. The claim was deleted.
- The draft said three skillforge validators import `yaml`. The architect found two do. The architect and critic also found that the `tiktoken` and `yaml` imports are guarded, so the draft's reason was inference. The author rewrote each site by hand and ran the validator. It rejects `resolve_route.py`, `count_memory_tokens.py`, `quick_validate.py`, and `package_skill.py` under its rule 2 (issue #5949).
- Steps 4, 5, and 6 read as complete. They are now marked partial.
- The `repository-completion-proof` row named the wrong blocker. It now names the two `GITHUB_SCRIPTS` assignments and the validator's rule 1 (`uv run python`).
- The Claude Code version string and the owner-approval sentence had no repo source. Both were removed.

### Major Changes Made

- Frontmatter unchanged. `status` stays `proposed` and `implemented` stays `false`.
- The assignment-site paragraph prints the validator's pattern. Both patterns give 97 at 48b4ea4c2.
- New section "Status at 2026-11-12" with a step table and a seven-skill table.

## Round 2 Summary

### Key Issues Addressed

- The lead sentence said steps 1 to 5 had merged while the table said partial. It now says steps 1 to 3 merged and steps 4 and 5 are partial.
- The section now says why `implemented` stays `false`.
- The section says which rows were reproduced by a hand rewrite and which were read from rule text or facts about the commands. "Rule 1" and "rule 2" name the validator.
- The `package_skill.py` reason now says it imports `yaml` through `quick_validate`.
- The `date` field was restored to 2026-11-11, the decision date.

### Agent Positions

| Agent | Round 1 | Round 2 | Notes |
|-------|---------|---------|-------|
| architect | Accept with changes | Accept with changes (P2 only) | Asked for this debate log, the lead-sentence fix, and the `package_skill.py` wording. All applied. |
| critic | Accept with changes (P0 on the status flip) | Accept with changes (P2 only) | Reproduced the rule 2 claims. Asked to scope the "checked by hand" claim, name the validator, and keep the date. All applied. |

### Next Steps

Merge the status section as `proposed`. The owner decides the seven skills in issue #7281.

## Debate State

**Round**: 2 of 10 (counted within this debate log)
**Status**: Consensus

Unresolved P0 issues: none.
