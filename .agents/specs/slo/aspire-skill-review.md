# SLO Document: Aspire Skill Review

## Service Overview

- **Name**: Aspire skill review and augmentation process
- **Owner**: ConfigGen team
- **Description**: Converts a pinned external skill catalog into cited local
  decisions, targeted skill changes, generated mirrors, and eval evidence.
- **Business Criticality**: Medium

## Critical User Journeys

1. Inventory: every Aspire skill at the pinned commit receives a review row.
2. Selection: SkillForge routes every reusable idea to an existing owner,
   augmentation, composition, creation, or rejection.
3. Validation: changed guidance passes Copilot-provider evals or deterministic
   tests, then generated and repository gates.

## Service Level Indicators

### SLI 1: Inventory completeness

- **Definition**: Reviewed source skills divided by source skills present at the
  pinned commit.
- **Measurement**:
  `decision_matrix_rows_with_valid_source / pinned_source_skill_count`
- **Data Source**: Commit-pinned inventory and decision matrix.

### SLI 2: Citation validity

- **Definition**: Matrix citations that resolve to the pinned commit.
- **Measurement**:
  `resolving_source_citations / total_source_citations`
- **Data Source**: GitHub API source snapshot.

### SLI 3: Behavioral non-regression

- **Definition**: Changed judgment-bearing skills that clear the local eval
  harness gate.
- **Measurement**:
  `changed_skills_with_prompt_gate_pass / changed_judgment_skills`
- **Data Source**: `eval-prompt-change.py` reports with the `copilot`
  provider.

### SLI 4: Generated consistency

- **Definition**: Expected generated skill copies with no unexpected drift.
- **Measurement**:
  `expected_generated_files_without_drift / expected_generated_files`
- **Data Source**: `build_all.py --check` and repository drift validators.

## Service Level Objectives

| SLI | Target | Measurement Window | Rationale |
|---|---|---|---|
| Inventory completeness | 100% | Per review | Silent omission invalidates the comparison |
| Citation validity | 100% | Per review | Unresolved citations cannot authorize a skill change |
| Behavioral non-regression | 100% of changed judgment skills | Per change set | ADR-057 blocks regressions and high flakiness |
| Generated consistency | 100% | Per change set | Customer-facing mirrors must match canonical sources |

## Error Budgets

| SLO | Error Budget | Allowed Failure | Response |
|---|---|---|---|
| Inventory completeness | 0% | 0 omitted source skills | Stop and complete matrix |
| Citation validity | 0% | 0 unresolved citations | Stop skill edits |
| Behavioral non-regression | 0% | 0 failed changed skills | Revise or remove change |
| Generated consistency | 0% | 0 unexpected drift files | Inspect source and regenerate |

## Alerting Strategy

### Blocking alerts

- Source count and matrix row count differ.
- A source citation does not resolve at the pinned commit.
- A prompt-change eval fails.
- A generated drift gate reports unexpected files.

### Non-blocking trend

- Track P50 PR review rounds against the current 2.7 baseline.
- Track eval delta and `has_improvement` as non-blocking evidence.
- Do not attribute movement to this change without a controlled comparison.

## Error Budget Policy

Any blocking SLO breach stops implementation or review. No exception marker or
fallback may convert an unknown source, failed eval, or drift result into pass.

## Implementation Checklist

- [ ] Commit-pinned inventory produced
- [ ] Decision matrix count reconciled
- [ ] Citations resolved
- [ ] Copilot-provider eval reports recorded
- [ ] Generated drift checks passed
