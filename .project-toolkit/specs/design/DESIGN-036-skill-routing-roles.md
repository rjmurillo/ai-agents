---
type: design
id: DESIGN-036
title: Skill routing-role frontmatter and the classification gate
status: implemented
priority: P1
related:
  - REQ-038
  - TASK-047
created: 2026-09-24
updated: 2026-09-24
author: spec-generator
tags:
  - skills
  - routing
  - validation
---

# DESIGN-036: Skill routing-role frontmatter and the classification gate

## Requirements Addressed

REQ-038 criteria 1 to 15.

## Where the declaration lives

Each skill template declares its role under the `metadata` key it already
supports, beside the ADR-110 `capability` block:

```yaml
metadata:
  routing:
    role: nested-helper
    invoker: pr-quality-all
    trigger: pr-quality-all runs the security axis
    user-facing: true
```

The "manifest" that issue #5384 asks for is the set of these blocks, read
and printed by the gate. This follows ADR-110: ownership lives in the
artifact, and no second registry is created (epic #5456 lists a new registry
as an abort condition). The issue's "small reviewed override file" is the
`scenario` key, which overrides the default scenario path per skill.

## Keys

| Key | Type | Required |
|---|---|---|
| `role` | one of six roles | always |
| `invoker` | skill, agent, `user`, or `harness` | unless deprecated |
| `trigger` | non-empty string | unless deprecated |
| `user-facing` | boolean | unless deprecated |
| `scenario` | relative path under `tests/evals/` | never; default `tests/evals/skill-scenarios/<name>.json` |
| `rationale` | non-empty string | explicit-only |
| `replaced-by` | non-deprecated skill name | deprecated, unless `removal-issue` |
| `removal-issue` | positive integer, checked whenever present | deprecated, unless `replaced-by` |

`user-facing` is true when a person may ask for the skill directly, by name
or by its trigger phrases. It is false for a helper that only another skill
or agent runs. An `explicit-only` skill must be user-facing, since a user
request is its only route.

## Role and invoker rules

| Role | Legal invoker |
|---|---|
| `front-door` | `autoplan`, or `harness` for a skill the harness selects by description |
| `lifecycle` | `spec`, `plan`, `build`, `test`, `review`, `ship` |
| `conditional-adjunct` | any other skill or agent, not the skill itself |
| `nested-helper` | any other skill or agent, not the skill itself |
| `explicit-only` | `user` |
| `deprecated` | any, or absent |

The six lifecycle skills are `front-door`: autoplan routes to them. A skill
they select is `lifecycle`.

A redirect ("Do NOT use for X (use Y)") is a conditional route from the
redirecting skill to Y. `harness` is for skills built to intercept requests
automatically (`autoplan`, `github-url-intercept`), not for plain description
matching, which every skill has.

## Evidence layers

1. **Classified**: the block is present and valid.
2. **Structurally reachable**: for front-door, lifecycle, adjunct, and helper
   roles, the invoker's canonical text names the skill as an exact token.
   Canonical text is the invoker's template plus the Markdown files under
   `.claude/skills/<invoker>/` other than `SKILL.md`, or the agent's
   `templates/agents/<name>.shared.md`. The gate parses each template's
   frontmatter and removes `metadata.routing` before matching, so a
   declaration cannot certify itself in any YAML form. `harness` routes pass by
   declaration. `user` routes (explicit-only) are outside this layer and
   leave its denominator. A skill that fails this check is "unresolved".
   It is reported, not refused: the routes are prose, and a common-word skill
   name makes this an upper bound.
3. **Scenario coverage**: the scenario file exists.
4. **Scored accuracy**: not measured here. #5389 owns it.

"Inbound-zero" lists skills that no other skill or agent text names at all.

## Gate

`scripts/validation/check_skill_routing_roles.py`:

- `validate_skill_routing_roles(repo_root) -> bool` for the pre-PR sequence.
- CLI: `--repo-root`, `--report`, `--format text|json`. Exit codes per
  ADR-035: 0 pass, 1 violation, 2 config error (no templates, or zero skills).
- Output is sorted by skill name, so repeated runs match byte for byte.

Registration: `validate_skill_routing_roles_declarations` in
`scripts/validation/checks_tooling.py`, one `_Gate` row in
`scripts/validation/pre_pr_sequence.py`. CI enforcement: a pytest case runs
the gate against the real repository, and `pytest.yml` runs the full suite.

## Rejected alternatives

- A central YAML manifest: a second source of truth that drifts on rename.
- Reusing `metadata.capability.kind`: ADR-110 closes that block to unknown
  keys, and "who invokes" is a different axis from "what it owns".
- Refusing unresolved routes: blocks prose edits for a check that is only an
  upper bound. Reported instead.
