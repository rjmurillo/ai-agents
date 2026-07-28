# Planning Artifacts

This directory holds planning documents for work that is currently in flight:
specs, PRDs, task breakdowns, and implementation plans.

**Status**: empty apart from this index. No planning work is open right now.

## When to add a file here

`.github/PULL_REQUEST_TEMPLATE.md` asks feature authors to create a spec here
before submitting if none exists. `.github/workflows/ai-spec-validation.yml`
accepts spec paths under either `.agents/specs/` or `.agents/planning/`.

Prefer `/spec` to generate the document rather than writing one by hand.

## Gates that run against this directory

| Gate | Trigger | What it checks |
|------|---------|----------------|
| `build/scripts/validate_planning_artifacts.py` | `validate-planning-artifacts.yml` on PR, and the `planning-artifacts` lefthook pre-commit hook | Effort estimates in an epic or PRD against the task breakdown total, orphan specialist conditions, document structure |
| `scripts/validation/git_hook_policy.py planning` | `planning-advisory` lefthook hook | Advisory guidance on planning changes |
| `.github/workflows/artifact-insight-scanner.yml` | Weekly, Monday | Scans documents modified in the last 7 days for insights |

The directory is not empty after the move: `INDEX.md` remains, so the validator
parses it and passes. Had the directory been emptied entirely, the validator
returns 0 on a zero-document set rather than erroring, so neither state fails a
gate.

## Retiring a document

When the work a document describes has shipped, move the document to
`.agents/archive/planning/` with `git mv` so history follows it. Record the
verdict and the evidence behind it in the archive index. Do not delete planning
documents.

Verify before retiring. A closed tracking issue alone is not proof. Confirm both
that the referenced work is closed and that the deliverable the document names is
present on disk.

Nothing automates this step today, which is why the directory accumulated six
months of finished work. The closest tracked work is #3426, which covers the same
mechanism gap for the sibling `.agents/plans/` directory. A scope note on that
issue asks whether the fix should cover this directory too.

## Archive

Retired planning documents live in [`.agents/archive/planning/`](../archive/planning/README.md).
110 files were moved there on 2026-07-27 under #3431, covering milestones v0.2.0
through v0.3.1, PR remediation plans, agent consolidation, knowledge integration,
and agent-slimming eval output. The archive index records the verification method
and the verdict for each cluster.

Earlier retired material sits at the root of [`.agents/archive/`](../archive/),
and retired execution plans sit in [`.agents/archive/plans/`](../archive/plans/README.md).
