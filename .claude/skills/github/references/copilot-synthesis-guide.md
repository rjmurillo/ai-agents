# Copilot Context Synthesis Guide

Documentation for the `copilot-synthesis.yml` configuration file.

## Purpose

When assigning Copilot to an issue, raw issue comments can be noisy and unstructured. The synthesis system:

1. Filters comments to trusted sources only (maintainers, known AI agents)
2. Extracts structured information (implementation plans, related issues)
3. Generates a synthesis comment that gives Copilot clear, actionable context
4. Assigns the copilot-swe-agent to the issue

The synthesis comment is idempotent - if one already exists (detected by marker), it updates rather than duplicates.

## Usage

```powershell
# Basic usage
pwsh .claude/skills/github/scripts/issue/Invoke-CopilotAssignment.ps1 -IssueNumber 123

# Preview without posting
pwsh .claude/skills/github/scripts/issue/Invoke-CopilotAssignment.ps1 -IssueNumber 123 -WhatIf

# Custom config
pwsh .claude/skills/github/scripts/issue/Invoke-CopilotAssignment.ps1 -IssueNumber 123 -ConfigPath "custom.yml"
```

## Configuration Reference

### trusted_sources.maintainers

Human users with authority to provide guidance. Their comments are extracted for the "Maintainer Guidance" section.

**Extracted content:**

- Bullet points (`- item` or `* item`)
- Numbered lists (`1. item`)
- Key decisions and direction

**Skipped content:**

- Checkbox items (`- [ ] task`) - task lists, not guidance
- Very short items (< 10 chars)

### trusted_sources.ai_agents

Bot accounts that provide structured analysis. Their comments are parsed using `extraction_patterns`.

**Known agents:**

- `coderabbitai` - Implementation plans, similar issues, related PRs
- `Copilot` - Clarifying questions, status updates
- `cursor[bot]` - Bug detection with line references
- `github-actions` - AI triage results (priority, category)

### extraction_patterns.coderabbit

Patterns for extracting structured content from CodeRabbit comments:

| Pattern | Header | Example |
|---------|--------|---------|
| `implementation_plan` | `## Implementation` | Steps 1, 2, 3... |
| `related_issues` | `🔗 Similar Issues` | `- #45: Description` |
| `related_prs` | `🔗 Related PRs` | `- #89: Description` |

### extraction_patterns.ai_triage

Patterns for AI triage comments:

| Pattern | Purpose | Example |
|---------|---------|---------|
| `marker` | Identifies triage comment | `<!-- AI-ISSUE-TRIAGE -->` |
| `priority` | Priority label prefix | `Priority: High` |
| `category` | Category label prefix | `Category: Bug` |

### synthesis.marker

HTML comment that identifies a synthesis comment for idempotency:

```html
<!-- COPILOT-CONTEXT-SYNTHESIS -->
```

The marker enables update-in-place behavior:

1. Script searches for marker in existing comments
2. If found: updates existing comment
3. If not found: creates new comment

## Generated Comment Structure

```markdown
<!-- COPILOT-CONTEXT-SYNTHESIS -->
@copilot Please review the synthesized context below...

## Maintainer Guidance
[Extracted bullet points from maintainer comments]

## AI Agent Recommendations
[Implementation plans, related issues/PRs from AI agents]

---
*Synthesized at 2025-12-20 12:00:00 UTC*
```

## Extending the Configuration

### Adding a Maintainer

1. Add GitHub login to `trusted_sources.maintainers`
2. No code changes required

### Adding an AI Agent

1. Add GitHub login to `trusted_sources.ai_agents`
2. If structured output, add `extraction_patterns`
3. Optionally update script to parse specific format

### Adding Extraction Patterns

1. Add section under `extraction_patterns`
2. Define patterns as key-value pairs
3. Update `Invoke-CopilotAssignment.ps1` to use patterns
4. Add tests

### Changing Synthesis Format

1. Modify `New-SynthesisComment` function in script
2. Update marker if needed
3. Test with `-WhatIf` to preview

## Related

- Script: `.claude/skills/github/scripts/issue/Invoke-CopilotAssignment.ps1`
- Module: `.claude/skills/github/modules/GitHubHelpers.psm1`
- Issue: <https://github.com/rjmurillo/ai-agents/issues/92>
