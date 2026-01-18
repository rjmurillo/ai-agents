# Incoherence Report: Installation Script Migration

**Date**: 2026-01-17
**Scope**: Documentation review following migration from PowerShell installation scripts to skill-installer
**Dimension**: D - Temporal Consistency (stale references to deleted files)

## Executive Summary

- **Issues Found**: 10 confirmed temporal incoherences
- **Severity Breakdown**: Critical: 2 | High: 3 | Medium: 5
- **Dimensions Analyzed**: D (Temporal Consistency)
- **Root Cause**: Deleted PowerShell installation infrastructure (install.ps1, Install-Common.psm1, Config.psd1, test files, CI workflow) still referenced in documentation

---

## Issues

### Issue I1: scripts/AGENTS.md Documents Deleted Install-Common.psm1 Library

**Type**: Gap (documentation for non-existent code)
**Severity**: critical
**Dimension**: D - Temporal Consistency

#### Source A: Documentation Claims Library Exists

**File**: `scripts/AGENTS.md`
**Lines**: 292-308

```markdown
## Shared Library

### lib/Install-Common.psm1

Shared functions used by all installation scripts:

| Function | Purpose |
|----------|---------|
| `Get-InstallConfig` | Load environment/scope configuration |
| `Resolve-DestinationPath` | Expand path expressions |
| `Test-SourceDirectory` | Validate source exists |
| `Get-AgentFiles` | Find agent files by pattern |
| `Initialize-Destination` | Create destination directory |
| `Test-GitRepository` | Check if path is git repo |
| `Initialize-AgentsDirectories` | Create `.agents/` subdirectories |
| `Copy-AgentFile` | Copy single agent with prompting |
| `Install-InstructionsFile` | Install/upgrade instructions |
| `Write-InstallHeader` | Display installation header |
| `Write-InstallComplete` | Display completion message |
```

#### Source B: File Deleted in Session Log

**File**: `.agents/sessions/2026-01-17-session-01-skill-installer.json`
**Entry**: filesChanged[104]

```json
{
  "path": "scripts/lib/Install-Common.psm1",
  "changeType": "deleted"
}
```

#### Analysis

The scripts/AGENTS.md file provides complete documentation for Install-Common.psm1 module with 10 exported functions, suggesting it's operational infrastructure. However, this file was deleted on 2026-01-17 as part of migrating to skill-installer. Users reading this documentation will expect to find this library and may attempt to use these functions.

#### Suggestions

1. **Remove entire section** (lines 290-308) since Install-Common.psm1 no longer exists
2. **Add historical note** if context is needed: "Prior to v0.2.0, installation used Install-Common.psm1 library (now replaced by skill-installer)"

#### Resolution

Remove the entire "Shared Library" section (lines 290-332) from scripts/AGENTS.md. The Install-Common.psm1 and Config.psd1 files no longer exist and should not be documented as operational infrastructure.

#### Status

✅ RESOLVED — scripts/AGENTS.md: Removed "Shared Library" section (lines 290-332) documenting Install-Common.psm1 and Config.psd1

<!-- /Resolution -->

---

### Issue I2: scripts/AGENTS.md Documents Deleted Config.psd1 Configuration

**Type**: Gap (documentation for non-existent code)
**Severity**: critical
**Dimension**: D - Temporal Consistency

#### Source A: Documentation Shows Configuration Structure

**File**: `scripts/AGENTS.md`
**Lines**: 310-332

```markdown
### lib/Config.psd1

Environment-specific configuration:

```powershell
@{
    _Common = @{
        BeginMarker = "<!-- BEGIN: ai-agents installer -->"
        EndMarker = "<!-- END: ai-agents installer -->"
        AgentsDirs = @(".agents/analysis", ".agents/planning", ...)
    }

    Claude = @{
        DisplayName = "Claude Code"
        SourceDir = "src/claude"
        FilePattern = "*.md"
        Global = @{ DestDir = '$HOME/.claude/agents' }
        Repo = @{ DestDir = '.claude/agents' }
    }

    # VSCode, Copilot configurations...
}
```
```

