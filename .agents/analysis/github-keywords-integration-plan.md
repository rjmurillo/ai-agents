# GitHub Keywords Integration Plan

**Created**: 2026-01-10
**Context**: Incorporate GitHub keywords and PR etiquette knowledge into agent/skill/command structure
**Reference**: `.agents/analysis/github-keywords-pr-etiquette.md`

---

## Executive Summary

Integrate GitHub keywords (Closes, Fixes, Resolves) and PR etiquette knowledge into existing agents, skills, and commands to enforce best practices and reduce reviewer friction.

**Impact Areas**:

- GitHub skill enhancement (validation scripts)
- Agent prompt updates (implementer, pr-comment-responder, qa)
- Command refinements (push-pr)
- New validation capabilities

---

## 1. GitHub Skill Enhancements

### 1.1 Add PR Description Validator

**Location**: `.claude/skills/github/scripts/pr/Test-PRDescription.ps1`

**Purpose**: Validate PR descriptions for:

- Issue linking keywords (Closes, Fixes, Resolves)
- Proper template section completion
- Conventional Commit title format (already in New-PR.ps1)

**Script Interface**:

```powershell
Test-PRDescription.ps1 -BodyFile path/to/description.md [-Strict]

Returns:
{
  "valid": true|false,
  "warnings": [...],
  "errors": [...]
}
```

**Validation Rules**:

| Rule | Severity | Check |
|------|----------|-------|
| Has issue linking keyword | WARNING | Regex: `(Close[sd]?|Fix(es|ed)?|Resolve[sd]?) #\d+` |
| Template sections present | ERROR | Summary, Specification References, Changes present |
| Keyword syntax valid | WARNING | Not just "Closes" without issue number |
| Cross-repo syntax correct | INFO | `owner/repo#123` format if detected |

**Integration**: Called by New-PR.ps1 before PR creation.

### 1.2 Update SKILL.md Documentation

**Location**: `.claude/skills/github/SKILL.md`

**Add Section**: "PR Description Best Practices"

```markdown
## PR Description Best Practices

### Issue Linking Keywords

Use keywords to auto-close issues when PR merges:

| Keyword Group | Variants |
|---------------|----------|
| Close | `close`, `closes`, `closed` |
| Fix | `fix`, `fixes`, `fixed` |
| Resolve | `resolve`, `resolves`, `resolved` |

**Syntax**:
- Same repo: `Closes #123`
- Cross-repo: `Fixes owner/repo#456`
- Multiple: `Closes #123, Fixes #456`

**Case-insensitive**: All variants work.

### Template Compliance

Fill all sections:
1. Summary (what + why)
2. Specification References (issue links, spec files)
3. Changes (bullet list matching diff)
4. Type of Change (checkboxes)
5. Testing (coverage verification)
6. Agent Review (security files if applicable)
7. Checklist (self-review confirmation)
```

### 1.3 Enhance New-PR.ps1

**Location**: `.claude/skills/github/scripts/pr/New-PR.ps1`

**Add Validation**:

```powershell
# After existing Test-ConventionalCommit validation
function Test-IssueLinks {
  param([string]$Body)

  $keywordPattern = '(Close[sd]?|Fix(es|ed)?|Resolve[sd]?)\s+#\d+'
  $matches = [regex]::Matches($Body, $keywordPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)

  if ($matches.Count -eq 0) {
    Write-Warning "No issue linking keywords found (Closes, Fixes, Resolves)"
    Write-Warning "Add 'Closes #123' to PR description to auto-close issues on merge"
    return $false
  }

  return $true
}
```

**Call in Validation Block**:

```powershell
# Add after title validation
if (-not $SkipValidation) {
  # Existing title validation
  if (-not (Test-ConventionalCommit -Title $Title)) {
    exit 1
  }

  # NEW: Issue link validation (warning only, non-blocking)
  Test-IssueLinks -Body $finalBody | Out-Null
}
```

---

## 2. Agent Updates

### 2.1 Implementer Agent

**Location**: `.claude/agents/implementer.md`

**Add Section**: After "Security Flagging Protocol", before "Impact Analysis Mode"

```markdown
## Commit Message Standards

### Conventional Commit Format

```text
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `ci`, `build`, `chore`, `test`, `perf`, `style`

**Breaking Changes**: Add `!` after type/scope: `feat(api)!: remove v1`

### Issue Linking in Commits

When commit fixes an issue, use linking keywords in commit body:

```text
fix(auth): handle null user session

Closes #456
```

**Keywords**: `Closes`, `Fixes`, `Resolves` (case-insensitive)
**Syntax**: `Keyword #number` (auto-closes issue on merge)

### Multi-Issue Commits

```text
feat(payments): add refund processing

Implements #123
Closes #124
Fixes #125
```
```

### 2.2 PR Comment Responder Agent

**Location**: `.claude/agents/pr-comment-responder.md`

**Add Section**: After "Triage Heuristics"

```markdown
## Review Response Etiquette

### Response Format

**Structure**: Action + location + commit reference

