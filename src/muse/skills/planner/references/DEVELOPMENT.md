# skills/planner/

## Overview

Planning skill with resources that the scripts and `SKILL.md` name by path.

## Index

| File/Directory                        | Contents                                       | Read When                                          |
| ------------------------------------- | ---------------------------------------------- | -------------------------------------------------- |
| `SKILL.md`                            | Planning workflow, phases                      | Using the planner skill                            |
| `scripts/planner.py`                  | Step-by-step planning orchestration            | Debugging planner behavior                         |
| `resources/plan-format.md`            | Plan template (injected by script)             | Editing plan structure                             |
| `resources/temporal-contamination.md` | Detection heuristic for contaminated comments  | Updating the temporal contamination rules          |
| `resources/diff-format.md`            | Unified diff spec for code changes             | Updating how plans write code changes              |
| `resources/default-conventions.md`    | Default structural conventions (4-tier system) | Updating review criteria or planner decision audit |

## How Resources Reach Agents

Resources are **authoritative sources**. No agent prompt embeds a copy of any of them.

- **SKILL.md** lists the resources, and the coordinator reads them directly.
- **The scripts** name a resource by path in the brief they print, and the agent reads the file.

Editing a resource takes effect on the next run. There is no copy to keep in sync.

### plan-format.md

Plan template injected by `scripts/planner.py` at planning phase completion. The script reads the file and prints its content.

### temporal-contamination.md

Authoritative source for temporal contamination detection. Two briefs name it:

| Script        | Step                                | Agent                     |
| ------------- | ----------------------------------- | ------------------------- |
| `planner.py`  | Review step 1 (comment review)      | `@agent-comment-analyzer` |
| `executor.py` | Step 4 (post-implementation review) | `@agent-code-reviewer`    |

### diff-format.md

Authoritative source for the unified diff format that plan milestones use for code changes. `SKILL.md` lists it under Resources. The implementer applies the diffs from the plan file.

### default-conventions.md

Authoritative source for default structural conventions (the four-tier decision backing system). Three places name it:

| Script        | Step                                | Agent or use                 |
| ------------- | ----------------------------------- | ---------------------------- |
| `planner.py`  | Review step 2 (plan review)         | `@agent-critic`              |
| `executor.py` | Step 4 (post-implementation review) | `@agent-code-reviewer`       |
| `planner.py`  | Planning decision audit             | Cited as `default-conventions domain` |

**Four-tier priority hierarchy** (higher overrides lower):

1. user-specified: explicit user instruction
2. doc-derived: project CLAUDE.md or documentation
3. default-derived: conventions in this resource
4. assumption: no backing found (requires user confirmation)

## Reference Check

After renaming or moving a resource, confirm the scripts still name it:

```bash
grep -n "temporal-contamination.md\|default-conventions.md" scripts/*.py
```

`tests/skills/planner/test_planner_delegation_targets.py` checks that every `@agent-*` name in the planner output exists as an agent template.
