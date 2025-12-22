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

## Skill-Diagnosis-001: Evidence-Based Diagnosis with Specific PR Data

**Statement**: Compare actual API response counts against expected counts from a real example PR to prove diagnostic gaps exist

**Context**: When diagnosing "missing data" bugs in API integrations or data fetching logic

**Evidence**: PR #235 - Used PR #233 as test case (26 review + 3 issue comments) to prove Get-PRReviewComments.ps1 only fetched 26, confirming gap

**Atomicity**: 95%

**Tag**: helpful (diagnostic validation)

**Impact**: 8/10 (validates diagnosis before fix)

**Created**: 2025-12-22

**Problem**:

```text
# WRONG - Vague suspicion without proof
"The script might be missing some comments, I think the API call is incomplete"
```

**Solution**:

```text
# CORRECT - Concrete evidence from real PR
"PR #233 has 29 total comments (verified in GitHub UI):
- 26 review comments (confirmed by API endpoint /pulls/233/comments)
- 3 issue comments (AI Quality Gate, CodeRabbit summary, confirmed by API endpoint /issues/233/comments)

Current script returns only 26 comments.
Gap confirmed: Missing 3 issue comments (100% reproducible)"
```

**Why It Matters**:

Evidence-based diagnosis transforms vague suspicions into concrete, reproducible bug reports:
- **Proves** the gap exists (not assumption)
- **Quantifies** the missing data (3 comments, not "some")
- **Identifies** the root cause (missing endpoint)
- **Validates** the fix (29 comments after fix = PASS)

**Pattern**:

```bash
# Step 1: Select a real test case PR
PR_NUMBER=233

# Step 2: Count expected items manually (GitHub UI, or sum API endpoints)
# Expected: 26 review + 3 issue = 29 total

# Step 3: Run current implementation
./Get-PRReviewComments.ps1 -PullRequest $PR_NUMBER | ConvertFrom-Json | Measure-Object
# Output: Count = 26

# Step 4: Document the gap
echo "Expected: 29, Actual: 26, Gap: 3 (10.3% missing)"

# Step 5: Identify missing items
gh api repos/owner/repo/issues/$PR_NUMBER/comments --jq '.[].user.login'
# Output: github-actions[bot], coderabbit[bot], user-commenter

# Step 6: Root cause confirmed - missing /issues/{n}/comments endpoint
```

**Anti-Pattern**:

```bash
# Hypothetical testing without real data
"Let's add the issue comments endpoint just in case"
# (No evidence gap exists, may be unnecessary change)
```

**Validation**: 1 (PR #235)

---

## Related Documents

- Source: `.agents/analysis/pr43-agent-capability-gap-analysis.md`
- Source: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`
- Source: `.agents/sessions/2025-12-21-session-56-ai-triage-retrospective.md`
- Related: skills-critique (conflict escalation)
- Related: skills-planning (Skill-Planning-003 parallel exploration)
- Related: skills-github-cli (gh pr view, gh run view)
