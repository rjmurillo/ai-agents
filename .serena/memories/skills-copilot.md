# Copilot Skills

**Created**: 2025-12-23 (consolidated from 3 memories)
**Sources**: PR #25, PR #32, PR #249, roadmap decisions
**Skills**: 8

---

## Part 1: Platform Priority Decision

**Date**: 2025-12-17 | **Status**: Active

**Platform Hierarchy**:

| Priority | Platform | Investment Level |
|----------|----------|------------------|
| P0 | Claude Code | Full investment |
| P1 | VS Code | Active development |
| P2 | Copilot CLI | Maintenance only |

**Key Limitations (Copilot CLI)**:
- User-level MCP config only (no project-level, no team sharing)
- No Plan Mode
- Limited context window (8k-32k vs 200k+)
- No semantic code analysis
- Known reliability issues with user-level agent loading

**RICE Score Comparison**:
- Claude Code: ~20+
- VS Code: ~10+
- Copilot CLI: 0.8

**Investment Decisions**:
- DECLINED: Copilot CLI sync in Sync-McpConfig.ps1
- MAINTENANCE ONLY: Existing agents remain, no new features
- NO PARITY REQUIREMENT: New features may ship to Claude Code/VS Code only

**Removal Criteria** (evaluate if any apply):
- Maintenance burden >10% of total development effort
- Zero user requests in 90 days
- No GitHub improvements to critical gaps in 6 months
- >90% users on Claude Code or VS Code

---

## Part 2: Follow-Up PR Pattern

**Behavior**: When Copilot receives a reply to its PR review comments, it creates a follow-up PR:
- Branch naming: `copilot/sub-pr-{original_pr_number}`
- Target branch: The original PR's branch (not main)
- Notification: Posts issue comment: "I've opened a new pull request, #{number}"

**Handling Duplicate Follow-Up PRs**:

```bash
# 1. Check review count
gh pr view {number} --json reviews --jq '.reviews | length'

# 2. If 0 reviews and issue was already fixed, close as duplicate
gh pr close {number} --comment "Closing: This follow-up PR is a duplicate of the fix already applied in commit {sha} on PR #{original}."
```

**Example (PR #32 / PR #33)**:
- Original PR #32: 5 Copilot comments about missing `devops`
- Fix applied: Commit 760f1e1 addressed all 5 comments
- Follow-up PR #33: Created by Copilot, duplicate of fix
- Resolution: Closed PR #33 as duplicate

---

## Part 3: PR Review Patterns

### Skill: Documentation Consistency Checking

Copilot cross-references inlined content against source documentation and flags discrepancies.

**Characteristics**:
- Identifies when inlined content differs from source documentation
- Provides specific code suggestions for fixes
- Comments are VALID (not false positives) for consistency checking
- Multiple comments may be generated for same issue across files

### Skill: Sequence Consistency Checking

Copilot identifies when documented workflows/sequences are incomplete.

**Trigger**: Cross-references agent sequences against Phase documentation.

**Triage Classification**:

| Comment Type | Likely Path | Handling |
|--------------|-------------|----------|
| Missing table row/entry | Quick Fix | Accept suggestion |
| Content differs from source | Standard | Investigate intent |
| Missing sequence element | Quick Fix | Apply across all files |
| Sequence differs from Phase | Quick Fix | Verify Phase docs are truth |
| Typo/formatting | Quick Fix | Accept suggestion |

---

## Part 4: False Positive Patterns

### Pattern: Contradictory Comments

- Same PR may have contradictory comments (e.g., "needs read permission" then "write permission is too broad")
- Both cannot be valid; indicates contextual confusion
- **Action**: Ignore the contradictory pair

### Pattern: PowerShell Escape Misunderstanding

- Copilot misunderstands backtick escapes
- `` `a `` (bell), `` `n `` (newline) incorrectly flagged as typos
- **Action**: Skip PowerShell escape false positives

### Pattern: Duplicate Detection

- Copilot often echoes cursor[bot] findings later
- Check cursor[bot] comments first to identify duplicates
- **Action**: Note as duplicate, address via cursor[bot] response

---

## Part 5: Actionability Metrics

**PR #249 Analysis** (2025-12-22):

| Metric | Historical | PR #249 | Trend |
|--------|------------|---------|-------|
| Signal Quality | ~35% | 21% | ↓ DECLINING |
| False Positives | ~10% | 64% | ↑ INCREASING |
| Duplicates of cursor[bot] | ~5% | 14% | → STABLE |

**Recommendation**: Copilot signal quality declining. Increase verification rigor. Prioritize cursor[bot] comments first.

---

## Part 6: Response Templates

**Accept suggestion**:
> Thanks @Copilot! Good catch - I'll make this update.

**Keep PR version (intentional change)**:
> @Copilot The change is intentional. I'll update the source documentation to reflect this improvement.

**Revert to source**:
> @Copilot Thanks for the consistency check. I'll update to match source documentation.

**Close duplicate follow-up PR**:
> Closing: This follow-up PR is a duplicate of the fix already applied in commit {sha} on PR #{original}.

---

## Quick Reference

| Skill | When to Use |
|-------|-------------|
| Part 1 | Platform investment decisions |
| Part 2 | Handling Copilot follow-up PRs |
| Part 3 | Triaging consistency checks |
| Part 4 | Identifying false positives |
| Part 5 | Setting verification rigor |
| Part 6 | Responding to comments |

## Related

- `skills-pr-review` (general PR review patterns)
- `skills-coderabbit` (CodeRabbit-specific patterns)
