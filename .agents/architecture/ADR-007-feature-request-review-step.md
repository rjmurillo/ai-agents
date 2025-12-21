---
status: proposed
date: 2025-12-19
decision-makers: ["architect", "user"]
consulted: ["analyst", "roadmap"]
informed: ["implementer", "devops"]
---

# ADR-007: Feature Request Review Step in Issue Triage Workflow

## Context and Problem Statement

The current `ai-issue-triage.yml` workflow has three main steps:

1. **Categorize Issue** (analyst agent) - determines category and labels
2. **Align to Roadmap** (roadmap agent) - determines priority, milestone, escalation
3. **Generate PRD** (explainer agent) - only for escalated issues

A new capability is requested: sophisticated feature request review that:

- Thanks the submitter politely
- Actively researches before asking questions (using search, GitHub, Stack Overflow)
- Evaluates: User Impact, Implementation/Maintenance, Alignment, Trade-offs
- Provides evidence-based recommendations (proceed/defer/request evidence)
- Is transparent about data availability (what was found vs. not found)
- Suggests assignees, labels, milestones

**Key architectural question**: Where should this capability fit in the workflow, and which agent should invoke it?

## Decision Drivers

1. **ADR-006 Compliance**: Thin workflows, testable modules pattern
2. **ADR-005 Compliance**: PowerShell-only scripting
3. **Copilot CLI Limitations**: De-prioritized to P2 (maintenance only)
4. **Conditional Execution**: Only feature requests need this review
5. **Research Tools**: Prompt references MCP tools not available in Copilot CLI
6. **Separation of Concerns**: Analyst categorizes; critic evaluates; new reviewer assesses value

## Considered Options

### Option 1: New Conditional Step After Categorization (RECOMMENDED)

Add a new step that runs only when `category=enhancement`:

```yaml
- name: Review Feature Request (Critic Agent)
  id: review-feature
  if: steps.parse-categorize.outputs.category == 'enhancement'
  uses: ./.github/actions/ai-review
  with:
    agent: critic
    context-type: issue
    prompt-file: .github/prompts/issue-feature-review.md
```

**Pros**:

- Clean conditional execution based on category
- Does not disrupt existing analyst/roadmap flow
- Uses critic agent (aligns with "constructively skeptical" requirement)
- Adds value without modifying working steps
- Easy to disable or modify independently

**Cons**:

- Adds workflow execution time for feature requests
- Another step to maintain

### Option 2: Replace Analyst Step for Feature Requests

Modify analyst step to use different prompt for features:

```yaml
prompt-file: ${{ steps.parse-categorize.outputs.category == 'enhancement' && '.github/prompts/issue-feature-review.md' || '.github/prompts/issue-triage-categorize.md' }}
```

**Pros**:

- No additional workflow steps

**Cons**:

- Breaks analyst role (categorization becomes conflated with evaluation)
- Cannot determine category before categorization step runs (circular dependency)
- Violates single responsibility principle
- Complex conditional logic in workflow YAML

### Option 3: Merge Into Roadmap Step

Enhance roadmap agent prompt to include feature evaluation:

**Pros**:

- No new steps
- Roadmap already considers strategic alignment

**Cons**:

- Roadmap agent becomes overloaded (priority + milestone + evaluation)
- Different concerns: Roadmap = strategic fit; Review = evidence-based assessment
- Prompt becomes too large and unfocused

### Option 4: New Dedicated Agent

Create new `feature-reviewer` agent:

**Pros**:

- Clear purpose and prompt optimization

**Cons**:

- Agent proliferation (18 agents already)
- Critic agent already serves "constructively skeptical" evaluation role
- No reuse benefit

## Decision Outcome

**Chosen option: Option 1 - New Conditional Step with Critic Agent**

### Rationale

1. **Role Alignment**: The prompt describes "polite, clear, and constructively skeptical" which matches the critic agent's purpose.

2. **Separation of Concerns**:
   - Analyst: Categorize (what type of issue)
   - Critic (new step): Evaluate (should we proceed with this feature)
   - Roadmap: Prioritize (when and where it fits)

3. **Conditional Execution**: Only runs for `category=enhancement`, avoiding unnecessary processing for bugs, docs, questions.

4. **ADR-006 Compliance**: Step invokes composite action; all parsing logic in PowerShell modules.

5. **Tool Availability**: Copilot CLI has limited tool access. The prompt must be adapted to work without MCP tools, relying on:
   - Issue body content (already provided)
   - Copilot's web search capabilities (limited)
   - Repository context from checkout

### Copilot CLI Tool Availability

The enhanced prompt references these MCP tools which are NOT available in Copilot CLI:

| Tool in Prompt | Copilot CLI Alternative |
|----------------|------------------------|
| `perplexity_search` | Use `copilot --websearch` flag (limited) |
| `WebFetch` | Not available; must work from issue content |
| `mcp__github` tools | Use `gh` CLI within workflow |
| `Serena` memory tools | Not available |
| `context7` docs | Not available |

**Adaptation Strategy**:

1. Remove explicit tool references from prompt
2. Instruct model to work from available context
3. Be transparent about what cannot be verified
4. Pre-fetch repository data in workflow steps before invoking Copilot

## Implementation

### Workflow Changes

File: `.github/workflows/ai-issue-triage.yml`

Add after `Parse Categorization Results` step:

