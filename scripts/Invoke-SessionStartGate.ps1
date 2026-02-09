<#
.SYNOPSIS
    Verification-based session start gate for all AI agents.

.DESCRIPTION
    Implements BLOCKING gates for AI agent sessions to ensure:
    1. Memory-First: memory-index and task-relevant memories loaded
    2. Skill Availability: GitHub skills cataloged and usage-mandatory memory loaded
    3. Session Log: Valid session log exists
    4. Branch Verification: Not on main/master branch

    This script enforces session protocol compliance through verification-based gates
    per ADR-033 (Routing-Level Enforcement Gates).
    
    Applicable to all AI agents including Claude Code, GitHub Copilot, and others.

.PARAMETER CheckOnly
    Run all gates and report status without blocking (for diagnostics)

.PARAMETER SkipMemoryGate
    Skip Gate 1 (Memory-First) - use only when memories genuinely not needed

.PARAMETER SkipSkillGate
    Skip Gate 2 (Skill Availability) - use only when no GitHub operations planned

.PARAMETER SkipSessionLogGate
    Skip Gate 3 (Session Log) - use only for non-session work (rare)

.PARAMETER SkipBranchGate
    Skip Gate 4 (Branch Verification) - use only for read-only operations

.EXAMPLE
    .\Invoke-SessionStartGate.ps1
    Runs all gates; blocks if any gate fails

.EXAMPLE
    .\Invoke-SessionStartGate.ps1 -CheckOnly
    Diagnostic mode: reports gate status without blocking

.NOTES
    EXIT CODES (per ADR-035):
    0  - Success: All gates passed
    1  - Logic error in gate script itself
    2  - Gate condition not met (BLOCKING)
    3  - External dependency failure (git, file system, etc.)

    See: ADR-033 Routing-Level Enforcement Gates
    See: ADR-035 Exit Code Standardization
    See: .agents/SESSION-PROTOCOL.md for session protocol
#>