#### Source B: File Deleted in Session Log

**File**: `.agents/sessions/2026-01-17-session-01-skill-installer.json`
**Entry**: filesChanged[105]

```json
{
  "path": "scripts/lib/Config.psd1",
  "changeType": "deleted"
}
```

#### Analysis

The scripts/AGENTS.md file documents the Config.psd1 data structure with detailed configuration examples, implying this is active configuration. However, Config.psd1 was deleted on 2026-01-17. The skill-installer tool uses its own configuration system via marketplace.json.

#### Suggestions

1. **Remove entire section** (lines 310-332) since Config.psd1 no longer exists
2. **Reference new system**: "Agent installation is now configured via `.claude-plugin/marketplace.json` (see docs/installation.md)"

#### Resolution

Already covered in I1 resolution - the entire "Shared Library" section (lines 290-332) will be removed from scripts/AGENTS.md, which includes both Install-Common.psm1 and Config.psd1 documentation.

#### Status

✅ RESOLVED — scripts/AGENTS.md: Config.psd1 documentation removed as part of I1 fix

<!-- /Resolution -->

---

### Issue I3: utilities-cva-refactoring Memory Lists Deleted Implementation Paths

**Type**: Gap (stale implementation references)
**Severity**: high
**Dimension**: D - Temporal Consistency

#### Source A: Memory Lists PowerShell Implementation Files

**File**: `.serena/memories/utilities-cva-refactoring.md`
**Line**: 159

```markdown
Implementation: scripts/lib/Install-Common.psm1, scripts/lib/Config.psd1, scripts/install.ps1
```

#### Source B: Files Deleted, New System in Place

**File**: `README.md`
**Lines**: 36-45 (updated to skill-installer)

```markdown
## Installation

Use [skill-installer](https://github.com/rjmurillo/skill-installer):

```bash
uv tool install git+https://github.com/rjmurillo/skill-installer
skill-installer source add rjmurillo/ai-agents
skill-installer interactive
```
```

#### Analysis

The utilities-cva-refactoring memory file references PowerShell scripts as the implementation path, but these were replaced by skill-installer. This memory may mislead agents searching for implementation context.

#### Suggestions

1. **Update implementation path**: "Implementation: [skill-installer](https://github.com/rjmurillo/skill-installer) (replaced PowerShell scripts in v0.2.0)"
2. **Add deprecation note**: Prepend "DEPRECATED: This analysis describes the PowerShell implementation (v0.1.x). Current installation uses skill-installer."

#### Resolution

Add deprecation header to .serena/memories/utilities-cva-refactoring.md: "DEPRECATED: This CVA describes the PowerShell installation implementation (v0.1.x, deleted 2026-01-17). Current installation uses skill-installer."

#### Status

✅ RESOLVED — .serena/memories/utilities-cva-refactoring.md: Added deprecation header with skill-installer reference

<!-- /Resolution -->

---

### Issue I4: Planning Prerequisites Assume Deleted Files Operational

**Type**: Gap (stale prerequisites)
**Severity**: high
**Dimension**: D - Temporal Consistency

#### Source A: Prerequisites List Deleted Files

**File**: `.agents/planning/claude-compat/vscode-copilot-parity-plan.md`
**Line**: 393

```markdown
Prerequisites: scripts/install.ps1 and scripts/lib/Config.psd1 are operational
```

#### Source B: Installation Now Uses Different System

**File**: `docs/installation.md` (rewritten 2026-01-17)

Current installation system is skill-installer, not PowerShell scripts.

#### Analysis

Planning document assumes PowerShell installation infrastructure exists as a prerequisite for work. This could block implementation if taken literally, even though the prerequisite is no longer relevant.

#### Suggestions