```yaml
- name: Review Feature Request (Critic Agent)
  id: review-feature
  if: steps.parse-categorize.outputs.category == 'enhancement'
  uses: ./.github/actions/ai-review
  with:
    agent: critic
    context-type: issue
    issue-number: ${{ github.event.issue.number }}
    prompt-file: .github/prompts/issue-feature-review.md
    timeout-minutes: 3
    bot-pat: ${{ secrets.BOT_PAT }}
    copilot-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}

- name: Parse Feature Review Results
  id: parse-review
  if: steps.review-feature.outcome == 'success'
  env:
    RAW_OUTPUT: ${{ steps.review-feature.outputs.findings }}
  run: |
    Import-Module .github/scripts/AIReviewCommon.psm1

    # Parse recommendation
    $recommendation = Get-FeatureReviewRecommendation -Output $env:RAW_OUTPUT

    # Parse suggested assignees (comma-separated)
    $assignees = Get-FeatureReviewAssignees -Output $env:RAW_OUTPUT

    # Parse suggested labels
    $labels = Get-FeatureReviewLabels -Output $env:RAW_OUTPUT

    echo "recommendation=$recommendation" >> $env:GITHUB_OUTPUT
    echo "assignees=$assignees" >> $env:GITHUB_OUTPUT
    echo "labels=$labels" >> $env:GITHUB_OUTPUT
```

### Prompt File Location

File: `.github/prompts/issue-feature-review.md`

Location follows existing pattern (all prompts in `.github/prompts/`).

### PowerShell Module Updates

File: `.github/scripts/AIReviewCommon.psm1`

Add functions:

```powershell
function Get-FeatureReviewRecommendation {
    [CmdletBinding()]
    param([string]$Output)
    # Parse recommendation from output
}

function Get-FeatureReviewAssignees {
    [CmdletBinding()]
    param([string]$Output)
    # Parse assignees from output (returns comma-separated string)
}

function Get-FeatureReviewLabels {
    [CmdletBinding()]
    param([string]$Output)
    # Parse labels from output (returns comma-separated string)
}
```

File: `.github/scripts/AIReviewCommon.Tests.ps1`

Add Pester tests for `Get-FeatureReviewRecommendation`, `Get-FeatureReviewAssignees`, and `Get-FeatureReviewLabels`.

## Prompt Adaptation for Copilot CLI

The original prompt assumes MCP tool access. For Copilot CLI, adapt as follows:

### Remove

- Explicit tool call references (`perplexity_search`, `WebFetch`, `mcp__*`)
- Assumptions about external data sources

### Retain

- Evaluation criteria (User Impact, Implementation, Alignment, Trade-offs)
- Evidence-based recommendation framework
- Transparency about data availability
- Polite acknowledgment of submitter

### Add

- Instruction to work from issue content and repository context only
- Explicit statement: "You do not have access to external search tools"
- Guidance to flag what would require manual research

### Adapted Prompt Structure

```markdown
# Feature Request Review Task

You are an expert .NET open-source reviewer (polite, clear, and constructively skeptical).

## Context Limitations

You have access to:
- The issue title and body
- Repository structure (from checkout)
- Your training knowledge

You do NOT have access to:
- Real-time web search
- Stack Overflow queries
- External API documentation
- Usage analytics

When information is unavailable, explicitly state "UNKNOWN - requires manual research".

## Evaluation Framework

### 1. Thank the Submitter
Acknowledge their contribution politely.

### 2. Evaluate (from available context)

| Criterion | Source | Assessment |
|-----------|--------|------------|
| User Impact | Issue description | [Assessment or UNKNOWN] |
| Implementation | Repository patterns | [Assessment or UNKNOWN] |
| Alignment | Issue labels, existing issues | [Assessment or UNKNOWN] |
| Trade-offs | Technical knowledge | [Assessment] |

### 3. Recommendation

RECOMMENDATION: [PROCEED | DEFER | REQUEST_EVIDENCE | NEEDS_RESEARCH]

Rationale: [1-2 sentences]

### 4. Suggested Actions

- Assignees: [usernames or "none suggested"]
- Additional Labels: [labels or "none"]
- Milestone: [milestone or "none"]

## Output Format

[Structured response following above framework]
```

## Consequences

### Positive

1. **Improved Feature Review**: Evidence-based evaluation instead of simple triage
2. **Polite Engagement**: Thanks submitters, improving community experience
3. **Transparency**: Clear about what can/cannot be verified
4. **Conditional**: Only runs for feature requests, not all issues

### Negative

1. **Copilot CLI Limitations**: Cannot perform live research; must rely on available context
2. **Additional Step**: Adds ~2-3 minutes for feature request processing
3. **Module Updates**: Requires new PowerShell parsing function

### Neutral

1. **Agent Choice**: Critic is reasonable but could be analyst; decision is defensible either way

## Validation Checklist

Before implementing:

- [ ] Workflow YAML remains < 100 lines per job
- [ ] Parsing logic in `AIReviewCommon.psm1` (not inline)
- [ ] Pester tests for new parsing function
- [ ] Prompt adapted for Copilot CLI tool limitations
- [ ] Conditional execution verified (`category == 'enhancement'`)
- [ ] Timeout reasonable (3 minutes suggested)

## Related Decisions

- [ADR-005](./ADR-005-powershell-only-scripting.md): All logic in PowerShell
- [ADR-006](./ADR-006-thin-workflows-testable-modules.md): Thin workflows pattern
- Serena memory `copilot-cli-deprioritization-decision`: Copilot CLI is P2

## References

- Current workflow: `.github/workflows/ai-issue-triage.yml`
- Existing prompts: `.github/prompts/issue-*.md`
- Critic agent: `src/claude/critic.md`
