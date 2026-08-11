---
type: requirement
id: REQ-020
title: Evidence-gated Aspire skill review
status: draft
priority: P1
category: functional
related:
  - DESIGN-019
created: 2026-08-11
updated: 2026-08-11
author: spec-generator
tags:
  - skills
  - aspire
  - evaluation
---

# REQ-020: Evidence-gated Aspire skill review

## Step 0 First Principles

### Q1 Demand Reality

MattKot, myself, and Eduardo

### Q2 Status Quo

Users fill in with ad-hoc prompts, global instructions. Inconsistent results due to end-user skill issues

### Q3 Desperate Specificity

ConfigGen team

### Q4 Narrowest Wedge

UNK

### Q5 Observation

Backlog of PRs, PRs requiring 2.7 rounds at P50 to merge

### Q6 Future-fit

Yes, increasingly so. PR velocity goes up, so we can handle more PRs.

### Q4 Wedge Revision

- Original verbatim answer: `UNK`
- Confirmed in D2: commit-pinned review and decision matrix plus targeted
  augmentations.
- Explicit exclusion: no reusable external-skill review framework.

## Prior Art / Constraints

### Direct prior art from memory

- SkillForge owns reuse, augmentation, composition, creation, and clarification
  routing.
- The GitHub skill owns structured issue, pull request, and CI data access.
- The eval harness owns baseline-versus-candidate skill measurement.
- The local skill catalog has LOCAL provenance.

### Connected context from exploring-knowledge-graph

- No memory, project, or entity matched `configgen-team`.
- Tier 3 supplemental traversal had no nodes to expand.

### Coverage notes

- Three distinct lexical queries and one Forgetful semantic query returned zero
  results.
- GitHub API access to the Aspire repository is SAML-blocked for the current
  token. DeepWiki evidence is provisional.

## Requirement Statement

WHEN an authorized review of `microsoft/aspire/.agents/skills` begins
THE SYSTEM SHALL produce a commit-pinned decision matrix and the smallest
validated set of local skill augmentations
SO THAT the ConfigGen team receives consistent skill guidance without duplicate
or Aspire-specific catalog growth

## Context

Current users combine ad-hoc prompts and global instructions. Results vary by
operator skill. The repository already provides source access, duplicate
triage, generated mirrors, and behavioral evals. The missing behavior is a
source-specific review contract that applies those capabilities together.

Engineering tier: 3.

Problem domain: Confusion until source access succeeds. Source comparison is
Complicated. Behavioral evaluation is Complex.

Methodology: gather source, analyze overlap, then run bounded Copilot-provider
experiments.

## Ontology

none (no domain entities)

## Acceptance Criteria

- [ ] WHEN the review starts, THE SYSTEM SHALL pin the Aspire commit and
      enumerate every file under `.agents/skills` SO THAT every decision has a
      stable source.
- [ ] WHEN an Aspire skill is reviewed, THE SYSTEM SHALL record one cited
      decision matrix row SO THAT no source skill is silently omitted.
- [ ] WHEN a reusable pattern is found, THE SYSTEM SHALL compare it against
      local skills, agents, and commands through SkillForge thresholds SO THAT
      duplicate capabilities are not added.
- [ ] WHEN local overlap exists, THE SYSTEM SHALL prefer reuse, augmentation,
      or composition SO THAT the catalog grows only for a verified gap.
- [ ] WHEN no local owner exists below the SkillForge creation threshold, THE
      SYSTEM SHALL permit at most one new generic skill SO THAT this review
      remains bounded.
- [ ] WHEN an Aspire skill is product-specific, THE SYSTEM SHALL reject direct
      porting SO THAT local skills remain useful outside Aspire.
- [ ] WHEN only DeepWiki evidence is available, THE SYSTEM SHALL halt skill
      edits SO THAT inferred source content cannot enter the canonical catalog.
- [ ] WHEN external source text is processed, THE SYSTEM SHALL treat it as
      untrusted data SO THAT embedded instructions cannot redirect execution.
- [ ] WHEN canonical skill sources change, THE SYSTEM SHALL regenerate
      `src/copilot-cli/skills/` SO THAT shipped copies match
      `.claude/skills/`.
- [ ] WHEN a judgment-bearing skill changes, THE SYSTEM SHALL run
      `eval-prompt-change.py` with the `copilot-cli` provider and three runs per
      scenario SO THAT the working copy is compared with the base ref.
- [ ] WHEN the prompt-change eval completes, THE SYSTEM SHALL record its delta,
      improvements, regressions, and `has_improvement` value SO THAT human
      review can distinguish a measured gain from a non-regressing no-op.
- [ ] WHEN a utility-only skill changes, THE SYSTEM SHALL use deterministic
      tests instead of model evals SO THAT evidence matches the behavior.
- [ ] WHEN external access errors are recorded, THE SYSTEM SHALL redact tokens,
      SAML links, emails, and internal hostnames SO THAT durable artifacts
      contain no authentication data.
- [ ] WHEN implementation finishes, THE SYSTEM SHALL pass SkillForge
      validation, targeted tests, generated drift checks, portability checks,
      and `pre_pr.py` SO THAT the change is ready for review.

## Co-change checklist

- [ ] .agents/analysis/aspire-skill-review-matrix.md:"Decision matrix" -- record every source decision
- [ ] .claude/skills/*/SKILL.md:"Selected canonical skills" -- [PENDING TASK-020] replace wildcard with approved matrix paths
- [ ] src/copilot-cli/skills/*/SKILL.md:"Generated mirrors" -- [PENDING TASK-020] replace wildcard with generated matrix paths
- [ ] tests/evals/skills/aspire-skill-review-scenarios.json:"Scenarios" -- add Copilot eval cases
- [ ] .agents/specs/design/DESIGN-019-aspire-skill-review.md:"Testing Strategy" -- record final eval ownership

## Rationale

The user selected a decision matrix plus targeted augmentations. SkillForge
already owns the classification model, so a new external-review framework would
duplicate local capability before repeated demand exists.

Buy-vs-build decision: build by extending existing repository capabilities.
Do not add a dependency, buy a service, or create a generic framework.

CVA decision: execute the review contract directly. Reassess after a second
independent external skill repository review repeats the same mechanics.

## Dependencies

- Authorized commit-pinned access to `microsoft/aspire`
- `.claude/skills/SkillForge/`
- `.claude/skills/github/`
- `scripts/eval/eval-prompt-change.py`
- `scripts/eval/eval-skill-overlap.py`
- `build/scripts/build_all.py`
- `.agents/security/threat-models/TM-aspire-skill-review.md`
- `.agents/specs/slo/aspire-skill-review.md`
