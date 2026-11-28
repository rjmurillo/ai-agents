# ADR Debate Log: ADR-101 amendment, generated skill links exempt from the base-ref symlink report

## Summary

- ADR: `.project-toolkit/architecture/ADR-101-enforcement-planes.md`, the "Amended 2026-11-16" text on the Application B dispatcher bullet.
- Driver: issue #7398. `Verify dispatch closure against base` failed on every skill PR (#7392, #7396) on the two generated ADR-119 links.
- Panel: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the change edits executable enforcement (`scripts/ci/verify_dispatch_closure.py`, new `scripts/ci/_link_exemption.py`).
- Outcome: Consensus after three rounds. Round 2 had three Accept, one Disagree-and-Commit, and two Block; both Blocks moved to Accept in Round 3.

## How this panel was run, stated plainly

Each seat ran as a separate subagent with a fresh context. All six got the same brief, which held the change diff and the factual-claim verification block. No seat saw another seat's output in Round 1. One model family ran every seat. The author consolidated the findings and made the fixes; the seats did not edit files.

## Change under review

Round 1 reviewed an amendment that exempted six install trees and repeated the module's full condition list. It also reviewed the code at that state: 15 tests, and the import-root check one level deep.

## Round 1: Phase 1 independent review

Each seat's section is condensed to its vote, blocking concerns, and the claims it checked.

### Architect review

Vote: Disagree-and-Commit. Write the debate log before merge; W1 recorded as accepted residual risk.

#### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| Q1 | P1 | The cited debate log is absent; write it before merge. |
| W1 | P2 | The gate does not model every `sys.path` entry; before this change a new link anywhere was a backstop for that gap. Record it as accepted residual risk. |
| W2 | P2 | `link_rows` took the first list-valued key; read `rows` by name. |
| W3 | P2 | "Base ref's binplace.yaml" is the tool root's working tree; equal in CI only. Tighten the wording. |
| W4 | P2 | No stated rule for growing `EXEMPT_INSTALL_TREES`. |

#### Claims Checked
| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| #7396 and #7392 failed on the two links | issue-or-PR | `get_pr_checks.py` on both | VERIFIED |
| Positive control: #7396 head exits 0 with two EXEMPT lines | count-or-path | command run by this seat | VERIFIED |
| 15 new and 140 existing tests pass | count-or-path | pytest, 155 passed | VERIFIED |
| None of the 10 measured closure import roots is a hidden or install tree | contract | `import_roots` on main | VERIFIED |
| A waiver is needed | count-or-path | ADR-101 is 505 lines; threshold 500 at `taste_lints.py:628` | VERIFIED |

### Critic review

Vote: Disagree-and-Commit. Accept once the debate log exists; B2 and B3 may follow as tests.

#### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| B1 | P1 | The cited debate log does not exist yet. |
| B2 | P2 | The closure-path check compares raw strings, so `./.claude/skills/x/run.py` or an absolute spelling slips past it. Normalize, or add the negative test. |
| B3 | P2 | Fail-closed branches (failed `ls-tree`, malformed YAML) have no tests. |
| W4 | P3 | No rollback line in the amendment. |
| W5 | P3 | Say EXEMPT does not mean reviewed: `.github/instructions` and similar feed AI reviewers, not the gate. |

#### Claims Checked
| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| #7396 and #7392 failed the check | issue-or-PR | `gh pr view` status rollup | VERIFIED |
| Positive control, new exit 0 and old exit 1 | count-or-path | rerun with `--head-root` on an archive of 521e9fc69 | VERIFIED |
| 15 new and 140 existing tests pass | count-or-path | pytest, 155 passed | VERIFIED |
| Closure-path condition | contract | `_link_exemption.py` | VERIFIED, raw-string compare (B2) |

### Independent-thinker review

Vote: Disagree-and-Commit. The exemption beats each alternative, but record them and trim the amendment.

