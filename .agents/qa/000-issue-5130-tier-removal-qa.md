---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-5174-b3bfa3aaa-remove-agent-tier-hierarchy-replace.json
qaCommit: 2221006824b0a485ddc8cd9d02947df9f993981a
---

# QA report: issue #5130, remove the agent tier hierarchy

## Scope validated

Replacement of the 4-tier agent hierarchy with functional `role:` metadata
across governance docs, 186 agent files in six trees, three consumers, and
their tests.

## Evidence

### Test suite

`uv run pytest tests/ -q -p no:randomly --ignore=tests/mutation`

```
3 failed, 27856 passed, 74 skipped, 2 warnings in 1244.89s (0:20:44)
```

All three failures were investigated and resolved:

| Failure | Cause | Resolution |
|---|---|---|
| `test_monolith_section_classification.py::test_every_monolith_section_is_classified[AGENT-SYSTEM.md]` | Renaming section 2.5 orphaned its row in `.agents/analysis/1769-monolith-section-classification.md` | Row updated with the new title and 58-line count. Re-run: 9 passed |
| `test_mutation_workspace_signals.py::test_catchable_signal_removes_marker_and_scratch[2]` | Collateral from force-killing a pytest run mid-suite to clear a mutation marker, not from this change | Re-run in isolation: 8 passed |
| `test_mutation_workspace_signals.py::test_concurrent_runs_use_distinct_markers_and_worktrees` | Same cause | Same. Re-run: 8 passed |

`tests/mutation/` was excluded from the timed run because those tests exercise
the mutation harness (unrelated to this change) and hold the git worktree
markers the pre-push `mutation-safety` gate reads. `test_mutation_workspace_signals.py`
was run separately and passes.

### Directly affected tests

`uv run pytest tests/test_openclaw_bridge.py tests/build_scripts/test_generate_agent_catalog.py tests/test_validate_copilot_agent_frontmatter.py -q`: 80 passed, including four new cases for the unknown-role fallback (positive, two negative, one edge).

### Generators and validators

| Command | Result |
|---|---|
| `uv run python build/generate_agent_catalog.py --check` | OK: docs/agent-catalog.md matches templates/agents/ |
| `uv run python build/scripts/detect_agent_drift.py` | merge-resolver baselined at 20.7% on both comparisons, unchanged; no new drift |
| `uv run python scripts/validation/validate_copilot_agent_frontmatter.py` | PASS, all 31 Copilot agent files |
| `uv run python build/scripts/build_all.py` | Written 51, no errors |
| `uv run ruff check <changed .py>` | All checks passed |
| `uv run mypy tests/build_scripts/test_generate_agent_catalog.py` | Success, no issues |

### Migration completeness

`grep -rn '^\s*tier:' templates/agents .claude/agents .github/agents src/claude src/vs-code-agents src/copilot-cli/agents` returns 0 matches.

Both key shapes were migrated: the top-level `tier:` (136 files) and the form
nested under `metadata:` (50 files). The nested form was missed on the first
pass and caught by the install-parity gate.

## Not validated

