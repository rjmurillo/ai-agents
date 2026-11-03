# ADR Debate Log: ADR-059 /pr-review Completion Gate Dispatcher and pass_when DSL (fourth debate)

## Summary

- **Rounds**: 2 of 10. Round 1 ended without consensus; round 2 reached it.
- **Prior debate log**: `.project-toolkit/critique/ADR-059-debate-log-3.md`
  (part 1; part 2 is `.project-toolkit/critique/ADR-059-debate-log-3-part-2.md`)
- **Outcome**: Consensus. Round 1: two Block, four Disagree-and-Commit.
  Round 2: five Accept, one Disagree-and-Commit.
- **Final Status**: accepted

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-059-pr-review-completion-gate-dispatcher.md`
- **Edit**: cite remap and one R3 sentence in "Amendment 2026-11-01: Step 0
  verify-only trust rules". Decision items 1 to 6 are unchanged.
  Frontmatter is unchanged. The ADR stays at 500 lines.
- **PR**: #7014, branch `fix/6506-batch7-merge-pr-automation-2`.
- **Code under the rules**: `src/claude/skills/github/scripts/pr/run_completion_gate.py`
  at commit `8d8c3b01d` (2026-11-02). The prior ADR commit is `2cbac5b56`
  (2026-11-02).
- **Owner decision**: D8 (2026-11-02) directs a full adr-review debate for
  ADR-059 edits inside PR #7014 before it merges.
- **Trigger**: any edit to the amendment opens a new debate
  (`debate-protocol.md#round-cap`). Log 3 closed by consensus in its round 4.

Why the ADR changed after log 3:

1. Four gate commits landed after `2cbac5b56`:
   - `f8f9b4653`: one trust pipeline, `_verify_tree_files`, for this work
     tree and for sibling work trees.
   - `e916f5707`: CWE-59. `_classify_argv_token` resolves the token as
     written, not its normpath.
   - `05f2b6d0a`: CWE-59. The D10 sibling spelling keeps its `..` parts.
     A spelling that enters a work tree of this repository and holds `..`
     blocks.
   - `8d8c3b01d`: stderr NOTE lines when the launcher verifier is
     unavailable and when D10 withholds install trust from a plugin root.
     `_SameRepositoryCheck` is renamed `_TreeTrustCheck`.
2. A `/review` analyst finding at `e916f5707` said the ADR's `gate.py`
   line cites no longer matched the code (the R3-ORDER concern from log 3).

Changes under review:

1. **Cites remapped.** Every `gate.py:N` and test-file line cite moved from
   the files at `2cbac5b56` to the files at `8d8c3b01d`, with a line diff.
   Five cites sat on rewritten lines and were re-anchored by hand:
   escaping paths join `untrusted` (3602), nested and untracked handling
   in `_verify_tree_files` (3321-3327), `_partition_external_files`
   (3468-3510), and the named-untracked rule (3322-3326).
2. **R3 `..` rule.** R3 now states the `05f2b6d0a` rule for spellings
   under a work tree of this repository.

Panel: full panel (architect, critic, independent-thinker, security,
analyst, high-level-advisor). The edit records a rule of an executable
trust gate, which the AGENTS.md ADR review rule routes to the full panel.

Method: each seat ran as its own `claude -p` process, with its Phase 1
prompt from `references/agent-prompts.md`, the Factual Claim Verification
Block, and the convergence instructions. Seats had read-only tools.

## Carried Forward From Prior Log

| Item from log 3 | Priority | State at the start of this debate |
|-----------------|----------|-----------------------------------|
| R3-ORDER | P2 | Reopened by the `/review` finding. Item 1 answers it for `8d8c3b01d`. |
| R3-GITCONFIG, R3-CONTAIN3A, R3-MARKER, R3-APPROVED-EXIT0 | P2 | Unchanged. |
| R4-* text findings deferred by log 3 | P2 | Unchanged. |
| R2-EXIT2-NODIFF, R2-CFGRESOLVED, R1-UNTRACKED-EXIT2, R1-GITDIR, R1-TOCTOU, R1-GATEEVIDENCE, AN1, CR4 | P2 | Unchanged. |
| R1-VERIFIER residual | P1 | Unchanged. No check inside the plugin can verify the plugin. |

