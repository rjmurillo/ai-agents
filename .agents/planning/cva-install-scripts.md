# Code Value Analysis: Install Scripts Refactoring

**Date**: 2025-12-15
**Author**: Orchestrator Agent
**Status**: Analysis Complete
**Branch**: feat/install-script

## Executive Summary

This document analyzes the install scripts in `scripts/` to identify duplication, extract common patterns, and design a refactored architecture supporting parameterized remote installation.

**Goal**: Enable installation via:

```powershell
iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/rjmurillo/ai-agents/main/scripts/install.ps1'))
```

With parameters: `-Environment [Claude|Copilot|VSCode]` `-Scope [Global|Local]`

---

## 1. Current State Analysis

### 1.1 Script Inventory

| Script | Lines | Environment | Scope | Source Dir |
|--------|-------|-------------|-------|------------|
| `install-claude-global.ps1` | 92 | Claude | Global | `src/claude` |
| `install-claude-repo.ps1` | 152 | Claude | Local | `src/claude` |
| `install-copilot-cli-global.ps1` | 113 | Copilot CLI | Global | `src/copilot-cli` |
| `install-copilot-cli-repo.ps1` | 167 | Copilot CLI | Local | `src/copilot-cli` |
| `install-vscode-global.ps1` | 93 | VSCode | Global | `src/vs-code-agents` |
| `install-vscode-repo.ps1` | 151 | VSCode | Local | `src/vs-code-agents` |

**Total**: 768 lines across 6 scripts

### 1.2 Source Directories

```
src/
  claude/           -> *.md files (18 agents)
  copilot-cli/      -> *.agent.md files (18 agents)
  vs-code-agents/   -> *.agent.md files (18 agents)
```

---

## 2. Duplication Analysis

### 2.1 Identical Patterns (High Duplication)

#### Pattern 1: Parameter Declaration

**Occurrences**: 6/6 scripts
**Lines per occurrence**: ~5 lines
**Total duplicated lines**: ~30

```powershell
param(
    [string]$RepoPath = (Get-Location).Path,  # Repo scripts only
    [switch]$Force
)
$ErrorActionPreference = "Stop"
```

#### Pattern 2: Source Directory Resolution

**Occurrences**: 6/6 scripts
**Lines per occurrence**: ~3 lines
**Total duplicated lines**: ~18

```powershell
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Join-Path (Split-Path -Parent $ScriptDir) "src" "<env-specific>"
```

#### Pattern 3: Source Validation

**Occurrences**: 6/6 scripts
**Lines per occurrence**: ~4 lines
**Total duplicated lines**: ~24

```powershell
if (-not (Test-Path $SourceDir)) {
    Write-Error "Source directory not found: $SourceDir"
    exit 1
}
```

#### Pattern 4: Destination Directory Creation

**Occurrences**: 6/6 scripts
**Lines per occurrence**: ~4 lines
**Total duplicated lines**: ~24

```powershell
if (-not (Test-Path $DestDir)) {
    Write-Host "Creating <dir> directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
}
```

#### Pattern 5: Agent File Discovery

**Occurrences**: 6/6 scripts
**Lines per occurrence**: ~5 lines
**Total duplicated lines**: ~30

```powershell
$AgentFiles = Get-ChildItem -Path $SourceDir -Filter "<pattern>"

if ($AgentFiles.Count -eq 0) {
    Write-Warning "No agent files found in source directory"
    exit 0
}
```

#### Pattern 6: File Copy Loop

**Occurrences**: 6/6 scripts
**Lines per occurrence**: ~15 lines
**Total duplicated lines**: ~90

```powershell
foreach ($File in $AgentFiles) {
    $DestPath = Join-Path $DestDir $File.Name
    $Exists = Test-Path $DestPath

    if ($Exists -and -not $Force) {
        $Response = Read-Host "  $($File.Name) exists. Overwrite? (y/N)"
        if ($Response -ne 'y' -and $Response -ne 'Y') {
            Write-Host "  Skipping $($File.Name)" -ForegroundColor Yellow
            continue
        }
    }

    Copy-Item -Path $File.FullName -Destination $DestPath -Force
    $Status = if ($Exists) { "Updated" } else { "Installed" }
    Write-Host "  $Status $($File.Name)" -ForegroundColor Green
}
```