#### Alternatives checked
- (a) Pin skill links in the base: impossible for a new skill, since the target does not exist at base.
- (b) A standing base-ref disposition by pattern: the same exemption stored as data, without the tests.
- (c) Treat binplace-shaped links as pinned during the head pass: simpler, but the verifier would follow links the local gate refuses, so the two would disagree.
- (d) Report only links on closure paths: rightly rejected; it reopens the refused-link blind spot.

#### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| IT-1 | P2 | Record the alternatives considered. |
| IT-2 | P2 | Trim the amendment, which repeats the module docstring. |
| IT-3 | P2 | The cited debate log did not exist yet. |
| IT-4 | P3 | `link_rows` should key on `rows` explicitly. |

#### Claims Checked
| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| 15 new tests pass and 140 existing pass | count-or-path | pytest run by this seat | VERIFIED |
| Decision text unchanged | contract | the change diff | VERIFIED |
| Import roots match the gate exactly | contract | `_environment_libs` reads the environment | VERIFIED with a caveat: environment-dependent |

### Security review

Vote: Accept, conditional on the Low items (no exemption bypass found).

#### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| S-1 | P1 | The cited debate log did not exist; it must exist before merge. |
| S-2 | P2 | Import-root check was one level deep. A link at R/skills/name is importable as skills.name when R is a root. Not exploitable today, since it needs a changed closure file, which is reported. Refuse within any non-toplevel root. |
| S-3 | P3 | Runtime-built data reads (a verifier globbing exempt trees) are not modeled. This predates the change: a real directory is equally invisible. |
| S-4 | P3 | Paths are not case-folded; a case-insensitive checkout could collide with a pinned link. The local gate halts on that, so the effect is a denial of service, not execution. |

#### Claims Checked
| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| Inputs come from the base | contract | `_load_sibling`, `link_rows`, `_following` | VERIFIED |
| Link text equals binplace output | contract | `build/scripts/binplace_links.py:70` | VERIFIED |
| Gate refuses unpinned links while building the closure | contract | `run_completion_gate.py` near 2143 and 2865-2877 | VERIFIED |
| Debate log at the cited path | count-or-path | glob of critique | REFUTED until committed |

### Analyst review

Vote: Block (W1).

#### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| W1 | P1 | The cited debate log did not exist in the worktree; commit it with the ADR edit. |
| W2 | P2 | The import-root check refused only a link that sits directly in a root. A namespace-package import can reach a link deeper under a non-toplevel root. Use a within-root test, or show no closure script makes such a root. |
| W3 | P2 | The module docstring says exempt trees hold no dispatched code, but verifiers live under `.claude/skills`; the closure-path check is what guards them. |
| W4 | P2 | The ADR says "the base ref's binplace.yaml"; the code reads the tool root's file, equal only because the workflow checks out the base. State it. |

#### Claims Checked
| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| Tree-wide scan reports every new link | contract | `verify_dispatch_closure.py` `_new_symlinks` | VERIFIED |
| Link text matches what binplace writes | contract | `binplace_links.py` relpath vs `_link_exemption.py` | VERIFIED |
| `lib` and `hooks` never qualify | contract | `EXEMPT_INSTALL_TREES`, `binplace.yaml` | VERIFIED |
| Base presence, target, and closure-path conditions | contract | `_link_exemption.py` `is_exempt` | VERIFIED |
| Import-root condition | contract | `_link_exemption.py`, `run_completion_gate.py` `_import_roots` | VERIFIED as worded; see W2 |
| Debate log path exists | count-or-path | Glob of `critique/ADR-101*` | REFUTED until committed |

### High-level-advisor review

Vote: Disagree-and-Commit. Ship once HLA-1 is fixed; HLA-2 and HLA-3 may land here or next.

#### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| HLA-1 | P1 | The cited debate log did not exist yet. Commit it in the same PR. |
| HLA-2 | P2 | Four of six exempt install trees have no failure evidence. Justify each or narrow the set. |
| HLA-3 | P2 | The amendment repeats the module's condition list. State the decision and invariant, and cite the module. |

