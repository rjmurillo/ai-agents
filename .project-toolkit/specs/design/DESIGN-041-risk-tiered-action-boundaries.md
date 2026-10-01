---
type: design
id: DESIGN-041
title: Harness deny set, pinned merge readback, and read-only grants
status: implemented
priority: P1
related:
  - REQ-043
  - TASK-052
  - ADR-112
created: 2026-09-28
updated: 2026-09-28
author: spec-generator
tags:
  - security
  - autonomy
  - v0.7.0
---

# DESIGN-041: Harness deny set, pinned merge readback, and read-only grants

## Requirements Addressed

REQ-043, acceptance criteria 1 through 11. ADR-112 holds the decision.

## Components

| Component | Plane | Role |
|---|---|---|
| `templates/hooks/settings.tmpl` `permissions.deny` | Claude harness | Denies the consequential tier |
| `tests/claude_permission_matcher.py` | Test | One model of the deny matcher, shared by two test modules |
| `merge_pr.py` | Skill script | Pins the head, reads the PR back, recovers, and audits |
| Claude agent `tools:` lists | Claude harness | Read-only grants for code-reviewer and comment-analyzer |

## Flow: merge

1. Fetch PR state. Refuse when `--expected-head-sha` differs.
2. Return `action: none` when the PR is already merged.
3. Run `gh pr merge --match-head-commit <sha>`.
4. On failure or timeout, read back. `MERGED` means recovered success.
5. On success, read back. Report merged only on `MERGED`, queued only with
   an auto-merge request, else exit 3.
6. Emit the audit record on every result.

## Testing

- `tests/test_action_tier_deny_rules.py`: exploits, evasions, neighbors,
  dead-rule coverage, and pinned gaps.
- `tests/test_merge_pr.py`: every REQ-043 failure-mode row.
- `tests/test_read_only_agent_grants.py`: both Claude trees.