#### Pattern 7: Git Repository Validation (Repo Scripts)

**Occurrences**: 4/6 scripts
**Lines per occurrence**: ~7 lines
**Total duplicated lines**: ~28

```powershell
$GitDir = Join-Path $RepoPath ".git"
if (-not (Test-Path $GitDir)) {
    Write-Warning "Target path does not appear to be a git repository"
    $Response = Read-Host "Continue anyway? (y/N)"
    if ($Response -ne 'y' -and $Response -ne 'Y') {
        exit 0
    }
}
```

#### Pattern 8: .agents Directory Creation (Repo Scripts)

**Occurrences**: 4/6 scripts
**Lines per occurrence**: ~15 lines
**Total duplicated lines**: ~60

```powershell
$AgentsDirs = @(
    ".agents/analysis",
    ".agents/architecture",
    # ... varies slightly
)

foreach ($Dir in $AgentsDirs) {
    $FullPath = Join-Path $RepoPath $Dir
    if (-not (Test-Path $FullPath)) {
        New-Item -ItemType Directory -Path $FullPath -Force | Out-Null
        $GitKeep = Join-Path $FullPath ".gitkeep"
        "" | Out-File -FilePath $GitKeep -Encoding utf8
        Write-Host "  Created $Dir" -ForegroundColor Green
    }
}
```

#### Pattern 9: Instructions File Handling (Append Logic)

**Occurrences**: 3/6 scripts
**Lines per occurrence**: ~18 lines
**Total duplicated lines**: ~54

```powershell
if ($CopilotExists -and -not $Force) {
    $ExistingContent = Get-Content -Path $DestCopilot -Raw
    $BeginMarker = "<!-- BEGIN: ai-agents installer -->"
    $EndMarker = "<!-- END: ai-agents installer -->"
    if ($ExistingContent -match [regex]::Escape($BeginMarker)) {
        # Content exists - replace the block for upgrades
        $Pattern = "(?s)$([regex]::Escape($BeginMarker)).*?$([regex]::Escape($EndMarker))"
        $NewContent = Get-Content -Path $SourceFile -Raw
        $Replacement = "$BeginMarker`n$NewContent`n$EndMarker"
        $UpdatedContent = $ExistingContent -replace $Pattern, $Replacement
        Set-Content -Path $DestFile -Value $UpdatedContent -Encoding utf8
        Write-Host "  Updated existing ai-agents content block"
    } else {
        # First time - append the block
        $NewContent = Get-Content -Path $SourceFile -Raw
        Add-Content -Path $DestFile -Value "`n`n$BeginMarker`n" -Encoding utf8
        Add-Content -Path $DestFile -Value $NewContent -Encoding utf8
        Add-Content -Path $DestFile -Value "`n$EndMarker" -Encoding utf8
    }
}
```

### 2.2 Duplication Summary

| Pattern | Instances | Lines Each | Total Duplicated |
|---------|-----------|------------|------------------|
| Parameter Declaration | 6 | 5 | 30 |
| Source Resolution | 6 | 3 | 18 |
| Source Validation | 6 | 4 | 24 |
| Dest Dir Creation | 6 | 4 | 24 |
| File Discovery | 6 | 5 | 30 |
| File Copy Loop | 6 | 15 | 90 |
| Git Validation | 4 | 7 | 28 |
| .agents Creation | 4 | 15 | 60 |
| Append Logic | 3 | 18 | 54 |
| **Total** | - | - | **358 lines** |

**Duplication Rate**: 358 / 768 = **46.6%** of code is duplicated

---

## 3. Environment-Specific Variations

### 3.1 Configuration Matrix

| Aspect | Claude | Copilot CLI | VSCode |
|--------|--------|-------------|--------|
| **Source Dir** | `src/claude` | `src/copilot-cli` | `src/vs-code-agents` |
| **File Pattern** | `*.md` | `*.agent.md` | `*.agent.md` |
| **Global Dest** | `~/.claude/agents` | `~/.copilot/agents` | `%APPDATA%/Code/User/prompts` |
| **Repo Dest** | `.claude/agents` | `.github/agents` | `.github/agents` |
| **Instructions File** | `CLAUDE.md` | `copilot-instructions.md` | `copilot-instructions.md` |
| **Instructions Dest (Global)** | `~/.claude/` | N/A | `prompts/` |
| **Instructions Dest (Repo)** | Repo root | `.github/` | `.github/` |
| **Known Bugs** | None | Global loading (#452) | None |

### 3.2 Scope-Specific Variations

| Aspect | Global (`-Global`) | Repo (`-RepoPath <path>`) |
|--------|--------|--------|
| **Path Parameter** | None (well-known path) | Required (`-RepoPath`) |
| **Git Validation** | No | Yes |
| **.agents Creation** | No | Yes |
| **Append Logic** | No (simple copy) | Yes (preserve existing) |
| **Commit Guidance** | No | Yes |

---

## 4. Proposed Architecture

### 4.1 Module Structure

```
scripts/
  install.ps1                    # Unified entry point (downloads and runs)
  lib/
    Install-Common.psm1          # Shared functions
    Config.psd1                  # Environment configurations