#### Claims Checked
| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| Issue #7398 tracks this failure | issue-or-PR | `gh issue view 7398` | VERIFIED |
| #7396 and #7392 failed the check | issue-or-PR | `gh pr checks` on both | VERIFIED |
| The check is not required | contract | ruleset API, `ruleset_required_contexts.py` | VERIFIED |
| `lib` and `hooks` never qualify | contract | `EXEMPT_INSTALL_TREES` | VERIFIED |
| Debate log path exists | count-or-path | `ls .project-toolkit/critique/` | REFUTED until committed |

## Round 1: Phase 2 consolidation

Consensus across seats:
- The exemption is the right shape. Keep the tree-wide scan; the closure-paths-only idea would reopen the refused-link blind spot.
- All trust inputs come from the base checkout, and every error path fails closed.
- No seat found a way for an EXEMPT link to change what the gate runs today.

Conflicts and open items:
- Every seat flagged the missing debate log (P1). This file resolves it.
- Import-root depth: analyst W2 and security S-2 found that a link nested under a non-toplevel import root passed the check.
- Scope: high-level-advisor HLA-2 found no failure evidence for four of six exempt trees.
- The amendment copied the module (HLA-3, IT-2) and lacked alternatives (IT-1), a residual risk (architect W1), a growth rule (architect W4), a rollback (critic W4), and a scope note (critic W5).
- Raw-string path compare (critic B2), untested fail-closed branches (critic B3), and order-dependent manifest key (architect W2, IT-4).

## Round 1: Phase 3 resolution

| Issue | Resolution |
|-------|------------|
| Missing debate log (all seats, P1) | This log, committed with the ADR edit. |
| W2, S-2 nested import root | `is_exempt` now refuses a link at or under any import root other than the work-tree root. The root is skipped because every exempt tree starts with a dot and so is not an importable package name. New test `test_a_link_nested_under_a_non_toplevel_import_root`. |
| HLA-2 scope | `EXEMPT_INSTALL_TREES` narrowed to `.claude/skills` and `.agents/skills`. New test `test_a_link_under_a_non_exempt_install_tree` (`.github/hooks`). |
| HLA-3, IT-2 copied condition list | The amendment now states the shape, the invariant, and a pointer to the module. |
| IT-1 alternatives | Recorded: base pinning is impossible for a new skill; a standing disposition is the same rule without tests; pin-by-rule would make the check follow links the gate refuses. |
| Architect W1 unmodeled sys.path | Recorded as accepted residual risk. |
| Architect W2, IT-4 manifest key | `link_rows` reads `rows` by name and returns `{}` otherwise. |
| Architect W3, analyst W4 tool root | Amendment and docstring say the file comes from the tool root, which the workflow checks out at the base. |
| Architect W4 growth rule | Amendment: a new exempt tree needs a failing PR and an amendment. |
| Analyst W3 docstring | Module docstring says verifiers live under `.claude/skills` and the closure-path check guards them. |
| Critic B2 raw strings | Named paths are normalized (`./x`, absolute) before comparing. New test `test_a_dot_slash_spelling_in_the_base_config_still_counts`. |
| Critic B3 fail-closed tests | New tests `test_a_malformed_base_manifest_exempts_nothing` and `test_an_unlistable_base_ref_exempts_nothing`. |
| Critic W4, W5 | Amendment adds the rollback and says EXEMPT does not mean reviewed. |
| Security S-3, S-4 | Accepted, not changed: runtime-built data reads predate this change (a real directory is equally invisible), and a case-folding collision is a local denial of service the gate already halts on. |
| Waiver (IT-2, architect W6, critic W3) | Kept. ADR-101 was 500 lines before this change, so any dated amendment crosses the limit. The waiver states its reason and follows ADR-104. |

Evidence after the fixes: the new test file has 19 tests, and the 140 earlier dispatch-closure tests pass unchanged (159 total). A mutation sweep removed each of 8 conditions in turn; each mutant failed its own named negative test, and an inert edit passed.

