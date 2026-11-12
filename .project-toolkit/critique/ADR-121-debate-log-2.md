# ADR Debate Log: ADR-121 One Resolver Launches Every Shipped Plugin-Root Shell Command (debate 2)

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-121-debate-log.md` (closed at consensus in round 1, no unresolved P0 issues)
- **Outcome**: Consensus
- **Final Status**: proposed
- **Panel**: the same six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), resumed with their round 1 context.
- **Trigger**: two review threads on PR #7326. One asked to align a sentence with the post-vote correction about validator rule 5. One (a Cursor Bugbot finding, Medium) said assignment sites such as `SCRIPTS_DIR=...` evade the locator.

## Round 1 Summary

### Key Issues Addressed

- The Enforcement section still said rules 1, 2, and 5 stop covering migrated sites. Rule 5 is a per-module import-time scan, so migration does not change it. Only rules 1 and 2 depend on the validator reading the target out of the locator.
- Assignment sites. At 48b4ea4c2, 97 lines in `templates` and `src/claude` assign a variable from the nested form. The locator takes the target in one command, so it cannot replace an assignment, and a foreign root still reaches the variable. The first debate's critic had raised variable assignments as a site shape, and the ADR had no rule for them.

### Major Changes Made

- Enforcement bullet corrected as above.
- New Rollout paragraph: step 3 inventories assignment sites by file, step 4 rewrites each follow-on call to the locator and deletes the assignment per skill, `--fix` reports what it cannot rewrite, the legacy allowance holds such files, and a skill counts as migrated only when no line in it assigns from the nested form.
- After the votes: the paragraph prints the counting pattern and says the pattern covers Markdown, YAML, and `.py` lines alike. It says assignment sites in `references/` files wait for step 5. Four seats reproduced 97 only with the stated pattern, and narrower patterns count 84 to 92.

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | Asked to state the pattern and the `references/` timing. Both added. |
| critic | Accept | Reproduced 97 at 48b4ea4c2 with the printed pattern. Asked to state the inventory scope. Added. |
| independent-thinker | Accept | Treats 97 as an upper bound. Earlier `allowed-tools` dissent stays recorded in step 3. |
| security | Accept | The foreign-root consequence holds and is today's loud exit 2, not a new exposure. Asked to print the pattern. Added. |
| analyst | Accept | Reproduced 97 in 50 files. Asked to state the method. Added. |
| high-level-advisor | Accept | Order of work unchanged. Notes the hand-rewrite cost may slow step 4. |

### Next Steps

Merge the ADR as `proposed`. Step 2, the resolver pull request, follows.

## Debate State

**Round**: 1 of 10 (counted within this debate log)
**Status**: Consensus

Unresolved P0 issues: none.