## Round 1 (2026-11-02)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Block | Every remapped cite holds. Blocks on the anchor sentence and a stale test name. |
| critic | Disagree-and-Commit | All 41 cite ranges checked and hold. Two P1 text errors. |
| independent-thinker | Block | Anchor sentence refuted (P0). Stale test name (P1). |
| security | Disagree-and-Commit | All 40 changed cites hold. One stale test name (P1). |
| analyst | Disagree-and-Commit | All 33 changed cites hold. Anchor and test name are P1. |
| high-level-advisor | Disagree-and-Commit | 45 cites checked. The remap was the right size. |

### Issues Raised

| ID | Priority | Agents | Finding |
|----|----------|--------|---------|
| D4-ANCHOR | P0/P1 | all but security | ADR line 105 says cites hold at "the commit that last changed this paragraph". That resolves to `2cbac5b56`, where the remapped cites do not hold. |
| D4-TESTNAME | P1 | all six | R3 Tests names `test_launcher_verifier_returns_none_when_git_fails`. `8d8c3b01d` renamed it to `test_launcher_verifier_returns_none_and_names_the_cause`. |
| D4-RANGE | P2 | security, independent-thinker, analyst, high-level-advisor | `test_run_completion_gate.py:2438-2645` stops before the renamed test ends at 2649. |
| D4-FAILFILE | P2 | critic, independent-thinker, analyst, high-level-advisor | `test_run_completion_gate_same_repository_failures.py` is missing from the D10 test list. |
| D4-DOTDOT | P2 | critic, analyst, high-level-advisor | "A `..` there blocks" is narrower than the code, which refuses `..` anywhere in an entering spelling. The `..` test runs before the link scan, so a `..` spelling is never scanned. |
| D4-PINDEF | P2 | security | The pinned-link cite `1566-1587` could start at the def, 1552. |

### Consensus And Conflicts

Every seat verified the remapped cites against the gate at `8d8c3b01d`. No
seat refuted a remapped `gate.py` cite or the five hand-anchored ones. The
two Block positions rest on refuted claims in text next to the cites.

### Revisions Made

1. **D4-ANCHOR.** The paragraph now names commit `8d8c3b01d` (2026-11-02)
   and any later commit that leaves the cited file unchanged. The ADR
   commit carries no gate or test change.
2. **D4-TESTNAME, D4-RANGE.** New test name; range `2438-2649`.
3. **D4-FAILFILE.** `..._same_repository_failures.py` (git and resolve
   failures) added. The links file now lists `..` spellings.
4. **D4-DOTDOT.** R3 now says the spelling, as written, blocks if it holds
   `..` anywhere; otherwise it is scanned for links.
5. **D4-PINDEF.** Cite now `gate.py:1552-1587`.

The ADR stays at 500 lines.

## Round 2 (2026-11-02)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Accept | No changed claim refuted. The anchor commit is HEAD, and only the ADR is modified. |
| critic | Accept | Round 1 concerns resolved. |
| independent-thinker | Accept | Anchor and test name fixed. |
| security | Accept | Test name and range fixed; `..` rule matches `_classify_external`. |
| analyst | Disagree-and-Commit | Every touched cite holds. One new P2 wording note. |
| high-level-advisor | Accept | Round 1 dissent resolved. |

### Issues Raised

| ID | Priority | Agents | Finding |
|----|----------|--------|---------|
| D4-SEGMENT | P2 | analyst | "Holds `..` anywhere" could read as a substring match. The code tests `".." in spelling.parts`, a whole path segment, so `foo..bar` does not block. Suggested wording: "blocks if any path segment is `..`". |

### Dissent Recorded

Analyst (Disagree-and-Commit): D4-SEGMENT above. The wording overstates
the rule by a small margin. It does not block.

### Residual P2 Findings

| Finding | Agent | Trigger to reopen |
|---------|-------|-------------------|
| D4-SEGMENT | analyst | The next edit to the R3 D10 bullet. |
| R3-ORDER (residual) | carried | The cites hold at `8d8c3b01d`. Any later gate commit must remap them in the same debate that lands it. |

## Closing Summary

Consensus in round 2: five Accept, one Disagree-and-Commit. The decision
is unchanged. The edit remaps line cites to `8d8c3b01d` and records the
`05f2b6d0a` `..` rule in R3.

### Recommendations

1. Land the ADR commit with no gate or test change, so the anchor holds.
2. Fix D4-SEGMENT at the next R3 edit.
