# Analysis: Check-SkillExists.ps1 Automation Tool

**Date**: 2025-12-18
**Analyst**: analyst agent
**Type**: Ideation research (shower thought)
**Priority**: P0 (Addresses critical skill usage violations)

---

## Value Statement

This tool addresses a critical pattern of agent behavior: repeatedly implementing GitHub operations inline instead of using tested, maintained skills. Session 15 documented 3+ skill usage violations within 10 minutes, requiring multiple user interventions. This tool enables automated skill discovery and verification-based enforcement via session protocol gates.

## Business Objectives

1. **Reduce rework overhead**: Eliminate time wasted writing inline code that duplicates existing skills (estimated 30-45 min per violation)
2. **Enforce DRY principle**: Prevent skill duplication across workflows and agent implementations
3. **Enable verification-based compliance**: Shift from trust-based ("agent promises to check") to verification-based ("tool output proves check occurred")
4. **Unblock agent productivity**: Allow agents to confidently check for capabilities without manual SKILL.md reading

---

## Context

### Problem Evidence

**Session 15 Timeline** (from `.agents/retrospective/2025-12-18-session-15-retrospective.md`):

- T+5: Agent used raw `gh pr view` command (skill exists but unused)
- T+10: User feedback: "Use the GitHub skill!"
- T+15: Agent continued using raw `gh` commands despite correction
- T+20: Agent created bash scripts duplicating skill functionality
- T+50: Skill duplication identified in `AIReviewCommon.psm1`
- **Total violations**: 5+ requiring user intervention

**Root Cause** (Five Whys Analysis from Session 15):

```text
Q1: Why did the agent use raw gh commands?
A1: Agent defaulted to writing inline code without checking for existing skills.

Q2: Why didn't the agent check for existing skills?
A2: Agent didn't have "check for skills first" in execution workflow.

Q3: Why isn't "check for skills first" in execution workflow?
A3: Memory skill-usage-mandatory exists but agent didn't read it before implementing.

Q4: Why didn't the agent read skill-usage-mandatory memory?
A4: No BLOCKING gate requiring memory read before GitHub operations.

Q5: Why is there no BLOCKING gate for skill checks?
A5: Session protocol has BLOCKING gates for Serena initialization, but not for skill usage validation.
```

**Root Cause**: Missing BLOCKING gate in session protocol for skill validation before GitHub operations.

### Current Skill Ecosystem

**Formal Skills** (with SKILL.md):

1. `.claude/skills/github/` - Complete GitHub CLI operations (11 scripts)
   - PR operations: Get-PRContext, Get-PRReviewComments, Get-PRReviewers, Post-PRCommentReply
   - Issue operations: Get-IssueContext, Post-IssueComment, Set-IssueLabels, Set-IssueMilestone
   - Reactions: Add-CommentReaction
2. `.claude/skills/steering-matcher/` - Steering file pattern matching (1 script)
   - Get-ApplicableSteering

**Utilities** (`.agents/utilities/`, no SKILL.md):

1. `fix-markdown-fences/` - Repair malformed markdown fences
2. `metrics/` - Agent usage metrics collection
3. `security-detection/` - Infrastructure file detection

**Total**: 2 formal skills (12 scripts), 3 utilities (6 scripts)

### Existing Documentation

**Memory**: `.serena/memories/skill-usage-mandatory.md`

- Documents requirement to use skills instead of raw commands
- Provides examples of WRONG (raw gh) vs CORRECT (skill scripts)
- Lists skill directory structure
- **Problem**: Trust-based; agents don't read it proactively

**Session Protocol**: `.agents/SESSION-PROTOCOL.md`

- Phase 1: Serena initialization (BLOCKING gate with tool output verification)
- Phase 2: Context retrieval (BLOCKING gate)
- Phase 3: Session log creation (REQUIRED)
- **Gap**: No Phase 1.5 for skill validation

---

## Methodology

### Research Approach

1. **Problem Analysis**: Reviewed Session 15 retrospective for violation patterns
2. **Skill Inventory**: Enumerated all existing skills and their capabilities
3. **Pattern Study**: Analyzed steering-matcher skill for design patterns
4. **Tool Research**: Web search for metadata discovery patterns and agent frameworks
5. **Integration Analysis**: Evaluated session protocol gates and verification mechanisms
6. **Design Exploration**: Prototyped interface options and implementation approaches

### Sources Consulted

- `.agents/retrospective/2025-12-18-session-15-retrospective.md` (Session 15 analysis)
- `.serena/memories/skill-usage-mandatory.md` (Current requirements)
- `.agents/SESSION-PROTOCOL.md` (Protocol gates)
- `.claude/skills/github/SKILL.md` (GitHub skill documentation)
- `.claude/skills/steering-matcher/Get-ApplicableSteering.ps1` (Pattern matching reference)
- Microsoft PowerShell documentation (Get-PSScriptFileInfo)
- AI agent framework research (LangChain, CrewAI, A2A protocol)

---

## Findings

### Fact 1: Current Skills Are Well-Structured (Verified)

**Evidence**:

- GitHub skill: 11 scripts organized by operation type (pr/, issue/, reactions/)
- Shared module: GitHubHelpers.psm1 with DRY utilities
- Comprehensive SKILL.md with examples and exit codes
- Pester tests for validation

**Implication**: Tool can leverage predictable directory structure for discovery.

### Fact 2: Skill Discovery Is Currently Manual (Verified)

**Evidence**:

- Agents must read SKILL.md to discover capabilities
- No programmatic way to check "does skill exist for operation X?"
- Session 15 agent didn't read SKILL.md before implementing

**Implication**: Automated discovery tool fills critical gap.

### Fact 3: Steering-Matcher Provides Design Pattern (Verified)

**Evidence** (from `Get-ApplicableSteering.ps1`):