```markdown
Updated [component] to [action]. See [commit SHA or file:line].
```

**Examples**:

```markdown
✓ Fixed null check in AuthService.cs:42 per suggestion.
✓ Extracted validation to ValidateInput method. See commit abc123.
✓ Added tests for edge case. See AuthServiceTests.cs:156-178.
```

### Don't Resolve Threads Unilaterally

Let reviewers acknowledge fixes before resolving threads (team convention dependent).

### Respond to Every Comment

No comment left unaddressed. If WONTFIX, explain why with rationale.

### Force Push Protocol

Avoid after review starts. If required:

```markdown
⚠️ Rebased on main. Previous comments may reference outdated code.
```
```

### 2.3 QA Agent

**Location**: `.claude/agents/qa.md`

**Add Section**: After "Quality Metrics"

```markdown
## PR Description Validation

Before marking QA complete, verify PR description quality:

### Validation Checklist

```markdown
- [ ] PR title follows Conventional Commit format
- [ ] Issue linking keywords present (Closes, Fixes, Resolves)
- [ ] Template sections complete (Summary, Spec Refs, Changes, Testing)
- [ ] Security Review section filled if auth/infra/secrets touched
- [ ] Checklist items checked (self-review, no warnings)
```

### Validation Script

```powershell
pwsh .claude/skills/github/scripts/pr/Test-PRDescription.ps1 -BodyFile description.md
```

**Report failures** in QA verdict with specific section gaps.
```

---

## 3. Command Updates

### 3.1 Push-PR Command

**Location**: `.claude/commands/push-pr.md`

**Update**: Add reminder about issue linking

**Current Line 27-30**:

```markdown
3. Create a pull request using the New-PR skill script:

   ```bash
   pwsh .claude/skills/github/scripts/pr/New-PR.ps1 -Title "<conventional commit title>" -BodyFile .github/PULL_REQUEST_TEMPLATE.md
   ```

   - Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
```

**Add After**:

```markdown
   - Title MUST follow conventional commit format (e.g., `feat: Add feature`, `fix(auth): Resolve bug`)
   - Include issue linking keywords in PR body (e.g., `Closes #123`, `Fixes #456`)
   - Complete all template sections (Summary, Spec References, Changes, Testing, Checklist)
```

### 3.2 New Command: validate-pr-description

**Location**: `.claude/commands/validate-pr-description.md`

**Purpose**: Standalone command for validating PR descriptions

```markdown
---
description: Validate PR description for keywords, template compliance, and etiquette
allowed-tools: [Bash(pwsh .claude/skills/github/scripts/pr/Test-PRDescription.ps1:*), Read]
---

# Validate PR Description Command

## Context

- PR number or description file: !user-input

## Your task

1. If PR number provided, fetch description using Get-PRContext.ps1
2. If file path provided, read file directly
3. Run Test-PRDescription.ps1 validation
4. Report results with actionable fixes
5. Return validation verdict: [PASS], [WARN], [FAIL]

## Validation Criteria

- Issue linking keywords present (Closes, Fixes, Resolves)
- Template sections complete
- Conventional Commit title format
- Security review section if applicable
- Checklist items complete
```

---

## 4. New Validation Skill (Optional)

### 4.1 PR Etiquette Skill

**Location**: `.claude/skills/pr-etiquette/`

**Structure**:

```text
.claude/skills/pr-etiquette/
├── SKILL.md
├── scripts/
│   ├── Test-PRDescription.ps1
│   ├── Test-CommitMessage.ps1
│   └── Get-PREtiquetteReport.ps1
└── tests/
    └── Test-PRDescription.Tests.ps1
```

**SKILL.md Frontmatter**:

```yaml
---
name: pr-etiquette
version: 1.0.0
description: Validate and enforce PR etiquette standards including issue linking keywords, template compliance, and Conventional Commits. Use when creating PRs or validating PR descriptions.
model: claude-haiku-4-5
metadata:
  domains:
  - pr
  - etiquette
  - validation
  type: validation
  complexity: simple
