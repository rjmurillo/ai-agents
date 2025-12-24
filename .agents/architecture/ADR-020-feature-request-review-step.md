---
status: proposed
date: 2025-12-19
decision-makers: [architect, user]
consulted: [analyst, roadmap]
informed: [implementer, devops]
---

# ADR-020: Feature Request Review Step in Issue Triage Workflow

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
5. **Research Tools**: Prompt adapted for context-limited execution
6. **Separation of Concerns**: Analyst categorizes AND evaluates (same agent, different prompts); roadmap prioritizes
7. **Existing Capability**: Analyst agent already defines Feature Request Review template (lines 178-215)

## Considered Options

### Option 1: New Conditional Step After Categorization (RECOMMENDED)

Add a new step that runs only when `category=enhancement`:

```yaml
- name: Review Feature Request (Analyst Agent)
  id: review-feature
  if: steps.parse-categorize.outputs.category == 'enhancement'
  uses: ./.github/actions/ai-review
  with:
    agent: analyst
    context-type: issue
    prompt-file: .github/prompts/issue-feature-review.md
```

**Pros**:

- Clean conditional execution based on category
- Does not disrupt existing analyst/roadmap flow
- Uses analyst agent (already has Feature Request Review capability in its definition)
- Same agent for categorization and evaluation ensures consistent context
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
- Analyst agent already has Feature Request Review capability
- No reuse benefit

### Option 5: Use Critic Agent (REJECTED)

Use critic agent for feature evaluation:

**Pros**:

- "Constructively skeptical" tone matches evaluation needs

**Cons**:

- Critic agent is scoped to "plan validation" not feature evaluation
- Critic constraints explicitly exclude "code review or completed work assessment"
- Analyst has richer context (already categorized the issue)
- Role mismatch creates maintenance confusion

## Decision Outcome

**Chosen option: Option 1 - New Conditional Step with Analyst Agent**

### Rationale

1. **Existing Capability**: Analyst agent already defines Feature Request Review template (lines 178-215 in `analyst.agent.md`) covering User Impact, Implementation, Alignment, Trade-offs, and Recommendations.

2. **Separation of Concerns**:
   - Analyst (step 1): Categorize (what type of issue)
   - Analyst (step 2): Evaluate (should we proceed with this feature) - same agent, different prompt
   - Roadmap: Prioritize (when and where it fits)

3. **Conditional Execution**: Only runs for `category=enhancement`, avoiding unnecessary processing for bugs, docs, questions.

4. **ADR-006 Compliance**: Step invokes composite action; all parsing logic in PowerShell modules.

5. **Critic Agent Rejected**: Critic is scoped to "plan validation" (pre-implementation review of internal plans), not feature request evaluation. Using critic would violate its defined constraints and create role confusion.

### Copilot CLI Tool Availability

**Correction (2025-12-23)**: Copilot CLI DOES support MCP tools:

- Ships with GitHub MCP server by default
- Custom MCP servers can be added via `~/.copilot/agents` or `.github/agents/`
- [Source: GitHub Changelog Oct 2025](https://github.blog/changelog/2025-10-28-github-copilot-cli-use-custom-agents-and-delegate-to-copilot-coding-agent/)

However, for simplicity and reliability, this implementation does NOT require MCP tools:

| Context Source | Availability |
|----------------|--------------|
| Issue title and body | Available (provided by workflow) |
| Repository structure | Available (from checkout) |
| Training knowledge | Available |
| Real-time web search | Optional (MCP can provide, but not required) |

**Prompt Strategy**:

1. Work from issue content and repository context
2. Be transparent about what cannot be verified
3. Use parseable output format for reliable extraction

## Implementation

### Workflow Changes

File: `.github/workflows/ai-issue-triage.yml`

Add after `Parse Categorization Results` step:

```yaml
- name: Review Feature Request (Analyst Agent)
  id: review-feature
  if: steps.parse-categorize.outputs.category == 'enhancement'
  uses: ./.github/actions/ai-review
  with:
    agent: analyst
    context-type: issue
    issue-number: ${{ github.event.issue.number }}
    prompt-file: .github/prompts/issue-feature-review.md
    timeout-minutes: 3
    bot-pat: ${{ secrets.BOT_PAT }}
    copilot-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}

- name: Parse Feature Review Results
  id: parse-review
  if: steps.review-feature.outcome == 'success'
  shell: pwsh
  env:
    RAW_OUTPUT: ${{ steps.review-feature.outputs.findings }}
  run: |
    Import-Module .github/scripts/AIReviewCommon.psm1

    # Parse recommendation (returns: PROCEED|DEFER|REQUEST_EVIDENCE|NEEDS_RESEARCH|DECLINE)
    $recommendation = Get-FeatureReviewRecommendation -Output $env:RAW_OUTPUT

    # Parse suggested assignees (returns comma-separated GitHub usernames)
    $assignees = Get-FeatureReviewAssignees -Output $env:RAW_OUTPUT

    # Parse suggested labels (returns comma-separated label names)
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

Add functions with hardened regex (per security review):

```powershell
function Get-FeatureReviewRecommendation {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [AllowNull()]
        [string]$Output
    )

    if ([string]::IsNullOrWhiteSpace($Output)) { return 'NEEDS_RESEARCH' }

    # Allowlist of valid recommendations
    $validRecommendations = @('PROCEED', 'DEFER', 'REQUEST_EVIDENCE', 'NEEDS_RESEARCH', 'DECLINE')

    if ($Output -match 'RECOMMENDATION:\s*(PROCEED|DEFER|REQUEST_EVIDENCE|NEEDS_RESEARCH|DECLINE)') {
        return $Matches[1]
    }
    return 'NEEDS_RESEARCH'  # Safe default
}

