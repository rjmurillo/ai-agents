# ADR-043: Scoped Tool Execution

## Status

Accepted

## Date

2026-01-21

## Context

Session protocol requires running quality checks at session end, including markdownlint for markdown formatting consistency. The current protocol uses repository-wide tool execution:

```bash
npx markdownlint-cli2 --fix "**/*.md"
```

This approach causes scope explosion when tools reformat files unrelated to the session's stated objective. PR #908 demonstrates this problem: the PR bundled 53 unrelated memory file changes because markdownlint reformatted the entire repository. This creates:

1. **Unclear PRs**: Changes exceed stated objective
2. **Review burden**: Reviewers must validate unrelated formatting changes
3. **Git noise**: Commit history polluted with tool side effects
4. **Merge conflicts**: Increased likelihood when multiple sessions run concurrently

The root cause is that session protocol tools operate on the entire repository rather than the working set relevant to the session.

## Decision

**Session protocol tools MUST scope to changed files rather than the entire repository.**

### Scoped Command Pattern

Replace repository-wide tool invocations with git-scoped patterns:

**Before (Repository-wide):**

```bash
npx markdownlint-cli2 --fix "**/*.md"
```

**After (Scoped to changed files):**

```bash
CHANGED_MD=$(git diff --name-only --diff-filter=d HEAD '*.md' 2>/dev/null)
if [ -n "$CHANGED_MD" ]; then
  echo "$CHANGED_MD" | xargs npx markdownlint-cli2 --fix --no-globs
fi
```

**PowerShell Equivalent:**

```powershell
$ChangedMd = git diff --name-only --diff-filter=d HEAD '*.md' 2>$null
if ($ChangedMd) {
    npx markdownlint-cli2 --fix --no-globs $ChangedMd
}
```

**Note:** The `--no-globs` flag disables config file glob patterns, ensuring only specified files are processed.

### Scope Definition

"Changed files" includes:

- Files with uncommitted modifications (`git diff --name-only`)
- Files staged for commit (`git diff --cached --name-only`)
- Files changed in the current branch vs base (`git diff --name-only origin/main...HEAD`)

The `--diff-filter=d` flag excludes deleted files (tools cannot format files that do not exist).

### Tool Coverage

This scoping applies to:

| Tool | Scope Pattern | Notes |
|------|---------------|-------|
| **markdownlint** | `git diff --name-only --diff-filter=d HEAD '*.md'` | Session protocol Phase 2 |
| **prettier** | `git diff --name-only --diff-filter=d HEAD '*.{json,yaml,yml}'` | If adopted |
| **PSScriptAnalyzer** | `git diff --name-only --diff-filter=d HEAD '*.ps1'` | When running for modified scripts |

### Exclusions

Repository-wide execution remains appropriate for:

- **Explicit cleanup sessions**: PRs with objective "Format all markdown files"
- **CI/CD validation**: Workflows that verify entire repository state
- **Pre-commit hooks**: User-initiated git hooks (not agent-driven)
- **Major version migrations**: Example: markdownlint v1 to v2 upgrade

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Status Quo** (format all files) | Simple command; consistent formatting | Scope explosion; PR noise; merge conflicts | PR #908 demonstrates this causes unacceptable scope creep |
| **Never run formatting** (manual only) | No tool side effects | Inconsistent formatting; manual burden | Loses automation benefit |
| **Separate formatting PRs** | Clean separation | Too heavyweight; delays feature PRs | Creates unnecessary process overhead |
| **Staged files only** (`--cached`) | Minimal scope | Misses unstaged changes that will be committed | May leave working tree inconsistent |
| **Branch diff only** (`origin/main...HEAD`) | Captures all session changes | Requires clean branch; fails on main | Too restrictive for investigation sessions |

### Trade-offs

**Gradual Cleanup vs Immediate Consistency:**

- Scoped execution means repository formatting improves gradually (only touched files get formatted)
- Alternative would require separate formatting PRs or tolerate scope explosion
- Decision: Gradual cleanup is acceptable. Periodic "format all" PRs can address remaining files.

**Command Complexity vs Tool Side Effects:**

- Scoped commands use git integration, increasing command complexity
- Alternative is simpler glob-based commands with uncontrolled scope
- Decision: Complexity is justified to prevent scope explosion.

## Consequences

### Positive

- **Prevents scope explosion**: Tool reformatting no longer pulls in unrelated changes
- **Focused PRs**: Changes match stated objective, improving review clarity
- **Faster execution**: Smaller file set to process (performance improvement)
- **Reduced merge conflicts**: Concurrent sessions less likely to conflict on formatting-only changes
- **Clear intent**: Git history shows deliberate changes, not tool side effects

### Negative

- **Gradual cleanup**: Repository formatting inconsistency may persist (files not touched remain unformatted)
- **Command complexity**: Git-integrated commands are more complex than glob patterns
- **Context dependency**: Requires git repository context (won't work in clean checkout without base branch)

### Neutral

- **CI validation unchanged**: Workflows continue to validate entire repository (appropriate for merge gates)
- **Learning curve**: Agents must adopt git diff pattern instead of glob pattern

## Implementation Notes

### Session Protocol Update

Update `.agents/SESSION-PROTOCOL.md` Phase 2 (Quality Checks):

```markdown
1. The agent MUST run scoped markdownlint on changed files:

   ```bash
   CHANGED_MD=$(git diff --name-only --diff-filter=d HEAD '*.md' 2>/dev/null)
   if [ -n "$CHANGED_MD" ]; then
     echo "$CHANGED_MD" | xargs npx markdownlint-cli2 --fix --no-globs
   fi
   ```

   Or PowerShell equivalent:

   ```powershell
   $ChangedMd = git diff --name-only --diff-filter=d HEAD '*.md' 2>$null
   if ($ChangedMd) {
       npx markdownlint-cli2 --fix --no-globs $ChangedMd
   }
   ```

2. The agent MAY run repository-wide formatting only when:
   - Session objective explicitly includes "format all files"
   - Creating a dedicated formatting cleanup PR
```

### Agent Prompt Updates

Update agent prompts (AGENTS.md, CLAUDE.md, .github/copilot-instructions.md) referencing markdownlint to use scoped pattern.

### Periodic Cleanup

Create periodic "formatting cleanup" issues/PRs to address unformatted files:

- Schedule: Quarterly or on-demand
- Scope: Repository-wide formatting
- Label: `chore`, `formatting`
- PR title: `chore: format all markdown files (periodic cleanup)`

### Verification

```bash
# Verify scoped command works
git diff --name-only --diff-filter=d HEAD '*.md'

# Verify excludes deleted files
git rm some-file.md
git diff --name-only --diff-filter=d HEAD '*.md'  # should not include some-file.md
```

## Related Decisions

- **ADR-001**: Markdown Linting (establishes markdownlint as standard)
- **ADR-005**: PowerShell-Only Scripting (provides PowerShell equivalent commands)
- **ADR-008**: Protocol Automation Lifecycle Hooks (session protocol automation context)
- **ADR-034**: Investigation Session QA Skip (defines session artifact scope)
- **ADR-042**: Python Migration Strategy (future: Python-based scoped tool runner)

## References

- Issue #948: [ADR] Scoped Tool Execution
- Issue #935: Update SESSION-PROTOCOL.md with scoped commands
- PR #908: 53 memory files reformatted (root cause demonstration)
- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` (lines 1348-1353)
- Git documentation: `git diff --name-only --diff-filter`

---

*Created: 2026-01-21*
*GitHub Issue: #948*
