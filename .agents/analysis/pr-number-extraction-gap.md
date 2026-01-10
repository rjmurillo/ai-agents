# Root Cause Analysis: Agent Prompt for PR Number When Already Provided

**Date**: 2026-01-08  
**Issue**: Agent asked for PR number when user provided "PR 806" and GitHub URL in initial request  
**Classification**: Agent Instruction Gap + Prompt Engineering Gap

## Value Statement

Autonomous execution requires agents to infer context from natural language and URLs, not prompt users for information already present. This analysis identifies why agents fail to extract PR numbers from text/URLs and recommends systematic fixes.

## Business Objectives

- Reduce friction in autonomous PR handling workflows
- Eliminate unnecessary clarification rounds
- Enable true "do not stop until merged" execution patterns
- Maintain alignment with `autonomous-execution-guardrails` memory (STRICTER protocols during autonomy)

## Context

### User's Initial Request

```text
Review PR 806 comments, evaluate items, plan and create fixes. 'runSubagent' as needed.
https://github.com/rjmurillo/ai-agents/pull/806
Do not stop until the PR is merged to main
```

**Provided Context**:

- PR number: "806" (explicit text)
- PR URL: `https://github.com/rjmurillo/ai-agents/pull/806`
- Repository: `rjmurillo/ai-agents` (from URL)
- Instruction mode: Autonomous ("do not stop until merged")

### Agent Behavior

The pr-comment-responder agent prompted for PR number instead of extracting "806" from the initial request.

**Expected Behavior**: Parse PR number from text or URL automatically.

**Actual Behavior**: Asked user to specify PR number.

### Relevant Memories

1. **`autonomous-execution-guardrails`**: States agents should be STRICTER with protocols during autonomous execution, not looser. Prompting for already-provided context violates this principle.

2. **`agent-workflow-scope-discipline`**: States agents should maintain scope and document issues rather than asking for clarification when context is discoverable.

## Methodology

1. Searched codebase for existing PR number extraction patterns
2. Analyzed pr-comment-responder agent definition and skill
3. Examined session logs for similar patterns
4. Reviewed global agent instructions (AGENTS.md)
5. Investigated related skills (github skill, pr-related scripts)

## Findings

### Facts (Verified)

#### 1. Agent Has `argument-hint` But No Extraction Guidance

