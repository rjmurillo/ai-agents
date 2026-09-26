---
type: task
id: TASK-048
title: Resolve catalog specialists before the autoplan orchestrator fallback
status: implemented
priority: P1
related:
  - REQ-039
  - DESIGN-037
created: 2026-09-25
updated: 2026-09-25
author: plan
tags:
  - skills
  - routing
  - autoplan
---

# TASK-048: Resolve catalog specialists before the autoplan orchestrator fallback

## Milestones

1. **Gate.** Add `intents` to `ROUTING_KEYS` and validate it in
   `check_skill_routing_roles.py`. Write the failing tests first.
2. **Resolver.** Write `tests/skills/autoplan/test_resolve_route.py`, then
   `.claude/skills/autoplan/scripts/resolve_route.py`.
3. **Catalog.** Reclassify `business-strategy`, `book-to-skill`,
   `world-model-diagnostic`, `dx-review`, and `programming-advisor`. Add
   intents to them and to `buy-vs-build-framework`. Quote the two remaining
   truncated rationales.
4. **Router.** Add the precedence list, the resolver step, the identity
   section, and the new capability row to the `autoplan` template. Add the
   positive and negative examples to the two advisor templates. Update
   REQ-019, DESIGN-036, and `docs/SKILL-AUTHORING.md`.
5. **Render.** Run `uv run python build/scripts/build_all.py`.
6. **Prove.** Run the targeted tests, the gate with `--report`, ruff, mypy,
   and `scripts/validation/pre_pr.py`.

## Risks

| Risk | Mitigation |
|---|---|
| Phrase matching misses a paraphrase | Several intents per skill; #5389 measures recall |
| A broad intent steals another skill's request | Negative fixtures per skill pair |
| Host interpreter lacks PyYAML | Exit 2 with a named module; the skill body falls back to descriptions |
| Mirror drift | `build_all.py --check` |

## Done When

Every REQ-039 criterion maps to a passing test or a gate run.