function Get-FeatureReviewAssignees {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [AllowNull()]
        [string]$Output
    )

    if ([string]::IsNullOrWhiteSpace($Output)) { return '' }

    if ($Output -match 'ASSIGNEES:\s*(.+?)(?:\r?\n|$)') {
        $raw = $Matches[1].Trim()
        if ($raw -eq 'none' -or $raw -eq 'none suggested') { return '' }

        # Validate each username against GitHub pattern (1-39 chars, alphanumeric + hyphen)
        $validated = $raw -split ',' | ForEach-Object {
            $user = $_.Trim()
            if ($user -match '^(?=.{1,39}$)[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$') {
                $user
            } else {
                Write-Warning "Skipped invalid assignee: $user"
            }
        } | Where-Object { $_ }
        return ($validated -join ',')
    }
    return ''
}

function Get-FeatureReviewLabels {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [AllowNull()]
        [string]$Output
    )

    if ([string]::IsNullOrWhiteSpace($Output)) { return '' }

    if ($Output -match 'LABELS:\s*(.+?)(?:\r?\n|$)') {
        $raw = $Matches[1].Trim()
        if ($raw -eq 'none') { return '' }

        # Validate label format (alphanumeric, hyphen, colon, slash allowed)
        $validated = $raw -split ',' | ForEach-Object {
            $label = $_.Trim()
            if ($label -match '^[a-zA-Z0-9][a-zA-Z0-9-:/ ]*$') {
                $label
            } else {
                Write-Warning "Skipped invalid label: $label"
            }
        } | Where-Object { $_ }
        return ($validated -join ',')
    }
    return ''
}
```

File: `.github/scripts/AIReviewCommon.Tests.ps1`

Add Pester tests (80% coverage per ADR-006):

```powershell
Describe 'Get-FeatureReviewRecommendation' {
    It 'Parses PROCEED recommendation' {
        $output = "RECOMMENDATION: PROCEED`nRationale: Good fit"
        Get-FeatureReviewRecommendation -Output $output | Should -Be 'PROCEED'
    }

    It 'Returns NEEDS_RESEARCH for empty input' {
        Get-FeatureReviewRecommendation -Output '' | Should -Be 'NEEDS_RESEARCH'
    }

    It 'Returns NEEDS_RESEARCH for invalid recommendation' {
        Get-FeatureReviewRecommendation -Output 'RECOMMENDATION: INVALID' | Should -Be 'NEEDS_RESEARCH'
    }
}

Describe 'Get-FeatureReviewAssignees' {
    It 'Parses single assignee' {
        $output = "ASSIGNEES: octocat"
        Get-FeatureReviewAssignees -Output $output | Should -Be 'octocat'
    }

    It 'Parses multiple assignees' {
        $output = "ASSIGNEES: user1,user2,user3"
        Get-FeatureReviewAssignees -Output $output | Should -Be 'user1,user2,user3'
    }

    It 'Returns empty for none suggested' {
        $output = "ASSIGNEES: none suggested"
        Get-FeatureReviewAssignees -Output $output | Should -Be ''
    }

    It 'Skips invalid usernames' {
        $output = "ASSIGNEES: valid-user,invalid..user,another-valid"
        Get-FeatureReviewAssignees -Output $output | Should -Be 'valid-user,another-valid'
    }
}