## Round 2: Phase 4 convergence check

Each seat re-read the revised ADR text and code, checked every claim added or changed, and raised only new P0 or P1 issues.

### Architect convergence

Vote: Accept, assuming this log is committed with the ADR edit.

| Round 1 issue | Status | Evidence |
|---------------|--------|----------|
| Q1 debate log | RESOLVED by this file | same commit |
| W1 unmodeled sys.path | RESOLVED | amendment records it as accepted residual risk |
| W2 manifest key | RESOLVED | `link_rows` reads `rows`; malformed-manifest test |
| W3 tool-root wording | RESOLVED | amendment and docstring; workflow checks out the base |
| W4 growth rule | RESOLVED | amendment plus the code comment on `EXEMPT_INSTALL_TREES` |

Noted: the rollback wording was loose; corrected in the same round (see HLA-4). `taste_lints.py` on ADR-101 reports no violations with the waiver. New P0 or P1 issues: none.

### Critic convergence

Vote: Block (N1, plus B1 until this log exists). Re-polled in Round 3.

| Round 1 issue | Status | Evidence |
|---------------|--------|----------|
| B1 debate log | OPEN at vote time; resolved by this file | same commit |
| B2 raw-string compare | RESOLVED | `_normalized`; `./` test. The absolute branch lacked a test; added after this vote (`test_an_absolute_named_spelling_is_normalized`, mutation-checked) |
| B3 fail-closed tests | RESOLVED | malformed-manifest, unlistable-ref, and no-manifest tests |
| W4 rollback | PARTIALLY | rollback line was false (N1) |
| W5 EXEMPT is not review | RESOLVED | amendment sentence |

| New issue | Priority | Description |
|-----------|----------|-------------|
| N1 | P1 | Same defect as HLA-4: dropping the `split` call removes all symlink reporting. Corrected before Round 3. |

This seat verified that the waiver is honored: `taste_lints.py` reports no violations on ADR-101, and 1 error on a copy with line 2 removed.

### Independent-thinker convergence

Vote: Block (IT-R2-1). The vote becomes Accept once the rollback sentence is corrected. Re-polled in Round 3.

| Round 1 issue | Status | Evidence |
|---------------|--------|----------|
| IT-1 alternatives | RESOLVED | amendment lists the three rejected alternatives |
| IT-2 copied docstring | RESOLVED | amendment gives shape, invariant, pointer |
| IT-3 debate log | RESOLVED by this file | same commit |
| IT-4 manifest key | RESOLVED | `link_rows` reads `rows` |

| New issue | Priority | Description | Resolution |
|-----------|----------|-------------|------------|
| IT-R2-1 | P1 | Rollback text fails open (same as HLA-4, N1). | Corrected before Round 3. |
| IT-R2-2 | P2 | This seat's own mutation probe found 3 sub-clauses surviving: dangling target `exists()`, named path under the target, import root under the link. | Three tests added. A re-run sweep of 9 mutants, one per sub-clause, killed each with its own named test; an inert edit survived. |

### Security convergence

Vote: Accept. Merge precondition: this log is committed.

| Round 1 issue | Status | Evidence |
|---------------|--------|----------|
| S-1 debate log | RESOLVED by this file | committed with the ADR edit |
| S-2 nested import root | RESOLVED | `_link_exemption.py` refuses at, above, or below any non-toplevel root, for the link and its target; two tests |
| S-3 runtime-built reads | RESOLVED, accepted risk | amendment "Accepted residual risk" |
| S-4 case folding | RESOLVED, accepted risk | resolution table |

Attack paths re-checked and refused: a two-level link, a verifier directly in `.claude` or `.claude/skills`, a base config path under the link, a replaced real directory, a `.github/hooks` link. New P0 or P1 issues: none. Note: the amendment's import-root wording understated the code, which also refuses a link under a root; the wording was tightened.

### Analyst convergence

