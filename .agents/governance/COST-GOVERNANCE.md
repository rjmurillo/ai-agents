# Cost Governance

## Overview

This document outlines cost optimization policies and practices for the AI Agents project, covering GitHub Actions infrastructure costs and work-selection-attributed model token costs.

## GitHub Actions Cost Policy

### Runner Selection (ADR-014)

**Policy**: All GitHub Actions workflows MUST use `ubuntu-24.04-arm` runners unless documented ARM compatibility issues exist.

**Cost Impact**:

| Runner Type | Cost/Min | Use Case | Status |
|-------------|----------|----------|--------|
| `ubuntu-24.04-arm` | $0.005 | Default for Linux workflows | **Preferred** |
| `ubuntu-latest` (x64) | $0.008 | ARM-incompatible workloads only | Exception only |
| `windows-latest` | $0.016 | Windows-specific requirements | Exception only |

**Savings**: 37.5% cost reduction on Linux workflows ($0.008 → $0.005 per minute)

**See**: [ADR-024: GitHub Actions Runner Selection](../../.project-toolkit/architecture/ADR-024-github-actions-runner-selection.md)

### Current Implementation Status

**Migrated to ARM (19 jobs)**:

- agent-metrics.yml (2 jobs)
- ai-issue-triage.yml (1 job)
- ai-pr-quality-gate.yml (4 jobs)
- ai-spec-validation.yml (1 job)
- copilot-context-synthesis.yml (2 jobs)
- drift-detection.yml (1 job)
- pester-tests.yml (3 jobs: check-paths, test, skip-tests)
- validate-generated-agents.yml (1 job)
- validate-paths.yml (3 jobs)
- validate-planning-artifacts.yml (1 job)

**x64 Exceptions (1 job)**:

- copilot-setup-steps.yml (copilot-setup-steps job) - Must match Copilot agent architecture (x64) for dependency compatibility

### Compliance Requirements

**All workflows MUST include ADR-014 compliance comments**:

ARM runners:

```yaml
jobs:
  job-name:
    # ADR-014: ARM runner for cost optimization (37.5% savings vs x64)
    runs-on: ubuntu-24.04-arm
```

Windows exceptions:

```yaml
jobs:
  job-name:
    # ADR-014 Exception: Windows runner required for [specific reason]
    # Issue: [Link to tracking issue or upstream limitation]
    runs-on: windows-latest
```

x64 exceptions (if any):

```yaml
jobs:
  job-name:
    # ADR-014 Exception: [Tool/dependency name] lacks ARM support
    # Issue: [Link to tracking issue or upstream limitation]
    runs-on: ubuntu-latest
```

## Cost Monitoring

### Metrics to Track

1. **Monthly runner minutes** by type (ARM, x64, Windows)
2. **Cost per runner type**
3. **Workflow execution time trends**
4. **Failed workflow retry costs**

### Review Cadence

- **Weekly**: Review source split, machinery share, retries and unsuccessful work, token and cost coverage, accepted-task completion, residual defects, human correction time, wall time, retrospectives, always-on context bytes, and tokens per merged PR. Treat missing telemetry as unknown. **Source:** #5702, `scripts/validation/instruction_budget.py`, and `scripts/validation/passive_context_budget.py`.
- **Monthly**: Review runner usage and costs
- **Quarterly**: Evaluate ARM compatibility of remaining x64 workloads
- **Annually**: Review runner selection policy against GitHub pricing changes

## Exception Process

### Requesting x64 or Windows Runners

When ARM runners cannot be used:

1. **Document the reason** in workflow with ADR-014 exception comment
2. **Link to evidence**:
   - Upstream issue for ARM support
   - Tool documentation stating x64/Windows requirement
   - Test results showing ARM incompatibility
3. **Create tracking issue** if tool is expected to add ARM support
4. **Re-evaluate quarterly** to migrate when possible

### Approval Requirements

- **Windows runners**: Automatic approval if Windows-specific functionality required
- **x64 runners**: Document ARM incompatibility with evidence
- **Self-hosted runners**: Requires architecture review (ADR process)

## Best Practices

### Workflow Optimization

1. **Cache dependencies** to reduce execution time
2. **Use path filters** to skip unnecessary runs
3. **Parallelize independent jobs** for faster feedback
4. **Set appropriate timeouts** to prevent runaway costs
5. **Use artifact retention policies** to limit storage costs

### ARM Compatibility Verification

Before migrating to ARM:

