---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-5174-b3bfa3aaa-remove-agent-tier-hierarchy-replace.json
qaCommit: 37b854c478ae68a9929fb58042cf42217614ee38
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

- The six-agent `adr-review` debate that `AGENTS.md` fires on a
  `.agents/SESSION-PROTOCOL.md` edit did not run; the authoring session had
  subagent invocation disabled. Recorded in the first section of
  `.agents/critique/5130-tier-hierarchy-removal-debate-log.md`.
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
| ADR-078 described orchestrator as `metadata.tier: manager`, a field this PR deletes | Copilot (x2), spec validator | Owner chose correction here over a follow-up PR. Five phrases fixed against the shipped frontmatter; four other `tier` uses left alone as different concepts. No `adr-review` ran, and the debate log says so. Gate confirmed a string check by negative control: `ADR-ZZZ` fails, `ADR-078` passes |
| PR body pinned a head SHA that went stale on every push, three revisions running | Copilot | Body no longer names a head. The head-bound record is `qaCommit` in this file, rebound per push; the body is narrative |
| Migration test module hit 531 lines against the 500-line taste ceiling while the description claimed lint clean | Copilot | Split by concern into `agent_metadata_helpers.py` (245), `test_agent_tree_discovery.py` (136), and the migration module (210). taste-lints reports no violations on any of the three; 11 tests still pass |
| `escalate_to_high_level_advisor` was called but never defined, and the next line indexed `positions[winner]` with a non-participant | Copilot | Escalation now appends an explicit result naming the arbiter and skips the winner branch. No undefined call, no bad lookup |
| Serena memory gave 186 as the PR file total | Copilot | 186 is the agent metadata count; the PR changed 208 files. Both now labelled |
| Body still carried two head-bound claims after declaring it no longer pins a head: "exit 0 on the current head" and "run to completion on the pushed head" | Copilot | Both narrowed to "the run for one push", pointing at `qaCommit` for the attested commit. The declaration and the prose now agree |
| Correcting ADR-078 re-arms `adr-review`, which the body still described as moot | this session, on re-reading the body after the edit | Acceptance box moved from `[~]` to `[ ]` and the section retitled. The criterion is unmet and applicable, which is worse than moot and the honest state. Auto-merge will not wait for it; flagged to the maintainer rather than disabled here |

Re-verified on this head: 11 migration guards, 44 bypass-checker tests, taste ratchet OK with slack,
ruff and mypy clean on changed files.

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
