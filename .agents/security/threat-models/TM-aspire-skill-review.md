# Threat Model: Aspire Skill Review

**Created**: 2026-08-11
**Version**: 1.0
**Status**: Draft
**Author**: Copilot
**Reviewers**: Security reviewer

## 1. Scope

### Subject

External skill content retrieval, classification, local skill changes, generated
mirrors, and Copilot-provider behavioral evaluation.

### Boundaries

**In Scope:**

- GitHub API and DeepWiki input
- SkillForge classification
- Canonical and generated skill artifacts
- Eval scenarios and reports

**Out of Scope:**

- Aspire runtime behavior
- Aspire repository mutations
- New authentication systems

### Stakeholders

| Role | Name | Responsibility |
|---|---|---|
| Owner | Richard Murillo | Final approval |
| Requester | ConfigGen team | Validate usefulness |
| Security | Security reviewer | Threat validation |

## 2. Architecture Overview

### Data Flow Diagram

```text
+------------------+       +------------------+       +------------------+
| GitHub /         | ----> | Review process   | ----> | .agents matrix   |
| DeepWiki         |       | and SkillForge   |       | and skill source |
+------------------+       +------------------+       +------------------+
         |                         |                          |
         | External trust         | Local process            | Generated
         | boundary               v                          v
         |                 +------------------+       +------------------+
         +---------------->| Copilot eval     |       | Copilot mirrors  |
                           | subprocess       |       |                  |
                           +------------------+       +------------------+
```

### Components

| ID | Name | Type | Description | Owner |
|---|---|---|---|---|
| C001 | External source | External Entity | Aspire source and DeepWiki results | Microsoft / DeepWiki |
| C002 | Review process | Process | Source normalization and decision matrix | ai-agents |
| C003 | Skill catalog | Data Store | Canonical `.claude/skills/` content | ai-agents |
| C004 | Eval harness | Process | Baseline and candidate comparison | ai-agents |
| C005 | Generated mirrors | Data Store | `src/copilot-cli/skills/` output | ai-agents |

### Data Flows

| ID | Source | Destination | Data | Protocol | Auth |
|---|---|---|---|---|---|
| DF001 | GitHub API | Review process | Commit and skill files | HTTPS | GitHub token |
| DF002 | DeepWiki | Review process | Provisional summaries | MCP | MCP session |
| DF003 | Review process | Skill catalog | Approved skill edits | File write | Local user |
| DF004 | Skill catalog | Eval harness | Candidate prompt content | File read | Local user |
| DF005 | Skill catalog | Generated mirrors | Generated skill copies | Local process | Local user |

### Trust Boundaries

| ID | Name | Description |
|---|---|---|
| TB001 | External content boundary | GitHub and DeepWiki content enters local reasoning |
| TB002 | Repository mutation boundary | Findings become tracked skill and spec files |
| TB003 | Eval subprocess boundary | Prompt content enters Copilot CLI in an isolated directory |

### Assets

| Asset | Classification | Sensitivity |
|---|---|---|
| GitHub token and SAML state | Confidential | High |
| Canonical skill catalog | Project source | High |
| Generated plugin skills | Customer-facing source | High |
| Eval scenarios and reports | Internal evidence | Medium |

## 3. STRIDE Analysis

### S - Spoofing

| ID | Element | Threat | Likelihood | Impact | Risk |
|---|---|---|---|---|---|
| T001 | C001 | Provisional summary is treated as authoritative Aspire source | Medium | High | High |

### T - Tampering

| ID | Element | Threat | Likelihood | Impact | Risk |
|---|---|---|---|---|---|
| T002 | DF001 | Source changes after review and invalidates citations | Medium | Medium | Medium |
| T003 | C002 | Embedded source instructions redirect the review or tool use | Medium | High | High |
| T004 | C005 | Generated mirror is hand-edited or drifts from canonical source | Low | High | Medium |

### R - Repudiation

