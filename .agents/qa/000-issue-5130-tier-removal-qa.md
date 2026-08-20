---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-5174-b3bfa3aaa-remove-agent-tier-hierarchy-replace.json
qaCommit: 64b86fb2b953b908d4889e1eb4c70560718ce6f8
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

Fourteen review findings landed after the original run. Each is covered:

| Finding | Source | Verification |
|---|---|---|
| OpenClaw export read only the top-level key, so nested-shape agents resolved to `support` | spec reviewer | 5 new cases in `tests/test_openclaw_bridge_roles.py`, incl. a negative control for unmigrated `metadata.tier`. Claude tree now resolves 4 strategic / 5 coordinator / 11 executor / 11 support |
| Frontmatter validator accepted any string for `role`, so `buidler` became `support` | Copilot review | `role` required and constrained to the four known values; 6 new cases incl. the typo and a stale `builder` value |
| Debate log claimed all three files quote ADR-009 verbatim | Copilot review | Replaced with a byte-measured per-file table; SESSION-PROTOCOL.md summarizes, orchestrator-routing carries the table only |
| Taste ratchet regressed 577 > 576 (test file crossed 500 lines) | pre-push merge-tree ratchet | Split by concern into two modules, 356 and 222 lines; ratchet back to `OK (count == baseline 576)` |
| No gate asserted zero `tier:` keys across the six agent trees, so a reintroduced `tier:` would pass every check | spec reviewer | `tests/test_agent_role_metadata_migration.py` reads both frontmatter shapes across all six trees; a discovery test acts as a negative control against vacuous globs |
| Nothing pinned the escalation target in the routing docs, which is how the stale `escalate_to_architect` survived | spec reviewer | Parametrized guard over AGENT-SYSTEM.md, SESSION-PROTOCOL.md, and orchestrator-routing-algorithm.md; verified non-vacuous by checking out origin's stale doc, where it fails |
| Tree roster was a one-directional config set: a renamed or seventh tree went unchecked | Cursor Bugbot | Roster now derived from `AGENT_TREES` in `validate_agent_matrix_refs.py`; a disk walk asserts nothing lives outside it. Verified by planting a seventh tree with `tier: builder`, which fails the walk while the old key check passes right through it |
| An agent declaring no role at all passed; the bridge exports absent as `support` | Copilot | Every agent definition must declare a known role. Verified against a planted role-less agent |
| Unparseable frontmatter was dropped from the corpus, so a malformed agent could keep `tier:` | Copilot | Tier check adds a textual sweep of the raw block. Verified against a planted agent whose frontmatter does not parse and carries `tier: builder` |
| Contradictory `role` in the two shapes failed nothing | spec validator | Now an error. Verified against a planted `executor` vs `strategic` file |
| Session artifact `endingCommit` was stale at `cc829f98be` | Copilot | Repointed to the final work commit; episode regenerated |
| Roster and discovery compared paths in two forms, so on Windows every real tree read as unconfigured | Cursor Bugbot | `as_posix()` on both sides. Measured with `PureWindowsPath`: six unconfigured before, zero after |
| The converse guard walked the filesystem, racing xdist siblings that create worktrees; CI `bulk-nested` went red while the same command passed locally twice | CI | Switched to `git ls-files`. Verified both ways: an untracked copy of `templates/agents` planted in the repo root no longer trips it, a staged `src/seventh-tree` still does |
| Secondary and primary rate limits shared one branch, so secondary callers were told to wait for a reset window that does not exist | Copilot | Split, matching the canonical pair in `github_core/api.py:330`. Three tests assert both directions |

Re-verified on this commit: the CI `bulk-nested` partition reproduced locally via
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
