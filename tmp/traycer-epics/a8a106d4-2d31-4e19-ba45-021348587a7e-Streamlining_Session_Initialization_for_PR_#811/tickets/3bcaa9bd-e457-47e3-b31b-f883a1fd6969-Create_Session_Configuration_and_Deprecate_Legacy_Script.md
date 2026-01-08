---
id: "3bcaa9bd-e457-47e3-b31b-f883a1fd6969"
title: "Create Session Configuration and Deprecate Legacy Script"
assignee: ""
status: 0
createdAt: "1767767035888"
updatedAt: "1767767097191"
type: ticket
---

# Create Session Configuration and Deprecate Legacy Script

## Objective

Create the session configuration file with defaults, deprecate the legacy New-SessionLog.ps1 script, and update slash command integration to point to the new orchestrator.

## Scope

**In Scope**:
- Create `file:.agents/.session-config.json` with default configuration
- Add JSON schema validation
- Mark `file:.claude/skills/session-init/scripts/New-SessionLog.ps1` as DEPRECATED
- Add deprecation warning to New-SessionLog.ps1 output
- Update `file:.claude/commands/session-init.md` to point to Invoke-SessionInit.ps1
- Document removal timeline (2-week grace period)

**Out of Scope**:
- Actual removal of New-SessionLog.ps1 (deferred to 2 weeks post-deployment)
- Changes to other slash commands
- Configuration UI or editor (JSON file is manually edited)

## Spec References

- **Tech Plan**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/23a7f44b-69e7-4399-a164-c8eedf67b455 (Configuration Schema, Migration Strategy)
- **Core Flows**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/15983562-81e6-4a00-bde0-eb5590be882a (Configuration Options)

## Acceptance Criteria

1. **.session-config.json created**:
   - Location: `.agents/.session-config.json`
   - Contains default configuration with all 4 settings
   - Includes JSON schema reference
   - Committed to repository

2. **Configuration schema**:
   ```json
   {
     "session": {
       "enforceInit": true,
       "promptOnCheckout": true,
       "blockCommits": true,
       "allowBypass": true
     }
   }
   ```

3. **New-SessionLog.ps1 deprecated**:
   - Header comments updated with DEPRECATED notice
   - Deprecation warning added to script output: "WARNING: This script is deprecated. Use Invoke-SessionInit.ps1 instead."
   - Script remains functional during grace period
   - Removal timeline documented in comments

4. **Slash command updated**:
   - `file:.claude/commands/session-init.md` updated to execute Invoke-SessionInit.ps1
   - Usage examples updated with new parameters (--verbose, --skip-commit, --dry-run)
   - Benefits section updated to reflect new capabilities

5. **Migration guide created**:
   - Document in `.claude/skills/session-init/MIGRATION.md`
   - Explains differences between old and new workflow
   - Provides removal timeline
   - Includes troubleshooting section

## Dependencies

- **Ticket 3**: Orchestrator and phase scripts (slash command points to orchestrator)

## Implementation Notes

**Deprecation Warning Pattern**:

```powershell
# Add to New-SessionLog.ps1 after line 57
Write-Warning "DEPRECATED: This script will be removed in 2 weeks."
Write-Warning "Use the new orchestrator instead:"
Write-Warning "  pwsh .claude/skills/session-init/scripts/Invoke-SessionInit.ps1"
Write-Warning "Or invoke via slash command: /session-init"
Write-Warning ""
```

**Configuration File Location**:
- `.agents/.session-config.json` (not repository root)
- Logical grouping with other agent artifacts
- Version-controlled for consistent behavior
