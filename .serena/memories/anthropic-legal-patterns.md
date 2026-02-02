# Anthropic Legal AI Workflow Patterns

**Source**: https://www.claude.com/blog/how-anthropic-uses-claude-legal
**Date**: 2026-01-04
**Session**: 309

## Key Patterns

### 1. Skills Architecture

Instruction files containing team expertise, formatting preferences, historical guidance.
- Natural language specifications
- Domain-specialized (employment, commercial, privacy)
- Inherited between team members
- Enable non-technical skill authoring

### 2. Self-Service Pre-Screening

Marketing review tool reduced turnaround from 2-3 days to 24 hours.
- Slack-based interface
- AI flags issues by risk level
- Human lawyers handle edge cases only
- Force multiplier effect

### 3. MCP Integration

Connected systems: Google Drive, JIRA, Slack, Google Calendar.
- Context surfacing at right moments
- Tool-agnostic skill authoring
- Separation of AI logic from APIs

### 4. Human-in-the-Loop Gate

All outputs route to humans for approval.
- AI handles first-pass, triage, drafting
- Lawyers remain decision-makers
- Trust maintenance, edge case catching

## Strategic Principles

1. **Pain point first**: "Don't start with what AI can do. Start with what we wish we didn't have to do."
2. **Natural language over code**: Reduce barrier to skill authoring
3. **Organizational multiplier**: Early adopters enable broader adoption
4. **Skill inheritance**: Knowledge transfer via prompt libraries, not memos

## ai-agents Alignment

| Pattern | ai-agents Status |
|---------|-----------------|
| Skills | ✅ `.claude/skills/` |
| Self-service | ⚠️ Partial (terminal-only) |
| MCP integration | ✅ Serena, Forgetful, GitHub |
| Human gates | ✅ Critic, QA routing |
| Pain point first | ✅ Velocity analysis |

## Gaps Identified

1. **Skill inheritance docs**: Need formal discovery/composition patterns
2. **Self-service depth**: Current tools require git knowledge

## Related

- Issue #324 (Velocity Improvement)
- Analysis: `.agents/analysis/anthropic-legal-ai-workflows.md`
