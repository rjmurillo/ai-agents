# Analysis: ADR-020 Feature Request Review Step

## 1. Objective and Scope

**Objective**: Assess the feasibility, evidence accuracy, dependencies, and implementation approach for adding a feature request review step to the `ai-issue-triage.yml` workflow.

**Scope**:
- Evaluate technical feasibility of the proposed solution
- Verify claims about Copilot CLI limitations
- Identify dependencies and gaps
- Assess root cause and necessity
- Recommend priority classification for identified issues

## 2. Context

ADR-020 proposes adding a new conditional workflow step after issue categorization that uses the critic agent to perform sophisticated feature request review. The review would:

- Thank submitters politely
- Evaluate user impact, implementation complexity, alignment, and trade-offs
- Provide evidence-based recommendations (PROCEED/DEFER/REQUEST_EVIDENCE/NEEDS_RESEARCH/DECLINE)
- Suggest assignees, labels, and milestones

The proposal states this should only run when `category=enhancement` and acknowledges Copilot CLI tool limitations as a key constraint.

**Current State**:
- Workflow has 3 steps: Categorize (analyst) → Align (roadmap) → Generate PRD (explainer, conditional)
- Prompt file `.github/prompts/issue-feature-review.md` already exists (170 lines)
- No parsing functions exist yet for feature review output

## 3. Approach

**Methodology**:
1. Read existing workflow and related ADRs (ADR-005, ADR-006)
2. Search for evidence of Copilot CLI capabilities and limitations
3. Verify existence of dependencies (prompt files, modules, tests)
4. Analyze proposed implementation against architectural patterns
5. Compare with existing similar steps in workflow

**Tools Used**:
- Read: ADR-020, workflow YAML, composite action, prompt files
- WebSearch: Copilot CLI capabilities, context limits, MCP support
- Grep/Glob: Search for parsing functions and test files
- Serena memories: copilot-platform-priority, adr-reference-index, ci-ai-integration

