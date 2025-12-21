# Analysis Skills

**Extracted**: 2025-12-16
**Source**: `.agents/analysis/` directory

## Skill-Analysis-001: Capability Gap Template (88%)

**Note**: This skill was originally Skill-Analysis-001. Renamed to avoid collision with Comprehensive Analysis Standard skill.

**Statement**: Structure gap analysis with ID, Severity, Root Cause, Affected Agents, Remediation

**Context**: Post-failure analysis and root cause investigation

**Evidence**: PR43 capability gap analysis used structured template

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Template**:

```markdown
## Gap [ID]: [Short Title]

**Severity**: Critical | High | Medium | Low
**Root Cause**: [Why the gap exists]
**Affected Agents**: [List of impacted agents]
**Impact**: [What fails when this gap exists]
**Remediation**: [Specific fix with files/changes]
**Verification**: [How to confirm fix works]
```

**Use Case**: After PR failures to systematically identify missing capabilities

**Source**: `.agents/analysis/pr43-agent-capability-gap-analysis.md`

---

## Skill-Analysis-002: Comprehensive Analysis Standard (95%)

**Statement**: Analysis documents MUST include multiple options with trade-offs, explicit recommendations, and implementation specifications detailed enough for direct implementation

**Context**: When analyst creates analysis documents for later implementation

**Evidence**: Analyses 002-004 provided complete specs that implementers followed exactly without clarification. 100% implementation accuracy across Sessions 19-21.

**Atomicity**: 95%

- Single concept (analysis standard) ✓
- Specific requirements (options, trade-offs, recommendations, specs) ✓
- Actionable (create comprehensive analysis) ✓
- Length: 16 words (-5%)

**Tag**: helpful

**Impact**: 9/10 - Enables 100% implementation accuracy

**Required Structure**:

1. **Options Analysis**: 3-5 alternative approaches
2. **Trade-off Tables**: Pros/cons for each option
3. **Evidence**: Verified facts, not assumptions
4. **Recommendation**: Explicit choice with rationale
5. **Implementation Specs**: Detailed enough to implement without clarification

**Example Evidence**:

- Analysis 002 (857 lines, 5 options) → Session 19: 100% specification match
- Analysis 003 (987 lines, design + risks) → Session 20: 100% specification match
- Analysis 004 (1,347 lines, 3 options + appendices) → Session 21: 100% specification match

**Validation**: 3 (Sessions 19, 20, 21)

**Created**: 2025-12-18

---

---

## Skill-Analysis-003: Git Blame Root Cause Investigation (92%)

**Statement**: Use `git blame` → `git show commit` → `gh pr view` workflow to trace code changes to originating PR and context

**Context**: When investigating bugs, regressions, or unexpected behavior to understand why code was written a certain way

**Trigger**: Need to understand why specific code exists or who introduced a change

**Evidence**: Session 56 (2025-12-21): Traced Import-Module bug from failing line → commit 981ebf7 → PR #212 → identified security remediation context

**Atomicity**: 92%

**Tag**: helpful (root cause analysis)

**Impact**: 9/10 - Essential for understanding code history and intent

**Created**: 2025-12-21

**Pattern**:

```bash
# Step 1: Identify the commit that introduced the line
git blame path/to/file.ps1 | grep "Import-Module"
# Output: 981ebf7 (Author 2025-12-21) Import-Module .github/scripts/...

# Step 2: View the full commit with context
git show 981ebf7
# Shows: full diff, commit message, author, date

# Step 3: Find the PR that introduced the commit
gh pr list --search "981ebf7" --state all
# OR extract PR number from commit message
git show 981ebf7 | grep -oP '#\K\d+'

# Step 4: View PR for full context
gh pr view 212
# Shows: description, discussion, review comments, linked issues

# Step 5: Understand the "why" - read PR description
gh pr view 212 --json body --jq '.body'
```

**Why It Matters**:

Understanding **why** code was written a certain way is critical for bug fixes:
- Avoid re-introducing previous bugs
- Understand trade-offs and constraints
- Identify if fix was incomplete or introduced regression
- Preserve security fixes while correcting bugs

**Session 56 Example**:

```bash
# Failing line identified: Import-Module .github/scripts/AIReviewCommon.psm1
git blame .github/workflows/ai-issue-triage.yml | grep "Import-Module"
# → 981ebf7

git show 981ebf7
# → PR #212: "fix(security): remediate CWE-20/CWE-78"

gh pr view 212
# → Security fix to prevent command injection
# → Replaced bash parsing with PowerShell
# → 51 bot reviews, but no execution tests

# Key insight: Bug introduced during security fix, but security value must be preserved
```

**Anti-Pattern**: Fixing bugs without understanding original context - may revert security fixes or reintroduce previous bugs

**Validation**: 1 (Session 56)

---

## Related Documents

- Source: `.agents/analysis/pr43-agent-capability-gap-analysis.md`
- Source: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`
- Source: `.agents/sessions/2025-12-21-session-56-ai-triage-retrospective.md`
- Related: skills-critique (conflict escalation)
- Related: skills-planning (Skill-Planning-003 parallel exploration)
- Related: skills-github-cli (gh pr view, gh run view)
