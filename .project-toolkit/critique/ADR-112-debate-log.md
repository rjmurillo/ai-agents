# ADR Debate Log: ADR-112 Risk-Tiered Action Boundaries for Agent Tools

## Summary

- **Rounds**: 2 (round 2 is the author's response, not a new vote)
- **Outcome**: Concluded Without Consensus
- **Final Status**: proposed; every round 1 finding is addressed or recorded as a gap, pending owner review

**Independence note.** One reviewing agent played all six seats in sequence.
The session had a three-subagent cap, so no seat ran as a separate agent.
The seats are not independent. Treat agreement between them as one voice.

Reviewed: ADR-112 working copy, REQ-043, TASK-052, the `AGENTS.md` guardrail
line, and commits `b97cfd2b0`, `6eddcf919`, `88d6fc524` against issue #5767.

## Round 1 Summary

### Evidence gathered

- `gh api repos/rjmurillo/ai-agents/rules/branches/main --jq '[.[].type]'`
  returned `deletion`, `non_fast_forward`, `pull_request`,
  `required_status_checks`, `required_linear_history`, `copilot_code_review`.
  The ADR table omits `copilot_code_review`.
- 31 files in `.claude/agents/`. Four carry `tools:` after this change
  (analyst, code-reviewer, comment-analyzer, security). 27 inherit every tool.
  The ADR counts (29 of 31 before, 27 in G1) are correct.
- The grant map names all 31 agents.
- `.claude/settings.json` holds 50 deny rules. The list matches
  `templates/hooks/settings.tmpl` rule for rule.
- The permission-modes docs say: "Deny rules block in every mode, including
  `bypassPermissions`." The ADR claim holds.
- The permissions docs say deny rules apply to a command "nested inside a
  subshell, a command substitution, or a control-flow body".
  `tests/claude_permission_matcher.py` does not model that rule.
- No committed file sets `bypassPermissions` or `defaultMode`. `git grep`
  finds it only in a memory backup and the new test.
- The four changed test modules pass: 252 passed.

### Key Issues Addressed

- **P1. MCP merge path is an unlisted bypass.**
  `.claude/skills/github/references/transport-routing.md` names
  `merge_pull_request` as the MCP stand-in for `merge_pr.py`. That tool has
  no head pin, readback, or audit. The inventory has no MCP plane, and G7
  names only raw `gh pr merge`. The issue asked for MCP grants to be mapped.
- **P1. Reviewed-head pin is inert for every caller.** No caller passes
  `--expected-head-sha`. `pr-autofix` SKILL.md line 897 and the github skill
  table omit it. Without it, the script pins the head it just fetched, so a
  wrong PR number still merges. REQ-043 lists wrong PR as covered.
- **P1. A documented recipe is now denied.** `.agents/governance/GOTCHAS.md`
  line 860 runs `COPILOT_GITHUB_TOKEN="$(gh auth token)" git push ...`. Per the
  docs, the `gh auth token*` deny fires inside a command substitution. The
  test matcher says it is allowed, so the tests cannot see this.
- **P1. Unpinned lease form is allowed and unlisted.**
  `git push --force-with-lease=feat/x origin feat/x` is not denied. It reads
  the tracking ref, the same risk as the bare form the ADR denies. It is not in
  G2 or `KNOWN_GAPS`.
- **P1. Acceptance criterion gap.** Issue #5767 asks for a test of failed
  rollback. The audit `rollback` field is a hint string. Nothing tests a
  failed rollback. For the `merge` strategy the hint `git revert <sha>` fails
  without `-m 1`.
- **P2. Operator setting cited as repository fact.** Context says "The
  repository runs agents in `bypassPermissions` mode". No committed config
  shows that. The docs also name auto mode as the default start mode.
- **P2. Ruleset list** omits `copilot_code_review`.
- **P2. Over-deny.** `gh api *-X DELETE*` blocks label and reaction removal,
  which the ADR puts in the shared-repository tier. `git commit * -n *`
  blocks a `-m` message that contains ` -n `. Only the `--no-verify` case is
  documented.

### Major Changes Made

None. The reviewer may edit only this log.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit: tier table and owner map fit ADR-097 and ADR-101, but the inventory skips the MCP plane. |
| critic | Block: three issue criteria lack evidence (wrong target, failed rollback, MCP grant mapping). |
| independent-thinker | Disagree-and-Commit: the `bypassPermissions` premise is an operator setting, yet deny-over-ask is right in any mode. |
| security | Block: `merge_pull_request` and the unpinned lease bypass the stated controls, and neither is in the gap table. |
| analyst | Disagree-and-Commit: counts and the deny-in-bypass claim check out; the ruleset list and matcher model are off. |
| high-level-advisor | Disagree-and-Commit: right shape and honest gap table; fix the P1 items before accepting. |

### Next Steps

1. Add an MCP row to the inventory and a gap for `merge_pull_request` and
   other MCP mutators, or deny them in `permissions.deny`.
2. Pass `--expected-head-sha` from `pr-autofix` and the github skill docs,
   or narrow the REQ-043 wrong-target claim.
3. Model substitution and subshell nesting in the test matcher. Then fix or
   exempt the `GOTCHAS.md` recipe.
4. Deny or record `--force-with-lease=<ref>` without a SHA.
5. Test a failed rollback, or state in the ADR that the criterion is open.
6. Restate the `bypassPermissions` premise as an operator setting. Add
   `copilot_code_review` to the ruleset row.
7. Run round 2 with independent agents once the session cap allows.

## Round 2 Summary: author response

No reviewer re-ran; the session had no subagent budget left. This round lists
how the author disposed of each round 1 finding. The round 1 votes stand as
recorded above. The owner's review of the pull request is the gate that
replaces a second vote.

### Key Issues Addressed

| Round 1 finding | Disposition |
|---|---|
| REST PUT and `_pr_is_merged` timeouts crash with a traceback | Fixed. Both now raise or return into the readback path; tests `TestRestPathTimeouts` |
| No caller passes `--expected-head-sha` | Fixed for `pr-autofix` (passes `$EXPECTED_HEAD_SHA`); github skill table lists the flag; ADR-112 section 4 narrows the wrong-PR claim to callers that pass it |
| MCP `merge_pull_request` bypasses the checks | Recorded as gap G8; transport table marks the MCP route not equivalent |
| `gh auth token` deny breaks the `GOTCHAS.md` push recipe; matcher ignores `$(...)` | Rule removed and recorded in G2; matcher docstring states the nesting limit |
| `--force-with-lease=<ref>` without a SHA is not denied | Recorded in G2 and pinned in `KNOWN_GAPS` |
| Failed rollback untested; `git revert` hint wrong for merge commits | Hint is now strategy-correct and tested (`TestRollbackHint`); G9 records that no automated rollback exists |
| Already-merged and head-mismatch paths emit no audit | Fixed; tests `TestRefusalAudit` |
| Over-deny of `gh api -X DELETE` and ` -n ` in messages | Recorded under Consequences, Negative |
| code-reviewer default scope needs Bash | Recorded in the grant map; callers pass the diff |
| `bypassPermissions` stated as repository fact; ruleset row incomplete | Reworded as an operator setting; `copilot_code_review` added |
| Invalid `--expected-head-sha` exits 1, not 2 | Kept: the script's existing contract maps invalid parameters to 1, and changing one flag alone would split it |

### Major Changes Made

- `merge_pr.py`: timeout handling on the REST path, audit on refusals,
  strategy-correct rollback hint.
- Deny set: `gh auth token` removed.
- ADR-112: gaps G8 and G9 added, G2 widened, section 4 narrowed.


## Round 3 Summary: pull request bot review

Devin and CodeRabbit reviewed PR #5986. The author disposed of each thread.

### Key Issues Addressed

| Finding | Disposition |
|---|---|
| Lease recipe reads the tracking ref at push time | Fixed: the SHA is captured before the rebase |
| Refusal paths skip the readback | Fixed: conflict and head-moved errors go through the readback |
| Armed auto-merge after an error reported as failure | Fixed: reported as queued |
| Missing head SHA leaves the merge unpinned | Fixed: refused with exit 3 |
| `MERGED` readback not checked against the pinned head | Fixed: a different or missing head is unverified, exit 3 |
| Conflict and CLOSED refusals lack audit | Fixed |
| Auto-merge path not head-pinned | Recorded as gap G10 |
| code-reviewer base-revision read needs a read-only route | Fixed: the GitHub read tool at the base ref |

### Agent Positions

| Agent | Position |
|---|---|
| Round 1 seats | Unchanged; no re-vote |
| Author | All bot findings fixed or recorded as G10 |
