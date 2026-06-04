---
type: requirement
id: REQ-018
title: Skill Catalog Prune M2 Session Cluster
status: implemented
priority: P2
category: maintainability
epic: skill-catalog-health
related:
  - ISSUE-1946
created: 2026-06-04
updated: 2026-06-04
author: richard
---

<!-- orphan-ref-ignore-file -->
<!-- M2 deletion spec: references to session-qa-eligibility and
     session-migration are intentional historical deletion targets. -->

# REQ-018: Skill Catalog Prune M2 Session Cluster

## Requirement Statement

WHEN a developer invokes session lifecycle skills after M2 lands,
THE SYSTEM SHALL route investigation-only QA eligibility to the `session` skill
and SHALL NOT expose a `session-migration` skill,
SO THAT session operations have one active entrypoint and no dead markdown-to-JSON conversion path.

## Context

Issue #1946 covers the second skill-catalog prune milestone. The `session-qa-eligibility` behavior was already folded into `session`: the `session` skill owns `Test-InvestigationEligibility` and the ADR-034 allowlist. The remaining M2 work removes the one-shot `session-migration` skill after auditing that active session logs are created as JSON.

Historical markdown files under `.agents/sessions/` remain an archive. They are not active inputs to `validate_session_json.py`, which validates explicit JSON paths.

## Acceptance Criteria

- [x] REQ-018-AC1: WHEN M2 lands, THE SYSTEM SHALL NOT contain `.claude/skills/session-migration/` SO THAT deleted conversion behavior is not available as a skill.
- [x] REQ-018-AC2: WHEN the Copilot CLI mirror is generated, THE SYSTEM SHALL NOT contain `src/copilot-cli/skills/session-migration/` SO THAT published users see the same skill catalog as Claude users.
- [x] REQ-018-AC3: WHEN users ask for investigation-only QA eligibility, THE SYSTEM SHALL route them to `session` SO THAT the ADR-034 allowlist has one owner.
- [x] REQ-018-AC4: WHEN evaluators encounter old `session-qa-eligibility` or `session-migration` prompts, THE SYSTEM SHALL answer with negative-routing guidance SO THAT stale references do not resurrect deleted skills.
- [x] REQ-018-AC5: WHEN changed skill and documentation surfaces are scanned, THE SYSTEM SHALL report no orphan references to deleted skills SO THAT future maintainers do not follow stale paths.
- [x] REQ-018-AC6: WHEN targeted tests run, THE SYSTEM SHALL preserve session creation, session validation, and memory episode extraction behavior SO THAT the deletion is behavior-preserving outside the removed migration entrypoint.

## Rationale

- `session` is the active session-lifecycle entrypoint and already contains the QA eligibility interface.
- `session-migration` was a one-shot helper. Keeping it after JSON-at-creation became the protocol adds catalog noise without active value.
- Negative-routing fixtures teach agents how to respond when they encounter old names in historical artifacts.

## Deferred

- The legacy markdown branch in `.github/workflows/ai-session-protocol.yml` still references a deleted PowerShell conversion script. That workflow repair is tracked separately from the M2 skill-catalog deletion.
