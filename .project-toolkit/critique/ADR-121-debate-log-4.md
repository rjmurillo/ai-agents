# ADR Debate Log: ADR-121 One Resolver Launches Every Shipped Plugin-Root Shell Command (debate 4)

## Summary

- **Rounds**: 1 of 10 recorded so far
- **Prior debate logs**: `.project-toolkit/critique/ADR-121-debate-log.md`, `-2.md`, and `-3.md`
- **Outcome**: Round 1 closed with six votes of Accept with changes. The changes are applied. Round 2 is not yet recorded in this log.
- **Final Status**: proposed
- **Panel**: the full panel of six seats: architect, critic, independent-thinker, security, analyst, and high-level-advisor. The amendment changes the launcher recipe, the resolver, and the validator, which other gates read.
- **Model**: every seat ran on Sonnet. The Opus credentials were rate limited for about five hours on 2026-11-14.
- **Trigger**: on 2026-11-14 the owner chose option A in issue #7281 (decision D15). The amendment lets the last seven skills migrate and settles five reviewer asks from PRs #7340 and #7341.

## Phase 0: Related Work

- Issue #7281, last comment "ADR-121 rollout status (2026-11-12) and the decision still open". It names the 22 sites, the seven blockers, and options A to C.
- PR #7340 review threads: target-aware selection (`fix-markdown-fences`) and `${CLAUDE_PLUGIN_ROOT:-}` for `set -u` (`memory-gate`).
- PR #7341 review threads: target-aware selection (`repository-completion-proof`), a `PLUGIN_ROOT` candidate (`research`, Hermes), `.claude` first (`repository-pr-recovery`), and `SKILLOPT_DIR` from the same root (`skillopt`).
- ADR-115 records that Hermes `PLUGIN_ROOT` reaches MCP stdio servers only. ADR-071 records a bare `PLUGIN_ROOT` for Copilot CLI 1.0.57 plugin hooks.

## Round 1 Summary

### Votes

| Seat | Vote | Required changes |
|---|---|---|
| architect | Accept with changes | Fix "would pass their cap". Make the locator win over a preset `SKILLOPT_DIR`, and fail when empty. Name the own-root comparison. Pass `-I` in `_launch`. Name the reader of `distribution`. Name an owner for the PowerShell block. |
| critic | Accept with changes | Define the own-root identity and the symlink rule. Define the `distribution` marker and the missing case. Add an interpreter-form table with Windows and `-I` rows. Name the owner of the allowance list. |
| security | Accept with changes | A preset `SKILLOPT_DIR` must not win. An empty `SKILLOPT_DIR` must not run `/skillopt.py`. Reword "admits nothing" and name the widening. |
| analyst | Accept with changes | Fix "pass". Measure the rows it could not, or drop them. Cite the Copilot claim. |
| independent-thinker | Accept with changes | Name the widening of decision 5, with a stderr notice. Narrow the version-skew claim, which only holds when the first root has the new resolver. |
| high-level-advisor | Accept with changes (P0) | Decision 11's "admits nothing the shell loop does not already try" is false. Fix it, and tie the closing claim to exact counts. |

### Key Issues Addressed

- **P0, decision 11 widening.** The draft said fallthrough admits nothing new. Four seats showed it lets a later root run when the first root holds the resolver but not the target. The resolver also reads the environment that the shell skipped where the host rewrote the token. The revision names both cases under "What it widens", ties them to decision 10, adds a stderr line on every fallthrough, keeps the own root first when it holds the target, and adds a runtime test with a foreign resolver-bearing root. The advisor's restriction to repo-local skills or to `.claude` was not taken, because it leaves the PR #7340 case unfixed.
- **P1, byte claim.** The draft said the two files "would pass their cap". They exceed it: 24,687 and 24,743 against 24,576. Fixed, with the arithmetic.
- **P1, own-root identity.** The revision compares candidates by `os.path.realpath` and drops duplicates, so `.claude` is never probed twice when it is the own root through an ADR-119 link. It uses `os.path.isfile`, the same lexical test as decision 6.
- **P1, version skew.** The draft claimed a fix for a skewed root. The revision says a root with an older resolver cannot fall through and still exits 2.
- **P1, interpreter forms.** The revision adds a table: who may use each form, what rule 2 does, and how the target starts. Both launch paths pass `-I`. The `uv` form becomes `uv run --frozen python`, the repository convention (security P2-1).
- **P1, repo-local gate.** The revision names `build/scripts/skill_distribution.py` as the reader of `metadata.distribution`. A missing or unknown value counts as shipped.
- **P1, `SKILLOPT_DIR`.** The locator now wins. A preset is used only when the locator fails. The assignment aborts on empty, and `references/` commands use `${SKILLOPT_DIR:?}`. The PowerShell block is named hand-written, uses `Test-Path -LiteralPath`, and gets a structure test.
- **P1, allowance list.** The revision names `GUARDED_IMPORT_ALLOWANCES` in `plugin_root_interpreter_allowances.py`, ties each entry to the sites it unblocks, and states that the blocked-module test runs in the pytest suite.
- **P1, closing claim.** Step 9 now names the counts: `templates/skills` from (15, 7) to (0, 0), with the Class G count of 17 kept. It cites the issue comment that scoped the 22 sites.
- **P2 items applied.** Pointers at decision 3. Rejection reasons rewritten: shadowing for `.claude` first, the ADR-071 citation for Copilot, and the loud abort plus byte cost for `set -u`. The `autoplan` `cd` alternative is recorded as weighed and rejected. Step 8 adds a test that every committed locator target resolves under its own root.

### Positions Not Taken

- **Manifest name check on env roots (security).** Rejected and recorded in the ADR. The Alternatives section already rejects the manifest as a marker, `.claude/` has none, and the Hermes packs are named `project-toolkit-delivery` and `project-toolkit-knowledge`.
- **Guard-aware rule 2 instead of a list (independent-thinker).** Not taken. The owner's option A names an allowance list. The ADR records the alternative and why the list stays.
- **Inline locators in `references/` instead of `where` (independent-thinker).** Not taken. Inlining would replace 24 short lines with locators of about 270 bytes each. `where` is a target, so decision 6 is unchanged.
- **Bump `date` (architect).** Not taken. Debate log 3 set `date` to the decision date on purpose.
- **Split step 9 (high-level-advisor).** The ADR keeps one step. The implementer may ship it as more than one pull request.

## Debate State

**Round**: 1 of 10 (counted within this debate log)
**Status**: Round 1 closed; changes applied to the ADR text.

Unresolved P0 issues after round 1 changes: none known. Round 2 votes on the revised text are not yet recorded.