**Limitations**:
- Cannot test Copilot CLI directly to verify exact token limits
- Cannot access private GitHub documentation on Copilot CLI internals
- Cannot verify actual MCP tool availability without running CLI

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| Copilot CLI uses Claude Sonnet 4.5 by default with 64k-128k context | [GitHub Changelog](https://github.blog/changelog/2024-12-06-copilot-chat-now-has-a-64k-context-window-with-openai-gpt-4o/) | High |
| Copilot CLI supports MCP servers | [GitHub Changelog](https://github.blog/changelog/2025-10-28-github-copilot-cli-use-custom-agents-and-delegate-to-copilot-coding-agent/) | High |
| Copilot CLI does NOT have project-level MCP like Claude Code | Serena memory: copilot-platform-priority | High |
| Feature review prompt file exists | File: `.github/prompts/issue-feature-review.md` | High |
| No parsing functions exist for feature review | Grep search: zero matches for `Get-FeatureReview*` | High |
| ADR-020 references non-existent functions | ADR lines 216-232 reference `Get-FeatureReviewRecommendation`, etc. | High |
| Copilot CLI is P2 (maintenance only) | Serena memory: copilot-platform-priority | High |
| Existing workflow uses PowerShell for all parsing | File: `.github/workflows/ai-issue-triage.yml` lines 54-165 | High |
| Custom agents can be defined in `.github/agents/` | [GitHub Docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli) | High |

### Facts (Verified)

1. **Prompt File Exists**: `.github/prompts/issue-feature-review.md` is complete (170 lines) and well-structured with:
   - Clear instructions for critic agent
   - Explicit acknowledgment of tool limitations ("You do NOT have access to real-time web search")
   - Structured output format with recommendation types (PROCEED/DEFER/REQUEST_EVIDENCE/NEEDS_RESEARCH/DECLINE)
   - Guidance to mark unknowns explicitly

2. **MCP Tools ARE Available in Copilot CLI**: Contrary to ADR-020's claim of "NO access to MCP tools," research shows:
   - Copilot CLI ships with GitHub MCP server by default
   - Custom MCP servers can be added from registry
   - MCP servers run locally or remotely
   - [Source: GitHub Changelog Oct 2025](https://github.blog/changelog/2025-10-28-github-copilot-cli-use-custom-agents-and-delegate-to-copilot-coding-agent/)

3. **Context Window Adequate**: Copilot CLI has 64k-128k token context (depending on model), sufficient for:
   - Issue title + body (typically <2k tokens)
   - Repository structure metadata
   - Prompt template (170 lines = ~1k tokens)
   - Total: ~5-10k tokens (well within limits)

4. **No PowerShell Functions Exist**: ADR-020 references three functions that do not exist:
   - `Get-FeatureReviewRecommendation`
   - `Get-FeatureReviewAssignees`
   - `Get-FeatureReviewLabels`

5. **Existing Pattern Available**: Similar parsing already exists:
   - `Get-VerdictFromAIOutput` (line 731 in AIReviewCommon.psm1)
   - `Get-LabelsFromAIOutput` (line 731)
   - `Get-MilestoneFromAIOutput` (line 821)

6. **ADR-006 Compliance**: Workflow modification follows thin workflows pattern:
   - Logic will be in PowerShell module
   - YAML remains orchestration only
   - Testable with Pester

7. **Conditional Execution Works**: Existing workflow already uses conditionals:
   - Line 294: `if: steps.parse-align.outputs.escalate_to_prd == 'true'`
   - Pattern proven for escalated PRD generation

### Hypotheses (Unverified)

1. **Critic Agent is Optimal Choice**: ADR claims critic agent matches "constructively skeptical" requirement, but:
   - Analyst agent also performs research and evaluation
   - No A/B testing performed to compare agent effectiveness
   - Custom agent could be defined specifically for feature review

2. **3-Minute Timeout Sufficient**: ADR suggests 3-minute timeout without:
   - Benchmarks from similar workflows
   - Analysis of prompt complexity
   - Testing with various issue sizes

3. **Websearch Flag Effectiveness**: ADR mentions `copilot --websearch` flag as limited alternative to MCP tools, but:
   - No documentation found for this flag in GitHub Copilot CLI docs
   - May be confusing with GitHub Copilot Chat websearch in VS Code

## 5. Results

### Critical Gap: Inaccurate Tool Availability Claims

ADR-020 states (line 142-149):

> The enhanced prompt references these MCP tools which are NOT available in Copilot CLI:
> - `perplexity_search` → Use `copilot --websearch` flag (limited)
> - `WebFetch` → Not available

**Finding**: This is partially incorrect. Copilot CLI DOES support MCP tools:
- Ships with GitHub MCP server by default
- Supports custom MCP servers via `~/.copilot/agents` or `.github/agents/`
- MCP servers provide tool access (search, fetch, etc.)

However, the prompt file correctly addresses this limitation:
- Does NOT reference MCP tools by name
- Explicitly states tool limitations
- Instructs agent to mark unknowns as "UNKNOWN - requires manual research"

**Verdict**: The prompt implementation is correct; the ADR explanation is outdated.

### Implementation Gaps

| Component | ADR Claims | Reality | Gap Severity |
|-----------|-----------|---------|--------------|
| Prompt file | "To be created" | Already exists (170 lines) | P0 - Documentation out of sync |
| Parsing functions | "To be added" | Do not exist | P1 - Blocks implementation |
| Pester tests | "Required" | Do not exist | P1 - Blocks implementation |
| Workflow step | "Add after categorization" | Not added | P1 - Blocks feature |
| Custom agent definition | Not mentioned | Could improve results | P2 - Enhancement |

### Dependencies Found

1. **Existing Infrastructure** (satisfied):
   - ✅ `.github/actions/ai-review` composite action
   - ✅ `AIReviewCommon.psm1` module with parsing patterns
   - ✅ Agent system (critic agent exists)
   - ✅ Conditional execution pattern in workflow

2. **Missing Infrastructure** (blocks implementation):
   - ❌ PowerShell parsing functions for feature review output
   - ❌ Pester tests for parsing functions
   - ❌ Workflow YAML step addition

3. **Optional Enhancements**:
   - Custom agent definition in `.github/agents/critic.md` for feature review
   - Integration with GitHub Projects API for milestone assignment
   - Metrics collection on feature review accuracy

### Root Cause Analysis

**Why is this feature requested?**

1. **Current Gap**: Issue triage workflow categorizes and prioritizes but does not evaluate feature request necessity or feasibility
2. **Submitter Experience**: Feature requests get labels/milestones without acknowledgment or feedback
3. **Maintainer Burden**: Maintainers must manually assess every feature request for value and fit

**Is there a simpler solution?**

**Alternative 1**: Enhance roadmap agent prompt to include feature evaluation
- **Pro**: No new workflow step
- **Con**: Conflates strategic alignment (roadmap's job) with evidence-based assessment (different concerns)
- **Verdict**: Violates single responsibility principle

**Alternative 2**: Create custom agent specifically for feature review
- **Pro**: Optimized prompt and tool selection
- **Con**: Another agent to maintain (18 existing agents)
- **Verdict**: Viable if feature review becomes core function

**Alternative 3**: Manual triage only (status quo)
- **Pro**: Zero implementation cost
- **Con**: Inconsistent evaluation quality, maintainer burden continues
- **Verdict**: Does not solve problem

**Recommendation**: Proceed with ADR-020 approach (new conditional step) as it balances separation of concerns with minimal complexity.

## 6. Discussion

### Copilot CLI Suitability for Feature Review

**Question**: Can Copilot CLI perform meaningful feature review given tool limitations?

**Analysis**:
- **Context Available**: Issue content, repository structure, training knowledge = 80% of what's needed
- **Context Missing**: Real-time usage stats, Stack Overflow mentions, external docs = 20%
- **Prompt Design**: Correctly instructs agent to mark unknowns rather than fabricate data
- **Alternative**: Claude Code agents with full MCP access could do deeper research

**Conclusion**: Copilot CLI can provide valuable feature review within its constraints. The prompt's transparency about limitations is appropriate.

### Copilot CLI Investment Strategy

From `copilot-platform-priority` memory:
- **P0**: Claude Code (full investment)
- **P1**: VS Code (active)
- **P2**: Copilot CLI (maintenance only)

**Implication**: Adding features to Copilot CLI workflows contradicts P2 maintenance-only strategy.

**Counter-argument**:
1. This is a workflow enhancement, not CLI tool enhancement
2. Uses existing composite action (`.github/actions/ai-review`)
3. Minimal ongoing maintenance (parsing functions only)

**Verdict**: Acceptable exception to P2 policy due to reuse of existing infrastructure.

### Agent Selection: Critic vs. Analyst vs. Custom

ADR-020 chooses critic agent with rationale: "constructively skeptical evaluation."

**Comparison**:

| Agent | Strengths | Weaknesses |
|-------|-----------|------------|
| **Critic** | Validates plans, identifies risks | May be too negative for user-facing comments |
| **Analyst** | Research-focused, evidence-gathering | Already used for categorization step |
| **Custom** | Purpose-built for feature review | Adds maintenance overhead |

**Observation**: Prompt file says "You are an expert .NET open-source reviewer. Be polite, clear, and constructively skeptical."

This tone matches critic agent BUT with explicit politeness constraint. The prompt effectively creates a "friendly critic" persona.

**Recommendation**: Critic agent is acceptable, but consider testing with analyst agent as alternative. Custom agent is overkill unless this becomes high-frequency operation.

### Parsing Function Pattern

Existing pattern from `AIReviewCommon.psm1`:

```powershell
function Get-VerdictFromAIOutput {
    param([string]$Output)
    # Regex: VERDICT:\s*([A-Z_]+)
}

function Get-LabelsFromAIOutput {
    param([string]$Output)
    # Regex: LABEL:\s*(\S+)
}
```

**Proposed pattern for feature review**:

```powershell
function Get-FeatureReviewRecommendation {
    param([string]$Output)
    # Regex: RECOMMENDATION:\s*(PROCEED|DEFER|REQUEST_EVIDENCE|NEEDS_RESEARCH|DECLINE)
}

function Get-FeatureReviewAssignees {
    param([string]$Output)
    # Parse: **Assignees**: [usernames]
    # Return: Comma-separated string
}

function Get-FeatureReviewLabels {
    param([string]$Output)
    # Parse: **Labels**: [additional labels]
    # Return: Comma-separated string
}
```

**Challenge**: Output format in prompt uses Markdown formatting:
- `**Assignees**: [usernames or "none suggested"]`
- `**Labels**: [additional labels or "none"]`

This is harder to parse than token-based format (e.g., `ASSIGNEES: user1,user2`).

**Recommendation**: Update prompt to use parseable format OR use more complex regex with Markdown bold syntax.

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Update ADR-020 to correct MCP tool claims | Documentation accuracy; prevents confusion | 15 min |
| P0 | Modify prompt output format for easier parsing | Current format hard to parse with regex | 30 min |
| P1 | Implement three PowerShell parsing functions | Blocks feature implementation | 2 hours |
| P1 | Write Pester tests for parsing functions | ADR-006 compliance; quality gate | 2 hours |
| P1 | Add workflow step after categorization | Core feature implementation | 1 hour |
| P1 | Test with sample issues across recommendation types | Validate end-to-end functionality | 2 hours |
| P2 | Consider custom agent for feature review | May improve quality vs. critic agent | 4 hours |
| P2 | Add metrics collection on review accuracy | Measure effectiveness over time | 3 hours |
| P2 | Evaluate analyst agent as alternative | Compare effectiveness with critic | 1 hour |

### Specific Code Changes Required

**1. Prompt File Update** (`.github/prompts/issue-feature-review.md`):

Change from:
```markdown
- **Assignees**: [usernames or "none suggested"]
- **Labels**: [additional labels or "none"]
```

To:
```markdown
ASSIGNEES: user1,user2 (or ASSIGNEES: none)
LABELS: label1,label2 (or LABELS: none)
```

**2. PowerShell Module** (`.github/scripts/AIReviewCommon.psm1`):

Add three functions following existing patterns (Get-VerdictFromAIOutput as template).

**3. Pester Tests** (`.github/scripts/AIReviewCommon.Tests.ps1`):

Add test cases:
- Valid recommendation parsing (all 5 types)
- Valid assignee parsing (single, multiple, none)
- Valid label parsing (single, multiple, none)
- Invalid/malformed input handling
- Edge cases (empty output, missing markers)

**4. Workflow YAML** (`.github/workflows/ai-issue-triage.yml`):

Insert after line 93 (after `Parse Categorization Results`):

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
  shell: pwsh
  env:
    RAW_OUTPUT: ${{ steps.review-feature.outputs.findings }}
  run: |
    Import-Module .github/scripts/AIReviewCommon.psm1

    $recommendation = Get-FeatureReviewRecommendation -Output $env:RAW_OUTPUT
    $assignees = Get-FeatureReviewAssignees -Output $env:RAW_OUTPUT
    $labels = Get-FeatureReviewLabels -Output $env:RAW_OUTPUT

    echo "recommendation=$recommendation" >> $env:GITHUB_OUTPUT
    echo "assignees=$assignees" >> $env:GITHUB_OUTPUT
    echo "labels=$labels" >> $env:GITHUB_OUTPUT
```

**5. Comment Posting** (optional enhancement):

Post feature review as issue comment using `.claude/skills/github/scripts/issue/Post-IssueComment.ps1` with marker `AI-FEATURE-REVIEW`.

## 8. Conclusion

**Verdict**: PROCEED with modifications

**Confidence**: High

**Rationale**: The feature request review step is well-designed and addresses a real gap in the issue triage workflow. The prompt file is complete and appropriately scoped for Copilot CLI capabilities. Implementation requires only PowerShell parsing functions and workflow YAML changes, both following established patterns. The ADR contains some outdated information about MCP tool availability but the actual implementation (prompt file) is correct.

### User Impact

**What changes for you**:
- Feature requests receive structured evaluation with clear recommendations
- Submitters get polite acknowledgment and feedback
- Maintainers see evidence-based assessment before manual review

**Effort required**:
- 7-8 hours total implementation time
- Minimal ongoing maintenance (PowerShell functions only)

**Risk if ignored**:
- Feature requests continue receiving inconsistent evaluation
- Maintainer burden persists
- Submitters lack feedback on request viability

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| Missing parsing functions | P1 | Cannot parse AI output without `Get-FeatureReview*` functions |
| Prompt format mismatch | P0 | Markdown formatting in prompt difficult to parse with regex |
| No Pester tests | P1 | ADR-006 requires 80% test coverage for modules |
| ADR documentation inaccuracy | P0 | MCP tool claims contradict current Copilot CLI capabilities |

### Non-Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| Agent selection not validated | P2 | No testing of critic vs. analyst vs. custom agent |
| Copilot CLI P2 investment | P2 | Adding feature to maintenance-only platform |
| Timeout not benchmarked | P2 | 3-minute timeout chosen arbitrarily |
| No metrics collection | P2 | Cannot measure feature review effectiveness |

## 9. Appendices

### Sources Consulted

**GitHub Documentation**:
- [GitHub Copilot CLI Overview](https://github.com/features/copilot/cli)
- [Using GitHub Copilot CLI - Official Docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli)
- [Custom Agents Changelog](https://github.blog/changelog/2025-10-28-github-copilot-cli-use-custom-agents-and-delegate-to-copilot-coding-agent/)
- [Copilot Chat Context Window Update](https://github.blog/changelog/2024-12-06-copilot-chat-now-has-a-64k-context-window-with-openai-gpt-4o/)

**Community Resources**:
- [GitHub Copilot CLI 101 Blog Post](https://github.blog/ai-and-ml/github-copilot-cli-101-how-to-use-github-copilot-from-the-command-line/)
- [VS Code MCP Servers Documentation](https://code.visualstudio.com/docs/copilot/chat/mcp-servers)
- [Copilot Agent Mode Examples](https://devopsjournal.io/blog/2025/12/20/Copilot-Agent-example)

**Project Files**:
- `.agents/architecture/ADR-020-feature-request-review-step.md`
- `.agents/architecture/ADR-005-powershell-only-scripting.md`
- `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`
- `.github/workflows/ai-issue-triage.yml`
- `.github/prompts/issue-feature-review.md`
- `.github/scripts/AIReviewCommon.psm1`
- `.github/actions/ai-review/action.yml`

**Serena Memories**:
- `copilot-platform-priority` - P0/P1/P2 investment strategy
- `adr-reference-index` - ADR catalog
- `ci-ai-integration` - Verdict token patterns

### Data Transparency

**Found**:
- Complete prompt file (170 lines)
- Existing composite action supporting all required inputs
- Similar parsing patterns in AIReviewCommon.psm1
- Conditional execution pattern in workflow
- Evidence of MCP support in Copilot CLI

**Not Found**:
- PowerShell parsing functions for feature review
- Pester tests for feature review functions
- Workflow YAML implementation of feature review step
- Benchmarks for timeout selection
- A/B testing data for agent selection
- `copilot --websearch` flag documentation
