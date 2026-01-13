# CVA Refactoring Skills

**Extracted**: 2025-12-15
**Source**: ai-agents install scripts consolidation

## Skill-Refactor-CVA-001: Phased Migration Pattern

**Statement**: CVA refactoring succeeds via additive phases: module first, entry point second, wrappers last

**Context**: When consolidating duplicated scripts into unified architecture

**Evidence**: ai-agents CVA produced 4 atomic commits, each buildable independently

**Atomicity**: 90%

**Application**:

1. Phase 1: Create shared module with extracted functions (non-breaking)
2. Phase 2: Create unified entry point using the module (additive)
3. Phase 3: Convert legacy scripts to thin wrappers (backward compatible)
4. Phase 4: Add new features (remote execution, interactive mode)

---

## Skill-PowerShell-Config-001: Config Data File Extraction

**Statement**: Extract environment variations to .psd1 data files, keeping logic generic

**Context**: When script variations differ only in configuration values

**Evidence**: Config.psd1 holds 3 environments x 2 scopes without logic changes

**Atomicity**: 92%

**Pattern**:

```powershell
# Config.psd1
@{
    Environment1 = @{
        SourceDir = "path1"
        FilePattern = "*.ext1"
        Global = @{ DestDir = '$HOME/.env1' }
        Repo = @{ DestDir = '.local/env1' }
    }
    Environment2 = @{
        # Similar structure
    }
}
```

---

## Skill-PowerShell-Remote-001: Remote Bootstrap Pattern

**Statement**: Detect iex context via empty $PSScriptRoot, download dependencies to temp

**Context**: When supporting remote script execution via Invoke-Expression

**Evidence**: install.ps1 bootstrap downloads module to $env:TEMP

**Atomicity**: 94%

**Pattern**:

```powershell
$IsRemoteExecution = -not $PSScriptRoot

if ($IsRemoteExecution) {
    $TempDir = Join-Path $env:TEMP "installer-$(Get-Random)"
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    
    $WebClient = New-Object System.Net.WebClient
    $WebClient.DownloadFile("$BaseUrl/module.psm1", "$TempDir/module.psm1")
    
    $ScriptRoot = $TempDir
} else {
    $ScriptRoot = $PSScriptRoot
}
```

---

## Skill-Refactor-Wrapper-001: Thin Wrapper Backward Compatibility

**Statement**: Maintain old interfaces as thin wrappers that call unified implementation

**Context**: When consolidating multiple scripts but needing backward compatibility

**Evidence**: 6 legacy scripts reduced to ~30 lines each, all call install.ps1

**Atomicity**: 91%

**Pattern**:

```powershell
# Old script (now wrapper)
param([switch]$Force)
$ErrorActionPreference = "Stop"

# Single delegation to unified script
$InstallScript = Join-Path $PSScriptRoot "install.ps1"
& $InstallScript -Environment Claude -Global -Force:$Force
```

---

## Skill-PowerShell-Markers-001: Content Block Markers

**Statement**: Use HTML comments (BEGIN/END markers) for upgradeable content blocks in markdown files

**Context**: When installers need to update portions of existing files

**Evidence**: Install-InstructionsFile handles append, upgrade, replace scenarios

**Atomicity**: 91%

**Pattern**:

```markdown
<!-- BEGIN: ai-agents installer -->
[Managed content that can be upgraded]
<!-- END: ai-agents installer -->
```

**Implementation**:

```powershell
$BeginMarker = "<!-- BEGIN: ai-agents installer -->"
$EndMarker = "<!-- END: ai-agents installer -->"

if ($ExistingContent -match [regex]::Escape($BeginMarker)) {
    # Upgrade: Replace existing block
    $Pattern = "(?s)$([regex]::Escape($BeginMarker)).*?$([regex]::Escape($EndMarker))"
    $UpdatedContent = $ExistingContent -replace $Pattern, "$BeginMarker`n$NewContent`n$EndMarker"
} else {
    # First install: Append block
    $UpdatedContent = $ExistingContent + "`n`n$BeginMarker`n$NewContent`n$EndMarker"
}
```

---

## Session Validation

**2025-12-15 Session**: All skills validated as helpful in install scripts refactoring:

- Skill-Refactor-CVA-001: Successfully applied, 4 atomic commits
- Skill-PowerShell-Config-001: Config.psd1 eliminated duplication
- Skill-PowerShell-Remote-001: Remote install working via iex
- Skill-Refactor-Wrapper-001: 6 legacy scripts backward compatible

---

## Related Files

- Plan: `.agents/planning/cva-install-scripts.md`
- Retrospective: `.agents/retrospective/2025-12-15-cva-install-scripts.md`
- Implementation: `scripts/lib/Install-Common.psm1`, `scripts/lib/Config.psd1`, `scripts/install.ps1`

## Related

- [utilities-markdown-fences](utilities-markdown-fences.md)
- [utilities-pathinfo-conversion](utilities-pathinfo-conversion.md)
- [utilities-precommit-hook](utilities-precommit-hook.md)
- [utilities-regex](utilities-regex.md)
- [utilities-security-patterns](utilities-security-patterns.md)