- Parses YAML front matter from markdown files
- Uses glob pattern matching with regex conversion
- Returns structured output (Name, Path, ApplyTo, Priority)
- Handles edge cases (no files, no matches, missing front matter)

**Implication**: Similar approach viable for skill discovery (parse SYNOPSIS, match operation types).

### Fact 4: Session Protocol Uses Verification-Based Gates (Verified)

**Evidence** (from `.agents/SESSION-PROTOCOL.md`):

- Phase 1 (Serena init): MUST call `mcp__serena__activate_project` + `mcp__serena__initial_instructions`
- Verification: Tool output exists in session transcript
- Blocking: Agent MUST NOT proceed until calls succeed

**Implication**: Check-SkillExists.ps1 can integrate as Phase 1.5 with same verification pattern.

### Fact 5: PowerShell Supports Script Metadata (Verified)

**Evidence**:

- Comment-based help: .SYNOPSIS, .DESCRIPTION, .PARAMETER, .EXAMPLE
- Get-PSScriptFileInfo cmdlet (PowerShell 7+)
- All GitHub skill scripts have consistent comment headers

**Implication**: Tool can parse script metadata for capability matching.

### Hypothesis 1: Keyword Matching Can Identify Operations (Unverified)

**Hypothesis**: Matching operation keywords (e.g., "PR comment", "issue label") against script SYNOPSIS can identify relevant skills.

**Needs Validation**:

- Test matching accuracy across all 12 GitHub skill scripts
- Determine if SYNOPSIS alone sufficient or need .DESCRIPTION
- Assess false positive/negative rates

### Hypothesis 2: Agents Will Use Tool If Required by Protocol (Unverified)

**Hypothesis**: Adding Check-SkillExists.ps1 as Phase 1.5 BLOCKING gate will reduce violations to near-zero.

**Needs Validation**:

- Pilot integration in 3-5 sessions
- Measure violation rate before/after
- Assess agent compliance with verification requirement

### Hypothesis 3: Self-Documenting Approach Reduces Maintenance (Unverified)

**Hypothesis**: Parsing script headers instead of manual registry eliminates maintenance when adding new skills.

**Needs Validation**:

- Confirm all skills have parseable headers
- Test robustness to header variations
- Compare maintenance vs manual skill.json registry

---

## Recommendations

### Proposed Interface Design

#### Option A: Simple Boolean Check (Recommended)

**Interface**:

```powershell
<#
.SYNOPSIS
    Checks if a skill exists for a GitHub operation.

.PARAMETER Operation
    GitHub operation type: "pr", "issue", "reaction", "repo"

.PARAMETER Action
    Action name: "comment", "label", "milestone", "context", etc.

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "pr" -Action "comment"
    # Returns: $true (Post-PRCommentReply.ps1 exists)

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "issue" -Action "close"
    # Returns: $false (no Close-Issue.ps1 script)

.OUTPUTS
    Boolean indicating skill existence
#>
```

**Pros**:

- Simple interface (2 parameters)
- Fast execution (file system check only)
- Easy integration into session protocol
- Clear yes/no answer

**Cons**:

- Requires agent to know operation taxonomy (pr vs issue)
- Doesn't provide usage instructions if skill exists
- No fuzzy matching for similar operations

**Implementation Complexity**: Low (50-75 lines)

#### Option B: Keyword Search with Recommendations (Advanced)

**Interface**:

```powershell
<#
.SYNOPSIS
    Searches for skills matching operation keywords.

.PARAMETER Keywords
    Keywords describing the operation (e.g., "post PR comment", "add issue label")

.PARAMETER Threshold
    Minimum match confidence (0-100). Default: 70

.EXAMPLE
    .\Check-SkillExists.ps1 -Keywords "post PR comment"
    # Returns:
    # [PSCustomObject]@{
    #     Exists = $true
    #     Confidence = 95
    #     ScriptPath = ".claude/skills/github/scripts/pr/Post-PRCommentReply.ps1"
    #     Synopsis = "Posts comments to PR review threads or top-level"
    #     Example = "Post-PRCommentReply.ps1 -PullRequest 50 -Body 'Fixed in abc1234.'"
    # }

.OUTPUTS
    PSCustomObject with match details or $null if no match
#>
```

**Pros**:

- Natural language queries (agent describes intent)
- Returns usage instructions if match found
- Fuzzy matching reduces false negatives
- Suggests similar skills if exact match missing

**Cons**:

- More complex implementation (150-200 lines)
- Slower execution (must parse all scripts)
- Confidence threshold requires tuning
- Potential false positives

**Implementation Complexity**: Medium (150-200 lines)

#### Option C: Hybrid (Simple + Fallback Search)

**Interface**:

```powershell
<#
.SYNOPSIS
    Checks for skill existence with optional keyword fallback.

.PARAMETER Operation
    GitHub operation type (exact match). Optional if Keywords provided.

.PARAMETER Action
    Action name (exact match). Optional if Keywords provided.

.PARAMETER Keywords
    Fallback: Keywords for fuzzy search if exact match fails.

.EXAMPLE
    # Exact match
    .\Check-SkillExists.ps1 -Operation "pr" -Action "comment"

.EXAMPLE
    # Fuzzy search
    .\Check-SkillExists.ps1 -Keywords "react to review comment"

.OUTPUTS
    PSCustomObject with Exists, ScriptPath, Synopsis (if match)
#>
```

**Pros**:

- Fast path for agents who know taxonomy (exact match)
- Fallback for exploratory queries (fuzzy match)
- Balances simplicity and flexibility

**Cons**:

- Most complex interface (3 parameters, conditional logic)
- Requires maintaining operation taxonomy mapping
- Two code paths to test and maintain

**Implementation Complexity**: High (200-250 lines)

### Recommendation: Option A (Simple Boolean) for MVP

**Rationale**:

