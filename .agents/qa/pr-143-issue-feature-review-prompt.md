# QA Report: Issue Feature Review Prompt

**Date**: 2025-12-22
**PR**: #143
**File**: `.github/prompts/issue-feature-review.md`
**Type**: AI Prompt Template

## Overview

This QA report covers the new `issue-feature-review.md` prompt template that will be used by the critic agent to evaluate feature requests in the issue triage workflow.

## Verification Scope

| Aspect | Status | Notes |
|--------|--------|-------|
| Prompt Structure | PASS | Follows established prompt template patterns |
| Instructions Clarity | PASS | Clear step-by-step evaluation framework |
| Output Format | PASS | Well-defined markdown output structure |
| Error Handling | PASS | Explicit "UNKNOWN" handling for unavailable data |
| Anti-patterns | PASS | Lists specific behaviors to avoid |

## Prompt Analysis

### 1. Role Definition
- Clear role: "expert .NET open-source reviewer"
- Behavioral guidance: "polite, clear, and constructively skeptical"

### 2. Context Limitations
- Explicitly states what tools are NOT available
- Instructs model to be transparent about data availability
- Pattern: "UNKNOWN - requires manual research by maintainer"

### 3. Evaluation Framework

| Step | Purpose | Validation |
|------|---------|------------|
| 1 | Acknowledge submitter | Genuine, not formulaic |
| 2 | Summarize request | Confirms understanding |
| 3 | Evaluate criteria | 5 criteria with confidence levels |
| 4 | Research questions | Self-answer before asking |
| 5 | Recommendation | PROCEED/DEFER/REQUEST_EVIDENCE/NEEDS_RESEARCH/DECLINE |
| 6 | Suggested actions | Assignees, labels, milestone, next steps |

### 4. Output Format Validation
- Structured markdown template provided
- All sections have clear placeholders
- Confidence levels required for each criterion

### 5. Anti-pattern Coverage
- "Can you provide more details?" without specifics: BLOCKED
- Claiming searches without access: BLOCKED
- DECLINE without rationale: BLOCKED
- Inventing evidence: BLOCKED

## Test Scenarios

### Scenario 1: Feature with Clear Value
- **Input**: Well-defined feature request with use case
- **Expected**: PROCEED recommendation with rationale
- **Prompt Coverage**: Steps 1-6 all applicable

### Scenario 2: Ambiguous Request
- **Input**: Vague feature idea without context
- **Expected**: REQUEST_EVIDENCE or NEEDS_RESEARCH
- **Prompt Coverage**: Step 4 triggers questions, Step 5 appropriate recommendation

### Scenario 3: Out-of-Scope Request
- **Input**: Feature that contradicts project goals
- **Expected**: DECLINE with respectful rationale
- **Prompt Coverage**: Anti-patterns ensure polite decline

## Recommendations

1. **Monitor first deployments**: Track initial runs for unexpected outputs
2. **Review confidence calibration**: Ensure "Unknown" is used appropriately
3. **Iterate on anti-patterns**: Add new patterns if issues arise

## Verdict

**PASS** - Prompt template follows established patterns, provides clear instructions, and includes appropriate safeguards against common issues.

## Evidence

- Prompt structure reviewed against existing `.github/prompts/` templates
- Evaluation criteria match project needs
- Output format enables downstream parsing by PowerShell functions