- The six-agent `adr-review` debate **ran on 2026-08-20**, in a later session
  with subagent invocation available, and its votes are recorded in
  `.agents/critique/5130-tier-hierarchy-removal-debate-log.md`. Seven agents,
  the six `adr-review` roles plus a `qa` pass: 4 ACCEPT, 1
  DISAGREE-AND-COMMIT, 2 BLOCK. Both P0s (a `security: 2` weight attributed to
  ADR-009 that ADR-009 does not grant, and two false citations in the debate
  log's own finding-5 answer) were fixed before the log was updated.

  **`architect`'s BLOCK has since been discharged.** Its P0 was that no ADR
  recorded the tier-to-role decision. The maintainer directed one be written,
  and `.agents/architecture/ADR-098-agent-role-metadata-replaces-tier-hierarchy.md`
  now carries it. The architect pass confirmed the discharge in the follow-on
  debate: "Yes."

  Editing an ADR re-fires `adr-review`, so the six roles ran a second time
  against ADR-098 itself: 2 ACCEPT, 1 DISAGREE-AND-COMMIT, 3 BLOCK. **Every
  block in that round was on the record, not the decision.** All three
  converged on one Context paragraph wrong three ways (24 agents ranked not
  nine; seven of the nine empowered agents deny delegation not six; two lack
  the line rather than one). Corrected against a re-measurement, along with
  eleven smaller findings.

  **What is still not validated is a re-vote.** Both rounds' clearing
  conditions are met by construction; no reviewer was re-run against the
  corrected artifacts. That distinction is recorded in the debate log rather
  than smoothed over.
- **Closed since**: three of the gaps below were implemented and are no longer
  open. `test_role_vocabulary_agrees_across_consumers` pins the four copies of
  the role vocabulary, `test_agents_present_in_several_trees_declare_one_role`
  catches cross-tree disagreement against the canonical template, and
  `test_every_agent_file_in_a_configured_tree_is_a_readable_definition` makes a
  malformed agent file fail closed instead of dropping out of the corpus. Each
  was verified against a planted violation, not from a passing run. A fourth
  guard, `test_the_role_inertness_sentence_survives_in_agent_system`, pins the
  sentence ADR-098 names as the mitigation for its Standing Dissent, which three
  passes of the ADR-098 debate found was held by nothing.

  Two residuals remain and have no fix: the equality test cannot see coordinated
  drift across all four copies, and a new tree using a bare `.md` suffix that
  also omits `role` stays invisible to discovery.

- The gaps as originally found by the `qa` pass, kept for the record: the four copies of `_KNOWN_ROLES` have no equality test
  (adding a fifth value to one copy leaves the suite green); nothing asserts
  that copies of the same agent agree across trees (setting
  `.claude/agents/janitor.md` to `strategic` against the template's `support`
  leaves 119 tests green and the drift detector silent); and a malformed agent
  file in a configured tree drops out of the corpus before the known-role
  check sees it. Copilot has since raised all three independently.
- `.agents/prototypes/agents/*.compressed.md` still carry `metadata.tier`.
  They are frozen prototype measurement artifacts for issue #1738
  (`prototype: true`) and were left unmodified so the recorded measurement
  stays faithful.

## Addendum: findings after the first QA pass

Twenty-nine review findings landed after the original run. Each is covered:

| Finding | Source | Verification |
|---|---|---|
| OpenClaw export read only the top-level key, so nested-shape agents resolved to `support` | spec reviewer | 5 new cases in `tests/test_openclaw_bridge_roles.py`, incl. a negative control for unmigrated `metadata.tier`. Claude tree now resolves 4 strategic / 5 coordinator / 11 executor / 11 support |
| Frontmatter validator accepted any string for `role`, so `buidler` became `support` | Copilot review | `role` required and constrained to the four known values; 6 new cases incl. the typo and a stale `builder` value |
| Debate log claimed all three files quote ADR-009 verbatim | Copilot review | Replaced with a byte-measured per-file table. At the time: SESSION-PROTOCOL.md summarized, orchestrator-routing carried the table only. That file has since been deleted upstream, and the log's reproduction block no longer opens it |
| Taste ratchet regressed 577 > 576 (test file crossed 500 lines) | pre-push merge-tree ratchet | Split by concern into two modules, 356 and 222 lines; ratchet back to `OK (count == baseline 576)` |
| No gate asserted zero `tier:` keys across the six agent trees, so a reintroduced `tier:` would pass every check | spec reviewer | `tests/test_agent_role_metadata_migration.py` reads both frontmatter shapes across all six trees; a discovery test acts as a negative control against vacuous globs |
| Nothing pinned the escalation target in the routing docs, which is how the stale `escalate_to_architect` survived | spec reviewer | Parametrized guard over AGENT-SYSTEM.md and orchestrator-routing-algorithm.md; verified non-vacuous by checking out origin's stale doc, where it fails. SESSION-PROTOCOL.md was a third case until PR #5179 deleted the file; see the row below |
| Tree roster was a one-directional config set: a renamed or seventh tree went unchecked | Cursor Bugbot | Roster now derived from `AGENT_TREES` in `validate_agent_matrix_refs.py`; a disk walk asserts nothing lives outside it. Verified by planting a seventh tree with `tier: builder`, which fails the walk while the old key check passes right through it |
| An agent declaring no role at all passed; the bridge exports absent as `support` | Copilot | Every agent definition must declare a known role. Verified against a planted role-less agent |
| Unparseable frontmatter was dropped from the corpus, so a malformed agent could keep `tier:` | Copilot | Tier check adds a textual sweep of the raw block. Verified against a planted agent whose frontmatter does not parse and carries `tier: builder` |
| Contradictory `role` in the two shapes failed nothing | spec validator | Now an error. Verified against a planted `executor` vs `strategic` file |
| Session artifact `endingCommit` was stale at `cc829f98be` | Copilot | Repointed to the final work commit; episode regenerated |
| Roster and discovery compared paths in two forms, so on Windows every real tree read as unconfigured | Cursor Bugbot | `as_posix()` on both sides. Measured with `PureWindowsPath`: six unconfigured before, zero after |
| The converse guard walked the filesystem, racing xdist siblings that create worktrees; CI `bulk-nested` went red while the same command passed locally twice | CI | Switched to `git ls-files`. Verified both ways: an untracked copy of `templates/agents` planted in the repo root no longer trips it, a staged `src/seventh-tree` still does |
| Secondary and primary rate limits shared one branch, so secondary callers were told to wait for a reset window that does not exist | Copilot | Split, matching the canonical pair in `github_core/api.py:330`. Three tests assert both directions |
| `.agents/SESSION-PROTOCOL.md` deleted upstream by PR #5179 while this branch edited it | `origin/main` at ba541c21f | Took the deletion on merge. `docs/agent-catalog.md` regenerated rather than hand-merged, the escalation guard no longer parametrizes over the deleted path, and the debate log records that the `adr-review` gate is moot rather than met |
| Discovery matched only valid roles, so a new tree with `role: strategc` was invisible to the guard meant to catch it | Copilot | Discovery is value-independent; type check retained because `tier` is overloaded (skills `3`, memories `2`, both int). Reproduced with a tracked `src/new-agents/foo.agent.md`, which now fails |
| Role vocabulary table listed `memory`, a skill, as a support-role agent | Copilot | Replaced with `skillbook`; other 17 names verified; a test now pins every cell against shipped frontmatter |
| Generic `API rate limit exceeded` cannot prove primary exhaustion, but the message claimed it | Copilot | Explicit-secondary branch unchanged; generic branch now gives advice valid under either limiter. Headers not fetched, and the comment records why (#4690 budget, and `--include` would change parsed stdout) |
| Two backticked paths in `## Changes` cite files this PR does not change, failing the description gate | CI `Validate PR` | Moved both citations to Notes for Reviewers. Re-extracted all 14 paths in that section; none is now absent from the diff |
| Debate log's reproduction block still opened the deleted `.agents/SESSION-PROTOCOL.md`, so running it raised `FileNotFoundError` | Copilot | Path dropped from the block and the change noted inline. Re-ran it: AGENT-SYSTEM.md carries table and protocol, orchestrator-routing carries the table, both name `high-level-advisor` |
| Negative control promised "absent or misspelled" but every case carried a role or tier, so a new tree omitting `role` entirely stayed invisible | Copilot | Second discovery signal added: a distinctive agent suffix on a real agent definition. Measured that `.agent.md` and `.shared.md` occur only in configured trees. Verified with a tracked `src/roleless-tree/foo.agent.md` carrying no role, which now fails the converse guard |
| Suffix signal sat behind a successful YAML parse, so a malformed agent in a new tree stayed invisible | Copilot | Suffix checked first, without parsing. Verified with a tracked `src/new-agents/foo.agent.md` carrying invalid frontmatter: invisible before, fails the converse guard now |
| An *unterminated* frontmatter block returned None from both extractors, so the raw `tier:` sweep skipped the file entirely | spec validator | Sweep falls back to whole file text when the fence cannot be delimited. Zero hits across all 190 agent files, so no false positives. Verified with `.claude/agents/zz-evader.md` carrying an unclosed block and `tier: builder` |
| `blocking` examined every voter, so a non-negotiable on the *winning* recommendation forced escalation, contradicting the docstring three lines above | Copilot | Narrowed to dissenters. Simulated both ways: architect=A/non-negotiable vs implementer=B escalated before, votes A now; a real dissenter still escalates |
| ADR-078 described orchestrator as `metadata.tier: manager`, a field this PR deletes | Copilot (x2), spec validator | Owner chose correction here over a follow-up PR. Seven phrases fixed against the shipped frontmatter (36, 79, 110, 111, 123, 206, 212); four other `tier` uses left alone as different concepts. The `adr-review` debate has since run and reviewed this correction specifically: its architect pass is why the option-C clause was re-grounded on the skill/agent boundary rather than renamed to a role boundary, a role granting nothing at runtime being unable to be broken. Gate confirmed a string check by negative control: `ADR-ZZZ` fails, `ADR-078` passes, so the green gate is still not evidence of review |
| The ADR-078 correction missed line 111, `orchestrator is a manager agent`, one sentence after a line I had classified as out of scope | spec-coverage CI on 074a3a0db | Sixth phrase fixed, plus line 110's `different tiers` to `different layers`. Root cause: adjudicating the word `tier` use-by-use instead of sweeping for the rank vocabulary. `grep -c ' manager'` on the file now returns 0, which is the check that would have caught it |
| PR body pinned a head SHA that went stale on every push, three revisions running | Copilot | Body no longer names a head. The head-bound record is `qaCommit` in this file, rebound per push; the body is narrative |
| Migration test module hit 531 lines against the 500-line taste ceiling while the description claimed lint clean | Copilot | Split by concern into `agent_metadata_helpers.py` (245), `test_agent_tree_discovery.py` (136), and the migration module (210). taste-lints reports no violations on any of the three; 11 tests still pass |
| `escalate_to_high_level_advisor` was called but never defined, and the next line indexed `positions[winner]` with a non-participant | Copilot | Escalation now appends an explicit result naming the arbiter and skips the winner branch. No undefined call, no bad lookup |
| Serena memory gave 186 as the PR file total | Copilot | 186 is the agent metadata count and is the durable figure. The PR-wide total was 208 when first flagged and is 212 as of this rebind; it moves on every review round, so the memory marks it a snapshot and carries the ratio as the lesson rather than the second number. Copilot re-flagged the 208 after it went stale, which is the behaviour that argued for the snapshot label |
| Body still carried two head-bound claims after declaring it no longer pins a head: "exit 0 on the current head" and "run to completion on the pushed head" | Copilot | Both narrowed to "the run for one push", pointing at `qaCommit` for the attested commit. The declaration and the prose now agree |
| Correcting ADR-078 re-arms `adr-review`, which the body still described as moot | this session, on re-reading the body after the edit | Acceptance box moved from `[~]` to `[ ]` and the section retitled. The criterion was unmet and applicable, which is worse than moot and was the honest state at the time. **Superseded: the debate has since run** against the ADR-078 correction and the wider change; see the row below and the debate log |
| The `adr-review` debate ran, so every artifact saying it had not was stale | a later session with subagent invocation available | Seven agents, 4 ACCEPT / 1 D&C / 2 BLOCK. Two P0s found and fixed: `security: 2` attributed to ADR-009 (`grep -c -i security` on the ADR returns 0, and ADR-009:90 grants only `architect > implementer`), and two false citations in this branch's own debate log. `architect`'s BLOCK on the absence of an ADR recording the decision is open and is a maintainer call under `AGENTS.md` "Ask First: New ADRs". Corrected here, in the debate log, and in ADR-078's note; the PR description is the remaining stale surface |
| My ADR-078 correction half-converted the skill-versus-agent axis: line 212 read `at skill tier ... at the agent layer` in one sentence | adr-review debate: architect, critic, independent-thinker, security, independently | `layer` throughout the ADR and both autoplan SKILL.md copies (Copilot mirror by regeneration, not by hand). `tier` now means only Cynefin complexity and the opus model tier |
| The Rationale cited `role:` as evidence for a routing constraint, while `AGENT-SYSTEM.md:836-840` added by this same PR says `role` grants and withholds nothing at runtime | adr-review debate: critic, security | Rewritten: the layering is the record's own contract, not a property read off metadata; containment comes from the platform. The pre-edit sentence had a real mechanism, `validate_tier_sequence`, which this PR deletes |
| ADR-078 Implementation Notes named `build/generate_agents.py` for `docs/agent-catalog.md`, which that script does not write | adr-review debate: architect | Both generators named correctly and the wrong trigger fixed. Verified: 0 catalog references in `generate_agents.py`; `generate_agent_catalog.py:51` owns the path; the catalog changed 33 lines in this PR from a frontmatter change |
| The ADR edit skipped the `date` bump `adr-best-practices.md:37` rule 1 requires, and left no in-file trace of the correction | adr-review debate: independent-thinker | `date` bumped, original decision date kept in prose, dated clarification note added to `## Status` on the ADR-068:17 precedent |
| Option C's rejection clause became circular after my rewrite and duplicated its own verdict cell | adr-review debate: critic, architect | Replaced with the external checkable consequence: a blocking session-start checklist cannot live in a surface that fires implicitly |
| "Six phrases" stated above a seven-row table | adr-review debate: analyst, critic, independent-thinker | Corrected to seven across six hunks here and in the PR body. Commit `d5453ca8a` says "sixth" and is immutable, so history and the log disagree by one; recorded rather than hidden |
| A security finding claimed the closed role set is unenforced on the Claude trees, proven by executing the validator for `All 0 files` | adr-review debate: security | Execution evidence correct, conclusion overstated. `test_every_agent_definition_declares_a_known_role` enforces the closed set across all six trees in both shapes, so a `strategoc` typo fails. Narrowed to a validator shape-blindness follow-up and recorded as a correction in the debate log |
| Two independent `adr-review` debates ran on this branch, concurrently and unaware of each other: six agents in one session (3 ACCEPT / 3 D&C / 0 BLOCK) and seven in another (4 ACCEPT / 1 D&C / 2 BLOCK) | both sessions, on merging | Both results are kept above rather than reconciled into one verdict. They disagree, and the disagreement is the finding: the seven-agent run caught two P0s the six-agent run missed, including a false ADR-009 citation. A single debate is not evidence of correctness, and averaging two into one would destroy the only signal that says so |

Re-verified on the attested commit: 11 migration guards, 44 bypass-checker tests, taste ratchet OK
with slack, ruff and mypy clean on changed files. The scoped pre-push pytest gate ran to completion
over all four partitions: 27493 + 24 + 46 + 30 passed, zero `FAILED` or `ERROR` lines, exit 0.

`qaCommit` names the commit this report attests to. Commits after it, if any, are documentation-only
edits to this file and the PR description; no code or agent metadata changed under them. That
distinction is stated rather than implied, because a `qaCommit` that silently lags the head is the
same stale-evidence defect the description stopped committing when it dropped its head SHA.

Earlier, after merging `origin/main` at ba541c21f: 295 tests across seven suites,
`generate_agent_catalog.py --check` OK, `validate_copilot_agent_frontmatter.py` PASS on 31 files,
`run_install_parity_ci.py` OK, `merge_tree_ratchet_check.py` OK against the new base.

Before that merge, on 64b86fb2b: the CI `bulk-nested` partition reproduced locally via
`run_pytest_selected.py`, 15074 passed and 62 skipped, which is the partition that was red.
Full suite under the repo's own partition contract: 27820 passed and 74 skipped in bulk,
85 passed in the three process-sensitive modules run serially.

An earlier full run here reported 7 failures. Those were caused by passing `-n 4` across the
whole suite, which violates the contract in `tests/validation/test_pytest_parallelism_policy.py`
that process-sensitive modules stay serial. All 7 pass serially. The methodology was wrong,
not the code, and the number is recorded here rather than quietly dropped.

`ruff` and `mypy` clean on all 12 changed Python files, `generate_agent_catalog.py --check` OK,
`validate_copilot_agent_frontmatter.py` PASS on 31 files, `run_install_parity_ci.py` OK,
`taste_count_ratchet.py` at baseline 576.

Every guard added for the findings above was run against a planted violation and fails on it. None is
asserted from a passing run alone, because a guard that has only ever passed has not been shown to work.

## Addendum: the ADR-098 review re-run (round 3)

`qaCommit` rebound to `3f5fb9c4e`. What was verified at that commit:

| Check | Command | Result |
|---|---|---|
| Role and discovery guards | `pytest tests/test_agent_role_metadata_migration.py tests/test_agent_tree_discovery.py tests/build_scripts/test_validate_agent_matrix_refs.py -q` | 166 passed |
| Monolith section classification | `pytest tests/test_monolith_section_classification.py -q` | 8 passed (the AGENT-SYSTEM.md section 2.5 edit did not orphan its row) |
| Lint | `ruff check` on the three changed Python files | All checks passed |
| Format | `ruff format --check tests/test_agent_role_metadata_migration.py` | Already formatted. The other two files were format-dirty at HEAD before this change and were not reformatted, to keep the diff on the change |
| Dash prohibition | scan of all seven changed files | 0 violations |

Two negative controls, both run rather than reasoned about:

- **The new nested guard.** Planted `.claude/agents/probe/zzbad.md` with
  unbalanced YAML and `role: strategc`. Before: `validate_agent_matrix_refs.py`
  exit 0, 27 role tests green. After: exit 2 naming the file. Removed: exit 0.
- **The scoped inertness pin.** Replacing the sentence in
  `.agents/AGENT-SYSTEM.md` fails
  `test_the_role_inertness_sentence_survives_in_agent_system`; restoring it
  passes.

One reviewer finding was refuted rather than fixed. The `architect` pass held
that a misplaced well-formed agent in a subdirectory escapes every guard.
Negative control: a planted `.claude/agents/probe/zzprobe.md` with valid
frontmatter makes the validator exit 2 with "agent definition in a
subdirectory", covered since issue #3601. No change was made for it, and no
residual was recorded, because recording a hole the tree already closes would
make ADR-098 false in the other direction.

Not validated at this commit: the full `pytest tests/` suite. The timed run in
the Evidence section above stands for the migration itself; this addendum's
changes touch one validator, three test files, and four documents, and the
suites covering them are named above. The pre-push `python-tests` job is the
gate that runs the rest.

### Final-gate evidence, run at `0a6870c19`

`Validate Spec Coverage` marked two acceptance criteria PARTIAL for lack of
evidence in this file rather than for lack of the work. Both commands were run
and their output is recorded here rather than only asserted in the PR body.

`uv run python scripts/validation/run_install_parity_ci.py`, exit 0:

```
Fetching main for diff base...
Running validate_install_parity.py against origin/main...
install-parity: OK
```

`uv run python scripts/validation/pre_pr.py`, exit 0, tail:

```
[PASS] Workflow Local Run (0.43s)
[PASS] Review Marker (SHA-bound /review) (0.07s)
[PASS] Instruction Budget (always-on) (0.13s)
[PASS] Always-on Corpus Claims (0.99s)

RESULT: All validations passed
```

Push landed, verified by the two commands `pre_pr.py` names:
`git rev-parse HEAD` and `git ls-remote origin claude/pr-5174-merge-review-gvrype`
both report `0a6870c1956fe490c8e1bce1d2425b5291e15ebf`.

The validator's second PARTIAL, that "the records state that reviewers were not
re-run after corrections", was true of the artifact it read and is no longer
true of the tree. It ran at 23:15Z against a PR body that still said the debate
ran three times with every clearing condition met by construction. Round 3 had
been pushed nine minutes earlier but the body describing it had not. The debate
log's round-3 section and the rewritten body now both record three re-run
lenses and their final votes. One limit stands and is stated in both places:
`critic` was not re-run a second time against the corrected number its BLOCK
named.

### Round-4 review fixes

`qaCommit` rebound. Verified at that commit:

| Check | Result |
|---|---|
| `pytest tests/test_agent_role_metadata_migration.py tests/test_agent_tree_discovery.py tests/build_scripts/test_validate_agent_matrix_refs.py -q` | 166 passed |
| `build/scripts/validate_agent_matrix_refs.py` | exit 0 |
| `ruff check` on the two changed Python files | All checks passed |
| Dash scan on the four changed files | 0 violations |

The corpus counts in this round are the measurement, not a repetition of one:
`_agent_files()` returns **190**, `_agent_definitions()` returns **186**, and
the difference is the four allowlisted siblings. The docstring that had said
175 and the comment quoting it were both stale, and both are updated together
with the figure dated.

One finding in this batch needed no code change: Copilot reported the PR body
still claiming 25 wrong roles in a default export. The body had already been
rewritten to 16 before the review was generated. It now states 16, and quotes
the old 25 only inside a labeled note recording that the number was wrong and
who caught it.