1. **Addresses P0 need**: Blocks agent from using raw gh commands when skill exists
2. **Fast integration**: Simple interface fits cleanly into Phase 1.5 gate
3. **Low maintenance**: No keyword parsing, confidence tuning, or taxonomy updates
4. **Verifiable output**: Boolean return enables clear protocol verification
5. **Incremental enhancement**: Can evolve to Option C later if needed

**Evolution Path**:

- v1.0: Simple boolean (Option A)
- v1.1: Add -ListAll parameter to enumerate available skills
- v2.0: Add keyword search fallback (Option C)

### Implementation Approach (Option A)

```powershell
<#
.SYNOPSIS
    Checks if a skill exists for a GitHub operation.

.DESCRIPTION
    Verifies skill script existence in .claude/skills/github/scripts/ directory structure.
    Uses predictable naming convention: {Operation}/{Verb}-{Entity}{Action}.ps1

.PARAMETER Operation
    GitHub operation type: "pr", "issue", "reaction"

.PARAMETER Action
    Action verb + noun: "PRContext", "IssueContext", "IssueComment", "PRCommentReply", "CommentReaction", "IssueLabels", "IssueMilestone"

.PARAMETER ListAvailable
    If specified, lists all available skills without checking for specific operation

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "pr" -Action "PRContext"
    True

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "issue" -Action "IssueClose"
    False

.EXAMPLE
    .\Check-SkillExists.ps1 -ListAvailable
    # Lists all available skills

.OUTPUTS
    Boolean or Array (if -ListAvailable)

.NOTES
    Exit Codes: 0=Exists, 1=Not found, 2=Invalid parameters
#>

[CmdletBinding(DefaultParameterSetName = 'Check')]
param(
    [Parameter(ParameterSetName = 'Check', Mandatory)]
    [ValidateSet("pr", "issue", "reaction")]
    [string]$Operation,

    [Parameter(ParameterSetName = 'Check', Mandatory)]
    [string]$Action,

    [Parameter(ParameterSetName = 'List')]
    [switch]$ListAvailable
)

$SkillRoot = Join-Path $PSScriptRoot ".." ".." ".." ".claude" "skills" "github" "scripts"

if ($ListAvailable) {
    # List all available skills
    Get-ChildItem -Path $SkillRoot -Recurse -Filter "*.ps1" |
        Where-Object { $_.Name -notmatch "\.Tests\.ps1$" } |
        ForEach-Object {
            $relativePath = $_.FullName -replace [regex]::Escape((Resolve-Path $SkillRoot).Path), ""
            [PSCustomObject]@{
                Operation = Split-Path (Split-Path $_.FullName) -Leaf
                Script = $_.Name
                Path = $_.FullName
            }
        }
    exit 0
}

# Check for specific skill
# Naming convention: Get-PRContext, Post-IssueComment, Add-CommentReaction
$verb = switch ($Action) {
    { $_ -match "^(Get|Post|Set|Add|Remove)" } { $matches[1]; break }
    default {
        Write-Error "Action must start with verb (Get, Post, Set, Add, Remove): $Action"
        exit 2
    }
}

$scriptName = "$verb-$Action.ps1"
$scriptPath = Join-Path $SkillRoot $Operation $scriptName

if (Test-Path $scriptPath) {
    Write-Output $true
    exit 0
} else {
    Write-Output $false
    exit 1
}
```

**Testing Strategy**:

```powershell
# Pester tests in Check-SkillExists.Tests.ps1
Describe "Check-SkillExists" {
    Context "Known skills" {
        It "Returns true for Get-PRContext" {
            .\Check-SkillExists.ps1 -Operation "pr" -Action "PRContext" | Should -Be $true
        }

        It "Returns true for Post-IssueComment" {
            .\Check-SkillExists.ps1 -Operation "issue" -Action "IssueComment" | Should -Be $true
        }

        It "Returns true for Add-CommentReaction" {
            .\Check-SkillExists.ps1 -Operation "reaction" -Action "CommentReaction" | Should -Be $true
        }
    }

    Context "Unknown skills" {
        It "Returns false for Close-Issue" {
            .\Check-SkillExists.ps1 -Operation "issue" -Action "IssueClose" | Should -Be $false
        }

        It "Returns false for invalid operation" {
            { .\Check-SkillExists.ps1 -Operation "repo" -Action "Archive" } | Should -Throw
        }
    }

    Context "List available" {
        It "Lists all skills without errors" {
            $skills = .\Check-SkillExists.ps1 -ListAvailable
            $skills.Count | Should -BeGreaterThan 10
        }

        It "Excludes test files" {
            $skills = .\Check-SkillExists.ps1 -ListAvailable
            $skills.Script | Should -Not -Contain "GitHubHelpers.Tests.ps1"
        }
    }
}
```

---

## Integration Points

### Option 1: Session Protocol Phase 1.5 Gate (Recommended)

**Location**: `.agents/SESSION-PROTOCOL.md`

**Change**:

```markdown
### Phase 1.5: Skill Validation (BLOCKING) [NEW]

The agent MUST verify skill availability before GitHub operations. This is a **blocking gate**.

**Requirements:**

1. The agent MUST run Check-SkillExists.ps1 before ANY GitHub operation
2. The agent MUST use existing skill if Check-SkillExists.ps1 returns true
3. The agent MUST NOT write inline gh commands when skill exists
4. The agent MAY extend skill if Check-SkillExists.ps1 returns false (after documenting need)

**Verification:**

- Tool output appears in session transcript
- Agent references Check-SkillExists.ps1 result before GitHub operations
- No raw gh commands when skill exists

**Usage Pattern:**

```powershell
# Before any GitHub PR operation
$skillExists = & .claude/skills/github/Check-SkillExists.ps1 -Operation "pr" -Action "PRContext"
if ($skillExists) {
    # Use skill
    & .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 50
} else {
    # Document missing capability and extend skill
    Write-Host "No skill for operation. Need to extend .claude/skills/github/"
}
```

**Rationale:** Agents who check for skills will use skills. Verification-based gate prevents trust-based compliance failures.
```