1. **Update prerequisite**: "Prerequisites: skill-installer properly configured with rjmurillo/ai-agents source"
2. **Mark plan as historical**: Add "NOTE: This plan was written for v0.1.x (PowerShell installation). Prerequisites have changed for v0.2.0+"

#### Resolution

Add historical note at top of .agents/planning/claude-compat/vscode-copilot-parity-plan.md: "HISTORICAL PLAN: Written for v0.1.x (PowerShell installation infrastructure). Prerequisites reference install.ps1 and Config.psd1 which were deleted 2026-01-17 and replaced by skill-installer."

#### Status

✅ RESOLVED — .agents/planning/claude-compat/vscode-copilot-parity-plan.md: Added historical context header explaining PowerShell infrastructure replacement

<!-- /Resolution -->

---

### Issue I5: GitHub Prompt Template References Deleted Config File

**Type**: Gap (stale template section)
**Severity**: high
**Dimension**: D - Temporal Consistency

#### Source A: Prompt Includes Config.psd1 Section

**File**: `.github/prompts/issue-prd-generation.md`
**Line**: 95

```markdown
### Config.psd1 Changes
[Example PowerShell configuration]
```

#### Source B: Config.psd1 Deleted

**File**: `.agents/sessions/2026-01-17-session-01-skill-installer.json`

Config.psd1 confirmed deleted.

#### Analysis

The issue PRD generation prompt template includes a section for documenting Config.psd1 changes. This will confuse users filling out the template, as they'll expect to document changes to a file that no longer exists.

#### Suggestions

1. **Remove Config.psd1 section** from template
2. **Replace with marketplace.json section**: "### Marketplace Manifest Changes (.claude-plugin/marketplace.json)"

#### Resolution

Remove Config.psd1 section from .github/prompts/issue-prd-generation.md. No replacement needed - Config.psd1 was installation infrastructure, not feature configuration.

#### Status

✅ RESOLVED — .github/prompts/issue-prd-generation.md: Removed Config.psd1 section from template (lines 94-99)

<!-- /Resolution -->

---

### Issue I6: install-script-ci-verification-workflow Memory Deprecated But Detailed

**Type**: Gap (deprecated memory with operational tone)
**Severity**: medium
**Dimension**: D - Temporal Consistency

#### Source A: Memory Marked Deprecated

**File**: `.serena/memories/install-script-ci-verification-workflow.md`
**Lines**: 1-6

```markdown
> **DEPRECATED (2026-01-17)**: This memory is historical. The PowerShell installation scripts
> and verify-install-script.yml workflow have been replaced by [skill-installer](https://github.com/rjmurillo/skill-installer).

- Added .github/workflows/verify-install-script.yml with matrix...
- Workflow uses dorny/paths-filter to skip when install-related files unchanged...
- Verification helper script checks destination directories...
```

#### Analysis

Memory correctly marked as deprecated but still contains detailed operational descriptions ("uses dorny/paths-filter", "checks destination directories") that read as if current. Could confuse agents searching for CI workflow context.

#### Suggestions

1. **Condense to historical summary**: Reduce detailed implementation notes since they're no longer relevant
2. **Keep as-is**: Deprecation notice is sufficient for historical reference

#### Resolution

Keep as-is. Deprecation notice at top is sufficient for historical reference.

#### Status

✅ NO ACTION REQUIRED — Memory already has deprecation notice added 2026-01-17

<!-- /Resolution -->

---

### Issue I7: install-scripts-cva Memory Deprecated But Incomplete Notice

**Type**: Gap (insufficient deprecation context)
**Severity**: medium
**Dimension**: D - Temporal Consistency

#### Source A: Memory Has Deprecation Header

**File**: `.serena/memories/install-scripts-cva.md`
**Lines**: 1-4

Similar deprecation notice to I6.

#### Analysis

Same issue as I6 - deprecated memory with extensive operational details that could confuse context retrieval.

#### Suggestions

