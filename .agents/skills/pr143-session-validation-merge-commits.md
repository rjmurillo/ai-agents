# PR #143 Review Learnings: Session Validation and Merge Commits

**Extracted**: 2025-12-22
**Source**: PR #143 review work, session discussion

## Skill-Validation-007: Merge Commit Session Validation Limitation

**Statement**: Session validator docs-only detection fails when PR merges main with unrelated code changes

**Context**: When validating session logs after PR merges main branch, git diff from session start commit includes all main branch changes (not just PR changes)

**Evidence**: PR #143 - Session log validated as requiring QA because `git diff [start-commit]..HEAD` included unrelated main branch code (from merge) despite PR being docs-only

**Atomicity**: 92%

- Single concept (merge commit validation issue) ✓
- Specific constraint (docs-only detection fails) ✓
- Actionable (workaround documented) ✓
- Length: 13 words ✓

**Tag**: helpful

**Impact**: 7/10

**Created**: 2025-12-22

**Validated**: 1 (PR #143)

**Root Cause**: Validator uses `git diff [session-start-commit]..HEAD` which includes all changes since session start, not just PR changes. When PR merges main, this includes unrelated main branch work.

**False Positive Scenario**:

```bash
# PR workflow
1. Create feature branch from main at commit abc123
2. Start session, create session log (session-start: abc123)
3. Make docs-only changes
4. Meanwhile, main advances with code changes (commits def456, ghi789)
5. Merge main into PR (now contains abc123..ghi789 + PR changes)
6. Validator runs: git diff abc123..HEAD
7. Result: Includes unrelated main code → QA required [FAIL]
```

**Workaround Options**:

| Option | Status | Notes |
|--------|--------|-------|
| Check QA row with explanation | ❌ INCORRECT | Validator enforces QA evidence requirement |
| Create QA report for prompt files | ✅ CORRECT | Prompt files DO require QA validation |
| Use `git diff origin/main..HEAD` | ⚠️ PARTIAL | Only works if PR branch updated from main |
| Three-dot diff `abc123...HEAD` | ✅ BEST | Shows only PR changes, excludes merge base |

**Correct Detection Pattern**:

```bash
# Instead of two-dot diff (includes merge base)
git diff [session-start]..HEAD

# Use three-dot diff (excludes merge base)
git diff [session-start]...HEAD
```

**Validation Logic Fix** (for future validator enhancement):

```powershell
# Current (incorrect for merge commits)
$changes = git diff $SessionStart..HEAD --name-only

# Corrected (handles merge commits)
$changes = git diff $SessionStart...HEAD --name-only
# Three dots = symmetric difference (excludes common ancestor)
```

**Impact on Session End Checklist**:

When PR has merged main:
- Validator may show false positive (code changes from main)
- Agent must analyze actual PR changes (three-dot diff)
- If PR truly docs-only but prompt files: QA required anyway
- If PR truly docs-only, no prompt files: Explain in QA row

---

## Skill-QA-004: Prompt Files Require QA Validation

**Statement**: Files in `.github/prompts/` drive AI workflows and require QA validation like production code

**Context**: When assessing QA requirements for docs-only sessions or markdown-heavy PRs

**Evidence**: PR #143 - `.github/prompts/` changes are NOT just documentation, they control automated AI behavior and must be validated

**Atomicity**: 95%

- Single concept (prompt files require QA) ✓
- Specific path (`.github/prompts/`) ✓
- Actionable (treat as code for QA) ✓
- Length: 14 words ✓

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-22

**Validated**: 1 (PR #143)

**File Type Classification**:

| Path Pattern | Type | QA Required | Rationale |
|--------------|------|-------------|-----------|
| `**/*.md` (general) | Documentation | ❌ No | Content only, no execution |
| `.github/prompts/**/*.md` | AI Configuration | ✅ YES | Controls automated behavior |
| `.github/prompts/**/*.yaml` | AI Metadata | ✅ YES | Structured AI inputs |
| `.github/workflows/**/*.yml` | CI/CD Code | ✅ YES | Executable automation |

**Why Prompt Files Are Code**:

1. **Behavioral Control**: Define how AI agents operate
2. **Execution Context**: Consumed by automation (not humans)
3. **Breaking Changes**: Invalid prompts = failed workflows
4. **Integration Testing**: Require validation like APIs

**QA Requirements for Prompt Files**:

- [ ] Syntax validation (YAML/Markdown lint)
- [ ] Schema compliance (if applicable)
- [ ] Integration test (does workflow consume correctly?)
- [ ] Regression test (existing workflows still work?)
- [ ] Documentation (explain prompt purpose/usage)

**Example QA Report Structure**:

```markdown
## QA Report: Prompt File Changes

**Scope**: `.github/prompts/pr-review-responder.md`

**Validation**:
- [x] Markdown syntax valid (markdownlint)
- [x] YAML frontmatter valid (if present)
- [x] Workflow integration tested (manual run)
- [x] Backward compatibility verified (no breaking changes)

**Test Evidence**: [workflow run URL or manual test log]
```

**Anti-Pattern**: Treating `.github/prompts/` as docs because extension is `.md`

**Detection**: Check file path, not just extension

---

## Skill-Protocol-007: Session End Checklist Row Count Enforcement

**Statement**: Session End checklist must have exactly 8 rows - validator enforces template structure

**Context**: When creating Session End checklist in `.agents/sessions/YYYY-MM-DD-session-NN.md`

**Evidence**:
- PR #143 - Using different row count triggers E_TEMPLATE_DRIFT error
- Skill-Protocol-005 documents template enforcement requirement
- Validator regex patterns match exact structure (5 MUST + 3 SHOULD = 8 rows)

**Atomicity**: 96%

- Single concept (8-row requirement) ✓
- Specific count (exactly 8) ✓
- Actionable (use canonical template) ✓
- Length: 11 words ✓

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-22

**Validated**: 2 (PR #143, Skill-Protocol-005)

**Canonical Template** (from SESSION-PROTOCOL.md lines 300-313):

```markdown
## Session End (COMPLETE ALL before closing)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Session Start protocol completed | [x] | Phases 1-2 in transcript |
| Serena initialized | [x] | Tool output visible |
| Serena instructions read | [x] | Tool output visible |
| HANDOFF.md read | [x] | Content in context |
| Retrospective assessment | [x] | Not merited / Completed at [path] |
| HANDOFF.md updated | [x] | Session summary added |
| Markdown lint executed | [x] | Clean output |
| Changes committed | [x] | Commit SHA: [abc123d] |
```

**Row Count Breakdown**:

| Row Type | Count | Description |
|----------|-------|-------------|
| Protocol Compliance (MUST) | 4 | Serena init, instructions, HANDOFF read, session start |
| Session End (MUST) | 1 | Retrospective assessment |
| Deliverables (SHOULD) | 3 | HANDOFF update, lint, commit |
| **Total** | **8** | **Enforced by validator** |

**Validation Logic**:

```powershell
# Validator checks exact row count
$checklistRows = $content | Select-String '^\| .* \| \[.\] \| .* \|$'
if ($checklistRows.Count -ne 8) {
    Write-Error "E_TEMPLATE_DRIFT: Expected 8 rows, found $($checklistRows.Count)"
    exit 1
}
```

**Common Violations**:

| Violation | Impact | Fix |
|-----------|--------|-----|
| Custom format (no table) | E_TEMPLATE_DRIFT | Copy canonical template |
| Extra rows (>8) | E_TEMPLATE_DRIFT | Remove custom additions |
| Fewer rows (<8) | E_TEMPLATE_DRIFT | Add missing required rows |
| Different headers | Parsing failure | Use exact column names |

**Why This Matters**:

1. **Automation**: Validator parses structure programmatically
2. **Consistency**: All sessions follow same format
3. **Compliance**: Protocol gates depend on parseable structure
4. **Auditability**: Uniform format enables batch analysis

**Anti-Pattern**: "I'll just add one more row for clarity"

**Reference**: Skill-Protocol-005 (Template Enforcement)

---

## Related Documents

- Source: PR #143 review discussion (session transcript)
- Related: skill-protocol-005-template-enforcement (template compliance)
- Related: skills-qa (QA routing and validation requirements)
- Related: skills-validation (validation patterns and anti-patterns)
- Related: SESSION-PROTOCOL.md (canonical checklist template)