```

### 4.2 Unified Entry Point: `install.ps1`

```powershell
<#
.SYNOPSIS
    Unified agent installer for Claude, Copilot CLI, and VSCode.

.PARAMETER Environment
    Target environment: Claude, Copilot, VSCode

.PARAMETER Scope
    Installation scope: Global, Local (repository)

.PARAMETER RepoPath
    Repository path for Local scope. Defaults to current directory.

.PARAMETER Force
    Overwrite existing files without prompting.

.EXAMPLE
    # Remote installation (interactive mode)
    iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/rjmurillo/ai-agents/main/scripts/install.ps1'))

    # Local installation - Global scope (well-known paths)
    .\install.ps1 -Environment Claude -Global
    .\install.ps1 -Environment Copilot -Global

    # Local installation - Repository scope (explicit path)
    .\install.ps1 -Environment Claude -RepoPath "C:\MyRepo"
    .\install.ps1 -Environment Copilot -RepoPath "."
#>

param(
    [Parameter(Mandatory)]
    [ValidateSet("Claude", "Copilot", "VSCode")]
    [string]$Environment,

    [Parameter(Mandatory, ParameterSetName = "Global")]
    [switch]$Global,

    [Parameter(Mandatory, ParameterSetName = "Repo")]
    [string]$RepoPath,

    [switch]$Force
)

# Determine scope from parameter set
$Scope = if ($Global) { "Global" } else { "Repo" }
if (-not $Global -and -not $RepoPath) {
    $RepoPath = (Get-Location).Path
}
```

### 4.3 Shared Module: `Install-Common.psm1`

#### Core Functions

```powershell
function Get-InstallConfig {
    param([string]$Environment, [string]$Scope)
    # Returns configuration hashtable from Config.psd1
}

function Test-SourceDirectory {
    param([string]$Path)
    # Validates source exists
}

function Initialize-Destination {
    param([string]$Path, [string]$Description)
    # Creates directory if needed
}

function Get-AgentFiles {
    param([string]$SourceDir, [string]$FilePattern)
    # Returns agent files matching pattern
}

function Copy-AgentFile {
    param(
        [System.IO.FileInfo]$File,
        [string]$DestDir,
        [switch]$Force
    )
    # Handles single file copy with overwrite prompting
}

function Test-GitRepository {
    param([string]$Path)
    # Validates path is a git repository
}

function Initialize-AgentsDirectories {
    param([string]$RepoPath, [string[]]$Directories)
    # Creates .agents subdirectories with .gitkeep
}

function Install-InstructionsFile {
    param(
        [string]$SourcePath,
        [string]$DestPath,
        [string]$AppendMarker,
        [switch]$Force
    )
    # Handles copy/append logic for instructions files
}

function Write-InstallHeader {
    param([string]$Title)
    # Consistent header output
}

