---
source: wiki/concepts/Engineering Process/Chromium Explainers and Blink Intents.md
created: 2026-04-11
review-by: 2026-07-11
---

# Explainers and Intents

Process for proposing, communicating, and gating changes. Adapted from Chromium's Blink intent process.

## Core Principle

Write an explainer BEFORE doing anything. Write an intent to communicate transparently. Intent types keep on-call DRI informed so no surprises.

## Two Artifacts

### Explainer

Written proposal that describes:

- The **problem** being solved (use cases, scenarios)
- The **proposed solution** (approach, API design)
- **Trade-offs** and alternatives considered

Purpose: gather feedback before significant implementation begins. Entry point into the process.

### Intent

Formal communication that requests approval to proceed. Intents are permission gates, not announcements.

## Intent Types

| Intent | Phase | Approval | What It Unlocks |
|--------|-------|----------|-----------------|
| Intent to Prototype | First checkpoint | None required | Begin implementation behind feature flag |
| Intent to Experiment | Optional | Lightweight | Run experiment in production |
| Intent to Ship | Final milestone | Full review | General availability |
| Intent to Deprecate | Lifecycle | Varies | Warn consumers, begin migration |
| Intent to Remove | Lifecycle | Varies | Deactivate code by default |

## Lifecycle

```
Use cases identified
    |
Write Explainer (public, reviewable)
    |
Socialize with stakeholders
    |
Intent to Prototype --> implement behind flag
    |
Gather feedback
    |
[Optional] Intent to Experiment --> limited rollout
    |
Iterate on design + address feedback
    |
Intent to Ship (full approval)
    |
Ship --> monitor --> Stable
```

## Fast Track

Lighter-weight path when consensus already exists:

- Design already agreed upon by stakeholders
- Already implemented in an analogous system
- Merged into an existing standard or pattern

Still requires tracking entry and Intent to Ship.

## Planning Application

### Before Planning

1. Write an explainer for any non-trivial feature
2. Define the problem and use cases before proposing solutions
3. Document trade-offs and alternatives considered

### During Planning

1. Map milestones to intent types (prototype, experiment, ship)
2. Identify approval gates for each phase
3. Plan feedback collection points between phases

### Communication

1. Intents keep stakeholders informed at each phase transition
2. No surprises for on-call DRI or dependent teams
3. Deprecation and removal intents manage lifecycle end

## Why It Matters

- Makes changes **predictable** for consumers
- Enables **cross-team coordination**
- Protects **backwards compatibility**
- Supports **deprecation and removal** lifecycle
- Creates **auditable decision trail**
