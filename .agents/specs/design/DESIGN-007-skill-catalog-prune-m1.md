---
type: design
id: DESIGN-007
title: Skill Catalog Prune M1
status: implemented
priority: P2
related:
  - REQ-007
adr: []
created: 2026-05-09
updated: 2026-05-10
author: richard
---

<!-- orphan-ref-ignore-file -->
<!-- M1 deletion design: every skill_name reference (doc-coverage, doc-sync,
     workflow) and proposed-but-not-built script reference is intentional
     historical documentation; orphan-ref-validator must skip this file. -->

# DESIGN-007: Skill Catalog Prune M1

## Requirements Addressed

- REQ-007 (all five acceptance criteria)

## Design Overview

Remove three skill directories, update one cross-reference file, delete four dead test cases, and regenerate the published copilot-cli skill copy. No new code is written. No abstractions are introduced. The change is purely subtractive.

## Component Architecture

### Component 1: Skill Directory Deletion

**Purpose:** Remove the source directories for the three deprecated skills.

**Responsibilities:**
- Delete `.claude/skills/doc-coverage/` (contains `SKILL.md` and `scripts/check_docs.py`)
- Delete `.claude/skills/doc-sync/` (contains `SKILL.md` and `references/` subdirectory)
- Delete `.claude/skills/workflow/` (contains `SKILL.md`, `modules/`, and `scripts/`)

**Interfaces:** None. Pure filesystem deletion.

### Component 2: Published Skill Copy Cleanup

**Purpose:** Remove stale published copies in `src/copilot-cli/skills/` that were generated from the now-deleted source directories.

**Responsibilities:**
- Delete `src/copilot-cli/skills/doc-coverage/` (auto-generated mirror)
- Delete `src/copilot-cli/skills/doc-sync/` (auto-generated mirror)
- Run `python3 build/scripts/build_all.py --platform copilot-cli` to confirm the build is clean and no orphaned references remain

**Interfaces:** `build/scripts/generate_skills.py` reads `.claude/skills/` as its source. After deletion, re-running the build must exit 0.

### Component 3: Cross-Reference Update

**Purpose:** Remove extinct skill names from `codebase-documenter/SKILL.md` "when NOT to use" section (lines 40-41).

**Responsibilities:**
- Replace any `doc-coverage` or `doc-sync` references with `doc-accuracy`
- Apply the same update to `src/copilot-cli/skills/codebase-documenter/SKILL.md` (the published copy)

**Interfaces:** Single file edit; no downstream imports.

### Component 4: Dead Test Deletion

**Purpose:** Remove four test cases in `tests/test_invoke_skill_learning.py` (lines 370-394) that assert `doc-sync` routing behavior.

**Responsibilities:**
- Identify and delete the four `doc-sync` routing assertions
- Confirm `pytest tests/test_invoke_skill_learning.py` exits 0 after deletion

**Interfaces:** Standard pytest runner. No mock or fixture changes expected.

## Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Published copy cleanup method | Manual deletion + build re-run | Simplest verification; avoids partial state |
| Cross-ref update scope | Source + published copy in same PR | Keeps drift detection clean at merge time |
| Test cleanup strategy | Delete assertions, no replacement | Replacement routing tests are out of scope for M1 (deferred) |
| Build verification | `build_all.py --platform copilot-cli` | Canonical build path; catches any lingering references |

## Security Considerations

No authentication, authorization, secrets, PII, or input validation is involved. This is pure file deletion and a cross-reference update. No new attack surface is introduced.

## Testing Strategy

| Test | Type | Command | Pass Condition |
|---|---|---|---|
| Source dirs absent | Filesystem assertion | `ls .claude/skills/` | No `doc-coverage`, `doc-sync`, `workflow` entries |
| Published dirs absent | Filesystem assertion | `ls src/copilot-cli/skills/` | No `doc-coverage`, `doc-sync` entries |
| Build exits 0 | Build smoke test | `python3 build/scripts/build_all.py --platform copilot-cli` | Exit code 0 |
| Routing tests pass | Unit test | `uv run pytest tests/test_invoke_skill_learning.py` | Exit code 0, zero `doc-sync` assertions |
| Drift detection clean | Pre-push hook | Triggered by `git push` | Zero drift reported |

## Open Questions

None. All data model items, integrations, and failure modes are documented in the PRD. No ambiguity remains.
