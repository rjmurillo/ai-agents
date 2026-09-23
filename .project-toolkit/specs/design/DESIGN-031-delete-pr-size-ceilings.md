---
type: design
id: DESIGN-031
title: Delete the PR size ceilings outright
status: implemented
priority: P1
related:
  - REQ-033
  - TASK-042
adr: ADR-100
created: 2026-09-22
updated: 2026-09-22
author: spec-generator
tags:
  - control-plane
  - adr-100
---

# DESIGN-031: Delete the PR size ceilings outright

## Requirements Addressed

- REQ-033: Delete the PR size ceilings outright

## Design Overview

Delete, do not demote. Each size ceiling is a leaf: no other gate reads its
output. So each one goes with its wiring and its tests, and nothing replaces
it.

## Components

| Ceiling | Code removed | Wiring removed |
|---------|--------------|----------------|
| Commit count, pre-push | `_check_commit_limit` in the hook policy module | Call in the pre-push path |
| Commit count, CI | Commit-count classifier module, `needs-split` label script | Three `pr-validation.yml` steps |
| Atomic commit | `check_atomic_commit` and its CLI handler | `atomic-commit` lefthook job |
| Scope | Scope script and its PR-base helper | `scope-policy` and `branch-scope` lefthook jobs |

Helpers that lose their last caller go too. Helpers with another caller stay.

## Documents

Templates change first, then the build regenerates mirrors. Hand-kept docs
change directly. Historical records stay as written.

## Decision Record

ADR-100 carries the owner amendment of 2026-09-22 and sets
`implemented: true`. Item 6 telemetry and the re-measure are withdrawn.

## Testing

Tests that cover only deleted code are deleted. Shared tests drop assertions
that name deleted jobs or modules. The full suite and the build check prove
the rest.