function Write-InstallComplete {
    param([string]$Environment, [string]$Scope)
    # Consistent completion message
}
```

### 4.4 Configuration Data: `Config.psd1`

```powershell
@{
    # Shared configuration (referenced by all environments)
    _Common = @{
        # Markdown-compatible markers for upgradeable content blocks
        BeginMarker = "<!-- BEGIN: ai-agents installer -->"
        EndMarker = "<!-- END: ai-agents installer -->"

        # Consistent .agents directories across all environments
        AgentsDirs = @(
            ".agents/analysis"
            ".agents/architecture"
            ".agents/planning"
            ".agents/critique"
            ".agents/qa"
            ".agents/retrospective"
            ".agents/roadmap"
            ".agents/devops"
            ".agents/security"
            ".agents/sessions"
        )
    }

    Claude = @{
        SourceDir = "src/claude"
        FilePattern = "*.md"
        Global = @{
            DestDir = { Join-Path $HOME ".claude\agents" }
            InstructionsFile = "CLAUDE.md"
            InstructionsDest = { Join-Path $HOME ".claude" }
        }
        Repo = @{
            DestDir = { param($RepoPath) Join-Path $RepoPath ".claude\agents" }
            InstructionsFile = "CLAUDE.md"
            InstructionsDest = { param($RepoPath) $RepoPath }
        }
    }

    Copilot = @{
        SourceDir = "src/copilot-cli"
        FilePattern = "*.agent.md"
        KnownBug = @{
            Id = "#452"
            Description = "User-level agents not loaded"
            Url = "https://github.com/github/copilot-cli/issues/452"
        }
        Global = @{
            DestDir = {
                if ($env:XDG_CONFIG_HOME) { Join-Path $env:XDG_CONFIG_HOME ".copilot\agents" }
                elseif ($env:USERPROFILE) { Join-Path $env:USERPROFILE ".copilot\agents" }
                else { Join-Path $HOME ".copilot/agents" }
            }
        }
        Repo = @{
            DestDir = { param($RepoPath) Join-Path $RepoPath ".github\agents" }
            InstructionsFile = "copilot-instructions.md"
            InstructionsDest = { param($RepoPath) Join-Path $RepoPath ".github" }
        }
    }

    VSCode = @{
        SourceDir = "src/vs-code-agents"
        FilePattern = "*.agent.md"
        Global = @{
            DestDir = {
                if ($env:APPDATA) { Join-Path $env:APPDATA "Code\User\prompts" }
                else { Join-Path $HOME ".config/Code/User/prompts" }
            }
            InstructionsFile = "copilot-instructions.md"
            InstructionsDest = {
                if ($env:APPDATA) { Join-Path $env:APPDATA "Code\User\prompts" }
                else { Join-Path $HOME ".config/Code/User/prompts" }
            }
        }
        Repo = @{
            DestDir = { param($RepoPath) Join-Path $RepoPath ".github\agents" }
            InstructionsFile = "copilot-instructions.md"
            InstructionsDest = { param($RepoPath) Join-Path $RepoPath ".github" }
        }
    }
}
```

---

## 5. Remote Execution Compatibility

### 5.1 Challenges for `iex` Execution

1. **Module Loading**: Modules cannot be loaded via `Import-Module` from URLs
2. **Relative Paths**: `$MyInvocation.MyCommand.Path` is empty in iex context
3. **Multi-File Dependencies**: Need to download multiple files

### 5.2 Solution: Self-Contained Bootstrap

For remote execution, the `install.ps1` will:

1. Detect execution context (local vs remote)
2. If remote: download required files to temp directory
3. Load functions inline or from downloaded modules
4. Execute installation

```powershell
# Detect execution context
$IsRemoteExecution = -not $MyInvocation.MyCommand.Path