**Pros**:

- Enforces skill usage at protocol level
- Verification-based (tool output proves compliance)
- Aligns with existing Phase 1/Phase 2 gate pattern
- Blocks work until check performed

**Cons**:

- Adds friction to GitHub operations (extra tool call)
- Requires agent to know they're about to do GitHub operation
- May be bypassed if agent doesn't recognize operation as "GitHub"

**Implementation Effort**: Medium (protocol doc update + agent instruction updates)

### Option 2: Orchestrator Pre-Flight Check (Alternative)

**Location**: `src/claude/orchestrator.md`

**Change**:

```markdown
### Routing Decision Process

**Step 3.5: Skill Validation (NEW)**

Before delegating GitHub operations, orchestrator MUST:

1. Identify if task involves GitHub operations (PR, issue, comment, label, milestone)
2. Run Check-SkillExists.ps1 to verify skill availability
3. Inject skill guidance into agent prompt:
   - If skill exists: "MUST use .claude/skills/github/scripts/{operation}/{script}"
   - If skill missing: "Extend .claude/skills/github/ with new script, don't write inline"

**Example:**

Task: "Post comment to PR #50"
Skill Check: Check-SkillExists.ps1 -Operation "pr" -Action "PRCommentReply" → True
Agent Prompt: "Use .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 for this task. Do not use raw gh commands."
```

**Pros**:

- Centralized enforcement (orchestrator only)
- No friction for non-GitHub operations
- Agents receive explicit guidance in prompt
- Works for delegated tasks

**Cons**:

- Doesn't help agents working directly (no orchestrator)
- Orchestrator must recognize all GitHub operation types
- Less verification-based (relies on prompt injection)

**Implementation Effort**: Low (orchestrator prompt update)

### Option 3: Pre-Commit Hook (Defensive)

**Location**: `.githooks/pre-commit`

**Change**:

```bash
# Check for raw gh commands in staged files
if git diff --cached --name-only | xargs grep -l "^\s*gh\s\+(pr|issue|api)" 2>/dev/null; then
    echo "⚠️  WARNING: Raw gh commands detected in staged files."
    echo "    Check if .claude/skills/github/ has capability for this operation:"
    pwsh .claude/skills/github/Check-SkillExists.ps1 -ListAvailable
    echo ""
    echo "    To bypass this check, commit with --no-verify"
    exit 1
fi
```

**Pros**:

- Catches violations before commit
- No agent cooperation required (technical control)
- Provides immediate feedback with skill list
- Works for all agents and humans

**Cons**:

- Late detection (code already written)
- Can be bypassed with --no-verify
- False positives (legitimate gh usage in documentation)
- Doesn't prevent inline code, just blocks commit

**Implementation Effort**: Low (add check to existing pre-commit hook)

### Recommended Integration Strategy

**Implement all three options in sequence:**

1. **Phase 1**: Pre-commit hook (defensive backstop)
   - Quick win, immediate protection
   - Week 1 implementation
2. **Phase 2**: Orchestrator pre-flight (centralized guidance)
   - Medium effort, high impact for delegated tasks
   - Week 2 implementation
3. **Phase 3**: Session protocol Phase 1.5 gate (comprehensive)
   - High effort, complete enforcement
   - Week 3-4 implementation after pilot validation

**Rationale**: Defense in depth. Hook prevents bad commits, orchestrator guides tasks, protocol ensures compliance.

---

## Open Questions

### Question 1: PowerShell vs Serena Memory?

**Question**: Should this be a PowerShell script or a Serena memory query?

**Analysis**:

| Approach | Pros | Cons |
|----------|------|------|
| **PowerShell script** | - Direct file system access (fast) <br> - Verifiable tool output <br> - Can be used outside Claude (pre-commit) <br> - Testable with Pester | - Requires pwsh in PATH <br> - Not cross-platform (requires PowerShell 7+) |
| **Serena memory** | - Already available to agents <br> - No external dependencies <br> - Cross-session persistence | - No verification mechanism <br> - Can't be used in pre-commit hooks <br> - Memory queries can't execute file system checks |

**Recommendation**: PowerShell script for v1.0

**Rationale**:

1. Verification requirement: Session protocol needs tool output (PowerShell provides, memory doesn't)
2. Pre-commit integration: Hook can call script (can't call Serena)
3. Testability: Pester tests validate behavior (memory has no test framework)
4. File system check: Script can verify actual file existence (memory is static knowledge)

**Future enhancement**: Store skill inventory in Serena memory as cache, updated by script on skill additions.

### Question 2: Granularity of Matching?

**Question**: How granular should matching be? "post PR comment" vs "GitHub operations"?

**Analysis**:

| Granularity | Example Input | Pros | Cons |
|-------------|---------------|------|------|
| **High (specific operation)** | Operation="pr", Action="PRCommentReply" | - Exact matches only <br> - No false positives <br> - Fast execution | - Requires taxonomy knowledge <br> - Brittle to naming changes |
| **Medium (operation category)** | Category="pr", Action="comment" | - Flexible action names <br> - Maps multiple actions to one skill | - Must maintain action mapping <br> - Potential false positives |
| **Low (keyword search)** | Keywords="post PR comment" | - Natural language queries <br> - No taxonomy required | - Slower execution (parses all scripts) <br> - Confidence tuning required <br> - False positives/negatives |

**Recommendation**: High granularity for v1.0 (Option A interface)

**Rationale**:

1. Simple implementation: Direct file system check (50 lines vs 200+ for keyword search)
2. Clear semantics: Boolean output easy to verify in protocol
3. Low maintenance: No keyword indexes or confidence tuning
4. Fast execution: No script parsing overhead
5. Incremental enhancement: Can add keyword fallback in v2.0

**Mitigation for taxonomy knowledge**: Provide -ListAvailable parameter showing all operations.

### Question 3: What If No Skill Exists?

**Question**: When Check-SkillExists.ps1 returns false, should it suggest creating a skill or allow inline implementation?

**Analysis**:

| Approach | Outcome | Pros | Cons |
|----------|---------|------|------|
| **Suggest skill creation** | Tool outputs: "No skill found. Extend .claude/skills/github/ with new script." | - Reinforces skill-first culture <br> - Maintains DRY principle <br> - Clear guidance | - Adds overhead for one-off operations <br> - May block urgent fixes |
| **Allow inline with justification** | Tool outputs: "No skill found. Document reason if writing inline." | - Flexibility for edge cases <br> - Doesn't block urgent work | - Creates loophole for violations <br> - Weakens skill-first culture |
| **Block until skill created** | Tool exits non-zero if skill missing, agent cannot proceed | - Absolute enforcement <br> - Guaranteed skill coverage | - Too rigid for experimentation <br> - May cause frustration |

**Recommendation**: Suggest skill creation (soft enforcement for v1.0)

**Rationale**:

1. Cultural shift takes time: Hard blocking may cause resistance
2. Edge cases exist: One-off operations may not warrant full skill
3. Measurable behavior: Can track how often agents extend vs inline
4. Incremental tightening: Can move to hard blocking in v2.0 if needed

**Implementation**:

```powershell
if (Test-Path $scriptPath) {
    Write-Output $true
    exit 0
} else {
    Write-Warning "No skill found for operation '$Operation' action '$Action'."
    Write-Warning "Consider extending .claude/skills/github/scripts/$Operation/ with new script."
    Write-Warning "See .claude/skills/github/SKILL.md for guidance."
    Write-Output $false
    exit 1
}
```

### Question 4: Partial Matches?

**Question**: How to handle similar-but-not-exact skills (e.g., "PR comment" when "PR comment reply" exists)?

**Analysis**:

For v1.0 (Option A - exact match): Partial matches not supported. Agent must know exact Action name.

**Mitigation strategies**:

1. **-ListAvailable parameter**: Shows all skills with operations, agent can visually match
   ```powershell
   .\Check-SkillExists.ps1 -ListAvailable | Where-Object { $_.Operation -eq "pr" }
   ```
2. **Clear error messages**: When false returned, suggest -ListAvailable
   ```powershell
   Write-Warning "No exact match. List all PR skills with:"
   Write-Warning "  .\Check-SkillExists.ps1 -ListAvailable | Where-Object { `$_.Operation -eq 'pr' }"
   ```
3. **Future enhancement**: Add -Fuzzy parameter in v2.0 for keyword matching

**Recommendation**: Document naming conventions in SKILL.md

**Example addition to `.claude/skills/github/SKILL.md`**:

```markdown
## Skill Naming Conventions

All skills follow pattern: `{Verb}-{Entity}{Action}.ps1`

| Operation | Entity | Examples |
|-----------|--------|----------|
| pr | PR, PRComment, PRReviewer | Get-PRContext, Post-PRCommentReply, Get-PRReviewers |
| issue | Issue, IssueComment, IssueLabel | Get-IssueContext, Post-IssueComment, Set-IssueLabels |
| reaction | CommentReaction | Add-CommentReaction |

**Verbs**: Get (retrieve), Post (create), Set (modify), Add (append), Remove (delete)
```

### Question 5: Phase 1.5 Integration Concerns?

**Question**: Should Check-SkillExists.ps1 be part of Phase 1.5 session protocol, or only called on-demand before GitHub operations?

**Analysis**:

| Approach | When Called | Pros | Cons |
|----------|-------------|------|------|
| **Phase 1.5 (session start)** | Once at session initialization | - Verifiable (tool output in transcript) <br> - Forces awareness upfront <br> - Aligns with Phase 1/2 pattern | - May be unnecessary if no GitHub ops in session <br> - Agents may forget by time of GitHub op |
| **On-demand (before each op)** | Each time GitHub operation needed | - No overhead if no GitHub ops <br> - Fresh verification at use time <br> - More precise enforcement | - Easy to forget (trust-based) <br> - No session-level verification <br> - Requires discipline per operation |

**Recommendation**: Hybrid approach

**Implementation**:

1. **Phase 1.5**: Run `Check-SkillExists.ps1 -ListAvailable` once at session start
   - Purpose: Agents see available skills upfront
   - Verification: Tool output proves awareness
   - Low overhead: Single call, not per-operation
2. **Per-operation**: Agents check specific skill before GitHub op
   - Purpose: Verify exact capability exists
   - Verification: Tool output in transcript before gh operation
   - Enforcement: Pre-commit hook catches violations

**Rationale**: Session start list builds awareness, per-operation check enforces usage. Defense in depth.

---

## Maintenance Burden Assessment

### Adding New Skills

**Current Process** (without Check-SkillExists.ps1):

1. Create new script in `.claude/skills/github/scripts/{operation}/`
2. Add Pester tests
3. Update SKILL.md documentation
4. Commit changes

**With Check-SkillExists.ps1 (Option A)**:

1. Create new script (same)
2. Add Pester tests (same)
3. Update SKILL.md documentation (same)
4. Commit changes
5. **No tool updates required** (self-documenting via file system)

**Maintenance Delta**: Zero additional steps.

**Rationale**: Option A uses file system as source of truth. Tool discovers skills by enumerating directory structure. No manual registry to update.

### Modifying Skill Names

**Scenario**: Rename Post-PRCommentReply.ps1 to Add-PRComment.ps1

**Impact**:

- Tool automatically reflects change (file system scan)
- SKILL.md documentation must be updated (already required)
- Existing agent code using old name breaks (already problematic)

**Maintenance Delta**: Zero additional steps.

### Adding New Operation Types

**Scenario**: Add "repo" operation type (e.g., Get-RepoInfo.ps1)

**With Option A**:

1. Create `.claude/skills/github/scripts/repo/` directory
2. Add Get-RepoInfo.ps1 script
3. Update ValidateSet in Check-SkillExists.ps1:
   ```powershell
   [ValidateSet("pr", "issue", "reaction", "repo")]  # Add "repo"
   ```
4. Update SKILL.md

**Maintenance Delta**: 1 line change to ValidateSet (minimal).

**Alternative**: Remove ValidateSet, accept any operation type. Tool returns false if directory doesn't exist.

**Recommendation**: Keep ValidateSet for typo prevention in v1.0, remove in v2.0 if adds friction.

### Version Management

**Question**: How to handle breaking changes to skill interfaces?

**Analysis**:

- Check-SkillExists.ps1 only verifies **existence**, not **interface compatibility**
- Interface changes (parameter renames, new required params) not detected by tool
- Agents may call skill with outdated syntax

**Mitigation**:

1. **Semantic versioning**: Tag skills with versions in SKILL.md
2. **Deprecation warnings**: Old skill scripts output warnings before removal
3. **Integration tests**: Pester tests catch interface changes
4. **Future enhancement**: Parse .PARAMETER blocks to show required params

**For v1.0**: Existence check only. Interface compatibility out of scope.

### Scalability Concerns

**Projected Growth**:

- Current: 12 scripts (2 formal skills)
- 6 months: ~25 scripts (add repo, security, workflow operations)
- 12 months: ~40 scripts (add milestone, project, discussion operations)

**Performance Impact (Option A)**:

- File system check: O(1) for specific operation
- List all skills: O(n) where n = number of scripts
- At 40 scripts: Negligible (<100ms on modern SSD)

**No scalability concerns for file system approach up to 100+ scripts.**

---

## Trade-offs and Risks

### Trade-off 1: Simplicity vs Flexibility

**Option A (Simple)**: Requires taxonomy knowledge (operation + action)
**Option C (Hybrid)**: Supports natural language queries but more complex

**Decision**: Option A for v1.0, evolve to C if agents struggle with taxonomy

**Risk Mitigation**: Provide -ListAvailable to reduce taxonomy barrier

### Trade-off 2: Enforcement Rigor

**Soft (suggest skill creation)**: Agents can still write inline if justified
**Hard (block until skill exists)**: Absolute enforcement but may frustrate

**Decision**: Soft enforcement for v1.0, monitor violation rates, tighten if needed

**Risk Mitigation**: Pre-commit hook provides hard stop at commit time

### Trade-off 3: Protocol Overhead

**Phase 1.5 gate**: Adds friction to every session
**On-demand**: Only called when needed but less verifiable

**Decision**: Hybrid (list at start, check per-op)

**Risk Mitigation**: Single -ListAvailable call is fast (<100ms), low overhead

### Risk 1: Agents Bypass Tool

**Scenario**: Agent writes inline gh command without calling Check-SkillExists.ps1

**Likelihood**: Medium (trust-based compliance always has gaps)

**Impact**: High (defeats purpose of tool)

**Mitigation**:

1. Pre-commit hook catches bypasses before commit (technical control)
2. Session protocol verification checks transcript for tool output
3. Retrospective analysis tracks bypass frequency

### Risk 2: Tool Returns False Negative

**Scenario**: Skill exists but tool returns false due to naming mismatch

**Likelihood**: Low (exact file system check)

**Impact**: Medium (agent writes duplicate code unnecessarily)

**Mitigation**:

1. Pester tests validate all known skills return true
2. -ListAvailable shows actual file names for manual verification
3. Session 15-style retrospective would catch pattern of false negatives

### Risk 3: Taxonomy Confusion

**Scenario**: Agent doesn't know whether operation is "pr" or "issue" (e.g., PR comments vs issue comments)

**Likelihood**: Medium (terminology varies across GitHub API)

**Impact**: Low (agent tries both, or uses -ListAvailable)

**Mitigation**:

1. SKILL.md documents terminology clearly
2. -ListAvailable parameter shows all operations
3. Error messages suggest -ListAvailable on failures

---

## Success Criteria

### Quantitative Metrics

| Metric | Current (Session 15) | Target (3 months) | Measurement |
|--------|---------------------|-------------------|-------------|
| **Skill usage violations per session** | 3-5 | <1 | Count raw `gh` commands in sessions where Check-SkillExists.ps1 used |
| **User interventions for skill violations** | 5+ | 0-1 | Count "use the skill" feedback instances |
| **Skill extension rate** | 0% | 25% | % of "skill not found" cases that result in new skill scripts |
| **Tool adoption rate** | 0% | 90% | % of GitHub operations preceded by Check-SkillExists.ps1 call |

### Qualitative Success

- Agents demonstrate "check first, implement second" behavior
- Retrospectives report reduced rework from inline implementations
- Skills directory grows organically as agents extend capabilities
- User feedback shifts from "use the skill!" to "good job checking"

### Failure Signals

- Agents continue writing inline gh commands despite tool availability
- Check-SkillExists.ps1 called but results ignored (theater compliance)
- Tool adds friction without reducing violations (low ROI)
- Agents find workarounds to bypass protocol gates

---

## Recommended Action Sequence

### Week 1: MVP Implementation

1. Create Check-SkillExists.ps1 (Option A interface)
2. Write Pester tests for all 12 existing GitHub skills
3. Add pre-commit hook check for raw gh commands
4. Document tool in `.claude/skills/github/SKILL.md`

**Deliverable**: Working tool with tests, defensive pre-commit hook

### Week 2: Integration & Pilot

1. Update SESSION-PROTOCOL.md with Phase 1.5 gate
2. Update orchestrator.md with pre-flight skill check
3. Update skill-usage-mandatory.md with Check-SkillExists.ps1 usage
4. Pilot with 3-5 agent sessions, measure violation rates

**Deliverable**: Protocol integration complete, baseline metrics collected

### Week 3: Refinement

1. Analyze pilot results (violation rates, agent feedback)
2. Refine error messages based on observed confusion points
3. Add -ListAvailable examples to SKILL.md
4. Document taxonomy in SKILL.md (entity naming conventions)

**Deliverable**: Polished tool with clear documentation

### Week 4: Rollout & Monitoring

1. Announce tool availability to all agents (HANDOFF.md update)
2. Add Check-SkillExists.ps1 to Phase 1.5 checklist template
3. Set up violation tracking in retrospective template
4. Monitor adoption rate for 2 weeks

**Deliverable**: Tool in production use across all sessions

### Month 2-3: Enhancement (Optional)

1. Evaluate need for keyword search fallback (Option C)
2. Consider Serena memory cache for faster lookups
3. Assess demand for interface compatibility checking
4. Gather agent feedback for v2.0 features

**Deliverable**: Roadmap for v2.0 enhancements

---

## Data Transparency

### Sources Consulted

**Verified (High Confidence)**:

- `.agents/retrospective/2025-12-18-session-15-retrospective.md` - Session 15 violation evidence
- `.serena/memories/skill-usage-mandatory.md` - Current skill usage requirements
- `.agents/SESSION-PROTOCOL.md` - Protocol gate patterns
- `.claude/skills/github/SKILL.md` - GitHub skill documentation
- `.claude/skills/github/scripts/**/*.ps1` - Actual skill scripts (enumerated)
- `.claude/skills/steering-matcher/Get-ApplicableSteering.ps1` - Pattern matching reference

**Research (Medium Confidence)**:

- [Microsoft Learn: Get-PSScriptFileInfo](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.psresourceget/get-psscriptfileinfo?view=powershellget-3.x) - PowerShell script metadata
- [LangChain, CrewAI AI Agent Frameworks](https://genfuseai.com/blog/best-ai-agent-frameworks) - Agent skill discovery patterns

**Not Found / Could Not Verify**:

- Industry benchmarks for agent skill usage violation rates (no public data)
- Other projects using similar skill existence checks (searched, none found in AI agent domain)
- Comparative analysis of PowerShell vs memory-based skill discovery (no existing research)

---

## Appendix A: Prototype Script

**File**: `.claude/skills/github/Check-SkillExists.ps1`

```powershell
<#
.SYNOPSIS
    Checks if a skill exists for a GitHub operation.

.DESCRIPTION
    Verifies skill script existence in .claude/skills/github/scripts/ directory structure.
    Uses predictable naming convention: {Operation}/{Verb}-{Entity}{Action}.ps1

.PARAMETER Operation
    GitHub operation type: "pr", "issue", "reaction"

.PARAMETER Action
    Action name matching script convention (e.g., "PRContext", "IssueComment", "CommentReaction")

.PARAMETER ListAvailable
    If specified, lists all available skills without checking for specific operation

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "pr" -Action "PRContext"
    True

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "issue" -Action "IssueComment"
    True

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "issue" -Action "IssueClose"
    False

.EXAMPLE
    .\Check-SkillExists.ps1 -ListAvailable | Where-Object { $_.Operation -eq "pr" }

.OUTPUTS
    [bool] or [PSCustomObject[]] (if -ListAvailable)

.NOTES
    Exit Codes: 0=Exists, 1=Not found, 2=Invalid parameters
    Version: 1.0
    Author: analyst agent
    Date: 2025-12-18
#>

[CmdletBinding(DefaultParameterSetName = 'Check')]
param(
    [Parameter(ParameterSetName = 'Check', Mandatory = $true)]
    [ValidateSet("pr", "issue", "reaction")]
    [string]$Operation,

    [Parameter(ParameterSetName = 'Check', Mandatory = $true)]
    [string]$Action,

    [Parameter(ParameterSetName = 'List')]
    [switch]$ListAvailable
)

$ErrorActionPreference = "Stop"

# Resolve path to .claude/skills/github/scripts relative to this script
$ScriptRoot = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptRoot)) {
    $ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$SkillRoot = Join-Path $ScriptRoot "scripts"

if (-not (Test-Path $SkillRoot)) {
    Write-Error "Skill directory not found: $SkillRoot"
    exit 2
}

if ($ListAvailable) {
    # List all available skills
    $skills = Get-ChildItem -Path $SkillRoot -Recurse -Filter "*.ps1" |
        Where-Object { $_.Name -notmatch "\.Tests\.ps1$" } |
        ForEach-Object {
            $operation = Split-Path (Split-Path $_.FullName) -Leaf
            [PSCustomObject]@{
                Operation = $operation
                Script = $_.Name
                Path = $_.FullName
            }
        } |
        Sort-Object Operation, Script

    $skills | Format-Table -AutoSize
    return $skills
}

# Check for specific skill
# Extract verb from Action if present (e.g., "Get" from "GetPRContext")
$verb = switch -Regex ($Action) {
    '^(Get|Post|Set|Add|Remove)' { $matches[1]; break }
    default {
        Write-Warning "Action should start with verb (Get, Post, Set, Add, Remove): $Action"
        Write-Warning "Attempting match without verb assumption..."
        $null
    }
}

# Build expected script name
if ($verb) {
    $scriptName = "$verb-$Action.ps1"
} else {
    # Try matching with common verbs
    $possibleVerbs = @("Get", "Post", "Set", "Add", "Remove")
    $scriptName = $null
    foreach ($v in $possibleVerbs) {
        $candidate = "$v-$Action.ps1"
        $candidatePath = Join-Path $SkillRoot $Operation $candidate
        if (Test-Path $candidatePath) {
            $scriptName = $candidate
            break
        }
    }

    if (-not $scriptName) {
        Write-Warning "No skill found for operation '$Operation' action '$Action'."
        Write-Warning "Consider extending .claude/skills/github/scripts/$Operation/ with new script."
        Write-Warning ""
        Write-Warning "List all $Operation skills with:"
        Write-Warning "  .\Check-SkillExists.ps1 -ListAvailable | Where-Object { `$_.Operation -eq '$Operation' }"
        Write-Output $false
        exit 1
    }
}

$scriptPath = Join-Path $SkillRoot $Operation $scriptName

if (Test-Path $scriptPath) {
    Write-Verbose "Skill found: $scriptPath"
    Write-Output $true
    exit 0
} else {
    Write-Warning "No skill found for operation '$Operation' action '$Action'."
    Write-Warning "Expected path: $scriptPath"
    Write-Warning ""
    Write-Warning "Consider extending .claude/skills/github/scripts/$Operation/ with new script."
    Write-Warning "See .claude/skills/github/SKILL.md for guidance."
    Write-Warning ""
    Write-Warning "List all $Operation skills with:"
    Write-Warning "  .\Check-SkillExists.ps1 -ListAvailable | Where-Object { `$_.Operation -eq '$Operation' }"
    Write-Output $false
    exit 1
}
```

---

## Appendix B: Pester Tests

**File**: `.claude/skills/github/tests/Check-SkillExists.Tests.ps1`

```powershell
BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." "Check-SkillExists.ps1"

    if (-not (Test-Path $ScriptPath)) {
        throw "Check-SkillExists.ps1 not found at $ScriptPath"
    }
}