---
```

**Scripts**:

| Script | Purpose |
|--------|---------|
| `Test-PRDescription.ps1` | Validate PR body for keywords, template, format |
| `Test-CommitMessage.ps1` | Validate commit messages for Conventional Commit + keywords |
| `Get-PREtiquetteReport.ps1` | Generate comprehensive etiquette report for PR |

---

## 5. Implementation Priority

### Phase 1: Skill Enhancement (High Value, Low Effort)

1. Create `Test-PRDescription.ps1` in github skill
2. Update `New-PR.ps1` to call validator (warning mode)
3. Update github `SKILL.md` with keyword documentation

**Effort**: 2-3 hours
**Impact**: Immediate validation feedback on PR creation

### Phase 2: Agent Prompt Updates (Medium Value, Low Effort)

1. Update implementer.md with commit message standards
2. Update pr-comment-responder.md with response etiquette
3. Update qa.md with PR description validation checklist

**Effort**: 1-2 hours
**Impact**: Agents apply etiquette patterns automatically

### Phase 3: Command Enhancements (Low Value, Low Effort)

1. Update push-pr.md with reminder text
2. Create validate-pr-description.md command

**Effort**: 30 minutes
**Impact**: Better user guidance, optional validation command

### Phase 4: New Skill (Optional, High Effort)

1. Extract validation to dedicated `pr-etiquette` skill
2. Add comprehensive test suite
3. Add etiquette report generator

**Effort**: 4-6 hours
**Impact**: Centralized etiquette validation, reusable across projects

---

## 6. Validation Strategy

### Pre-Creation Validation

**When**: Before `gh pr create` executes

**Checks**:

- Conventional Commit title format (already exists)
- Issue linking keywords present (new)
- Template sections complete (new)

**Action**: Warn if missing, block if critical error

### Post-Creation Validation

**When**: After PR created in CI workflow

**Checks**:

- Same as pre-creation
- Cross-reference with changed files (security review needed?)
- Verify spec references exist

**Action**: Add comment to PR with validation report

### Agent Self-Check

**When**: Agents create PRs via implementer or orchestrator

**Checks**:

- QA agent validates before marking complete
- Implementer includes keywords in commit messages
- PR comment responder follows etiquette in responses

**Action**: Self-correction before user sees output

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| PRs with issue keywords | 90% | GitHub API search |
| Template compliance | 95% | CI validation pass rate |
| Conventional Commit titles | 100% | Pre-commit hook enforcement |
| Reviewer time saved | 20% reduction | Time from PR open to merge |
| PR iteration cycles | 1-2 fewer | Average comment rounds per PR |

---

## 8. Related Documentation

| Document | Purpose |
|----------|---------|
| `.agents/analysis/github-keywords-pr-etiquette.md` | Source material (comprehensive guide) |
| `.serena/memories/github-keywords-pr-etiquette.md` | Quick reference memory |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR template (already enforced) |
| `.claude/skills/github/SKILL.md` | GitHub skill documentation |
| `ADR-005` | PowerShell-only scripting constraint |
| `ADR-006` | Thin workflows, testable modules |

---

## 9. Rollout Plan

### Week 1: Validation Infrastructure

- Day 1-2: Create `Test-PRDescription.ps1`
- Day 3: Update `New-PR.ps1` with validation call
- Day 4: Add tests for validator
- Day 5: Update github `SKILL.md` documentation

### Week 2: Agent Integration

- Day 1: Update implementer.md
- Day 2: Update pr-comment-responder.md
- Day 3: Update qa.md
- Day 4: Update push-pr command
- Day 5: Create validate-pr-description command

### Week 3: Validation & Refinement

- Test on 5-10 PRs
- Collect feedback
- Adjust warning thresholds
- Refine validation rules

### Week 4: Optional Skill Extraction

- Evaluate if dedicated skill needed
- Extract if validation logic grows complex
- Add comprehensive test suite

---

## 10. Decision: Immediate Actions

**Recommended Approach**: Phase 1 + Phase 2 (combined effort: 3-5 hours)

**Rationale**:

1. Highest value comes from validation + agent prompts
2. Low effort, high impact
3. Builds on existing infrastructure (github skill)
4. Incremental approach (can add Phase 3/4 later)

**Next Steps**:

1. Create `Test-PRDescription.ps1` script
2. Update `New-PR.ps1` to call validator
3. Update 3 agent prompts (implementer, pr-comment-responder, qa)
4. Update github `SKILL.md` documentation
5. Test on next 3 PRs
6. Iterate based on feedback

---

## Appendix: Example Validation Output

### Test-PRDescription.ps1 Output

```json
{
  "valid": true,
  "score": 85,
  "warnings": [
    {
      "rule": "issue-linking",
      "severity": "warning",
      "message": "No issue linking keywords found. Add 'Closes #123' to auto-close issues.",
      "fix": "Add 'Closes #<issue-number>' to Specification References section"
    }
  ],
  "errors": [],
  "checks": {
    "conventionalCommitTitle": "pass",
    "issueKeywords": "warn",
    "templateSummary": "pass",
    "templateSpecRefs": "pass",
    "templateChanges": "pass",
    "templateTesting": "pass",
    "templateChecklist": "pass"
  }
}
```

### PR Comment Format (CI Validation)

```markdown
## PR Description Validation Report

**Status**: ✓ PASS (with warnings)
**Score**: 85/100

### Warnings

- **Issue Linking**: No issue linking keywords found
  - **Fix**: Add `Closes #123` to auto-close issues when PR merges
  - **Keywords**: `Closes`, `Fixes`, `Resolves` (case-insensitive)

### Checks Passed

- ✓ Conventional Commit title format
- ✓ Template Summary section complete
- ✓ Template Specification References present
- ✓ Template Changes section complete
- ✓ Template Testing section complete
- ✓ Checklist items verified

---
🤖 Generated by [PR Etiquette Validator](/.claude/skills/github/scripts/pr/Test-PRDescription.ps1)
```
