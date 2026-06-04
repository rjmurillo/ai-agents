---
type: task
id: TASK-018
title: Skill Catalog Prune M2 Session Cluster
status: done
priority: P2
complexity: S
estimate: 3
created: 2026-06-04
updated: 2026-06-04
related:
  - DESIGN-018
  - REQ-018
blocked_by: []
blocks: []
assignee: copilot
---

<!-- orphan-ref-ignore-file -->
<!-- M2 deletion task: references to session-qa-eligibility and
     session-migration are intentional historical deletion targets. -->

# TASK-018: Skill Catalog Prune M2 Session Cluster

## Design Context

Implements DESIGN-018 for Issue #1946. The session-cluster M2 work keeps QA eligibility behavior in `session` and deletes the inactive migration skill after confirming active session logs are JSON at creation.

## Objective

Remove the `session-migration` skill and its tests, clean live references, regenerate mirrors, and verify no changed reference surface points callers at deleted skills.

## In Scope

- Delete `.claude/skills/session-migration/`.
- Delete `src/copilot-cli/skills/session-migration/`.
- Delete root `scripts/convert_session_to_json.py` and its tests.
- Update session-init, memory extraction, skill reference, evaluator, and allowlist documentation.
- Validate targeted tests, orphan references, generated mirrors, and plugin manifests.

## Out of Scope

- Rewriting `.github/workflows/ai-session-protocol.yml`.
- Migrating historical markdown archives.
- Creating a replacement migration skill or shim.

## Acceptance Criteria

- [x] TASK-018-AC1: `.claude/skills/session-migration/` does not exist.
- [x] TASK-018-AC2: `src/copilot-cli/skills/session-migration/` does not exist.
- [x] TASK-018-AC3: `session-init` guidance creates JSON logs directly and does not instruct callers to run migration.
- [x] TASK-018-AC4: `docs/skill-reference.md` identifies `session` as the QA eligibility owner.
- [x] TASK-018-AC5: `tests/evals/skills/triage-prompts.json` has negative-routing fixtures for old session skill names.
- [x] TASK-018-AC6: `uv run python -m pytest tests/skills/test_session_scripts.py tests/skills/session/ tests/skills/memory/test_extract_session_episode.py -q` passes.
- [x] TASK-018-AC7: scoped `orphan-ref-validator` passes on changed reference surfaces.
- [x] TASK-018-AC8: `python3 build/scripts/build_all.py --check` passes.
- [x] TASK-018-AC9: plugin manifest validation and parity checks pass.

## Files Affected

| File or directory | Action | Purpose |
|---|---|---|
| `.claude/skills/session-migration/` | DELETE | Remove source migration skill. |
| `src/copilot-cli/skills/session-migration/` | DELETE | Remove published mirror. |
| `scripts/convert_session_to_json.py` | DELETE | Remove root conversion helper. |
| `tests/skills/session/test_convert_session_to_json.py` | DELETE | Remove migration tests. |
| `tests/test_convert_session_to_json.py` | DELETE | Remove migration tests. |
| `tests/skills/test_session_scripts.py` | UPDATE | Drop deleted script import checks. |
| `.claude/skills/session-init/SKILL.md` | UPDATE | Remove migration routing. |
| `src/copilot-cli/skills/session-init/SKILL.md` | UPDATE | Mirror the session-init update. |
| `.claude/skills/memory/scripts/extract_session_episode.py` | UPDATE | Remove migration reference. |
| `src/copilot-cli/skills/memory/scripts/extract_session_episode.py` | UPDATE | Mirror the memory script update. |
| `scripts/modules/investigation_allowlist.py` | UPDATE | Remove stale QA eligibility consumer note. |
| `docs/skill-reference.md` | UPDATE | Document `session` as the surviving owner. |
| `tests/evals/skills/triage-prompts.json` | UPDATE | Add negative-routing fixtures. |
| `.claude/.claude-plugin/plugin.json` | UPDATE | Bump package version after deletion. |
| `src/copilot-cli/.claude-plugin/plugin.json` | UPDATE | Keep mirror version aligned. |

## Verification Evidence

- Targeted pytest: 204 passed.
- Scoped orphan-ref validator: `VERDICT: PASS`.
- Full generation check: `build_all_check_pass`.
- Plugin manifests: all validated.
- Plugin parity: versions match at `0.5.111`.
