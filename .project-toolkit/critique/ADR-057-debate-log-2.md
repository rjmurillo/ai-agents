# ADR Debate Log 2: ADR-057 Amendment 2026-11-25, Deterministic Evidence Check

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-057-debate-log.md`
- **Outcome**: Consensus (5 Accept, 1 Disagree-and-Commit)
- **Final Status**: accepted (the record's status is unchanged; this debate covers one amendment)
- **Panel**: full six seats. The change adds executable enforcement: a blocking gate in `pre_pr.py` and `Validate PR`.
- **Claims ledger**: `.project-toolkit/critique/ADR-057-claims-ledger.md`
- **Date**: 2026-11-25

## Exit gates before review

| Gate | Result |
|---|---|
| Claims ledger | VERIFIED. 16 rows at hand-off. |
| Documentation accuracy (`doc-accuracy` Phase 4) | NOT RUN. Each ledger row is backed by a test or a direct file read instead. |
| Self-consistency | VERIFIED. No contradiction among the decision items or with the limits. |
| Refuting seat (analyst, haiku) | No FALSE finding except the debate log path, which this file now fills. Shell-only rows came back UNAVAILABLE; the writer had run them. |

## Round 1 Summary

### Votes

| Seat | Vote | Main finding |
|---|---|---|
| architect | Disagree-and-Commit | Lines 92, 135, 137, and 218 still said no CI check blocks. |
| critic | Block | Label flip, deleted FAIL evidence, new and deleted drivers can never pass, CI merge-commit hash. |
| independent-thinker | Block | List-form `allowed-tools` skips the grant rule. Denylist leaks. Item 8 overclaims. |
| security | Block | List-form bypass. Denylist misses `git -C . push`, `uv:*`, `mcp__` writes. Same-PR runner edit forges the verdict. |
| analyst | Disagree-and-Commit | CI hashes the merge commit, not the PR head. Score copy not pinned by a test. |
| high-level-advisor | Disagree-and-Commit | No rollback line. Grant rule goes past decision 9; say so. |

### Key Issues Addressed

| Finding | Seat | Priority | Resolution |
|---|---|---|---|
| List-form `allowed-tools` read as empty | independent-thinker, security | P0 | Fixed. A list is joined; any other type fails closed. Two tests. |
| Grant denylist leaks | independent-thinker, security | P1 | Fixed. Replaced by an allowlist. 21 failing and 6 passing grant forms tested. |
| Same-PR runner or check edit | security | P1 | Partly fixed. A gated branch may not change the runner or the check. Named as a residual: a PR that edits the check changes the check. |
| Results file edited or deleted after a FAIL | critic, independent-thinker, security | P1 | Fixed. Results files are append-only. An edit, a delete, or a second add fails. |
| Merge resolution edits escape | critic, security | P2 | Fixed. `diff-tree --cc` reads a merge's own edits. A second add catches a resolution equal to one parent. |
| Label flip in the scenario commit | critic | P1 | Fixed. A kept scenario may not change `expected_verdict` since the merge base. |
| New and deleted drivers can never pass | critic | P1 | Decided by the writer: neither is gated. A new skill beside a deleted one is gated as a possible rename. Flagged for the owner in the PR body. |
| CI hashes the merge commit | analyst, critic | P1 | Fixed. CI passes the PR head as `--head-ref`. |
| Torn references at lines 92, 135, 137, 218, 277 | architect | P1 | Fixed. Each names the gated-change exception. |
| Item 8 overclaims "a later run cannot replace it" | independent-thinker | P1 | Fixed by append-only, and the limit list names history rewrite. |
| Trigger 4 miss rate unknown | independent-thinker | P1 | Named. The amendment says it measures precision only. |
| No rollback path | high-level-advisor | P1 | Fixed. One PR removes the CI step and the `pre_pr` registration; no skip flag exists. |
| Score copy not pinned | analyst | P2 | Fixed. `TestEndToEndConformance` runs the runner's own comparison and gate on 7 tables. |
| Base `model_used` unchecked | analyst | P2 | Fixed. Both sides checked. |
| Stripped-line compare in trigger 4 | independent-thinker | P2 | Fixed. Both sides strip. |
| `prompt_path` form unstated | analyst | P2 | Fixed. Item 3 names the form. |
| `GH_TOKEN` reachable in the step | security | P2 | Fixed. The step sets `GH_TOKEN: ""`. |
| `security_critical` self-declared; base commit only an ancestor | critic | P2 | Named as limits. |
| Grant rule is beyond decision 9 | high-level-advisor | P2 | Labeled in the amendment. |
| ADR-127 still says "until the decision 9 check lands" | architect | P2 | Out of scope. Flagged in the PR body for the owner. |
| `scripts/eval/` has no CODEOWNERS line | security | P2 | Out of scope. Flagged in the PR body for the owner. |

### Security seat recommendation from the ADR-127 review

Decision: adopted, as an allowlist. A touched skill tagged `reference` may hold only read tools, read-only MCP tools, read-only Bash commands, and Bash grants that run its own `scripts/`.
Reason: without it, tagging a skill `reference` dodges the driver trigger.
Cost: no template sets `metadata.shape` at `c0b72f8539` (2026-11-25), so it blocks no current file.

## Round 2 Summary

### Votes

| Seat | Vote | Main finding |
|---|---|---|
| architect | Accept | All round 1 findings closed. ADR-127 still says "until the decision 9 check lands"; outside ADR-057. |
| critic | Disagree-and-Commit | The new-driver exemption departs from ADR-127 decision 7 trigger 1. Say so, and let the owner confirm. |
| independent-thinker | Disagree-and-Commit | The own-script pattern accepted `..`, so a reference tag could still hide a merge grant. |
| security | Block | `git grep -O` and `git diff --output` escape the read list. `..` in own-script. Write beside a script grant. Judge-code and workflow residuals. |
| analyst | Accept | Merged tree is not re-evaluated when `main` edits the same skill. Symlinked reference unaddressed. |
| high-level-advisor | Accept | Freeze scope: further gaps go into Limits, not new mechanisms. |

### Key Issues Addressed

| Finding | Seat | Priority | Resolution |
|---|---|---|---|
| `..` and shell operators in a Bash grant | independent-thinker, security | P1 | Fixed in the existing grant rule. 5 tests. |
| `git grep -O`, `--output`, `--ext-diff`, `--textconv`, `--open-files-in-pager` | security | P1 | Fixed. `git grep` dropped; the flags fail. 3 tests. |
| Write tool beside a script grant | security | P1 | Fixed. The pair fails. 1 test; `Write` alone still passes. |
| MCP write tool with a read verb | security | P2 | Tightened: a write word in the name fails. The name heuristic is a named limit. |
| PR can weaken the check or edit the workflow step | security | P1 | Named limit. CODEOWNERS covers `.github/workflows/` and `scripts/validation/`. |
| Checkout token persists in `.git/config` | security | P2 | Named limit. Changing checkout affects every step of the job; out of scope. |
| New-driver exemption departs from ADR-127 | critic | P2 | Stated in amendment item 5 as a reading the ADR-127 owner confirms at PR review. |
| Merged tree not re-evaluated | analyst | P2 | Named limit. |
| Symlinked reference | analyst | P2 | Named limit. It fails closed. |
| Conformance edge patterns (unscored first base run, mixed case) | analyst | P2 | Deferred. Equivalent by reading `_run_passed` and `check_scenario_pass`; both uppercase and strip. |

Scope freeze (high-level-advisor): round 2 added no new mechanism. Each code change tightens the existing grant rule.

## Round 3 Summary

### Votes

| Seat | Vote | Note |
|---|---|---|
| architect | Accept | Carried from round 2. |
| critic | Accept | New-driver reading stated in item 5 for the owner to confirm. |
| independent-thinker | Accept | Traversal and operators closed. Own-script prefix is unanchored (P2). |
| security | Disagree-and-Commit | A write tool beside a read-only git grant can set `diff.external` in `.git/config`. A `*` grant lets the model add flags at run time. |
| analyst | Accept | Carried from round 2. |
| high-level-advisor | Accept | Carried from round 2, on the condition of no new mechanism. |

### Resolutions

| Finding | Seat | Priority | Resolution |
|---|---|---|---|
| Write tool beside any Bash grant | security | P1 | Fixed, the condition of the security vote. The existing write-plus-script rule now covers any Bash grant. 1 test. |
| `*` grant lets the model add flags at run time | security | P1 | Named limit. The rule reads grant text only. |
| Own-script prefix is unanchored | independent-thinker | P2 | Named limit. |

### Standing dissent (security, Disagree-and-Commit)

The grant rule reads grant text, so it cannot bound what a wildcard grant runs.
The seat commits because no template sets `metadata.shape` today, and the limit is named in the amendment.

### Recommendations to the owner

- Confirm or reject the reading in amendment item 5: a brand-new driver is not gated.
- ADR-127 still says "until the decision 9 check lands" in four places. A follow-up amends it.
- `scripts/eval/` has no CODEOWNERS line.

## Edits after the debate (from `/review` round 1)

The `/review` axes found these after consensus. Each is a fix or a wording change; none adds a mechanism.

| Finding | Axis | Change |
|---|---|---|
| Delegation tools in the reference allowlist | security, agent-safety, qa | Task and Agent removed. `mkdir` removed from the read-only Bash list. The amendment lists the real allowlist. |
| Judge paths omit the gate wiring | architect, agent-safety | Item 10 now covers `pre_pr_sequence.py`, `checks_ci_parity.py`, and `pr-validation.yml`. |
| Pooled base runs dropped from the model check | correctness | Fixed in code. 1 test. |
| Malformed base scenario file fails open | spec-compliance, qa, observability | It now fails closed. |
| Pre-existing matching results file | analyst, code-quality | Item 6 states that it counts as first. |
| Precision overstated | decision-rigor | Item 4 says precision is inferred from 5 hits and recall is unknown. |
| Reversibility table | decision-rigor | Row updated with the rollback path. |
| Runner tree and merge queue | devops | Two limits added. |
