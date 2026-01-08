---
id: "d7629154-6085-4366-8036-462e0f9dad15"
title: "Implement Three-Phase Orchestration Scripts"
assignee: ""
status: 0
createdAt: "1767766960244"
updatedAt: "1767767097029"
type: ticket
---

# Implement Three-Phase Orchestration Scripts

## Objective

Create the orchestrator and three phase scripts that implement the optimized session initialization workflow with phased batching, multi-checkpoint validation, and auto-fix capabilities.

## Scope

**In Scope**:
- Create `file:.claude/skills/session-init/scripts/Invoke-SessionInit.ps1` (orchestrator)
- Create `file:.claude/skills/session-init/scripts/Initialize-SessionContext.ps1` (Phase 1)
- Create `file:.claude/skills/session-init/scripts/New-SessionLogFile.ps1` (Phase 2)
- Create `file:.claude/skills/session-init/scripts/Commit-SessionLog.ps1` (Phase 3)
- Create `file:.claude/skills/session-init/scripts/Repair-SessionLog.ps1` (auto-fix)
- Implement hashtable validation contracts between phases
- Implement auto-fix retry policy (max 2 retries per checkpoint, iterative)
- Implement session number auto-detection algorithm
- Add Pester tests for all scripts

**Out of Scope**:
- Git hook integration (handled in separate ticket)
- Configuration file creation (handled in separate ticket)
- Documentation updates (handled in separate ticket)
- Deprecation of New-SessionLog.ps1 (handled in separate ticket)

## Spec References

- **Tech Plan**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/23a7f44b-69e7-4399-a164-c8eedf67b455 (Components 1-4, 6)
- **Core Flows**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/15983562-81e6-4a00-bde0-eb5590be882a (Flows 1-4)
- **Epic Brief**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/5312ae6b-3c86-4b02-ae5d-9ae3a14daf8a (Root Causes 1-6)

## Acceptance Criteria

1. **Orchestrator (Invoke-SessionInit.ps1)**:
   - Parses command-line arguments: SessionNumber, Objective, Verbose, SkipCommit, DryRun
   - Loads configuration from .agents/.session-config.json (with error handling)
   - Executes phases sequentially with hashtable validation between phases
   - Validates required fields in phase outputs, aborts on missing fields
   - Handles optional fields with defaults
   - Returns exit codes: 0 (success), 1 (Phase 1 failure), 2 (Phase 2 failure), 3 (Phase 3 failure), 4 (config error)

2. **Phase 1 (Initialize-SessionContext.ps1)**:
   - Imports GitHelpers.psm1 for git state detection
   - Checks Serena MCP availability (optional, continues if unavailable)
   - Reads HANDOFF.md for context (optional, continues if fails)
   - Auto-detects next session number using algorithm from Tech Plan
   - Returns hashtable with required fields: RepoRoot, Branch, Commit, Status
   - Returns optional fields: SerenaInitialized, HandoffRead

3. **Phase 2 (New-SessionLogFile.ps1)**:
   - Receives Phase 1 context hashtable, validates required fields
   - Prompts for session number and objective if not provided
   - Extracts template using existing Extract-SessionTemplate.ps1
   - Runs Checkpoint 1: Test-TemplateStructure
   - Auto-fills evidence fields (git state only, memory placeholder)
   - Runs Checkpoint 2: Test-EvidenceFields
   - Applies auto-fix if validation fails (max 2 retries, iterative)
   - Runs Checkpoint 3: Invoke-FullValidation
   - Writes session log file
   - Returns hashtable with SessionLogPath, SessionNumber, Objective, ValidationCheckpoints

4. **Phase 3 (Commit-SessionLog.ps1)**:
   - Receives Phase 2 context hashtable, validates required fields
   - Runs final validation with Validate-SessionProtocol.ps1
   - Stages session log file with `git add`
   - Commits with conventional commit message
   - Returns hashtable with Success, SessionLogPath, CommitSHA, ValidationResult

5. **Auto-Fix (Repair-SessionLog.ps1)**:
   - Detects 5 fixable issues: absolute paths, commit SHA format, missing evidence, template header mismatch, path escape characters
   - Applies fixes to file on disk (file-based pattern)
   - Tracks attempted fixes to prevent duplicates
   - Returns hashtable with FixesApplied array and Success boolean
   - Implements retry policy: max 2 attempts per checkpoint, iterative application

6. **Pester Tests**:
   - `.claude/skills/session-init/tests/Invoke-SessionInit.Tests.ps1`
   - `.claude/skills/session-init/tests/Initialize-SessionContext.Tests.ps1`
   - `.claude/skills/session-init/tests/New-SessionLogFile.Tests.ps1`
   - `.claude/skills/session-init/tests/Commit-SessionLog.Tests.ps1`
   - `.claude/skills/session-init/tests/Repair-SessionLog.Tests.ps1`
   - 80%+ code coverage for all scripts

7. **Integration Test**:
   - End-to-end test that runs orchestrator and validates all 3 phases execute correctly
   - Test with mocked git repository and SESSION-PROTOCOL.md
   - Verify tool call count = 1 (orchestrator invocation)

## Dependencies

- **Ticket 1**: Validation module refactoring (provides checkpoint functions)
- **Ticket 2**: Shared helper modules (provides GitHelpers and TemplateHelpers)

## Implementation Notes

**Hashtable Validation Pattern** (from Tech Plan):

```powershell
# Orchestrator validates Phase 1 output
function Test-Phase1Output {
    param([hashtable]$Output)
    
    # Required fields
    if (-not $Output.ContainsKey('RepoRoot')) { throw "Missing required field: RepoRoot" }
    if (-not $Output.ContainsKey('Branch')) { throw "Missing required field: Branch" }
    if (-not $Output.ContainsKey('Commit')) { throw "Missing required field: Commit" }
    if (-not $Output.ContainsKey('Status')) { throw "Missing required field: Status" }
    
    # Type validation
    if ($Output.Commit -notmatch '^[a-f0-9]{7,12}$') { throw "Invalid Commit SHA format" }
    if ($Output.Status -notin @('clean', 'dirty')) { throw "Invalid Status value" }
    
    # Optional fields (set defaults if missing)
    if (-not $Output.ContainsKey('SerenaInitialized')) { $Output.SerenaInitialized = $false }
    if (-not $Output.ContainsKey('HandoffRead')) { $Output.HandoffRead = $false }
}
```

**Auto-Fix Retry Policy** (from Tech Plan):
- Maximum 2 retries per checkpoint
- Apply fixes iteratively (one at a time)
- Track attempted fixes to prevent duplicates
- Abort after 2 failed attempts with error listing unfixed issues
