---
type: requirement
id: REQ-019
title: Autoplan Router Skill
status: implemented
priority: P2
category: developer-experience
epic: skill-routing
related:
  - TASK-019
issues:
  - 2828
created: 2026-07-03
updated: 2026-07-03
author: richard
---

# REQ-019: Autoplan Router Skill

## Requirement Statement

WHEN a user gives a concrete request without naming a skill,
THE SYSTEM SHALL route the request through `/autoplan` to the matching skill, lifecycle chain, or orchestrator fallback,
SO THAT users do not need to manually choose from the full skill catalog.

## Context

Issue #2828 requested a lazy router inspired by gstack autoplan. The implemented scope is the mechanical router skill and its Copilot CLI mirror. The open design question about whether `/autoplan` should retire the `orchestrator` agent is not part of this requirement.

## Acceptance Criteria

- [x] REQ-019-AC1: WHEN `/autoplan` is invoked, THE SYSTEM SHALL classify the request by intent family and size tier SO THAT routing starts from the user's outcome.
- [x] REQ-019-AC2: WHEN a request maps to a high-traffic workflow, THE SYSTEM SHALL route through the table in `.claude/skills/autoplan/SKILL.md` SO THAT common work avoids the orchestrator fallback.
- [x] REQ-019-AC3: WHEN a new capability is requested, THE SYSTEM SHALL invoke `buy-vs-build-framework` before `/spec` SO THAT repository governance is preserved.
- [x] REQ-019-AC4: WHEN security triage is needed, THE SYSTEM SHALL route detection through `security-detection` and vulnerability review through `security-review` or `security-scan` SO THAT security paths use the canonical skills.
- [x] REQ-019-AC5: WHEN a decision is mechanical, taste-based, or sovereignty-bound, THE SYSTEM SHALL apply the matching handling rule SO THAT user-owned decisions are not auto-decided.
- [x] REQ-019-AC6: WHEN no routing row matches, THE SYSTEM SHALL fall back to `Task(subagent_type="orchestrator")` SO THAT long-tail work still has an owner.
- [x] REQ-019-AC7: WHEN the skill is published to Copilot CLI, THE SYSTEM SHALL include the generated `src/copilot-cli/skills/autoplan/SKILL.md` mirror SO THAT both harnesses expose the same router.
- [x] REQ-019-AC8: WHEN plugin source changes, THE SYSTEM SHALL bump both project-toolkit plugin manifests to the same patch version SO THAT release validation can prove parity.

## Out of Scope

- Retiring or deleting the `orchestrator` agent.
- Rewriting the root skill-routing guidance to delegate to `/autoplan`.
