---
type: design
id: DESIGN-019
title: Aspire skill review and augmentation design
status: draft
priority: P1
related:
  - REQ-020
  - TASK-019
  - TASK-020
  - TASK-021
  - TASK-022
  - TASK-023
created: 2026-08-11
updated: 2026-08-11
author: spec-generator
tags:
  - skills
  - aspire
  - evaluation
---

# DESIGN-019: Aspire skill review and augmentation design

## Requirements Addressed

- REQ-020: Evidence-gated Aspire skill review

## Design Overview

Use existing repository capabilities as a staged pipeline:

1. Retrieve and pin the complete Aspire skill source.
2. Normalize source evidence into a decision matrix.
3. Apply SkillForge overlap routing across skills, agents, and commands.
4. Select the smallest approved augmentation set.
5. Edit canonical skills only.
6. Run Copilot-provider evals or deterministic tests.
7. Generate Copilot CLI mirrors and run repository gates.

No reusable external-review framework is introduced.

## Component Architecture

| Component | Responsibility | Existing owner |
|---|---|---|
| Source collector | Pin commit and enumerate Aspire skill files | GitHub API |
| Evidence matrix | Record source facts, local overlap, decision, and citation | `.agents/analysis/` |
| Duplicate router | Score use, augment, compose, create, or reject | SkillForge |
| Canonical skill editor | Apply approved generic guidance | `.claude/skills/` |
| Behavioral evaluator | Compare baseline and candidate skill behavior | Eval harness |
| Mirror generator | Produce shipped Copilot CLI skill copies | `build_all.py` |
| Validation gates | Prove structure, tests, drift, portability, and pre-PR state | Existing validators |

## Technology Decisions

| Decision | Choice | O5 source | Rationale |
|---|---|---|---|
| Source identity | GitHub commit SHA | N/A | Stable citations and complete enumeration |
| Provisional discovery | DeepWiki, read-only | N/A | Useful for leads, not authoritative changes |
| Duplicate policy | SkillForge thresholds | N/A | Existing catalog owner |
| New skill limit | Zero or one | N/A | User-approved scope cap |
| Behavioral provider | `copilot-cli` | N/A | Measures models used by repository owners |
| Eval gate | Prompt-change PASS | N/A | ADR-057 blocks regressions and high flakiness |
| Utility verification | Deterministic tests | N/A | Model judgment is the wrong evidence |
| Mirror ownership | Canonical `.claude/skills/` plus generation | N/A | Prevents hand-edited drift |

## Decision-rule Traceability

No OntologyFragment decision rules apply.

Repository rules:

- SkillForge prevents duplicate skill creation.
- Generated artifact rules require canonical edits and generated mirrors.
- External content remains untrusted data.
- GitHub source access must be commit-pinned before skill edits.

## Security Considerations

Threat model: `.agents/security/threat-models/TM-aspire-skill-review.md`.

Named trust boundaries:

1. External GitHub and DeepWiki content entering local reasoning.
2. Review findings becoming tracked repository files.
3. Skill prompts entering the Copilot CLI eval subprocess.

High risks:

- Provisional source accepted as authoritative.
- External instructions redirect execution.
- Sensitive authentication data enters durable artifacts.
- Generated customer-facing skill copies drift.

Mitigations map to REQ-020 acceptance criteria 1, 7, 8, 9, 10, and 12.

## Testing Strategy

### Source and matrix

- Reconcile source skill count to matrix row count.
- Resolve every citation against the pinned commit.
- Include negative controls for omitted skills and unresolved paths.

### Skill overlap

- Run SkillForge triage for every reusable candidate.
- Run `eval-skill-overlap.py` for close local candidates when prose comparison
  cannot distinguish ownership.

### Behavioral changes

Use for each changed judgment-bearing skill:

```bash
uv run python scripts/eval/eval-prompt-change.py \
  --prompt .claude/skills/<changed-skill>/SKILL.md \
  --scenarios tests/evals/skills/aspire-skill-review-scenarios.json \
  --base-ref origin/main \
  --provider copilot-cli \
  --runs 3 \
  --output <report-path>
```

Pass when the harness gate returns PASS. Record `has_improvement` and delta as
non-gating evidence for human review, matching ADR-057.

### Utility changes

Run targeted deterministic tests for script output, exit codes, and edge cases.

### Generated artifacts

- Run `uv run python build/scripts/build_all.py`.
- Run the targeted generated drift and portability checks.
- Run `uv run python scripts/validation/pre_pr.py`.

## Open Questions

- Which source candidates survive authorized retrieval and overlap scoring?
- Which exact canonical skills change?
- Does any candidate justify the one allowed new skill?
- Which final eval scenario belongs to each changed judgment-bearing skill?
- Which exact canonical and generated paths replace the co-change checklist
  wildcards after TASK-020?