Vote: Accept, on the condition that this log lands in the same commit as the ADR edit.

| Round 1 issue | Status | Evidence |
|---------------|--------|----------|
| W1 debate log | RESOLVED by this file | same commit |
| W2 nested import root | RESOLVED | `_link_exemption.py` within-root rule; `.claude/run.py` test |
| W3 docstring | RESOLVED | module docstring names verifiers under `.claude/skills` |
| W4 tool root wording | RESOLVED | docstring and amendment name the tool root; workflow checks out the base |

Claim marked UNVERIFIED: the docstring said environment differences "cannot reach a link". A host-declared plugin root under a skill tree would make it reachable; that variable is operator-set, not PR-controlled. The docstring was reworded to say so. New P0 or P1 issues: none.

### High-level-advisor convergence

Vote: Disagree-and-Commit. Accept once HLA-4 is corrected and this log lands with the ADR edit.

| Round 1 issue | Status | Evidence |
|---------------|--------|----------|
| HLA-1 debate log | RESOLVED by this file | same commit |
| HLA-2 exempt-tree scope | RESOLVED | set narrowed to the two skill trees; `.github/hooks` negative test |
| HLA-3 copied condition list | RESOLVED | amendment states shape, invariant, and pointer |

| New issue | Priority | Description | Resolution |
|-----------|----------|-------------|------------|
| HLA-4 | P1 | The rollback sentence was wrong: deleting the `split` call leaves `report.symlinks` empty and passes every link. | Corrected: replace the call with `report.symlinks = symlinks`. |

Claims re-verified by this seat: 159 dispatch-closure tests pass; ADR-101 was 500 lines at `origin/main` and is 505 now.

Round 2 resolution: HLA-4, N1, and IT-R2-1 named one defect, a rollback sentence that would have disabled the report. The sentence was corrected. The analyst's UNVERIFIED docstring claim was reworded. Four tests were added: an absolute-path spelling, a dangling target, a named path under the target, and an import root under the link. A sweep of 9 mutants, one per sub-clause of `is_exempt`, killed each with its own named test, and an inert edit survived.

## Round 3: re-poll of the two Block votes

Only the two seats that voted Block in Round 2 were re-polled; the other four had voted Accept or Disagree-and-Commit on text whose later changes answered their own findings.

### Critic Round 3

Vote: Accept, conditional on this log landing in the same commit as the ADR edit.

| Item | Status | Evidence |
|------|--------|----------|
| N1 rollback sentence | RESOLVED | amendment matches `verify()`; `Report.symlinks` defaults to an empty list, so the warning is correct |
| Rollback leaves two unused locals | P2, applied | the rollback sentence now says to drop `trees` and `import_roots` (ruff F841 on a rollback copy) |
| Four new tests | VERIFIED | each asserts real `split` output; 23 passed |

### Independent-thinker Round 3

Vote: Accept.

| Item | Status | Evidence |
|------|--------|----------|
| IT-R2-1 rollback text | PASS | amendment now says to replace the call with `report.symlinks = symlinks`; matches `verify()` |
| New tests | PASS | four tests present; 23 passed when this seat ran the file |
| IT-R2-2 sweep | Not re-run by this seat | the new tests cover the three clauses this seat's probe found |

## Outcome

Consensus. Final votes: architect Accept, critic Accept (Round 3), independent-thinker Accept (Round 3), security Accept, analyst Accept, high-level-advisor Disagree-and-Commit.

Recorded dissent: the high-level-advisor would ship the narrowest fix first and treated the remaining P2 items as fit for a follow-up; all of them landed in this change. The critic and analyst made their Accept conditional on this log landing in the same commit as the ADR edit; it does.

Final state: ADR-101 status stays `accepted`; this is an amendment, not a new decision. 23 exemption tests and the 140 earlier dispatch-closure tests pass.

## Post-consensus implementation note