1. Same as I6 - condense or keep as-is with clear deprecation
2. Consider moving to `.agents/retrospective/` as historical architecture analysis

#### Resolution

Keep as-is. Same as I6 - deprecation notice is sufficient.

#### Status

✅ NO ACTION REQUIRED — Memory already has deprecation notice added 2026-01-17

<!-- /Resolution -->

---

### Issue I8: QA Report 892 Cites Test Results from Deleted Files

**Type**: Gap (historical record with stale references)
**Severity**: medium
**Dimension**: D - Temporal Consistency

#### Source A: QA Report References Test Files

**File**: `.agents/qa/892-install-script-variable-conflict-test-report.md`
**Lines**: 67, 101

Test results cited from Install-Common.Tests.ps1 and install.Tests.ps1 (both deleted).

#### Analysis

Historical QA report from issue #892 documents test results as evidence. While the tests no longer exist, this is archival documentation of work performed. May be acceptable to preserve as historical record with context note.

#### Suggestions

1. **Add archival note**: Prepend "HISTORICAL RECORD: This QA report documents tests from PowerShell implementation (v0.1.x, deleted 2026-01-17)"
2. **Keep as-is**: QA reports are historical evidence, no modification needed

#### Resolution

Keep as-is. QA reports are historical evidence of testing performed. No modification needed.

#### Status

✅ NO ACTION REQUIRED — QA reports are archival records

<!-- /Resolution -->

---

### Issue I9: Architecture Review References Deleted Files with Line Numbers

**Type**: Gap (historical record with specific code references)
**Severity**: medium
**Dimension**: D - Temporal Consistency

#### Source A: Design Review Cites Deleted Code

**File**: `.agents/architecture/DESIGN-REVIEW-install-script-parameter-validation.md`
**Lines**: 17, 53, 165

References to scripts/tests/install.Tests.ps1 and scripts/lib/Install-Common.psm1 with specific line numbers.

#### Analysis

Architectural design review documents decisions with code evidence. Similar to I8, this is historical evidence of design quality. Line-specific references are now dead links.

#### Suggestions

1. **Add archival note**: "HISTORICAL REVIEW: This design review applies to PowerShell implementation (v0.1.x, deleted 2026-01-17)"
2. **Keep as-is**: Architecture reviews are historical decisions

#### Resolution

Keep as-is. Architecture reviews are historical decisions and evidence. No modification needed.

#### Status

✅ NO ACTION REQUIRED — Architecture reviews are archival records

<!-- /Resolution -->

---

### Issue I10: Security Report Analyzes Deleted Code

**Type**: Gap (historical security analysis)
**Severity**: medium
**Dimension**: D - Temporal Consistency

#### Source A: Security Review References Deleted Files

**File**: `.agents/security/SR-vscode-copilot-parity-plan.md`
**Lines**: 76, 125

Security analysis cites code locations in install.ps1 and Install-Common.psm1.

#### Analysis

Security review of PowerShell implementation. Like I8 and I9, this is archival security evidence. May be valuable for understanding security decisions even if code is gone.

#### Suggestions

1. **Add archival note**: "HISTORICAL SECURITY REVIEW: Analysis of PowerShell implementation (v0.1.x, deleted 2026-01-17). Current installation via skill-installer has different security surface."
2. **Keep as-is**: Security reviews are permanent record

#### Resolution

Keep as-is. Security reviews are permanent record of security analysis performed. No modification needed.

#### Status

✅ NO ACTION REQUIRED — Security reviews are archival records

<!-- /Resolution -->

---

## Summary

**Critical Issues (2)**: Require immediate fixes - operational documentation claiming deleted files exist

**High Priority (3)**: Update to prevent confusion - memory/planning files with stale implementation references

**Medium Priority (5)**: Historical documents - may preserve with archival context notes

**Next Steps**: Fill in Resolution sections above with specific decisions, then run reconciliation phase (steps 14-22) to apply fixes.
