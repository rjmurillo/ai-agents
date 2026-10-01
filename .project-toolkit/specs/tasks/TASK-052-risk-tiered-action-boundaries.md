---
type: task
id: TASK-052
title: Implement risk-tiered action boundaries
status: complete
priority: P1
complexity: M
source: issue-5767
related:
  - REQ-043
  - DESIGN-041
  - ADR-112
created: 2026-09-28
updated: 2026-09-28
author: plan
---

# TASK-052: Implement risk-tiered action boundaries

Implements REQ-043 through DESIGN-041. Four slices, each shippable and tested alone.

## Slice 1: Consequential-tier deny rules (AC 3)

- Move the Claude deny matcher out of
  `tests/test_security_agent_git_write_guard.py` into a shared test helper so
  two test modules use one model.
- Add the ADR-112 deny set to `templates/hooks/settings.tmpl`; regenerate
  `.claude/settings.json` with `build_all.py`.
- New test module: each rule blocks its exploit, spares its neighbor, and a
  negative control proves the matcher fires.
- Update recipes the new rules block: bare `--force-with-lease` in
  `git-advanced-workflows`, "avoid `--no-verify`" in `pr-autofix`.

Done when: new tests pass and the existing guard test passes unchanged in
intent.

## Slice 2: Merge preconditions, readback, recovery, audit (AC 4 to 8)

- `merge_pr.py`: `--expected-head-sha`, `--match-head-commit`, readback via
  `gh pr view`, timeout handling, recovered and queued results, audit record.
- Tests in `tests/test_merge_pr.py` for wrong target, stale head, partial
  failure, silent failure, retry, timeout, and readback failure.

Done when: every failure mode row in REQ-043 has a passing test.

## Slice 3: Least-privilege grants (AC 2, 9)

- Add read-only `tools:` lists to the `code-reviewer` and `comment-analyzer`
  Claude templates; fix the `code-reviewer.shared.md` projection note.
- Test that neither Claude agent holds Bash, Edit, Write, or NotebookEdit.

Done when: regenerated agents carry the lists and the test passes.

## Slice 4: Canonical owner and prose consolidation (AC 1, 10, 11)

- ADR-112: tier contract, control inventory, grant map, enforced versus
  advisory table, open gaps.
- `AGENTS.md` Autonomy Guardrail line points to ADR-112 at equal or smaller
  byte count.

Done when: `AGENTS.md` byte count does not grow and ADR-112 lists every gap.

## Risk register

| Risk | Mitigation |
|---|---|
| A deny rule blocks legitimate automation (the #5013 shape) | Neighbor tests for every rule; repo automation runs via subprocess, which deny rules never see |
| Readback breaks existing merge tests | Update fixtures to return the post-merge state explicitly |
| Deny patterns are evadable | ADR-112 lists them as defense in depth with named gaps |

## Validation

Focused pytest per slice, then `build_all.py --check` and `pre_pr.py` once
at the final head.