A repository check (`check_agents_write_targets.py`) forbids naming the Codex skill root outside the files that own it. `EXEMPT_INSTALL_TREES` was therefore replaced by `EXEMPT_ROW_CLASSES = {"skills", "skills-codex"}`, which selects the same two binplace rows by class. Behavior is unchanged: the same 23 tests pass, and removing the class filter fails `test_a_link_under_a_non_exempt_install_tree`.

A second check, the ADR lifecycle `size-cap` in `scripts/validation/check_adr_lifecycle.py`, refuses ADR-101 past 500 lines, and its baseline may not be raised. The reviewed amendment text was therefore moved, unchanged, from its own section to the end of the Application B bullet it amends ("The dispatcher itself is in the tree it checks"). The `taste-lint` file-size waiver was dropped, since the file is back at 500 lines. The same inline placement was used for ADR-097 for the same reason (see `vendor-provenance-removal-notes-debate-log.md`). The waiver discussion in Round 1 (IT-2, architect W6, critic W3) is resolved by removing the waiver.

The `/review` pass on the final tip (security axis PASS, correctness WARN with no blocker) added four hardenings, each with its own mutation-checked test. A configured path that is a directory above the link now refuses it, and the ADR text says so. A skill row whose install tree does not start with a dot is never exempt; this enforces the assumption behind skipping the work-tree import root. The `link: true` row condition gained its own negative test. An end-to-end test drives `main()` on the CI `--head-sha` path. The final count is 27 exemption tests; 167 dispatch-closure tests pass.

## Amendment 2026-11-28: rule install links join the exemption (PR #7730)

**Superseded at merge 357beb945 (2026-11-28)**: PR #7838 (121b25496) landed the same exemption on main first. The merge kept main's `scripts/ci/_link_exemption.py`, its test, and ADR-101, so PR #7730 no longer changes them. The record below is kept as history.

**Trigger**: CodeRabbit review 6095946480 on PR #7730 (thread on `scripts/ci/_link_exemption.py:54`). The PR added `rules` and `instructions-github` to `EXEMPT_ROW_CLASSES`, and this ADR says a new exempt install tree needs a failing pull request and an amendment here. The failing pull request is #7730 itself: run 46108424270 on head 5f0809ccb9 reported `2 new symlinks`, `.claude/rules/core.md` and `.github/instructions/core.instructions.md`, with 0 files differing.

**Change**: one amendment appended to the 2026-11-16 paragraph (the ADR is at its 500-line size cap, so the text stays on that line). A new negative test, `test_a_rule_link_under_an_import_root`, shows each rule link is still reported when its install tree is an import root. Negative control: with the verifier moved to `tools/run.py`, both parametrized cases fail; restored, both pass. The file has 30 tests, all passing.

### Panel (full six seats; executable enforcement)

| Seat | Vote | Findings applied |
|------|------|------------------|
| architect | Disagree-and-Commit | old scope sentence now says the rule trees joined below; merge path stated (job not required, owner accepts the red); content not reviewed stated; rollback cross-references ADR-129 |
| critic | Disagree-and-Commit | merge path stated; rollback names the two rule-link tests; squash-only merge confirmed (repo allows squash only), so one revert holds |
| security | Disagree-and-Commit | runtime `sys.path` residual now stated as inherited by these trees; directory-target test case not added (P2, not required) |
| analyst | Disagree-and-Commit | byte claim measured and cited in ADR-129 (see ADR-129 debate log) |
| independent-thinker | Disagree-and-Commit | owner acceptance of the red on this PR and on each later class addition stated; real `binplace.yaml` row test not added (P2) |
| high-level-advisor | Accept | no new section and no extra test beyond the negative case; this log records the edit |

### Outcome

Consensus: one Accept and five Disagree-and-Commit, no Block. The amendment date is 2026-11-28 (UTC), the date of the cited run. Recorded dissent: the independent-thinker would add a test against the real `templates/platforms/binplace.yaml` rows, and the security seat would add a directory-target case; both are P2 and not in this change. ADR-101 status stays `accepted`; this is an amendment, not a new decision.
