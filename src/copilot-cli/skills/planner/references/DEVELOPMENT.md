# skills/planner/

## Overview

Planning skill with resources that must stay synced with agent prompts.

## Index

| File/Directory                        | Contents                                       | Read When                                    |
| ------------------------------------- | ---------------------------------------------- | -------------------------------------------- |
| `SKILL.md`                            | Planning workflow, phases                      | Using the planner skill                      |
| `scripts/planner.py`                  | Step-by-step planning orchestration            | Debugging planner behavior                   |
| `resources/plan-format.md`            | Plan template (injected by script)             | Editing plan structure                       |
| `resources/temporal-contamination.md` | Detection heuristic for contaminated comments  | Updating TW/QR temporal contamination logic  |
| `resources/diff-format.md`            | Unified diff spec for code changes             | Updating Developer diff consumption logic    |
| `resources/default-conventions.md`    | Default structural conventions (4-tier system) | Updating QR RULE 2 or planner decision audit |

## Resource Sync Requirements

Resources are **authoritative sources**.

- **SKILL.md** references resources directly (main Claude can read files)
- **Agent prompts** embed resources 1:1 (sub-agents cannot access files reliably)

### plan-format.md

Plan template injected by `scripts/planner.py` at planning phase completion.

**No agent sync required** - the script reads and outputs the format directly, so editing
this file takes effect immediately without updating any agent prompts.

### temporal-contamination.md

Authoritative source for temporal contamination detection. Full content embedded 1:1.

| Synced To                    | Embedded Section           |
| ---------------------------- | -------------------------- |
| `agents/technical-writer.md` | `<temporal_contamination>` |
| `agents/quality-reviewer.md` | `<temporal_contamination>` |

**When updating**: Modify `resources/temporal-contamination.md` first, then copy content into both `<temporal_contamination>` sections.

### diff-format.md

Authoritative source for unified diff format. Full content embedded 1:1.

| Synced To             | Embedded Section |
| --------------------- | ---------------- |
| `agents/developer.md` | `<diff_format>`  |

**When updating**: Modify `resources/diff-format.md` first, then copy content into `<diff_format>` section.

### default-conventions.md

Authoritative source for default structural conventions (the four-tier decision backing system). Embedded in QR for RULE 2 enforcement; referenced by planner for decision audit.

| Synced To                    | Embedded Section        |
| ---------------------------- | ----------------------- |
| `agents/quality-reviewer.md` | `<default_conventions>` |

**When updating**: Modify `resources/default-conventions.md` first, then update the `<default_conventions>` section in QR. The planner.py decision audit references this resource by path.

**Four-tier priority hierarchy** (higher overrides lower):

1. user-specified: explicit user instruction
2. doc-derived: project CLAUDE.md or documentation
3. default-derived: conventions in this resource
4. assumption: no backing found (requires user confirmation)

## Sync Verification

After modifying a resource, verify sync:

```bash
# Check temporal-contamination.md references
grep -l "temporal.contamination\|four detection questions\|change-relative\|baseline reference" agents/*.md

# Check diff-format.md references
grep -l "context lines\|AUTHORITATIVE\|APPROXIMATE\|context anchor" agents/*.md

# Check default-conventions.md references
grep -l "default_conventions\|domain: god-object\|domain: test-organization" agents/*.md
```

If grep finds files not listed in sync tables above, update this document.