[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$SkipMemoryGate,
    [switch]$SkipSkillGate,
    [switch]$SkipSessionLogGate,
    [switch]$SkipBranchGate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Color output functions
function Write-GateHeader {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Write-GatePass {
    param([string]$Message)
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-GateFail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Write-GateWarning {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-GateInfo {
    param([string]$Message)
    Write-Host "  → $Message" -ForegroundColor Gray
}

# Gate result tracking
$gateResults = @{
    Gate1_MemoryFirst = $null
    Gate2_SkillAvailability = $null
    Gate3_SessionLog = $null
    Gate4_BranchVerification = $null
}

$failedGates = @()
$exitCode = 0

# Helper: Find repo root
function Get-RepoRoot {
    try {
        $root = (git rev-parse --show-toplevel 2>&1)
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return $root.Trim()
    } catch {
        return $null
    }
}

$repoRoot = Get-RepoRoot
if (-not $repoRoot) {
    Write-GateFail "Could not find git repository root"
    Write-GateInfo "Ensure you are inside a git repository"
    exit 3  # External dependency failure
}

Write-Host "`nSession Start Gate - Verification-Based Protocol Enforcement" -ForegroundColor Magenta
Write-Host "Repository: $repoRoot" -ForegroundColor Gray
Write-Host "Mode: $(if ($CheckOnly) { 'Check Only (Non-Blocking)' } else { 'Enforcement (Blocking)' })" -ForegroundColor Gray

# ============================================================================
# GATE 1: Memory-First Verification
# ============================================================================

if (-not $SkipMemoryGate) {
    Write-GateHeader "Gate 1: Memory-First Verification"
    Write-GateInfo "Verifying memory-index and task-relevant memories are available"

    $memoryIndexPath = Join-Path $repoRoot ".serena" "memories" "memory-index.md"
    $gate1Pass = $true

    # Check if memory index exists
    if (-not (Test-Path $memoryIndexPath)) {
        Write-GateFail "Memory index not found: $memoryIndexPath"
        Write-GateInfo "Memory-first workflow requires memory-index to identify task-relevant memories"
        Write-GateInfo "Expected path: .serena/memories/memory-index.md"
        $gate1Pass = $false
    } else {
        Write-GatePass "Memory index exists: $memoryIndexPath"
        
        # Parse memory index to identify available memories
        try {
            $indexContent = Get-Content $memoryIndexPath -Raw
            $memoryCount = ([regex]::Matches($indexContent, '\[([^\]]+)\]\(([^\)]+)\.md\)')).Count
            Write-GateInfo "Memory index contains $memoryCount memory references"
            
            # Check for essential Tier 1 memories (always-load)
            $tier1Memories = @('project-overview', 'codebase-structure', 'usage-mandatory')
            $missingTier1 = @()
            
            foreach ($memory in $tier1Memories) {
                $memoryPath = Join-Path $repoRoot ".serena" "memories" "$memory.md"
                if (-not (Test-Path $memoryPath)) {
                    $missingTier1 += $memory
                }
            }
            
            if ($missingTier1.Count -gt 0) {
                Write-GateWarning "Missing Tier 1 (essential) memories: $($missingTier1 -join ', ')"
                Write-GateInfo "Tier 1 memories should always be loaded at session start"
                Write-GateInfo "If these memories don't exist, consider creating them or updating tier definitions"
            } else {
                Write-GatePass "All Tier 1 (essential) memories available"
            }
            
        } catch {
            Write-GateWarning "Could not parse memory index: $($_.Exception.Message)"
            Write-GateInfo "Manual verification recommended"
        }
    }

    $gateResults.Gate1_MemoryFirst = $gate1Pass
    if (-not $gate1Pass) {
        $failedGates += "Gate 1 (Memory-First)"
    }
} else {
    Write-GateHeader "Gate 1: Memory-First Verification (SKIPPED)"
    $gateResults.Gate1_MemoryFirst = $null
}

# ============================================================================
# GATE 2: Skill Availability Check
# ============================================================================

if (-not $SkipSkillGate) {
    Write-GateHeader "Gate 2: Skill Availability Check"
    Write-GateInfo "Cataloging available GitHub skills and verifying usage-mandatory memory"

    $skillBasePath = Join-Path $repoRoot ".claude" "skills" "github" "scripts"
    $gate2Pass = $true

    # Check if skills directory exists
    if (-not (Test-Path $skillBasePath)) {
        Write-GateFail "GitHub skills directory not found: $skillBasePath"
        Write-GateInfo "Expected path: .claude/skills/github/scripts/"
        $gate2Pass = $false
    } else {
        Write-GatePass "GitHub skills directory exists: $skillBasePath"
        
        # List available skill operations
        $operations = @('pr', 'issue', 'reactions', 'label', 'milestone')
        $skillCount = 0
        
        foreach ($op in $operations) {
            $opPath = Join-Path $skillBasePath $op
            if (Test-Path $opPath) {
                $scripts = @(Get-ChildItem -Path $opPath -Filter "*.ps1" -ErrorAction SilentlyContinue)
                if ($scripts.Count -gt 0) {
                    $skillCount += $scripts.Count
                    Write-GateInfo "$op operations: $($scripts.Count) skills available"
                }
            }
        }
        
        if ($skillCount -eq 0) {
            Write-GateWarning "No GitHub skill scripts found"
            Write-GateInfo "Skills should be in .claude/skills/github/scripts/<operation>/"
        } else {
            Write-GatePass "Total GitHub skills cataloged: $skillCount"
        }
    }

    # Check for usage-mandatory memory
    $usageMandatoryPath = Join-Path $repoRoot ".serena" "memories" "usage-mandatory.md"
    if (-not (Test-Path $usageMandatoryPath)) {
        Write-GateWarning "usage-mandatory memory not found: $usageMandatoryPath"
        Write-GateInfo "This memory documents skill-first requirement (no raw gh commands when skills exist)"
        Write-GateInfo "Consider creating this memory or loading it if it exists elsewhere"
    } else {
        Write-GatePass "usage-mandatory memory available"
    }

    $gateResults.Gate2_SkillAvailability = $gate2Pass
    if (-not $gate2Pass) {
        $failedGates += "Gate 2 (Skill Availability)"
    }
} else {
    Write-GateHeader "Gate 2: Skill Availability Check (SKIPPED)"
    $gateResults.Gate2_SkillAvailability = $null
}

# ============================================================================
# GATE 3: Session Log Verification
# ============================================================================

if (-not $SkipSessionLogGate) {
    Write-GateHeader "Gate 3: Session Log Verification"
    Write-GateInfo "Verifying session log exists and is valid"

    $sessionsDir = Join-Path $repoRoot ".agents" "sessions"
    $gate3Pass = $true

    # Check if sessions directory exists
    if (-not (Test-Path $sessionsDir)) {
        Write-GateFail "Sessions directory not found: $sessionsDir"
        Write-GateInfo "Expected path: .agents/sessions/"
        $gate3Pass = $false
    } else {
        # Look for today's session log
        $today = Get-Date -Format "yyyy-MM-dd"
        $todaysSessions = Get-ChildItem -Path $sessionsDir -Filter "$today-session-*.json" -ErrorAction SilentlyContinue
        
        if ($todaysSessions.Count -eq 0) {
            Write-GateFail "No session log found for today ($today)"
            Write-GateInfo "Create session log: .agents/sessions/$today-session-01.json"
            Write-GateInfo "Use session-init skill or manual creation following session log schema"
            $gate3Pass = $false
        } else {
            $latestSession = $todaysSessions | Sort-Object Name -Descending | Select-Object -First 1
            Write-GatePass "Session log found: $($latestSession.Name)"
            
            # Validate session log structure
            try {
                $sessionContent = Get-Content $latestSession.FullName -Raw | ConvertFrom-Json
                
                # Check required fields
                $requiredFields = @('schemaVersion', 'session', 'protocolCompliance')
                $missingFields = @()
                
                foreach ($field in $requiredFields) {
                    if (-not $sessionContent.PSObject.Properties.Name.Contains($field)) {
                        $missingFields += $field
                    }
                }
                
                if ($missingFields.Count -gt 0) {
                    Write-GateWarning "Session log missing required fields: $($missingFields -join ', ')"
                    Write-GateInfo "Run: python3 scripts/validate_session_json.py $($latestSession.FullName)"
                } else {
                    Write-GatePass "Session log structure valid"
                    Write-GateInfo "Objective: $($sessionContent.session.objective)"
                }
                
            } catch {
                Write-GateWarning "Could not parse session log as JSON: $($_.Exception.Message)"
                Write-GateInfo "Run: python3 scripts/validate_session_json.py $($latestSession.FullName)"
            }
        }
    }

    $gateResults.Gate3_SessionLog = $gate3Pass
    if (-not $gate3Pass) {
        $failedGates += "Gate 3 (Session Log)"
    }
} else {
    Write-GateHeader "Gate 3: Session Log Verification (SKIPPED)"
    $gateResults.Gate3_SessionLog = $null
}

# ============================================================================
# GATE 4: Branch Verification
# ============================================================================

if (-not $SkipBranchGate) {
    Write-GateHeader "Gate 4: Branch Verification"
    Write-GateInfo "Verifying not on main/master branch"

    $gate4Pass = $true

    try {
        $currentBranch = (git branch --show-current 2>&1).Trim()
        
        if ($LASTEXITCODE -ne 0) {
            Write-GateFail "Could not determine current branch"
            Write-GateInfo "Git command failed: $currentBranch"
            $gate4Pass = $false
            $exitCode = 3  # External dependency failure
        } elseif ($currentBranch -in @('main', 'master')) {
            Write-GateFail "Currently on protected branch: $currentBranch"
            Write-GateInfo "Session protocol requires work to be done on feature branches"
            Write-GateInfo "Create a feature branch: git checkout -b feat/your-feature-name"
            Write-GateInfo "Or: git checkout -b fix/your-fix-name"
            $gate4Pass = $false
        } else {
            Write-GatePass "Current branch: $currentBranch"
            
            # Get starting commit
            try {
                $startingCommit = (git rev-parse --short HEAD 2>&1).Trim()
                if ($LASTEXITCODE -eq 0) {
                    Write-GateInfo "Starting commit: $startingCommit"
                }
            } catch {
                # Non-critical, just informational
            }
        }
        
    } catch {
        Write-GateFail "Branch verification failed: $($_.Exception.Message)"
        $gate4Pass = $false
        $exitCode = 3  # External dependency failure
    }

    $gateResults.Gate4_BranchVerification = $gate4Pass
    if (-not $gate4Pass) {
        $failedGates += "Gate 4 (Branch Verification)"
    }
} else {
    Write-GateHeader "Gate 4: Branch Verification (SKIPPED)"
    $gateResults.Gate4_BranchVerification = $null
}

# ============================================================================
# SUMMARY
# ============================================================================

Write-Host "`n============================================================" -ForegroundColor Magenta
Write-Host "Gate Results Summary" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta

$passedCount = 0
$failedCount = 0
$skippedCount = 0

foreach ($gate in $gateResults.Keys | Sort-Object) {
    $result = $gateResults[$gate]
    $gateName = $gate -replace '_', ' '
    
    if ($null -eq $result) {
        Write-Host "  ${gateName}: SKIPPED" -ForegroundColor Yellow
        $skippedCount++
    } elseif ($result) {
        Write-Host "  ${gateName}: PASS" -ForegroundColor Green
        $passedCount++
    } else {
        Write-Host "  ${gateName}: FAIL" -ForegroundColor Red
        $failedCount++
    }
}

Write-Host "`nTotal: $passedCount passed, $failedCount failed, $skippedCount skipped" -ForegroundColor Gray

if ($failedCount -gt 0) {
    Write-Host "`n❌ SESSION START BLOCKED" -ForegroundColor Red
    Write-Host "Failed gates: $($failedGates -join ', ')" -ForegroundColor Red
    Write-Host "`nREMEDIATION STEPS:" -ForegroundColor Yellow
    
    if ($failedGates -contains "Gate 1 (Memory-First)") {
        Write-Host "  • Ensure .serena/memories/ directory exists" -ForegroundColor Yellow
        Write-Host "  • Read memory-index.md to identify task-relevant memories" -ForegroundColor Yellow
        Write-Host "  • Load Tier 1 memories (project-overview, codebase-structure, usage-mandatory)" -ForegroundColor Yellow
    }
    
    if ($failedGates -contains "Gate 2 (Skill Availability)") {
        Write-Host "  • Verify .claude/skills/github/scripts/ directory exists" -ForegroundColor Yellow
        Write-Host "  • Ensure GitHub skill scripts are present" -ForegroundColor Yellow
    }
    
    if ($failedGates -contains "Gate 3 (Session Log)") {
        Write-Host "  • Create session log: .agents/sessions/$(Get-Date -Format 'yyyy-MM-dd')-session-01.json" -ForegroundColor Yellow
        Write-Host "  • Use session-init skill or follow session log schema" -ForegroundColor Yellow
        Write-Host "  • See: .agents/SESSION-PROTOCOL.md for template" -ForegroundColor Yellow
    }
    
    if ($failedGates -contains "Gate 4 (Branch Verification)") {
        Write-Host "  • Create feature branch: git checkout -b feat/your-feature-name" -ForegroundColor Yellow
        Write-Host "  • Or switch to existing feature branch: git checkout <branch-name>" -ForegroundColor Yellow
    }
    
    Write-Host "`nSee: .agents/CODEX-PROTOCOL.md for complete session protocol" -ForegroundColor Gray
    
    if (-not $CheckOnly) {
        Write-Host "`nBLOCKING: Fix failed gates before proceeding with work" -ForegroundColor Red
        exit 2  # Gate condition not met
    } else {
        Write-Host "`n(Running in Check-Only mode - not blocking)" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n✅ ALL GATES PASSED - Session start authorized" -ForegroundColor Green
    Write-Host "`nNext steps:" -ForegroundColor Gray
    Write-Host "  1. Read .agents/HANDOFF.md for project status" -ForegroundColor Gray
    Write-Host "  2. Load task-relevant memories from memory-index" -ForegroundColor Gray
    Write-Host "  3. Begin work per session objective" -ForegroundColor Gray
    Write-Host "  4. Update session log with progress" -ForegroundColor Gray
}

exit $exitCode
