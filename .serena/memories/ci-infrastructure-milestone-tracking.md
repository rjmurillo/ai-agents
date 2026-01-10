# CI Infrastructure: Milestone Tracking Automation

**Category**: CI/CD Workflow Patterns
**Created**: 2026-01-09
**Last Updated**: 2026-01-09
**Related**: ci-infrastructure-yaml-shell-patterns, workflow-patterns-composite-action, usage-mandatory, skills-github-cli-index

## Overview

Automated milestone assignment workflow that assigns the latest semantic version milestone to merged PRs and closed issues.

**Workflow**: `.github/workflows/milestone-tracking.yml`
**Scripts**: `scripts/Get-LatestSemanticMilestone.ps1`, `scripts/Set-ItemMilestone.ps1`

## Trigger Conditions

- **PR closed** with `merged == true` (not just closed unmerged)
- **Issue closed** (any close reason)
- Both types trigger same workflow, different conditional steps

## Implementation Pattern

### Thin Workflow (ADR-006)

Workflow YAML just coordinates, all logic in PowerShell scripts:

```yaml
- name: Assign milestone
  shell: pwsh -NoProfile -Command "& '{0}'"
  env:
    GH_TOKEN: ${{ github.token }}
    PR_NUMBER: ${{ github.event.pull_request.number }}
  run: |
    ./scripts/Set-ItemMilestone.ps1 `
      -ItemType pr `
      -ItemNumber $env:PR_NUMBER
```

**Security**: Uses environment variables (not direct template interpolation) to prevent command injection.

### Semantic Version Detection

Script: `scripts/Get-LatestSemanticMilestone.ps1`

Logic:
1. Query all open milestones: `gh api repos/$Owner/$Repo/milestones?state=open`
2. Filter regex: `^\d+\.\d+\.\d+$` (e.g., "0.2.0", "1.10.3")
3. Sort using `[System.Version]` (not string comparison, so 0.10.0 > 0.2.0)
4. Return latest milestone title and API number

**Exit codes**:
- 0: Success (milestone found)
- 2: No semantic version milestones found
- 3: API error

**Output**:
- GITHUB_OUTPUT: `milestone_title=X.Y.Z`, `milestone_number=N`, `found=true/false`
- Step summary: Formatted table with detection status

### Assignment Orchestration

Script: `scripts/Set-ItemMilestone.ps1`

Logic:
1. Check if item already has milestone: `gh api repos/$Owner/$Repo/issues/$Number`
2. If has milestone: exit with "skipped" (preserves manual assignments)
3. If no milestone:
   - Call `Get-LatestSemanticMilestone.ps1` (unless `-MilestoneTitle` provided)
   - Delegate to `.claude/skills/github/scripts/issue/Set-IssueMilestone.ps1` skill
4. Output structured result

**Exit codes**:
- 0: Success (assigned or skipped)
- 2: Milestone detection failed
- 3: API error
- 5: Assignment failed

**Output**:
- GITHUB_OUTPUT: `success=true/false`, `item_type=pr|issue`, `item_number=N`, `milestone=X.Y.Z`, `action=assigned|skipped|failed`
- Step summary: Formatted status with milestone details

## Key Design Decisions

### Why Semantic Version Detection?
- **Flexibility**: No hardcoded milestone names (unlike moq.analyzers "vNext")
- **Maintainability**: New versions don't require workflow updates
- **Convention**: Follows semantic versioning standard

### Why Skip Existing Milestones?
- **Preserves manual curation**: Maintainers may assign specific milestones for strategic reasons
- **Non-invasive**: Only fills in gaps, doesn't override decisions
- **Idempotent**: Can re-run without side effects

### Why Delegate to Skill?
- **DRY**: Set-IssueMilestone.ps1 already handles validation, error cases, API calls
- **usage-mandatory**: Must use skills over raw gh commands (ADR)
- **Testing**: Skill already has test coverage
- **Maintenance**: Updates to skill benefit all callers

### Why Support Both PRs and Issues?
- **Consistency**: Unified milestone tracking across all work items
- **Flexibility**: Issues often become PRs, milestone continuity matters
- **Convention**: GitHub API treats PRs as issues for most operations

