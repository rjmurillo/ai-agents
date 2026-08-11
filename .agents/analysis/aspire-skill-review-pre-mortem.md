# Pre-Mortem Risk Inventory

**Project:** Aspire skill review and augmentation
**Date:** 2026-08-11
**Participants:** Individual analysis

## Project Context

- **Objective:** Produce a commit-pinned decision matrix and the smallest
  validated local skill augmentations.
- **Timeline:** TASK-019 through TASK-023.
- **Key Dependencies:** Authorized Aspire source, SkillForge, Copilot CLI eval
  provider, build generation, and repository validation gates.

The project failed. It did not produce trusted skill guidance, and the changes
increased review rounds instead of reducing them.

## Risk Summary

| Priority | Count | Top Risk |
|---|---|---|
| Critical | 3 | Source evidence remained incomplete |
| High | 4 | Eval evidence measured the wrong behavior |
| Medium | 0 | N/A |
| Low | 0 | N/A |

## Critical Risks

### R1: Source evidence remained incomplete

- **Category:** External
- **Failure Scenario:** SAML access stayed blocked, DeepWiki omitted files, and
  local changes were based on provisional summaries.
- **Likelihood:** 4 | **Impact:** 5 | **Score:** 20
- **Root Cause:** The review treated discovery evidence as source authority.
- **Mitigation:**
  - **Prevention:** TASK-019 requires an authorized commit-pinned inventory.
  - **Detection:** Source count, paths, and hashes must reconcile before
    TASK-020.
  - **Response:** Halt skill edits and publish provisional research only.
- **Owner:** TASK-019 implementer
- **Status:** Mitigating

### R2: Behavioral eval measured the wrong comparison

- **Category:** Technical
- **Failure Scenario:** A skill-versus-no-skill harness passed while the changed
  prompt regressed against its base version.
- **Likelihood:** 4 | **Impact:** 4 | **Score:** 16
- **Root Cause:** The spec selected knowledge integration instead of prompt
  change evaluation.
- **Mitigation:**
  - **Prevention:** DESIGN-019 requires `eval-prompt-change.py`.
  - **Detection:** Dry-run records base and working-copy prompt sources.
  - **Response:** Reject the report and rerun with `--provider copilot`.
- **Owner:** TASK-022 implementer
- **Status:** Mitigating

### R3: Duplicate capability entered the skill catalog

- **Category:** Process
- **Failure Scenario:** A new skill duplicated an existing skill, agent, or
  command and split trigger ownership.
- **Likelihood:** 3 | **Impact:** 5 | **Score:** 15
- **Root Cause:** Review stopped at matching names instead of routing across the
  whole capability ecosystem.
- **Mitigation:**
  - **Prevention:** TASK-020 applies SkillForge thresholds to skills, agents,
    and commands.
  - **Detection:** Close candidates run pairwise overlap evaluation.
  - **Response:** Remove the new skill and augment or compose the existing owner.
- **Owner:** TASK-020 implementer
- **Status:** Mitigating

## High Risks

### R4: External instructions redirected execution

- **Category:** Security
- **Failure Scenario:** A source skill told the agent to run commands, post
  comments, or change scope, and the agent obeyed.
- **Likelihood:** 3 | **Impact:** 4 | **Score:** 12
- **Root Cause:** Repository content crossed the instruction trust boundary.
- **Mitigation:**
  - **Prevention:** Treat every external file as untrusted data.
  - **Detection:** Review durable artifacts for copied operational commands.
  - **Response:** Remove affected content, rotate exposed credentials, and
    rerun from the pinned source.
- **Owner:** Security reviewer
- **Status:** Mitigating

### R5: Decision matrix silently omitted a source skill

- **Category:** Process
- **Failure Scenario:** The final recommendation looked complete but lacked one
  or more source directories.
- **Likelihood:** 3 | **Impact:** 4 | **Score:** 12
- **Root Cause:** Human-readable matrix rows were not reconciled to the
  machine-readable inventory.
- **Mitigation:**
  - **Prevention:** TASK-020 consumes TASK-019's JSON path list.
  - **Detection:** Matrix row count and source IDs must equal inventory count.
  - **Response:** Block TASK-021 until missing rows are added.
- **Owner:** TASK-020 implementer
- **Status:** Mitigating

### R6: Generated skill copies drifted

- **Category:** Technical
- **Failure Scenario:** Canonical skills changed but shipped Copilot copies were
  stale or hand-edited.
- **Likelihood:** 3 | **Impact:** 4 | **Score:** 12
- **Root Cause:** Source and generated surfaces changed independently.
- **Mitigation:**
  - **Prevention:** Edit only `.claude/skills/` and run `build_all.py`.
  - **Detection:** Generated drift checks and diff review.
  - **Response:** Discard generated hand edits and regenerate.
- **Owner:** TASK-023 implementer
- **Status:** Mitigating

### R7: Copilot judge could not discriminate changes

- **Category:** Technical
- **Failure Scenario:** Baseline and candidate tied because scenarios or verdict
  criteria were too weak.
- **Likelihood:** 3 | **Impact:** 3 | **Score:** 9
- **Root Cause:** Eval fixtures encoded the authoring prompt rather than hidden
  failure conditions.
- **Mitigation:**
  - **Prevention:** Include negative and edge scenarios for duplicate creation,
    source identity, and product-specific copying.
  - **Detection:** Reports surface delta and `has_improvement`; ADR-057 still
    gates regressions and high flakiness.
  - **Response:** Recalibrate scenarios, then rerun both variants.
- **Owner:** TASK-022 implementer
- **Status:** Mitigating

## Medium Risks

None.

## Low Risks

None.

## Action Items

| Action | Owner | Due Date | Risk Addressed |
|---|---|---|---|
| Pin and reconcile Aspire source | TASK-019 implementer | Before TASK-020 | R1, R5 |
| Bind matrix rows to local owners | TASK-020 implementer | Before TASK-021 | R3, R5 |
| Dry-run prompt-change scenarios | TASK-022 implementer | Before provider calls | R2, R7 |
| Review untrusted-content handling | Security reviewer | Before TASK-023 | R4 |
| Regenerate and inspect mirrors | TASK-023 implementer | Before pre-PR | R6 |

## Review Schedule

- **Next review:** After TASK-020 selects the exact change set.
- **Review frequency:** At each task boundary.