Describe 'Get-FeatureReviewLabels' {
    It 'Parses single label' {
        $output = "LABELS: enhancement"
        Get-FeatureReviewLabels -Output $output | Should -Be 'enhancement'
    }

    It 'Parses labels with special chars' {
        $output = "LABELS: area:ci/cd,priority:high"
        Get-FeatureReviewLabels -Output $output | Should -Be 'area:ci/cd,priority:high'
    }

    It 'Returns empty for none' {
        $output = "LABELS: none"
        Get-FeatureReviewLabels -Output $output | Should -Be ''
    }
}
```

## Prompt Output Format

The prompt MUST produce parseable output tokens for reliable extraction:

### Required Output Tokens

```text
RECOMMENDATION: PROCEED|DEFER|REQUEST_EVIDENCE|NEEDS_RESEARCH|DECLINE
ASSIGNEES: user1,user2 (or "none" if no suggestion)
LABELS: label1,label2 (or "none" if no additional labels)
```

### Prompt Template

File: `.github/prompts/issue-feature-review.md`

```markdown
# Feature Request Review Task

You are an expert .NET open-source reviewer (polite, clear, and constructively skeptical).

## Context Available

You have access to:
- The issue title and body
- Repository structure (from checkout)
- Your training knowledge

When information is unavailable, explicitly state "UNKNOWN - requires manual research".

## Evaluation Framework

### 1. Thank the Submitter
Acknowledge their contribution politely.

### 2. Evaluate

| Criterion | Assessment |
|-----------|------------|
| User Impact | [Assessment or UNKNOWN] |
| Implementation Complexity | [Assessment or UNKNOWN] |
| Strategic Alignment | [Assessment or UNKNOWN] |
| Trade-offs | [Assessment] |

### 3. Recommendation

Provide ONE of: PROCEED, DEFER, REQUEST_EVIDENCE, NEEDS_RESEARCH, DECLINE

### 4. Output (REQUIRED FORMAT)

You MUST include these exact tokens at the end of your response:

RECOMMENDATION: [your recommendation]
ASSIGNEES: [comma-separated usernames or "none"]
LABELS: [comma-separated labels or "none"]
```

### Token Definitions

| Token | Valid Values | Default |
|-------|--------------|---------|
| RECOMMENDATION | PROCEED, DEFER, REQUEST_EVIDENCE, NEEDS_RESEARCH, DECLINE | NEEDS_RESEARCH |
| ASSIGNEES | GitHub usernames (1-39 chars, alphanumeric + hyphen) | none |
| LABELS | Label names (alphanumeric, hyphen, colon, slash) | none |

## Consequences

### Positive

1. **Improved Feature Review**: Evidence-based evaluation instead of simple triage
2. **Polite Engagement**: Thanks submitters, improving community experience
3. **Transparency**: Clear about what can/cannot be verified
4. **Conditional**: Only runs for feature requests, not all issues
5. **Existing Capability**: Uses analyst's existing Feature Request Review template

### Negative

1. **Context Limitations**: Works from available context only; manual research may be needed
2. **Additional Step**: Adds ~2-3 minutes for feature request processing
3. **Module Updates**: Requires three new PowerShell parsing functions with tests

### Neutral

1. **Same Agent, Two Prompts**: Analyst invoked twice (categorize, then evaluate) - acceptable tradeoff for separation of concerns

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
- Analyst agent: `.github/agents/analyst.agent.md` (lines 178-215: Feature Request Review template)
- Parsing patterns: `.github/scripts/AIReviewCommon.psm1`

## Related Issues

- **Issue #110**: Design: Feature Request Review Step for Issue Triage Workflow

## Review History

- **2025-12-23**: Multi-agent review (6 agents) via adr-review skill
  - Verdict: NEEDS REVISION → Addressed in this revision
  - Key changes: Switched from critic to analyst agent, corrected MCP tool claims, added parseable output format
  - Debate log: `.agents/critique/ADR-020-debate-log.md`
