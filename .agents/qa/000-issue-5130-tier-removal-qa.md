---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-5174-b3bfa3aaa-remove-agent-tier-hierarchy-replace.json
qaCommit: 4557cdb9592eb595c4c1b09ff0901eabc4752f69
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
