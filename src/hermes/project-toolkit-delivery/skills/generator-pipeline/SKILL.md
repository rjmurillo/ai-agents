---
name: generator-pipeline
version: 0.1.0
description: Rules for editing generated artifacts and their templates. Agents,
  rules, skills, hooks, and settings render from `templates/` through
  `build_all.py`. Use when you edit anything under `templates/`, a build
  generator, or a file that a generator writes. Do NOT use to run
  CI pipelines (use pipeline-validator) or to author a skill's content (use
  skillforge).
license: MIT
---

# Generator Pipeline

Generated files are never hand-edited. Edit the template source,
run `build_all.py` from the build tree, and commit the template and its
output together. A second build run must leave `git status` clean.

## Triggers

Use this skill when the user says:

- `edit the template` before changing a generated file
- `regenerate the outputs` after a template change
- `is this file generated` when unsure where to edit

## Process

1. Find the source. Read [rule-generated-artifacts.md](references/rule-generated-artifacts.md) for the output-to-source map.
2. Edit the template. Read [rule-templates.md](references/rule-templates.md) for template grammar and escaping.
3. Run `build_all.py`.
4. Run it again. Confirm `git status --porcelain` shows no new changes.

## Verification

- The pre-PR runner (`pre_pr.py`) reports `Generated Artifact Staleness` as passed.

Folded rules, read before editing what they govern: [generated-artifacts](references/rule-generated-artifacts.md), [templates](references/rule-templates.md).
