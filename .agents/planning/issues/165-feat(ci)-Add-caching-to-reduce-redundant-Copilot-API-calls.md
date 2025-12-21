---
number: 165
title: "feat(ci): Add caching to reduce redundant Copilot API calls"
state: OPEN
created_at: 12/20/2025 10:39:36
author: rjmurillo-bot
labels: ["enhancement", "area-workflows", "automation"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/165
---

# feat(ci): Add caching to reduce redundant Copilot API calls

## Problem Statement

Each AI Quality Gate run makes 6 independent Copilot API calls, one per matrix job. When a workflow is re-run:
- All 6 API calls are made again
- Context is re-built from scratch (PR diff, description)
- Results are not cached between runs

This wastes premium API requests when:
1. Re-running due to infrastructure failures (5 agents already passed)
2. Minor PR updates that don't change the relevant files
3. Manual re-triggers for the same commit

### Cost Impact

| Scenario | Current Cost | With Caching |
|----------|--------------|--------------|
| Re-run for infra failure | 6 requests | 1 request |
| Minor doc update | 6 requests | 0 requests (cache hit) |
| Force re-run same commit | 6 requests | 6 requests (explicit bypass) |

## Proposed Solution

### 1. Result Caching by Content Hash

Cache AI review results keyed by:
- Agent name
- Prompt template hash
- Context content hash (PR diff + description)

```yaml
- name: Check cache for previous review
  id: cache-check
  uses: actions/cache@v4
  with:
    path: ai-review-cache/
    key: ai-review-${{ matrix.agent }}-${{ hashFiles(steps.context.outputs.context_file) }}
    restore-keys: |
      ai-review-${{ matrix.agent }}-

- name: Skip Copilot if cached
  if: steps.cache-check.outputs.cache-hit == 'true'
  run: |
    echo "Using cached review result"
    cp ai-review-cache/${{ matrix.agent }}-result.txt /tmp/ai-review-output.txt
```

### 2. Selective Re-run by Agent

Add workflow_dispatch inputs to bypass cache for specific agents:

```yaml
workflow_dispatch:
  inputs:
    agents:
      description: 'Agents to run (comma-separated, or "all")'
      required: false
      default: 'all'
    bypass-cache:
      description: 'Bypass cache and force fresh review'
      type: boolean
      default: false
```

### 3. Cache Invalidation Triggers

Invalidate cache when:
- Prompt templates change (different hash)
- PR base branch updates (merge from main)
- Explicit bypass requested
- Cache older than 24 hours

### 4. Incremental Context Analysis

For subsequent runs on the same PR:
- Cache the "baseline" review
- Only analyze new changes since last review
- Merge findings with previous results

## Acceptance Criteria

- [ ] Cache hit rate > 50% for re-runs
- [ ] Cache bypass option available
- [ ] Cache invalidation logic tested
- [ ] Cost reduction of 30-50% for re-run scenarios
- [ ] Metrics track cache hit/miss rates

## Related

- Issue #163: Job-level retry (caching complements retry)
- Issue #164: Failure categorization
- PR #156: Trigger for this investigation

## Labels

`enhancement`, `ci`, `cost-optimization`

---

## Comments

### Comment by @coderabbitai on 12/20/2025 10:40:39

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

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/163
- https://github.com/rjmurillo/ai-agents/issues/153
- https://github.com/rjmurillo/ai-agents/issues/116
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/moq.analyzers#554 - ci: run performance validation nightly and increase benchmark iteration count [merged]
rjmurillo/moq.analyzers#562 - feat(ci): automate and enhance performance validation, add semantic PR checks, and consolidate build steps [merged]
rjmurillo/vs-code-agents#57 - feat: Phase 1 CWE-78 Incident Remediation (Issues #16, #17, #18) [closed]
rjmurillo/ai-agents#76 - fix(workflows): strengthen AI review rigor and enable PR gating [merged]
rjmurillo/ai-agents#100 - fix(ci): ensure Pester Tests workflow satisfies required checks for all PRs [closed]
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

### Comment by @github-actions on 12/20/2025 10:43:36

<!-- AI-PRD-GENERATION -->

## 📋 Product Requirements Document

> [!IMPORTANT]
> This PRD was automatically generated based on issue triage escalation.
> **Complexity Score**: 8/12 ()
> **Escalation Criteria**: feature_request, multi_phase_work, research_required

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

Now I have comprehensive context. Let me create the PRD for this caching feature.

The file could not be created in that location. Let me output the PRD directly:

---

# PRD: CI Caching to Reduce Redundant Copilot API Calls

## Executive Summary

The AI Quality Gate workflow makes 6 independent Copilot API calls per run. Re-runs waste API requests when previous results remain valid. This PRD defines a caching mechanism to eliminate redundant calls.

| Scope | Status | Blocker |
|-------|--------|---------|
| Result caching by content hash | :green_circle: READY | None |
| Selective re-run by agent | :green_circle: READY | None |
| Cache invalidation logic | :green_circle: READY | None |
| Incremental context analysis | :yellow_circle: PARTIAL | Complexity requires Phase 2 |

**Verdict**: READY for Phase 1 implementation (core caching). Phase 2 addresses incremental analysis.

---

## 1. Problem Statement

### Current State

| Metric | Current Behavior |
|--------|------------------|
| API calls per workflow run | 6 (security, qa, analyst, architect, devops, roadmap) |
| Re-run behavior | All 6 agents execute from scratch |
| Context rebuild | Full PR diff + description fetched each time |
| Cache utilization | 0% (no caching exists) |
| Cost per re-run | 6 API requests |

### Gap Analysis

| Gap | Impact | Priority |
|-----|--------|----------|
| No result persistence | All 6 calls repeat on re-run | P0 |
| No content-based invalidation | Cannot detect when cache is stale | P0 |
| No selective agent execution | Cannot re-run single agent | P1 |
| No incremental diffing | Minor updates trigger full review | P2 |

### User Impact

1. **Repository Maintainers**: Wasted API quota on infrastructure failures (5 agents passed, 1 failed).
2. **Contributors**: Slower feedback on re-runs.
3. **Cost**: Premium Copilot API requests consumed redundantly.

---

## 2. Research Findings

### Primary Sources

| Source | Finding | Confidence |
|--------|---------|------------|
| actions/cache@v4 docs | Supports `key` and `restore-keys` for fallback matching. `cache-hit` output indicates exact match. | CONFIRMED |
| GitHub Actions hashFiles | `hashFiles()` computes SHA-256 of file contents. Glob patterns supported. | CONFIRMED |
| Existing ai-pr-quality-gate.yml | Uses `actions/cache@v4` for npm packages (lines 124-130). Pattern established. | CONFIRMED |
| AIReviewCommon.psm1 | Verdicts are simple strings (PASS, WARN, CRITICAL_FAIL). Easy to serialize. | CONFIRMED |

---

## 3. Proposed Solution

### Phase 1: Result Caching by Content Hash (READY)

**Estimated Effort**: M (4-8 hours)

| Task | Description |
|------|-------------|
| 1.1 | Add step to compute context content hash before Copilot invocation |
| 1.2 | Add cache restore step keyed by agent + context hash |
| 1.3 | Add conditional skip of Copilot CLI when cache hits |
| 1.4 | Add cache save step after successful Copilot invocation |
| 1.5 | Add cache bypass input for workflow_dispatch |

### Phase 2: Selective Re-run by Agent (READY)

**Estimated Effort**: S (2-4 hours)

| Task | Description |
|------|-------------|
| 2.1 | Add `agents` input to workflow_dispatch (comma-separated or "all") |
| 2.2 | Add matrix filter based on input value |
| 2.3 | Update aggregate job to handle partial results |

### Phase 3: Cache Invalidation Logic (READY)

**Estimated Effort**: S (2-4 hours)

| Task | Description |
|------|-------------|
| 3.1 | Include prompt template hash in cache key |
| 3.2 | Add timestamp-based TTL (24h) via key prefix |
| 3.3 | Document invalidation triggers in workflow comments |

### Phase 4: Incremental Context Analysis (DEFER)

**Estimated Effort**: L (8-16 hours)

**Recommendation**: Defer to follow-up issue. Core value delivered by Phase 1-3.

---

## 4. Functional Requirements

### FR-1: Cache Storage (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Cache MUST store verdict and findings for each agent | Cache contains `{agent}-verdict.txt` and `{agent}-findings.txt` |
| FR-1.2 | Cache key MUST include agent name | Key pattern: `ai-review-{agent}-{hash}` |
| FR-1.3 | Cache key MUST include context content hash | Hash computed from PR diff + description |
| FR-1.4 | Cache MUST be scoped to PR | Key includes PR number or commit SHA |

### FR-2: Cache Lookup (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-2.1 | Workflow MUST check cache before Copilot invocation | Cache check step precedes invoke step |
| FR-2.2 | Cache hit MUST skip Copilot CLI call | No API request when cache-hit=true |
| FR-2.3 | Cached verdict MUST be used for aggregation | Same verdict logic applies to cached results |

### FR-3: Cache Bypass (P1)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-3.1 | workflow_dispatch MUST support bypass-cache input | Boolean input `bypass-cache` available |
| FR-3.2 | bypass-cache=true MUST skip cache lookup | Copilot CLI always invoked when bypass=true |
| FR-3.3 | bypass-cache MUST still save results to cache | Fresh results stored for future runs |

### FR-4: Cache Invalidation (P1)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-4.1 | Cache key MUST include prompt template hash | Different prompt versions create different keys |
| FR-4.2 | Cache SHOULD expire after 24 hours | Date prefix in key or rely on GitHub's 7-day eviction |
| FR-4.3 | Base branch update MUST invalidate cache | Merge from main changes context hash |

### FR-5: Selective Agent Execution (P2)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-5.1 | workflow_dispatch MAY specify agents to run | Input `agents` accepts comma-separated list |
| FR-5.2 | Default value MUST be "all" | All 6 agents run when not specified |
| FR-5.3 | Partial runs MUST aggregate available results | Missing agents show as "SKIPPED" in report |

---

## 5. Technical Design

### Cache Key Structure

```text
ai-review-{agent}-{context_hash}-{prompt_hash}

Examples:
ai-review-security-abc123def456-789xyz
ai-review-qa-abc123def456-789xyz
```

### Context Hash Computation

```yaml
- name: Compute context hash
  id: context-hash
  shell: bash
  env:
    PR_NUMBER: ${{ env.PR_NUMBER }}
  run: |
    CONTEXT_FILE=$(mktemp)
    gh pr diff "$PR_NUMBER" > "$CONTEXT_FILE" 2>/dev/null || echo "no-diff" > "$CONTEXT_FILE"
    gh pr view "$PR_NUMBER" --json body,title >> "$CONTEXT_FILE" 2>/dev/null || true
    CONTEXT_HASH=$(sha256sum "$CONTEXT_FILE" | cut -d' ' -f1 | head -c 16)
    rm -f "$CONTEXT_FILE"
    echo "context_hash=$CONTEXT_HASH" >> $GITHUB_OUTPUT
```

### Cache Lookup and Skip Logic

```yaml
- name: Check cache for previous review
  id: cache-check
  uses: actions/cache@v4
  with:
    path: ai-review-cache/
    key: ai-review-${{ matrix.agent }}-${{ steps.context-hash.outputs.context_hash }}-${{ steps.prompt-hash.outputs.prompt_hash }}
    restore-keys: |
      ai-review-${{ matrix.agent }}-${{ steps.context-hash.outputs.context_hash }}-

- name: Use cached result
  if: steps.cache-check.outputs.cache-hit == 'true' && inputs.bypass-cache != 'true'
  run: |
    echo "Cache HIT - using cached review result"
    cp ai-review-cache/${{ matrix.agent }}-verdict.txt ai-review-results/
    cp ai-review-cache/${{ matrix.agent }}-findings.txt ai-review-results/
    echo "cache_used=true" >> $GITHUB_OUTPUT
```

### workflow_dispatch Inputs

```yaml
workflow_dispatch:
  inputs:
    pr_number:
      description: 'PR number to review'
      required: true
      type: number
    bypass-cache:
      description: 'Bypass cache and force fresh review'
      type: boolean
      default: false
    agents:
      description: 'Agents to run (comma-separated, or "all")'
      required: false
      default: 'all'
```

---

## 6. Implementation Plan

### Phase 1: Core Caching (4-8 hours)

1. Add context hash computation step
2. Add prompt hash computation step
3. Add cache restore step before AI review
4. Add conditional skip logic
5. Add cache save step after AI review

### Phase 2: Bypass and Selective Run (2-4 hours)

1. Add `bypass-cache` input
2. Add `agents` input with matrix filter
3. Update aggregate job for partial results

### Decision Tree

```text
Is PR re-triggered?
├── NO → Execute all 6 agents (no cache)
└── YES → Check cache for each agent
         ├── Cache HIT → Use cached result
         └── Cache MISS → Execute agent, save result
```

---

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Stale cache after code changes | Low | High | Context hash includes PR diff |
| Cache size limits | Low | Medium | Each entry <100KB |
| Prompt changes not detected | Medium | Medium | Include prompt hash in key |
| Debugging difficulty | Medium | Low | Log cache hit/miss and key |

---

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| Cache hit rate on re-runs | >50% |
| API request reduction | 30-50% |
| Time to feedback (cached) | <30s |

---

## 9. Open Questions (Non-Blocking)

1. **TTL beyond 7-day eviction**: GitHub's default is likely sufficient.
2. **Metrics dashboard**: Defer to Phase 3 if needed.
3. **Incremental diffing**: Create follow-up issue if Phase 1-3 shows need.

---

**Verdict**: READY. Implementation can proceed with Phase 1 (core caching) immediately.

---

<sub>📋 Generated by [AI PRD Generation](https://github.com/rjmurillo/ai-agents) · [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20393187237)</sub>



### Comment by @github-actions on 12/20/2025 10:43:38

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
|  **Priority** | `P1` |
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
  "reasoning": "Feature request to add caching to GitHub Actions AI Quality Gate workflow to reduce Copilot API costs on re-runs"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
```json
{
  "milestone": "v1.1",
  "priority": "P1",
  "epic_alignment": "",
  "confidence": 0.75,
  "reasoning": "CI cost optimization affects workflow reliability and cost, aligns with v1.1 maintainability focus but no existing epic covers CI caching",
  "escalate_to_prd": true,
  "escalation_criteria": ["feature_request", "multi_phase_work", "research_required"],
  "complexity_score": 8
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20393187237)</sub>


