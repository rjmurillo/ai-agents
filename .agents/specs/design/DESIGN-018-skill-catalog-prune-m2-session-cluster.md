---
type: design
id: DESIGN-018
title: Skill Catalog Prune M2 Session Cluster
status: implemented
priority: P2
related:
  - REQ-018
adr: []
created: 2026-06-04
updated: 2026-06-04
author: richard
---

<!-- orphan-ref-ignore-file -->
<!-- M2 deletion design: references to session-qa-eligibility and
     session-migration are intentional historical deletion targets. -->

# DESIGN-018: Skill Catalog Prune M2 Session Cluster

## Requirements Addressed

- REQ-018 (all six acceptance criteria)

## Design Overview

Remove the deprecated migration skill, remove its published Copilot CLI mirror, update routing guidance, and keep session QA eligibility under the `session` skill. The design is subtractive: no replacement migration module is introduced.

## Component Architecture

### Component 1: Source Skill Deletion

**Purpose:** Remove the source skill for the inactive markdown-to-JSON migration path.

**Responsibilities:**

- Delete `.claude/skills/session-migration/SKILL.md`.
- Delete `.claude/skills/session-migration/scripts/convert_session_to_json.py`.
- Delete `.claude/skills/session-migration/tests/test_convert_session_to_json.py`.
- Delete root `scripts/convert_session_to_json.py` and tests tied to it.

**Interfaces:** None. The migration entrypoint is removed.

### Component 2: Published Mirror Cleanup

**Purpose:** Keep the Copilot CLI mirror aligned with the source skill catalog.

**Responsibilities:**

- Delete `src/copilot-cli/skills/session-migration/`.
- Run `python3 build/scripts/build_all.py --check`.
- Validate plugin manifests and manifest parity after version bump.

**Interfaces:** `build/scripts/build_all.py` reads `.claude/skills/` and generated platform configuration.

### Component 3: Routing and Reference Cleanup

**Purpose:** Replace active references to deleted skills with the surviving owner.

**Responsibilities:**

- Update `session-init` guidance to describe JSON-at-creation without a migration step.
- Update memory extraction guidance so episode extraction no longer routes through migration.
- Update `docs/skill-reference.md` to describe the `session` skill as the owner of eligibility checks.
- Update `tests/evals/skills/triage-prompts.json` to negative-routing fixtures.

**Interfaces:** Human-facing skill documentation and evaluator fixtures.

## Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Migration replacement | None | Active session logs are JSON at creation; historical markdown logs are an archive. |
| QA eligibility owner | `session` skill | The interface and ADR-034 allowlist already live there. |
| Stale reference handling | Negative-routing fixtures | Agents need to answer old names safely instead of invoking deleted skills. |
| Mirror verification | `build_all.py --check` plus plugin manifest validators | Matches repository generation and packaging gates. |

## Security Considerations

No authentication, authorization, secrets, PII, or external input surface is added. Deleting the converter reduces attack surface by removing a file parsing path.

## Testing Strategy

| Test | Type | Command | Pass Condition |
|---|---|---|---|
| Targeted session and memory tests | pytest | `uv run python -m pytest tests/skills/test_session_scripts.py tests/skills/session/ tests/skills/memory/test_extract_session_episode.py -q` | Exit 0 |
| Orphan references on changed surfaces | CLI validator | `python3 .claude/skills/orphan-ref-validator/scripts/scan.py --output human --targets ...` | `VERDICT: PASS` |
| Generated mirror check | Build validator | `python3 build/scripts/build_all.py --check` | Exit 0 |
| Plugin manifest validation | Build validator | `python3 build/scripts/validate_plugin_manifests.py --manifest .claude/.claude-plugin/plugin.json --manifest src/copilot-cli/.claude-plugin/plugin.json` | Exit 0 |
| Manifest parity | Build validator | `python3 build/scripts/check_plugin_manifest_parity.py` | Exit 0 |

## Open Questions

None for M2. The workflow cleanup noted in REQ-018 is separate follow-up work.