1. **Check tool ARM support**:
   - GitHub official actions (all ARM-compatible)
   - Python packages (verify ARM64 wheels available)
   - Node.js packages (verify ARM64 support)
   - Docker images (verify multi-arch or ARM64 images exist)
2. **Test locally** on ARM64 Linux if available
3. **Test in PR** before merging
4. **Monitor first runs** for performance/compatibility issues

## Cost Optimization Wins

### Completed Initiatives

| Initiative | Impact | Status |
|------------|--------|--------|
| ARM Runner Migration | 37.5% reduction on Linux workflows | ✅ Complete |

### Planned Initiatives

| Initiative | Target Date | Expected Impact |
|------------|-------------|-----------------|
| Workflow path filter optimization | Q1 2026 | 20-30% reduction in unnecessary runs |
| Dependency caching improvements | Q1 2026 | 10-15% execution time reduction |

## Model Token Cost Policy

### Cost Model

For one task, model token cost is a fraction of human cost. Over a period, total model cost is that fraction multiplied by the number of tasks agents choose to run. Agents set that multiplier through work selection, so the relevant split is human-selected versus agent-selected work. This policy covers work-selection-attributed period cost. It does not claim that the repository tracks all model token spend.

**Refs:** #5436, #5702, and the review corrections in #5705.

### Metrics to Track

Review these metrics weekly:

- Issues created per week by mutually exclusive recorded provenance bucket: human-only (`source:human` without `source:agent`), agent-only (`source:agent` without `source:human`), conflict (both labels), and unknown (unlabeled). Labels record provenance; they do not independently verify who selected the work.
- The share of new issues about repository machinery, including validators, ratchets, hooks, ADRs, `pr-autofix`, and memory. Treat title matching as a labeled heuristic, not causal attribution.
- Retries and unsuccessful work.
- Token and cost coverage, including where the harness exposes token data. Missing coverage is unknown.
- Accepted-task completion, residual defects, human correction time, and wall time.
- Count retrospectives per week.
- Always-on context bytes per session. Parse rule frontmatter for `paths: ["**"]` before summing file bytes. Static rule bytes are not per-session token consumption.
- Tokens per merged PR where the harness exposes them.

**Source:** #5702 defines the read-only provenance and machinery measurement surface. The existing `scripts/validation/instruction_budget.py` and `scripts/validation/passive_context_budget.py` provide related context-budget surfaces; neither currently reads Claude rule frontmatter.

### Baseline (2026-09-10)

The historical snapshot recorded in #5705 reported:

- 405 issues created in 30 days and 278 closed. A backlog snapshot reported 228 open issues, with 200 open issues under 20 days old.
- 96 retrospectives in 40 days.
- Five globally scoped Claude rule files totaling 56,984 static bytes, about 57 KB: `voice.md`, `builder-ethos.md`, `universal.md`, `search-before-building.md`, and `claude-model-patches.md`.
- The other 24 rule files totaling 220 KB were path-scoped and loaded only when a matching path was edited.

The historical retrieval metadata is incomplete: the backlog query is not recorded, the state filter is not recorded, the retrieval date is 2026-09-10 but the time is not recorded, and the source SHA is not recorded. The reproducible rule-byte query is to parse YAML frontmatter in `.claude/rules/*.md` for `paths: ["**"]` and sum file bytes, but the cited snapshot's retrieval time and source SHA are not recorded. These figures are historical context, not recomputed acceptance evidence. Recompute issue, provenance, and machinery figures through #5702. For rule bytes, use a reproducible reader that parses the frontmatter; the cited budget tools do not currently perform that read. Missing token, retry, completion, defect, correction-time, or wall-time telemetry is unknown.

**Source:** #5705's historical snapshot and review corrections; #5702; `scripts/validation/instruction_budget.py`; `scripts/validation/passive_context_budget.py`.

### Runaway Condition

Raise an owner-reviewed signal when the weekly report shows agent-sourced share exceeds 50 percent of new issues or more than 3 retrospectives in a week. These are review signals, not automatic enforcement thresholds. A human maintainer must decide whether this signal is a significant governance change under `governance.md` MUST 2 and whether an ADR is required. This issue does not create that ADR.

**Source:** #5705 review corrections, `.claude/rules/governance.md` MUST 2, and #5702.

## References

- [ADR-024: GitHub Actions Runner Selection](../../.project-toolkit/architecture/ADR-024-github-actions-runner-selection.md)
- [GitHub Actions Pricing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [GitHub ARM Runners Documentation](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners/about-github-hosted-runners#standard-github-hosted-runners-for-public-repositories)
