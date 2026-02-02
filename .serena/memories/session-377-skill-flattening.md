# Session 377: Skill Directory Flattening (2026-01-06)

## Context
Debugged why session skills weren't appearing in `/skills` command output. User expected to see session-init, session-log-fixer, and session-qa-eligibility as individual skills but only saw "session" parent skill.

## Root Cause
Claude Code's skill discovery doesn't support nested SKILL.md files. When a SKILL.md exists at parent level (`.claude/skills/session/SKILL.md`), discovery stops and doesn't descend into subdirectories to find child skills.

## Solution Pattern
**CRITICAL**: All skills MUST be flat at `.claude/skills/{name}/SKILL.md` level. No nesting supported by Claude Code skill discovery.

## Changes Made

### Directory Restructuring
Flattened nested structure using `git mv` to preserve history:
- `.claude/skills/session/init/` → `.claude/skills/session-init/`
- `.claude/skills/session/log-fixer/` → `.claude/skills/session-log-fixer/`
- `.claude/skills/session/qa-eligibility/` → `.claude/skills/session-qa-eligibility/`
- Deleted `.claude/skills/session/SKILL.md` (parent index)

### Frontmatter Corrections
- Fixed `session-qa-eligibility/SKILL.md` name from `qa-eligibility` to `session-qa-eligibility`
- All other skills already had correct names matching directory

### Path Reference Updates (13 files)
1. **Test files**:
   - `tests/Extract-SessionTemplate.Tests.ps1`: Updated `$scriptPath` to `session-init`
   - `tests/Get-ValidationErrors.Tests.ps1`: Updated `$scriptPath` to `session-log-fixer`

2. **Script documentation**:
   - `session-init/scripts/Extract-SessionTemplate.ps1`: Updated `.EXAMPLE` blocks
   - `session-log-fixer/scripts/Get-ValidationErrors.ps1`: Updated `.EXAMPLE` blocks

3. **SKILL.md documentation**:
   - `session-init/SKILL.md`: Updated usage examples
   - `session-log-fixer/SKILL.md`: Updated usage examples (3 locations)

4. **Linter auto-fix**:
   - `session-qa-eligibility/SKILL.md`: Auto-updated script path references

## Cross-Session Patterns

### Skill Discovery Constraints
1. **No nesting**: Skills must be at `.claude/skills/{name}/SKILL.md`
2. **No parent indexes**: Parent SKILL.md blocks discovery of children
3. **Flat structure only**: All skill directories must be siblings

### Migration Pattern
When converting nested skills to flat:
1. Use `git mv` to preserve history
2. Update frontmatter `name` to match new directory
3. Search for path references: `grep -r "old/path" **/*.{ps1,md}`
4. Update tests, scripts, and documentation
5. Delete parent SKILL.md after moving children
6. Run markdownlint to catch remaining references

### Reference Search Pattern
```bash
# Find all references to old paths
grep -r "session/init\|session/log-fixer\|session/qa-eligibility" \
  --include="*.ps1" --include="*.md"
```

## Verification Evidence
- Markdownlint: PASS (0 errors)
- Git rename detection: Working (16 files, all renamed properly)
- Expected: `/skills` will show 29 skills (was 27)
- Commit: d2901e9c

## Related Memories
- [session-375-skillforge-session-skills](session-375-skillforge-session-skills.md): Original skill creation
- [session-376-issue-808-validation](session-376-issue-808-validation.md): Issue #808 validation work
- [skills-session-init-index](skills-session-init-index.md): Session init workflow
- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md): Skill conventions

## Lessons Learned
1. Claude Code skill discovery is opinionated: flat structure only
2. Always check for existing patterns before creating nested structures
3. Git history preservation requires `git mv`, not `mv` + `git add`
4. Linters may auto-fix path references after moves (watch for side effects)

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
