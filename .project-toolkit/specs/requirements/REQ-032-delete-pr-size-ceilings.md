---
type: requirement
id: REQ-032
title: Delete the PR size ceilings outright
status: implemented
priority: P1
category: functional
epic: EPIC-5456
source: GH-5241
related:
  - REQ-023
  - TASK-041
created: 2026-09-22
updated: 2026-09-22
author: spec
tags:
  - control-plane
  - adr-100
  - pr-size-ceilings
---

# REQ-032: Delete the PR size ceilings outright

## Step 0 First Principles

### Q1 Demand Reality

rjmurillo, the repository owner, on 2026-09-22 in the #5241 session: "we don't
need to remeasure; just remove the PR size ceilings. They were to prevent
runaway or large merges, but we have other guardrails in place now. It's just
a PITA to deal with and creates overhead and tax. Kill it". Issue #5241 (the
ADR-100 work list). Epic #5456, which names #5241 as a subtraction candidate.

### Q2 Status Quo

Three ceilings still run as advisories after ADR-099 and PR #5723. The
pre-push `push-ref-policy` job prints a commit-count note. `pr-validation.yml`
classifies the commit count and adds or removes the `needs-split` label. The
pre-commit `atomic-commit` job prints a five-file advisory. The pre-commit
`scope-policy` job and the pre-push `branch-scope` job print a 50-file
advisory. Contributors read and ignore these notes on every push.

### Q3 Desperate Specificity

The owner, and every agent session that pushes a long-lived branch. They pay
hook time and CI time for output nobody acts on, and agents still ration
commits against numbers that no longer enforce anything.

### Q4 Narrowest Wedge

One PR that deletes the ceiling code, its hook and workflow wiring, its tests,
and the live documents that describe it. About one hour AI-assisted.

### Q5 Observation

ADR-100 Context measures eight in-tree workarounds and the #4954 round 15
commit rationing caused by the ceilings. The owner comment on #5241
(2026-09-11) records that item 5 churn is gone and item 6 is the only open
item. The owner now withdraws item 6.

### Q6 Future-fit

At 10x more PRs the ceilings cost 10x more hook and CI time and still block
nothing. Deletion scales. Review, required checks, and the QA gate remain the
guardrails against a bad large merge.

## Step 0.5 Prior Art

Searched: REQ-023 (demotion of items 2 to 4), ADR-099 (commit-count block
removal), ADR-100 (retirement decision). Not a halt: those records demoted the
ceilings to advisories and planned telemetry. This spec deletes the advisories
and withdraws the telemetry, on the owner decision above.

## Problem Statement

The PR size ceilings no longer block anything, but their advisory code,
labels, hook jobs, and documents still run and still shape agent behavior.

## User Stories

- As a contributor, when I push a large branch, I see no size notice and pay no
  size-check time.
- As a maintainer, I read no rule, skill, or doc that names a size ceiling as
  current behavior.

## Ontology

- Size ceiling: any check whose only input is a count of commits or files.
  Instances: commit-count classifier, `needs-split` label automation,
  atomic-commit advisory, scope advisory.
- Not a size ceiling: `pr_description` checks, QA report binding, review
  gates. These stay.

## Data Model

No persistent data. The `needs-split` GitHub label stays in the repository
label set; only its automation goes.

## Integrations

`pr-validation.yml` stops calling the GitHub label API for `needs-split`.
Failure modes shrink: no label API call, no commit list fetch.

## Failure Modes

- A deleted module is still imported: the import fails at hook start and every
  push fails. Mitigation: full test suite plus a grep for each deleted name.
- A lefthook job references a deleted script: the hook fails. Mitigation:
  lefthook tests and a real `lefthook run pre-push` dry run.
- A generated mirror keeps the old text: mirror drift checks fail. Mitigation:
  edit templates, then run the build.

## Security

No security surface. The change removes code and one label API call. It adds
no input, secret, or permission.

## Observability

What proves this works: `git grep` for each deleted identifier returns only
historical records, and pre-push output shows no size notice.

## Acceptance Criteria

1. When a branch of any commit count is pushed, the pre-push hook shall print
   no commit-count notice and shall not run `git rev-list --count` for it.
2. When a PR is validated, `pr-validation.yml` shall not classify the commit
   count and shall not add or remove the `needs-split` label.
3. When a commit of any file count is made, no pre-commit job shall count its
   files against a ceiling.
4. When a commit or push of any size runs, no hook job shall run a scope-size
   check.
5. The repository shall not contain the modules `pr_commit_count.py`,
   `update_needs_split_label.py`, `detect_scope_explosion.py`, or
   `scope_pr_base.py`, nor tests that exist only to cover them.
6. When `git grep` runs for `check_atomic_commit`, `_check_commit_limit`,
   `pr_commit_count`, `detect_scope_explosion`, and `update_needs_split_label`
   outside historical records, it shall return no match.
7. Live contributor documents (CONTRIBUTING, scripts/AGENTS, governance
   constraints and gotchas, skills, and agent templates) shall not describe a
   size ceiling as current behavior.
8. ADR-100 shall record the 2026-09-22 owner decision, withdraw item 6 and the
   re-measure, and set `implemented: true`.
9. When the build runs, the generated mirrors shall match their templates.
10. When the full test suite runs, it shall pass.

## Out of Scope

- Historical records: sessions, retrospectives, critiques, episodes, analysis,
  metrics snapshots, earlier specs, and earlier ADR bodies other than ADR-100.
- Deleting the `needs-split` label from the GitHub repository.
- The `-m` fallback in `post_qa_code_changes` (owner triage: obsolete).
- `.claude/rules/universal.md` SHOULD-5 (one logical change per commit). It
  names no number and stays as author guidance.

## Deferred

None.

## Open Questions

None. The owner answered the only one (telemetry and re-measure) with "Kill
it".

## CVA Summary

Common: each ceiling counts commits or files and prints a note. Variable: the
counted unit, the hook stage, and the CI label side effect. Relationship: none
of them feeds another gate, so each deletes on its own.

## Buy-vs-build Decision

N/A (refactor: deletion).

## Complexity Classification

Tier 2. Domain: Clear. Methodology: delete, then run the full suite.