**File**: [src/claude/pr-comment-responder.md](src/claude/pr-comment-responder.md#L5)

```yaml
argument-hint: Specify the PR number or review comments to address
```

**Problem**: `argument-hint` tells the agent to expect PR number parameter but provides NO guidance on:

- Extracting PR numbers from natural language text ("PR 806", "#806")
- Parsing PR numbers from GitHub URLs (`https://github.com/owner/repo/pull/NNN`)
- Inferring repository from URL context

**Evidence**: Agent definition contains 1,551 lines with detailed workflow phases, but ZERO lines dedicated to context inference or PR number extraction patterns.

#### 2. No Regex Patterns for GitHub URL Parsing

**Search Results**: Grep for `github\.com.*pull.*\d+|PR.*\d+.*extract|parse.*url` returned ZERO matches in agent definitions.

**Existing Patterns Found**:

- `.claude/skills/github/scripts/issue/New-Issue.ps1` (line 84): Contains comment about parsing issue URLs but no reusable regex pattern
- No PR URL parsing utilities in `.claude/skills/github/`

**Gap**: No shared utility for extracting PR/issue numbers from GitHub URLs despite this being a common operation.

#### 3. Global Agent Instructions Lack Context Inference Guidance

**File**: [AGENTS.md](AGENTS.md)

**Search Results**: Searched for "extract.*PR", "parse.*PR", "infer.*context" - no matches.

**Gap**: Global instructions emphasize:

- Using skills instead of raw `gh` commands (present)
- Verifying branch before operations (present)
- Session protocol requirements (present)
- **Context inference from user input**: MISSING

#### 4. Skill Definition Has No Pre-Flight Context Extraction Phase

**File**: [.claude/skills/pr-comment-responder/SKILL.md](.claude/skills/pr-comment-responder/SKILL.md)

**Phases Defined**:

- Phase 0: Memory Initialization (BLOCKING)
- Phase 1: Context Gathering (assumes PR number already provided)
- Phases 2-9: Comment processing workflow

**Missing Phase**: "Phase -1: Context Inference" before memory initialization

**Evidence**: [references/workflow.md](.claude/skills/pr-comment-responder/references/workflow.md#L27) shows Step 1.1 expects `[number]` placeholder:

```powershell
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest [number] -IncludeChangedFiles
```

No preceding step to determine what `[number]` should be from user input.

#### 5. Similar Issues Not Found in Session Logs

**Search**: Searched `.agents/sessions/**/*.md` for patterns like "What is the PR number", "Please provide.*PR", "Which PR"

**Results**: No matches found

**Interpretation**: Either:

- This is a new failure mode (likely given recent autonomous execution push)
- Session logs don't capture agent prompts for clarification (possible filtering)
- Agents have been receiving PR numbers pre-parsed from other sources

### Hypotheses (Unverified)

**Hypothesis 1**: Skill invocation bypasses argument parsing

When user invokes via slash command (`/pr-comment-responder`) vs natural language, the agent may not have access to structured argument extraction.

**Hypothesis 2**: URL recognition requires explicit tool call

Agents may need explicit instruction to use regex or specialized tool for URL parsing rather than assuming they'll do it automatically.

**Hypothesis 3**: Agent expects structured parameters over natural language

The `argument-hint` format may train agents to expect parameters in specific format rather than inferring from natural language.

## Recommendations

### Root Cause Classification

**Category**: Agent Instruction Gap + Prompt Engineering Gap

**Severity**: HIGH (blocks autonomous PR workflows)

**Scope**: System-wide (affects all agents that accept GitHub context as input)

### Recommendation 1: Add Context Inference Phase to PR Comment Responder (P0)

**Location**: [.claude/skills/pr-comment-responder/SKILL.md](.claude/skills/pr-comment-responder/SKILL.md)

**Change**: Add new "Phase -1: Context Inference" before Phase 0

```markdown
## Phase -1: Context Inference (BLOCKING)

Before ANY memory or API operations, extract PR context from user input.

### Step -1.1: Parse PR Number from Text

```bash
# Extract PR number from common patterns
PR_NUMBER=""

# Pattern 1: "PR 806", "PR#806", "#806"
if echo "$USER_INPUT" | grep -qE '(PR\s*#?\s*|#)([0-9]+)'; then
  PR_NUMBER=$(echo "$USER_INPUT" | grep -oE '(PR\s*#?\s*|#)([0-9]+)' | grep -oE '[0-9]+' | head -1)
fi

# Pattern 2: GitHub PR URL
if echo "$USER_INPUT" | grep -qE 'github\.com/[^/]+/[^/]+/pull/([0-9]+)'; then
  PR_NUMBER=$(echo "$USER_INPUT" | grep -oE 'github\.com/[^/]+/[^/]+/pull/([0-9]+)' | grep -oE '[0-9]+$')
fi

if [ -z "$PR_NUMBER" ]; then
  echo "[ERROR] No PR number found in input. Provide PR number or GitHub URL."
  exit 1
fi

echo "[CONTEXT] Extracted PR number: $PR_NUMBER"
```

### Step -1.2: Infer Repository from URL

```bash
# Extract repository from GitHub URL if present
if echo "$USER_INPUT" | grep -qE 'github\.com/([^/]+)/([^/]+)/pull'; then
  REPO_OWNER=$(echo "$USER_INPUT" | sed -n 's|.*github\.com/\([^/]*\)/.*|\1|p')
  REPO_NAME=$(echo "$USER_INPUT" | sed -n 's|.*github\.com/[^/]*/\([^/]*\)/pull.*|\1|p')
  REPO="$REPO_OWNER/$REPO_NAME"
  echo "[CONTEXT] Extracted repository: $REPO"
else
  # Use current repository
  REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
  echo "[CONTEXT] Using current repository: $REPO"
fi
```

**Verification Gate**: PR number extracted OR exit with error (no prompting)
```

### Recommendation 2: Create Shared GitHub Context Extraction Utility (P1)

**Location**: New file `.claude/skills/github/scripts/utils/Extract-GitHubContext.ps1`

**Purpose**: Reusable utility for extracting PR/issue numbers and repository from natural language and URLs

```powershell
<#
.SYNOPSIS
Extracts GitHub context (PR number, issue number, repository) from text or URLs.

.PARAMETER InputText
The user input text containing PR/issue references or GitHub URLs.

.PARAMETER ContextType
Type of context to extract: 'PR', 'Issue', or 'Auto' (default).

.OUTPUTS
PSCustomObject with properties: Type, Number, Repository, URL, RawInput

.EXAMPLE
Extract-GitHubContext -InputText "Review PR 806 comments"
# Returns: @{ Type='PR'; Number=806; Repository=$null; URL=$null }

.EXAMPLE
Extract-GitHubContext -InputText "https://github.com/owner/repo/pull/123"
# Returns: @{ Type='PR'; Number=123; Repository='owner/repo'; URL='...' }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, ValueFromPipeline)]
    [string]$InputText,

    [Parameter()]
    [ValidateSet('PR', 'Issue', 'Auto')]
    [string]$ContextType = 'Auto'
)

# Regex patterns
$patterns = @{
    PRText = 'PR\s*#?\s*(\d+)|#(\d+)'
    IssueText = 'Issue\s*#?\s*(\d+)|#(\d+)'
    PRURL = 'github\.com/([^/]+)/([^/]+)/pull/(\d+)'
    IssueURL = 'github\.com/([^/]+)/([^/]+)/issues/(\d+)'
}

# Try URL patterns first (more specific)
if ($InputText -match $patterns.PRURL) {
    return [PSCustomObject]@{
        Type = 'PR'
        Number = [int]$Matches[3]
        Repository = "$($Matches[1])/$($Matches[2])"
        URL = $Matches[0]
        RawInput = $InputText
    }
}

if ($InputText -match $patterns.IssueURL) {
    return [PSCustomObject]@{
        Type = 'Issue'
        Number = [int]$Matches[3]
        Repository = "$($Matches[1])/$($Matches[2])"
        URL = $Matches[0]
        RawInput = $InputText
    }
}

# Try text patterns
if ($ContextType -in @('PR', 'Auto') -and $InputText -match $patterns.PRText) {
    $number = if ($Matches[1]) { [int]$Matches[1] } else { [int]$Matches[2] }
    return [PSCustomObject]@{
        Type = 'PR'
        Number = $number
        Repository = $null
        URL = $null
        RawInput = $InputText
    }
}

if ($ContextType -in @('Issue', 'Auto') -and $InputText -match $patterns.IssueText) {
    $number = if ($Matches[1]) { [int]$Matches[1] } else { [int]$Matches[2] }
    return [PSCustomObject]@{
        Type = 'Issue'
        Number = $number
        Repository = $null
        URL = $null
        RawInput = $InputText
    }
}

# No context found
Write-Error "No GitHub context found in input: $InputText"
return $null
```

**Tests**: Create `tests/Extract-GitHubContext.Tests.ps1` with test cases:

- "PR 806" → Number=806
- "PR#806" → Number=806
- "#806" → Number=806
- "https://github.com/owner/repo/pull/123" → Number=123, Repository="owner/repo"
- "Review PR 806 and fix issues" → Number=806
- Invalid input → Error

### Recommendation 3: Add Context Inference to Global Agent Instructions (P1)

**Location**: [AGENTS.md](AGENTS.md)

**Section**: Add new section after "Commands (Essential Tools)"

```markdown
## Context Inference Requirements

Agents MUST extract context from user input before requesting clarification.

### GitHub Context Patterns

When user mentions PRs or issues:

| Pattern | Example | Action |
|---------|---------|--------|
| PR text | "PR 806", "PR#806", "#806" | Extract number with regex `PR\s*#?\s*(\d+)` |
| PR URL | `github.com/owner/repo/pull/123` | Extract number AND repository |
| Issue text | "Issue 42", "#42" | Extract number with regex `Issue\s*#?\s*(\d+)` |
| Issue URL | `github.com/owner/repo/issues/42` | Extract number AND repository |

### Inference Before Clarification Rule

**MUST**: Attempt context extraction BEFORE asking user for clarification.

**MUST NOT**: Prompt for information already present in user input (text or URLs).

**Pattern**:

```python
# 1. Try extraction
context = extract_github_context(user_input)

# 2. If extraction fails, THEN prompt
if not context:
    ask_user("Please provide PR number or GitHub URL")

# 3. Proceed with extracted context
use_context(context.number, context.repository)
```

### Utility Integration

Use [Extract-GitHubContext.ps1](.claude/skills/github/scripts/utils/Extract-GitHubContext.ps1) for standardized extraction:

```powershell
$context = pwsh .claude/skills/github/scripts/utils/Extract-GitHubContext.ps1 -InputText "$USER_INPUT"
if ($context) {
    # Proceed with $context.Number, $context.Repository
} else {
    # Error: No context found
}
```
```

### Recommendation 4: Update pr-comment-responder Agent Frontmatter (P2)

**Location**: [src/claude/pr-comment-responder.md](src/claude/pr-comment-responder.md#L5)

**Change**: Update `argument-hint` to reflect context inference capability

```yaml
# Before
argument-hint: Specify the PR number or review comments to address

# After
argument-hint: PR number (e.g., "PR 806"), GitHub PR URL, or PR context. Agent extracts PR number from text and URLs automatically.
```

### Recommendation 5: Add Validation to Pre-Commit Hook (P3)

**Location**: [.githooks/pre-commit](.githooks/pre-commit)

**Purpose**: Detect agent definitions that accept GitHub context without context inference guidance

```bash
# Check for agents with PR/Issue parameters but no extraction guidance
if git diff --cached --name-only | grep -qE '(src|templates)/.*\.md'; then
  for file in $(git diff --cached --name-only | grep -E '(src|templates)/.*\.md'); then
    if grep -qE 'argument-hint:.*PR|argument-hint:.*Issue' "$file"; then
      if ! grep -qE 'Extract.*GitHub.*Context|parse.*PR.*number|regex.*github\.com' "$file"; then
        echo "[WARNING] $file: Agent accepts GitHub context but lacks extraction guidance"
        echo "  Add context inference phase or reference Extract-GitHubContext.ps1"
      fi
    fi
  done
fi
```

## Open Questions

1. **Should context extraction be a global agent capability or skill-specific?**
   - Global: All agents benefit, reduces duplication
   - Skill-specific: More flexibility, clearer ownership

2. **What format should `Extract-GitHubContext.ps1` output use?**
   - JSON: Machine-readable, consistent with gh CLI
   - PSCustomObject: PowerShell-native, easier for scripts
   - Both: JSON via `-AsJson` parameter

3. **Should agents error or prompt when context extraction fails?**
   - Error: Aligns with autonomous-execution-guardrails (STRICTER)
   - Prompt: User-friendly, allows recovery
   - Hybrid: Error during autonomous execution, prompt otherwise

4. **How should this integrate with Task tool argument passing?**
   - Does Claude Code's Task tool pre-parse arguments?
   - Do we need both natural language extraction AND structured parameter handling?

## Evidence

### Codebase State

- **Agent definitions**: 3 platforms (Claude, VS Code, Copilot CLI) × 14 agents = 42 files
- **Context inference patterns found**: 0 files
- **GitHub URL parsing patterns found**: 1 comment in New-Issue.ps1
- **Shared extraction utilities**: 0 files

### Memory References

- `autonomous-execution-guardrails`: Requires STRICTER protocols during autonomy
- `agent-workflow-scope-discipline`: Document issues, don't expand scope
- `session-320-pr806-review`: PR #806 review completion (no extraction issue noted)

### Related Issues/PRs

- PR #806: Spec validation PR context confusion (different issue - workflow using wrong PR)
- Session 131: PR #810 review (successful - PR number likely pre-provided)

## Implementation Priority

| Recommendation | Priority | Effort | Impact |
|----------------|----------|--------|--------|
| Add Context Inference Phase (R1) | P0 | 2 hours | Immediate fix for pr-comment-responder |
| Create Extract-GitHubContext.ps1 (R2) | P1 | 4 hours | Reusable across all agents |
| Update Global Instructions (R3) | P1 | 1 hour | System-wide guidance |
| Update Frontmatter (R4) | P2 | 15 min | Documentation clarity |
| Add Pre-Commit Validation (R5) | P3 | 2 hours | Prevents regressions |

**Total Effort**: ~9.25 hours

**Timeline**: Complete P0 immediately, P1 within same sprint, P2-P3 in next sprint

## Conclusion

The agent failed to extract PR number from user input due to a system-wide gap in context inference guidance. The pr-comment-responder agent has detailed workflow phases but assumes PR number is already provided. No shared utilities exist for extracting PR/issue numbers from natural language text or GitHub URLs.

**Root Cause**: Agent Instruction Gap + Prompt Engineering Gap

**Fix Ownership**:

- **Immediate** (P0): pr-comment-responder skill enhancement
- **Strategic** (P1): Shared utility creation + global guidance
- **Preventive** (P2-P3): Documentation and validation

**Alignment Check**: All recommendations align with `autonomous-execution-guardrails` memory by eliminating unnecessary user prompts and enabling stricter autonomous execution protocols.

---

**Analysis Complete**: 2026-01-08  
**Analyst**: analyst agent  
**Next Steps**: Review with architect for shared utility design, implementer for Phase -1 addition