| ID | Element | Threat | Likelihood | Impact | Risk |
|---|---|---|---|---|---|
| T005 | C002 | A source skill is omitted without a recorded decision | Medium | Medium | Medium |

### I - Information Disclosure

| ID | Element | Threat | Likelihood | Impact | Risk |
|---|---|---|---|---|---|
| T006 | DF001 | Token, SAML URL, email, or internal host enters a tracked artifact | Low | High | Medium |
| T007 | C004 | Eval errors persist raw prompt or provider output containing secrets | Low | High | Medium |

### D - Denial of Service

| ID | Element | Threat | Likelihood | Impact | Risk |
|---|---|---|---|---|---|
| T008 | C004 | Unbounded scenarios or repeated provider calls exhaust eval budget | Medium | Medium | Medium |

### E - Elevation of Privilege

| ID | Element | Threat | Likelihood | Impact | Risk |
|---|---|---|---|---|---|
| T009 | C002 | External paths escape approved repository destinations | Low | High | Medium |

## 4. Threat Matrix Summary

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk | Status |
|---|---|---|---|---|---|---|---|
| T001 | C001 | S | Provisional source accepted as authoritative | Medium | High | High | Mitigating |
| T002 | DF001 | T | Source changes after review | Medium | Medium | Medium | Mitigating |
| T003 | C002 | T | Embedded instruction execution | Medium | High | High | Mitigating |
| T004 | C005 | T | Generated mirror drift | Low | High | Medium | Mitigating |
| T005 | C002 | R | Silent source-skill omission | Medium | Medium | Medium | Mitigating |
| T006 | DF001 | I | Sensitive data enters artifacts | Low | High | Medium | Mitigating |
| T007 | C004 | I | Eval output leaks prompt or credentials | Low | High | Medium | Mitigating |
| T008 | C004 | D | Unbounded eval spend | Medium | Medium | Medium | Mitigating |
| T009 | C002 | E | External path escape | Low | High | Medium | Mitigating |

## 5. Mitigations

### T001: Provisional source accepted as authoritative

- [ ] Require a commit-pinned GitHub API source before skill edits.
- [ ] Label DeepWiki findings provisional.
- [ ] Map to acceptance criteria 1 and 7.

### T002: Source changes after review

- [ ] Record the Aspire commit SHA in every matrix citation.
- [ ] Compare only against the pinned source snapshot.
- [ ] Map to acceptance criterion 1.

### T003: Embedded instruction execution

- [ ] Treat external content as data.
- [ ] Never execute commands copied from source skills.
- [ ] Map to acceptance criterion 8.

### T004: Generated mirror drift

- [ ] Edit only canonical `.claude/skills/` files.
- [ ] Regenerate and run drift checks.
- [ ] Map to acceptance criteria 9 and 14.

### T005: Silent source-skill omission

- [ ] Require one decision row for every source skill.
- [ ] Map to acceptance criterion 2.

### T006: Sensitive data enters artifacts

- [ ] Redact tokens, SAML links, emails, and internal hostnames.
- [ ] Keep authentication errors out of durable artifacts.
- [ ] Map to acceptance criterion 13.

### T007: Eval output leaks prompt or credentials

- [ ] Use the eval harness fixed provider error categories.
- [ ] Persist scored results, not raw provider process output.
- [ ] Map to acceptance criterion 10.

### T008: Unbounded eval spend

- [ ] Use bounded scenario sets and three runs per scenario.
- [ ] Dry-run fixtures before provider calls.
- [ ] Map to acceptance criterion 10.

### T009: External path escape

- [ ] Normalize source paths as data.
- [ ] Write only to approved repository and session destinations.
- [ ] Map to acceptance criteria 2 and 14.

## 6. Residual Risk

The Copilot judge can still mis-score a candidate. Three-run comparison,
negative scenarios, no-regression checks, and human review reduce this risk.

## 7. Validation

- [ ] Every component has a named threat.
- [ ] Every trust boundary has a corresponding threat.
- [ ] Every High risk has a mitigation.
- [ ] Every mitigation maps to an acceptance criterion.
