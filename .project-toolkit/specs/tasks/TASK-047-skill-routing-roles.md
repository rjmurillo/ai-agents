---
type: task
id: TASK-047
title: Classify every skill's routing role and gate uncategorized catalog growth
status: implemented
priority: P1
related:
  - REQ-038
  - DESIGN-036
created: 2026-09-24
updated: 2026-09-24
author: plan
tags:
  - skills
  - routing
  - validation
---

# TASK-047: Classify every skill's routing role and gate uncategorized catalog growth

## Steps

1. Write `tests/validation/test_check_skill_routing_roles.py` with `tmp_path`
   fixtures for every REQ-038 exit-1 case, a passing catalog, and the edge
   cases.
2. Write `scripts/validation/check_skill_routing_roles.py` until the tests
   pass.
3. Register the gate in `checks_tooling.py` and `pre_pr_sequence.py`, and
   update the pre-PR registry test.
4. Add a `metadata.routing` block to every `templates/skills/*.SKILL.md.tmpl`.
   Pick the invoker whose text names the skill. When no invoker names it, use
   `explicit-only` with a rationale.
5. Run `uv run python build/scripts/build_all.py` to render the mirrors.
6. Document classification in `docs/SKILL-AUTHORING.md`.
7. Run the gate with `--report`, the targeted tests, ruff, and mypy.

## Done When

Every REQ-038 acceptance criterion maps to a passing test or a gate run, and
the real catalog passes the gate.
