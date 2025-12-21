---
number: 163
title: "feat(ci): Implement job-level retry for AI Quality Gate matrix jobs"
state: OPEN
created_at: 12/20/2025 10:38:40
author: rjmurillo-bot
labels: ["enhancement", "area-workflows", "priority:P1", "automation"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/163
---

# feat(ci): Implement job-level retry for AI Quality Gate matrix jobs

## Problem Statement

When a single matrix job in the AI PR Quality Gate workflow fails due to infrastructure issues (e.g., Copilot CLI access problems), re-running the workflow requires re-executing ALL 6 matrix jobs. This is wasteful because:

1. **Cost**: Each matrix job makes 1 premium GitHub Copilot API request
2. **Time**: Full workflow runs take ~90 seconds; re-running 6 jobs when only 1 failed wastes 5x the compute
3. **False positives**: Infrastructure failures (exit code 1 with no output) cascade to CRITICAL_FAIL verdict

### Evidence

From run [20392831443](https://github.com/rjmurillo/ai-agents/actions/runs/20392831443):
- 5 of 6 agents returned PASS
- Analyst agent failed with: "Copilot CLI failed (exit code 1) with no output"
- Final verdict: CRITICAL_FAIL (one bad agent poisoned the batch)

### Cost Analysis

| Metric | Per Run | With Retry |
|--------|---------|------------|
| Matrix jobs | 6 | 6 |
| Premium requests | 6 | 12 (6 wasted) |
| Compute minutes | ~1.5 min | ~3 min |

## Proposed Solution

### Option A: Job-Level Retry (Recommended)

Add `retry-on-infrastructure-failure` logic to the composite action:

```yaml
# In action.yml, wrap invoke step with retry
- name: Invoke Copilot CLI with retry
  id: invoke
  shell: bash
  run: |
    MAX_RETRIES=2
    RETRY_DELAY=10
    
    for i in $(seq 1 $MAX_RETRIES); do
      # ... invoke copilot ...
      if [ $EXIT_CODE -eq 0 ]; then
        break
      elif is_infrastructure_failure "$OUTPUT" "$STDERR"; then
        echo "::warning::Infrastructure failure detected, retry $i of $MAX_RETRIES"
        sleep $RETRY_DELAY
      else
        break  # Code quality failure, don't retry
      fi
    done
```

### Option B: Categorize Failures

Distinguish between:
- **Infrastructure failures**: Copilot CLI exit 1 with no output, timeouts, rate limits
- **Code quality failures**: Actual CRITICAL_FAIL verdicts from AI analysis

Infrastructure failures should NOT cascade to final verdict. Instead:
1. Mark agent as SKIPPED or DEGRADED
2. Allow workflow to continue with partial results
3. Surface warning in PR comment without blocking

### Option C: Selective Re-run API

Use GitHub's "Re-run failed jobs" feature more effectively:
- Ensure matrix jobs are independently re-runnable
- Add workflow_dispatch input for single-agent re-run

## Acceptance Criteria

- [ ] Infrastructure failures retry automatically (1-2 attempts with backoff)
- [ ] Infrastructure failures do not cascade to CRITICAL_FAIL
- [ ] Cost reduced by ~50% for infrastructure-related re-runs
- [ ] PR comment clearly indicates infrastructure vs code quality issues
- [ ] Metrics added to track retry rates and success patterns

## Related

- PR #156: Demonstrated this failure pattern
- Run 20392831443: Evidence of infrastructure failure
- Copilot CLI de-prioritization decision: Known reliability issues

## Labels

`enhancement`, `ci`, `cost-optimization`

---

## Comments

### Comment by @coderabbitai on 12/20/2025 10:41:25

<!-- This is an auto-generated issue plan by CodeRabbit -->


### 📝 CodeRabbit Plan Mode
Generate an implementation plan and prompts that you can use with your favorite coding agent.

- [ ] <!-- {"checkboxId": "8d4f2b9c-3e1a-4f7c-a9b2-d5e8f1c4a7b9"} --> Create Plan

<details>
<summary>Examples</summary>

- [Example 1](https://github.com/coderabbitai/git-worktree-runner/issues/29#issuecomment-3589134556)
- [Example 2](https://github.com/coderabbitai/git-worktree-runner/issues/12#issuecomment-3606665167)

</details>

---

<details>
<summary><b>🔗 Similar Issues</b></summary>

**Possible Duplicates**
- ISSUE-153

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/153
- https://github.com/rjmurillo/ai-agents/issues/74
- https://github.com/rjmurillo/ai-agents/issues/108
- https://github.com/rjmurillo/ai-agents/issues/105
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/moq.analyzers#554 - ci: run performance validation nightly and increase benchmark iteration count [merged]
rjmurillo/vs-code-agents#57 - feat: Phase 1 CWE-78 Incident Remediation (Issues #16, #17, #18) [closed]
rjmurillo/ai-agents#76 - fix(workflows): strengthen AI review rigor and enable PR gating [merged]
rjmurillo/ai-agents#100 - fix(ci): ensure Pester Tests workflow satisfies required checks for all PRs [closed]
rjmurillo/ai-agents#109 - fix(ci): add checkout step to skip-tests job in Pester workflow [closed]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo-bot](https://github.com/rjmurillo-bot)
- [rjmurillo](https://github.com/rjmurillo)
</details>


---
<details>
<summary> 🧪 Issue enrichment is currently in open beta.</summary>


You can configure auto-planning by selecting labels in the issue_enrichment configuration.

To disable automatic issue enrichment, add the following to your `.coderabbit.yaml`:
```yaml
issue_enrichment:
  auto_enrich:
    enabled: false
```
</details>

💬 Have feedback or questions? Drop into our [discord](https://discord.gg/coderabbit) or [schedule a call](https://calendly.com/parth-coderabbit/issues-feedback)!

### Comment by @github-actions on 12/20/2025 10:42:23

<!-- AI-PRD-GENERATION -->

## 📋 Product Requirements Document

> [!IMPORTANT]
> This PRD was automatically generated based on issue triage escalation.
> **Complexity Score**: 8/12 ()
> **Escalation Criteria**: feature_request, multi_phase_work, architectural_impact

<details>
<summary>📖 About this PRD</summary>

This PRD was generated by the **Explainer Agent** after the issue was flagged
for detailed analysis. The document is designed to be self-contained - it can
be passed to a separate AI agent instance for implementation without additional
context.

**PRD Depth Levels**:
- **Standard** (4-6): Brief analysis, clear requirements
- **Detailed** (7-9): Research section, blocking questions
- **Comprehensive** (10-12): Phased implementation, risk analysis

</details>

---

Now I have enough context. Let me create the PRD for the job-level retry feature.

The file creation was denied. Let me output the PRD directly:

---

# PRD: Job-Level Retry for AI Quality Gate Matrix Jobs

## Executive Summary

The AI PR Quality Gate workflow runs 6 matrix jobs in parallel. When a single job fails due to infrastructure issues, the entire workflow is marked CRITICAL_FAIL, requiring re-execution of all 6 jobs. This wastes compute resources and GitHub Copilot API requests.

| Scope | Status | Blocker |
|-------|--------|---------|
| Job-level retry logic | :green_circle: READY | None |
| Infrastructure failure detection | :green_circle: READY | None |
| Failure categorization (infra vs code quality) | :green_circle: READY | None |
| PR comment differentiation | :green_circle: READY | None |
| Retry metrics tracking | :yellow_circle: PARTIAL | Metrics collection mechanism not defined |

**Verdict: READY** - Implementation can proceed with core retry functionality.

## Problem Statement

### Current State

| Component | Current Behavior |
|-----------|------------------|
| Matrix jobs | 6 agents run in parallel (security, qa, analyst, architect, devops, roadmap) |
| Failure handling | Single job failure cascades to CRITICAL_FAIL for entire workflow |
| Retry mechanism | None - full workflow must be re-run manually |
| Cost per run | 6 premium Copilot API requests |
| Re-run cost | 12 premium requests (6 wasted if only 1 job failed) |

### Gap Analysis

1. **No automatic retry**: Infrastructure failures require manual intervention
2. **No failure categorization**: Infrastructure failures treated same as code quality failures
3. **Wasted resources**: Re-running all jobs when 1 failed wastes 5x compute
4. **Poor visibility**: PR comments do not distinguish failure types

### User Impact

- **Maintainers**: Must manually re-run failed workflows, increasing toil
- **Contributors**: PRs blocked by infrastructure issues, not actual code problems
- **Cost**: Each unnecessary re-run costs 6 premium Copilot API requests

## Research Findings

### Evidence from Production (CONFIRMED)

Run [20392831443](https://github.com/rjmurillo/ai-agents/actions/runs/20392831443):

- 5 of 6 agents returned PASS
- Analyst agent failed with: "Copilot CLI failed (exit code 1) with no output"
- Root cause: Infrastructure failure (Copilot API connectivity or access issue)
- Impact: CRITICAL_FAIL verdict despite 83% success rate

### Infrastructure Failure Patterns (CONFIRMED)

From `action.yml` lines 522-568, infrastructure failures are detected by:

1. **Exit code 1 with no output**: CLI produced no stdout or stderr
2. **Timeout (exit code 124)**: CLI exceeded timeout threshold
3. **Empty response**: No parseable verdict in output

Current behavior creates synthetic CRITICAL_FAIL verdict:

```bash
OUTPUT="VERDICT: CRITICAL_FAIL"$'\n'"MESSAGE: Copilot CLI failed (exit code $EXIT_CODE) with no output"
```

### Retry Pattern Precedent (CONFIRMED)

The codebase already has retry logic in `AIReviewCommon.psm1`:

```powershell
function Invoke-WithRetry {
    $delay = $InitialDelay
    for ($i = 1; $i -le $MaxRetries; $i++) {
        try { return & $ScriptBlock }
        catch {
            if ($i -eq $MaxRetries) { throw }
            Start-Sleep -Seconds $delay
            $delay = $delay * 2
        }
    }
}
```

Configuration defaults: `MaxRetries = 3`, `RetryDelay = 30` seconds.

## Proposed Solution

### Phase 1: Infrastructure Retry in Composite Action (READY)

**Estimated Effort**: M (2-4 hours)

| Task | Description |
|------|-------------|
| 1.1 | Add `is_infrastructure_failure()` function to detect retry-eligible failures |
| 1.2 | Wrap Copilot CLI invocation in retry loop (max 2 retries, 10s delay) |
| 1.3 | Add retry attempt counter to outputs |
| 1.4 | Update action outputs to include `retry_count` and `failure_type` |

### Phase 2: Failure Categorization (READY)

**Estimated Effort**: S (1-2 hours)

| Task | Description |
|------|-------------|
| 2.1 | Create `INFRA_FAIL` verdict type distinct from `CRITICAL_FAIL` |
| 2.2 | Update `Merge-Verdicts` to handle `INFRA_FAIL` as non-blocking |
| 2.3 | Add `DEGRADED` final verdict when some agents had infrastructure issues |

### Phase 3: PR Comment Differentiation (READY)

**Estimated Effort**: S (1-2 hours)

| Task | Description |
|------|-------------|
| 3.1 | Update PR comment template to show infrastructure failures separately |
| 3.2 | Add warning callout for infrastructure issues |
| 3.3 | Include retry count in agent status table |

## Functional Requirements

### FR-1: Infrastructure Failure Detection (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Detect infrastructure failures by exit code and output analysis | Exit code 1 with empty stdout/stderr identified as infrastructure failure |
| FR-1.2 | Detect timeout failures | Exit code 124 identified as infrastructure failure |
| FR-1.3 | Distinguish infrastructure from code quality failures | Code quality failures (CRITICAL_FAIL with actual findings) are not retried |

### FR-2: Automatic Retry (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-2.1 | Retry infrastructure failures automatically | Up to 2 retry attempts with 10-second delay |
| FR-2.2 | Do not retry code quality failures | Failures with parseable CRITICAL_FAIL verdict are not retried |
| FR-2.3 | Use exponential backoff | Delay doubles on each retry (10s, 20s) |
| FR-2.4 | Output retry count | `retry_count` output indicates retries attempted |

### FR-3: Failure Categorization (P1)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-3.1 | Support INFRA_FAIL verdict | New verdict type for infrastructure failures that exhausted retries |
| FR-3.2 | Do not cascade INFRA_FAIL to final verdict | Single INFRA_FAIL does not make final verdict CRITICAL_FAIL |
| FR-3.3 | Support DEGRADED final verdict | Final verdict is DEGRADED when some agents had INFRA_FAIL |

## Technical Design

### action.yml Changes

```yaml
outputs:
  retry-count:
    description: 'Number of retry attempts made (0 = first attempt succeeded)'
    value: ${{ steps.invoke.outputs.retry_count }}
  failure-type:
    description: 'Type of failure: NONE, INFRA, CODE_QUALITY'
    value: ${{ steps.invoke.outputs.failure_type }}
```

### Invoke Step Changes

```bash
is_infrastructure_failure() {
  local exit_code="$1"
  local stdout="$2"
  local stderr="$3"
  
  [ "$exit_code" -eq 124 ] && return 0
  [ "$exit_code" -eq 1 ] && [ -z "$stdout" ] && [ -z "$stderr" ] && return 0
  echo "$stdout$stderr" | grep -qE 'rate limit|network|timeout|connection|unavailable' && return 0
  return 1
}

MAX_RETRIES=2
RETRY_DELAY=10
RETRY_COUNT=0
FAILURE_TYPE="NONE"

for attempt in $(seq 1 $((MAX_RETRIES + 1))); do
  # ... invoke copilot CLI ...
  
  if [ $EXIT_CODE -eq 0 ]; then break; fi
  
  if is_infrastructure_failure "$EXIT_CODE" "$OUTPUT" "$STDERR_OUTPUT"; then
    if [ $attempt -le $MAX_RETRIES ]; then
      echo "::warning::Infrastructure failure, retry $attempt of $MAX_RETRIES"
      RETRY_COUNT=$attempt
      sleep $RETRY_DELAY
      RETRY_DELAY=$((RETRY_DELAY * 2))
    else
      FAILURE_TYPE="INFRA"
    fi
  else
    FAILURE_TYPE="CODE_QUALITY"
    break
  fi
done
```

### AIReviewCommon.psm1 Changes

Update `Merge-Verdicts` to handle `INFRA_FAIL`:

```powershell
$infraFailCount = 0
foreach ($verdict in $Verdicts) {
    switch ($verdict) {
        'INFRA_FAIL' { $infraFailCount++ }
        { $_ -in 'CRITICAL_FAIL', 'REJECTED', 'FAIL' } { return 'CRITICAL_FAIL' }
        'WARN' { if ($final -eq 'PASS') { $final = 'WARN' } }
    }
}

if ($infraFailCount -gt 0 -and $final -eq 'PASS') { return 'DEGRADED' }
return $final
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Retry delays extend workflow time | Medium | Low | Cap at 2 retries with 10s/20s delays (max 30s added) |
| False positive infrastructure detection | Low | Medium | Conservative detection - only clear infrastructure signals |
| Retry masks persistent issues | Low | High | Log retry patterns, surface in metrics |

## Success Metrics

| Metric | Target |
|--------|--------|
| Reduction in full workflow re-runs | 50% decrease for infrastructure failures |
| Retry success rate | 80% of infrastructure failures succeed on retry |
| Total workflow time increase | Less than 60 seconds average |

## Implementation Files

| File | Purpose |
|------|---------|
| `.github/actions/ai-review/action.yml` | Composite action to modify |
| `.github/scripts/AIReviewCommon.psm1` | PowerShell module with verdict handling |
| `.github/scripts/AIReviewCommon.Tests.ps1` | Tests for PowerShell module |
| `.github/workflows/ai-pr-quality-gate.yml` | Workflow that consumes action |

---

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-20 | explainer | Initial PRD |

---

<sub>📋 Generated by [AI PRD Generation](https://github.com/rjmurillo/ai-agents) · [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20393176428)</sub>



### Comment by @github-actions on 12/20/2025 10:42:25

<!-- AI-ISSUE-TRIAGE -->

## AI Triage Summary

> [!NOTE]
> This issue has been automatically triaged by AI agents

<details>
<summary>What is AI Triage?</summary>

This issue was analyzed by AI agents:

- **Analyst Agent**: Categorizes the issue and suggests appropriate labels
- **Roadmap Agent**: Aligns the issue with project milestones and priorities
- **Explainer Agent** (if escalated): Generates comprehensive PRD

</details>

### Triage Results

| Property | Value |
|:---------|:------|
| **Category** | `enhancement` |
| **Labels** | enhancement area-workflows area-infrastructure |
|  **Priority** | `P2` |
| **Milestone** | v1.1 |
| **PRD Escalation** | Generated (see below) |

<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "area-workflows", "area-infrastructure"],
  "category": "enhancement",
  "confidence": 0.95,
  "reasoning": "Feature request to implement job-level retry logic for GitHub Actions workflow matrix jobs to reduce costs and handle infrastructure failures gracefully"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
Based on the issue analysis and roadmap context:

**Issue Assessment:**
- **Type**: Feature request for CI/CD workflow improvement (job-level retry)
- **Impact**: Medium - affects cost and time for workflow reruns (6 matrix jobs)
- **Scope**: Multiple phases proposed (retry logic, failure categorization, selective re-run)
- **Evidence**: Documented run with 5/6 PASS, 1 infrastructure failure = CRITICAL_FAIL cascade
- **Cost data**: 50% potential reduction in wasted premium API requests

**Roadmap Alignment:**
- No direct epic alignment, but relates to AI PR Quality Gate workflow (v1.0 Complete)
- Copilot CLI reliability issues are documented in the Copilot CLI de-prioritization decision
- This issue addresses infrastructure failures in workflows that use Copilot CLI

**Escalation Criteria Met:**
1. **Feature Request**: New retry functionality, failure categorization
2. **Multi-Phase Work**: Three options proposed, acceptance criteria spans multiple areas
3. **Architectural Impact**: Changes to composite action pattern, affects all 6 matrix agents

```json
{
  "milestone": "v1.1",
  "priority": "P2",
  "epic_alignment": "",
  "confidence": 0.70,
  "reasoning": "Cost optimization for known Copilot CLI reliability issues; aligns with v1.1 maintainability focus but not critical path",
  "escalate_to_prd": true,
  "escalation_criteria": ["feature_request", "multi_phase_work", "architectural_impact"],
  "complexity_score": 8
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20393176428)</sub>