Describe "Check-SkillExists" {
    Context "Known PR skills" {
        It "Returns true for Get-PRContext" {
            $result = & $ScriptPath -Operation "pr" -Action "PRContext"
            $result | Should -Be $true
        }

        It "Returns true for Post-PRCommentReply" {
            $result = & $ScriptPath -Operation "pr" -Action "PRCommentReply"
            $result | Should -Be $true
        }

        It "Returns true for Get-PRReviewComments" {
            $result = & $ScriptPath -Operation "pr" -Action "PRReviewComments"
            $result | Should -Be $true
        }

        It "Returns true for Get-PRReviewers" {
            $result = & $ScriptPath -Operation "pr" -Action "PRReviewers"
            $result | Should -Be $true
        }
    }

    Context "Known issue skills" {
        It "Returns true for Get-IssueContext" {
            $result = & $ScriptPath -Operation "issue" -Action "IssueContext"
            $result | Should -Be $true
        }

        It "Returns true for Post-IssueComment" {
            $result = & $ScriptPath -Operation "issue" -Action "IssueComment"
            $result | Should -Be $true
        }

        It "Returns true for Set-IssueLabels" {
            $result = & $ScriptPath -Operation "issue" -Action "IssueLabels"
            $result | Should -Be $true
        }

        It "Returns true for Set-IssueMilestone" {
            $result = & $ScriptPath -Operation "issue" -Action "IssueMilestone"
            $result | Should -Be $true
        }
    }

    Context "Known reaction skills" {
        It "Returns true for Add-CommentReaction" {
            $result = & $ScriptPath -Operation "reaction" -Action "CommentReaction"
            $result | Should -Be $true
        }
    }

    Context "Unknown skills" {
        It "Returns false for non-existent issue close action" {
            $result = & $ScriptPath -Operation "issue" -Action "IssueClose"
            $result | Should -Be $false
        }

        It "Returns false for non-existent PR merge action" {
            $result = & $ScriptPath -Operation "pr" -Action "PRMerge"
            $result | Should -Be $false
        }
    }

    Context "Invalid parameters" {
        It "Throws error for invalid operation type" {
            { & $ScriptPath -Operation "repo" -Action "RepoInfo" } | Should -Throw
        }

        It "Requires operation parameter in Check mode" {
            { & $ScriptPath -Action "PRContext" } | Should -Throw
        }

        It "Requires action parameter in Check mode" {
            { & $ScriptPath -Operation "pr" } | Should -Throw
        }
    }

    Context "List available skills" {
        It "Lists all skills without errors" {
            $skills = & $ScriptPath -ListAvailable
            $skills.Count | Should -BeGreaterThan 10
        }

        It "Excludes test files" {
            $skills = & $ScriptPath -ListAvailable
            $skills.Script | Should -Not -Contain "GitHubHelpers.Tests.ps1"
            $skills.Script | Should -Not -Match "\.Tests\.ps1$"
        }

        It "Includes expected PR skills" {
            $skills = & $ScriptPath -ListAvailable
            $prSkills = $skills | Where-Object { $_.Operation -eq "pr" }
            $prSkills.Script | Should -Contain "Get-PRContext.ps1"
            $prSkills.Script | Should -Contain "Post-PRCommentReply.ps1"
        }

        It "Includes expected issue skills" {
            $skills = & $ScriptPath -ListAvailable
            $issueSkills = $skills | Where-Object { $_.Operation -eq "issue" }
            $issueSkills.Script | Should -Contain "Get-IssueContext.ps1"
            $issueSkills.Script | Should -Contain "Post-IssueComment.ps1"
        }

        It "Returns PSCustomObjects with required properties" {
            $skills = & $ScriptPath -ListAvailable
            $firstSkill = $skills | Select-Object -First 1
            $firstSkill.PSObject.Properties.Name | Should -Contain "Operation"
            $firstSkill.PSObject.Properties.Name | Should -Contain "Script"
            $firstSkill.PSObject.Properties.Name | Should -Contain "Path"
        }
    }
}
```

---

**End of Analysis**
