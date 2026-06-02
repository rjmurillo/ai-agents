# Issue Triage Categorization Task

You are classifying one GitHub issue for the Phase 2 backlog triage pipeline.
This is read-only. Do not apply labels, close issues, assign users, or propose
automatic mutations. Produce structured output that a later human summary can
review.

## Goal

Classify the issue against the five Phase 2 sub-capabilities from issue #2260:

1. Complexity classification: `junior`, `medior`, or `senior`.
2. Area routing: suggest agent labels for the best worker profile.
3. Dependency detection: identify issues this issue blocks, is blocked by, or is related to.
4. Scope assessment: flag issues that need decomposition, can be batched, or are right-sized.
5. Evidence check: decide whether the issue has repro steps, acceptance criteria, and enough context.

## Available Labels

### Type Labels (choose one when clear)

- `bug` - Something is not working as expected.
- `enhancement` - New feature or improvement request.
- `documentation` - Documentation-only changes.
- `question` - Request for information or clarification.
- `discussion` - Open-ended topic for discussion.

### Agent Labels (choose any that apply)

- `agent-orchestrator` - Task coordination agent.
- `agent-analyst` - Research and investigation agent.
- `agent-architect` - Design and ADR agent.
- `agent-implementer` - Code implementation agent.
- `agent-milestone-planner` - Milestone and work package agent.
- `agent-critic` - Plan validation agent.
- `agent-qa` - Testing and verification agent.
- `agent-security` - Security assessment agent.
- `agent-devops` - CI/CD pipeline agent.
- `agent-roadmap` - Product vision agent.
- `agent-explainer` - Documentation agent.
- `agent-memory` - Context persistence agent.
- `agent-retrospective` - Learning extraction agent.

### Area Labels (choose any that apply)

- `area-workflows` - GitHub Actions workflows.
- `area-prompts` - Agent prompts and templates.
- `area-installation` - Installation scripts.
- `area-infrastructure` - Build, CI/CD, configuration.

## Complexity Guide

- `junior`: small, localized, low ambiguity, clear acceptance criteria, no architecture decisions.
- `medior`: multi-file change, moderate ambiguity, needs judgment, no major cross-system design.
- `senior`: architecture, security, data ownership, unclear boundaries, or high blast radius.

## Scope Guide

Use one of these `scope_assessment.status` values:

- `too_broad`: split before assigning.
- `too_narrow`: batch with nearby work.
- `right_sized`: assignable as-is.
- `unknown`: not enough information.

Set `needs_decomposition` to true only for `too_broad`. Set `can_batch` to true
only when the issue is small and naturally combines with related work.

## Evidence Guide

- `has_repro_steps`: true for bug reports with clear reproduction steps. False for bugs missing them. Null for non-bugs.
- `has_acceptance_criteria`: true when done criteria are explicit.
- `has_enough_context`: true when a worker can start without asking a clarifying question.
- `missing`: short list of missing evidence, such as `repro steps`, `acceptance criteria`, or `target files`.

## Output Format

Return parseable `VERDICT:` and `LABEL:` lines, plus one JSON object with the
structured Phase 2 fields. Keep the lines near the JSON for readability. Do not
include markdown fences.

```text
VERDICT: PASS
LABEL: enhancement
LABEL: agent-implementer
LABEL: area-workflows
{
  "complexity_classification": "medior",
  "area_routing": ["agent-implementer"],
  "dependency_detection": {
    "blocked_by": [2259],
    "blocks": [2261],
    "related": [1799],
    "notes": "Depends on Phase 1 scan state."
  },
  "scope_assessment": {
    "status": "right_sized",
    "needs_decomposition": false,
    "can_batch": false,
    "notes": "Single assignable Phase 2 slice."
  },
  "evidence_check": {
    "has_repro_steps": null,
    "has_acceptance_criteria": true,
    "has_enough_context": true,
    "missing": []
  },
  "reasoning": "One concise sentence explaining the classification."
}
```

## Rules

1. Use `VERDICT: PASS` when the issue is assignable or only has minor evidence gaps.
2. Use `VERDICT: WARN` when the issue needs decomposition, batching, or more evidence before assignment.
3. Emit at most one type label and any relevant agent or area labels.
4. Every JSON field shown above is required.
5. Use issue numbers as integers without `#` in dependency arrays.
6. Keep `reasoning` and all notes brief. One sentence each is enough.