if ($IsRemoteExecution) {
    # Download files to temp
    $TempDir = Join-Path $env:TEMP "ai-agents-install"
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

    # Download module and config
    $BaseUrl = "https://raw.githubusercontent.com/rjmurillo/ai-agents/main/scripts"
    Invoke-WebRequest "$BaseUrl/lib/Install-Common.psm1" -OutFile "$TempDir\Install-Common.psm1"
    Invoke-WebRequest "$BaseUrl/lib/Config.psd1" -OutFile "$TempDir\Config.psd1"

    # Download source files based on environment selection
    # ... (interactive selection if parameters not provided)
}
```

### 5.3 Interactive Mode for Remote

When invoked without parameters via `iex`:

```powershell
if (-not $Environment) {
    Write-Host "Select Environment:" -ForegroundColor Cyan
    Write-Host "  1. Claude Code"
    Write-Host "  2. GitHub Copilot CLI"
    Write-Host "  3. VS Code / Copilot Chat"
    $choice = Read-Host "Enter choice (1-3)"
    $Environment = @{ "1" = "Claude"; "2" = "Copilot"; "3" = "VSCode" }[$choice]
}

if (-not $Global -and -not $RepoPath) {
    Write-Host "Select Scope:" -ForegroundColor Cyan
    Write-Host "  1. Global (all projects - well-known path)"
    Write-Host "  2. Repository (specify path)"
    $choice = Read-Host "Enter choice (1-2)"
    if ($choice -eq "1") {
        $Global = $true
        $Scope = "Global"
    } else {
        $RepoPath = Read-Host "Enter repository path (or press Enter for current directory)"
        if (-not $RepoPath) { $RepoPath = (Get-Location).Path }
        $Scope = "Repo"
    }
}
```

---

## 6. Migration Strategy

### 6.1 Phase 1: Create Common Module (Non-Breaking)

1. Create `scripts/lib/Install-Common.psm1`
2. Create `scripts/lib/Config.psd1`
3. Test module functions independently
4. Keep existing scripts untouched

### 6.2 Phase 2: Create Unified Entry Point (Additive)

1. Create `scripts/install.ps1`
2. Wire up to common module
3. Test all environment/scope combinations
4. Document new unified interface

### 6.3 Phase 3: Refactor Legacy Scripts (Optional)

1. Update legacy scripts to use common module
2. Mark as deprecated in favor of `install.ps1`
3. Keep for backward compatibility

### 6.4 Phase 4: Remote Execution Support

1. Add bootstrap logic for remote execution
2. Test via GitHub raw URLs
3. Add interactive mode for parameter-less invocation

---

## 7. Estimated Impact

### 7.1 Line Count Reduction

| Metric | Current | After Refactor |
|--------|---------|----------------|
| Total Script Lines | 768 | ~350 |
| Duplication Rate | 46.6% | <10% |
| Files | 6 | 3 (entry + module + config) |

### 7.2 Maintainability Improvements

- **Single Source of Truth**: All logic in one module
- **Configuration-Driven**: Changes via Config.psd1, not code edits
- **Testable**: Functions can be unit tested
- **Extensible**: New environments added via config, not new scripts

### 7.3 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing workflows | Low | Medium | Keep legacy scripts |
| Remote execution fails | Medium | Medium | Fallback to local install |
| Config parsing errors | Low | High | Validate config on load |

---

## 8. Implementation Tasks

### Task Breakdown

1. **Create module structure** (implementer)
   - [ ] Create `scripts/lib/` directory
   - [ ] Implement `Install-Common.psm1` with all shared functions
   - [ ] Create `Config.psd1` with environment configurations

2. **Create unified entry point** (implementer)
   - [ ] Implement `install.ps1` with parameter handling
   - [ ] Add remote execution detection and bootstrap
   - [ ] Add interactive mode for parameter-less invocation

3. **Testing** (qa)
   - [ ] Test Claude Global installation
   - [ ] Test Claude Local installation
   - [ ] Test Copilot Global installation (with bug warning)
   - [ ] Test Copilot Local installation
   - [ ] Test VSCode Global installation
   - [ ] Test VSCode Local installation
   - [ ] Test remote execution via iex

4. **Documentation** (explainer)
   - [ ] Update README with new installation method
   - [ ] Document parameters and usage examples
   - [ ] Add troubleshooting guide

---

## 9. Appendix: Detailed Function Specifications

### 9.1 Copy-AgentFile

```powershell
function Copy-AgentFile {
    <#
    .SYNOPSIS
        Copies a single agent file with overwrite handling.

    .PARAMETER File
        FileInfo object for the source file.

    .PARAMETER DestDir
        Destination directory path.

    .PARAMETER Force
        Skip overwrite prompting.

    .OUTPUTS
        [string] Status message: "Installed", "Updated", or "Skipped"
    #>
    param(
        [Parameter(Mandatory)]
        [System.IO.FileInfo]$File,

        [Parameter(Mandatory)]
        [string]$DestDir,

        [switch]$Force
    )

    $DestPath = Join-Path $DestDir $File.Name
    $Exists = Test-Path $DestPath

    if ($Exists -and -not $Force) {
        $Response = Read-Host "  $($File.Name) exists. Overwrite? (y/N)"
        if ($Response -ne 'y' -and $Response -ne 'Y') {
            Write-Host "  Skipping $($File.Name)" -ForegroundColor Yellow
            return "Skipped"
        }
    }

    Copy-Item -Path $File.FullName -Destination $DestPath -Force
    $Status = if ($Exists) { "Updated" } else { "Installed" }
    Write-Host "  $Status $($File.Name)" -ForegroundColor Green
    return $Status
}
```

### 9.2 Install-InstructionsFile

```powershell
function Install-InstructionsFile {
    <#
    .SYNOPSIS
        Installs or updates an instructions file with upgradeable content blocks.

    .DESCRIPTION
        Uses markdown-compatible HTML comments (BEGIN/END markers) to create
        upgradeable content blocks. On first install, appends the block.
        On subsequent runs, replaces the existing block content (upgrade).

    .PARAMETER SourcePath
        Path to source instructions file.

    .PARAMETER DestPath
        Destination path for instructions file.

    .PARAMETER BeginMarker
        HTML comment marking start of managed content block.

    .PARAMETER EndMarker
        HTML comment marking end of managed content block.

    .PARAMETER Force
        Replace entire file instead of using content blocks.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$SourcePath,

        [Parameter(Mandatory)]
        [string]$DestPath,

        [string]$BeginMarker = "<!-- BEGIN: ai-agents installer -->",
        [string]$EndMarker = "<!-- END: ai-agents installer -->",

        [switch]$Force
    )

    if (-not (Test-Path $SourcePath)) {
        Write-Warning "Instructions file not found: $SourcePath"
        return
    }

    $NewContent = Get-Content -Path $SourcePath -Raw
    $DestExists = Test-Path $DestPath

    if ($DestExists -and -not $Force) {
        $ExistingContent = Get-Content -Path $DestPath -Raw

        if ($ExistingContent -match [regex]::Escape($BeginMarker)) {
            # Upgrade: Replace existing content block
            $Pattern = "(?s)$([regex]::Escape($BeginMarker)).*?$([regex]::Escape($EndMarker))"
            $Replacement = "$BeginMarker`n$NewContent`n$EndMarker"
            $UpdatedContent = $ExistingContent -replace $Pattern, $Replacement
            Set-Content -Path $DestPath -Value $UpdatedContent -Encoding utf8
            Write-Host "  Upgraded existing ai-agents content block" -ForegroundColor Green
        }
        else {
            # First install: Append content block
            Add-Content -Path $DestPath -Value "`n`n$BeginMarker`n" -Encoding utf8
            Add-Content -Path $DestPath -Value $NewContent -Encoding utf8
            Add-Content -Path $DestPath -Value "$EndMarker`n" -Encoding utf8
            Write-Host "  Appended ai-agents content block" -ForegroundColor Green
        }
    }
    else {
        # New file or Force: Write with content block wrapper
        $WrappedContent = "$BeginMarker`n$NewContent`n$EndMarker`n"
        Set-Content -Path $DestPath -Value $WrappedContent -Encoding utf8
        $Status = if ($DestExists) { "Replaced" } else { "Installed" }
        Write-Host "  $Status instructions file" -ForegroundColor Green
    }
}
```

---

## 10. Next Steps

1. **Route to architect** for design review of module structure
2. **Route to implementer** for implementation
3. **Route to qa** for test strategy
4. **Route to critic** for plan validation before implementation

---

*Generated by CVA Analysis - Orchestrator Agent*