## Comparison to Source Workflow (moq.analyzers)

| Aspect | moq.analyzers | ai-agents |
|--------|--------------|-----------|
| Milestone | Hardcoded "vNext" | Auto-detect latest semantic |
| Scope | PRs only, main branch | PRs + issues, all branches |
| Logic | Inline YAML (GraphQL) | PowerShell scripts |
| Language | Bash/GitHub expressions | PowerShell (ADR-005) |
| Reusability | Workflow-specific | Delegates to tested skills |
| Detection | N/A (fixed name) | Semantic version parsing |

## Usage Examples

### Manual Script Invocation

```powershell
# Auto-detect milestone and assign to PR
./scripts/Set-ItemMilestone.ps1 -ItemType pr -ItemNumber 123

# Assign specific milestone to issue
./scripts/Set-ItemMilestone.ps1 -ItemType issue -ItemNumber 456 -MilestoneTitle "0.2.0"

# Query latest semantic milestone
./scripts/Get-LatestSemanticMilestone.ps1
```

### Expected Output

**Success (assigned)**:
```
milestone_title=0.2.0
milestone_number=42
action=assigned
```

**Success (skipped)**:
```
milestone=1.0.0
action=skipped
message=Already has milestone '1.0.0'. No action taken.
```

**Error (no semantic milestones)**:
```
Exit code: 2
message=No open milestones matching semantic versioning format (X.Y.Z) found.
```

## Testing Strategy

### Unit Tests (Pester)

**Get-LatestSemanticMilestone.Tests.ps1**:
- Multiple semantic milestones (returns latest)
- Version sorting (0.10.0 > 0.3.0 > 0.2.0)
- Mix of semantic and non-semantic (filters)
- No semantic milestones (exit 2)
- API errors (exit 3)
- GITHUB_OUTPUT integration

**Set-ItemMilestone.Tests.ps1**:
- PR without milestone (assigns)
- PR with milestone (skips)
- Issue without milestone (assigns)
- Issue with milestone (skips)
- Milestone detection failure (propagates)
- Assignment failure (propagates)
- Parameter validation

### Integration Testing

Manual verification after deployment:
1. Create test PR without milestone, merge
2. Verify workflow triggers
3. Check GITHUB_OUTPUT values in logs
4. Validate step summary formatting
5. Test with existing milestone (should skip)
6. Test with no semantic milestones (should fail gracefully)

## Error Handling

### No Semantic Milestones
- Detection script exits with code 2
- Assignment script propagates error
- Workflow fails with clear error message
- **Resolution**: Create semantic version milestone (e.g., 0.2.0, 1.0.0)

### API Rate Limits
- Scripts exit with code 3 (API error)
- GitHub Actions will retry on transient failures
- **Resolution**: Wait for rate limit reset or use PAT with higher limits

### Permission Denied
- Scripts exit with code 4 (auth error)
- Clear guidance in error message
- **Resolution**: Ensure workflow has `issues: write`, `pull-requests: write`

## Maintenance Notes

### Adding New Milestone Strategies
Extend `Get-LatestSemanticMilestone.ps1`:
- Add new regex pattern for different versioning schemes
- Preserve semantic version detection as default
- Make strategy configurable via parameter

### Changing Assignment Logic
Extend `Set-ItemMilestone.ps1`:
- Add `-Force` parameter to override existing milestones
- Add milestone selection criteria (e.g., by priority label)
- Maintain backward compatibility with auto-detection

### Performance Optimization
Current: Queries milestones on every invocation
Future: Cache milestone detection results (TTL: 1 hour)
Implementation: Use GitHub Actions cache with milestone list

## Related Patterns

- **ci-infrastructure-yaml-shell-patterns**: PowerShell for security
- **workflow-patterns-composite-action**: Reusable workflow components
- **usage-mandatory**: Skill delegation over raw gh commands
- **skills-github-cli-index**: GitHub CLI usage patterns
- **pattern-thin-workflows**: Logic in scripts, not YAML

## Session Reference

Implemented in: `.agents/sessions/2026-01-09-session-811.md`
Branch: `feat/milestone-backstop`
