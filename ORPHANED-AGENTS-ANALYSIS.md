# Analysis: Orphaned .github/agents/ Directory

**Date**: 2026-03-07  
**Investigator**: DevClaw DEVELOPER  
**Issue**: #972 (VS Code Agent Consolidation)

## Summary

The `.github/agents/` directory is **orphaned and stale**. It contains 25 files with outdated `model` field values and should be removed. The authoritative source is `src/vs-code-agents/` per ADR-036.

## Findings

### 1. Directory Comparison

| Property | `.github/agents/` | `src/vs-code-agents/` | Status |
|----------|-------------------|----------------------|--------|
| File Count | 25 | 19 | ❌ Mismatch |
| Last Updated | 2025-01-02 (commit 8d9b5a09) | Current (auto-generated) | ❌ Stale |
| Model Field | `Claude Opus 4.5 (anthropic)` | `Claude Opus 4.5 (copilot)` | ❌ Incorrect |
| Purpose | Unknown | Generated (per ADR-036) | ❓ Unclear |
| CI Target | Not referenced | Used by GitHub Actions workflows | ✓ Correct |

### 2. Model Field Drift

**Evidence**: Sample `analyst.agent.md`

```yaml
# .github/agents/analyst.agent.md
model: Claude Opus 4.5 (anthropic)  ❌ WRONG - indicates Anthropic API platform

# src/vs-code-agents/analyst.agent.md  
model: Claude Opus 4.5 (copilot)    ✓ CORRECT - indicates VS Code Copilot platform
```

All 18 shared agents show this pattern of drift.

### 3. Extra Agents in .github/agents/

`.github/agents/` contains 7 agents NOT in `templates/agents/`:

1. `code-reviewer.agent.md`
2. `code-simplifier.agent.md`
3. `comment-analyzer.agent.md`
4. `pr-test-analyzer.agent.md`
5. `silent-failure-hunter.agent.md`
6. `type-design-analyzer.agent.md`
7. `pr-comment-responder.prompt.md` (not .agent.md)

**Status of these agents:**

- Exist in `src/claude/` as manual agent definitions (Claude Code agents)
- Should NOT be in `.github/agents/` (VS Code platform)
- May be legacy copies from before consolidation

### 4. Architecture Decision (ADR-036) Status

✓ **Implemented Correctly**:

- `src/vs-code-agents/` is the designated generation target
- `templates/platforms/vscode.yaml` correctly points to `src/vs-code-agents`
- `build/Generate-Agents.ps1` generates to `src/vs-code-agents`
- Pre-commit hooks stage generated files from `src/vs-code-agents`
- Documentation (README.md, CONTRIBUTING.md) references `src/vs-code-agents`

❌ **Incomplete Cleanup**:

- `.github/agents/` was never removed
- Old directory creates confusion about authoritative source
- Stale model field values could mislead users

### 5. Historical Context

**Git Log** (selected commits):

- `a1fa3826` (2025-03-21): "feat: add VS Code agent system" — initial `.github/agents/`
- `20d23ae2` (2025-05-14): "feat: add VS Code agent system" — likely superseded by ADR-036
- `bdacb6b1` (2025-10-19): Last edit to `.github/agents/` (line ending normalization)
- After 2025-10-19: No commits to `.github/agents/` (indicates abandonment)

## Recommendation

### Phase 4: Cleanup (2-hour task)

**Task: Remove orphaned `.github/agents/` directory**

1. **Verify no tools reference `.github/agents/`**
   - ✓ DONE: Grep confirms no GitHub Actions reference it
   - ✓ DONE: Documentation doesn't mention it
   - ✓ DONE: No VSCode extension config references it

2. **Remove the directory**

   ```bash
   git rm -r .github/agents/
   git commit -m "chore(agents): remove orphaned .github/agents/ directory

   - Directory was stale and contained outdated model field values
   - ADR-036 designates src/vs-code-agents/ as the authoritative source
   - Pre-commit hooks ensure generated agents stay current
   - Removing to prevent confusion about which directory is current"
   ```

3. **Investigate 7 "extra" agents**
   - These agents exist in `src/claude/` (Claude Code platform)
   - They should NOT be in VS Code agents directory (not generated)
   - Verify they're intentionally Claude-only per ADR-036
   - If Claude-only: Document in templates/README.md why they're excluded from generation

## Decision Points

### Question 1: Platform Intent

**Are the 7 "extra" agents intentionally Claude-only?**

- code-reviewer
- code-simplifier  
- comment-analyzer
- pr-test-analyzer
- silent-failure-hunter
- type-design-analyzer

**Current Status**: Exist in `src/claude/`, NOT in templates (so not generated for VS Code/Copilot CLI)

**Decision Needed**:

- [ ] YES → Document in ADR-036 amendment why these are Claude-only
- [ ] NO → Create `templates/agents/*.shared.md` for these to include in Copilot platforms

### Question 2: Timeline

**How quickly should we remove `.github/agents/`?**

**Options**:

- [ ] Immediate (next PR): Clean break, reduces confusion
- [ ] After v1.1 release: Lower risk, but leaves stale directory longer
- [ ] During v1.2 cleanup: Bundle with other maintenance

**Recommendation**: Immediate — the cleanup is low-risk and improves clarity.

## Implementation Checklist

- [ ] Remove `.github/agents/` directory
- [ ] Verify CI/CD doesn't break (none reference it)
- [ ] Document decision in ADR-036 amendment
- [ ] Add "Agent Platform Specificity" section to templates/README.md
- [ ] Update CONTRIBUTING.md to remove any `.github/agents/` references
- [ ] Test pre-commit hook and generation still work

## Files Affected

**Deleted:**

- `.github/agents/` (25 files)

**Updated:**

- `CONTRIBUTING.md` (if any references exist)
- `.agents/architecture/ADR-036-two-source-agent-template-architecture.md` (amendment)

**No Changes Needed:**

- `src/vs-code-agents/` (remains authoritative)
- `src/claude/` (remains authoritative for Claude)
- `templates/agents/` (remains source for generation)
- `build/Generate-Agents.ps1` (no changes needed)

---

## Verification Checklist

After cleanup:

- [ ] `ls -la .github/` shows no `agents/` directory
- [ ] `git log --name-only` shows `.github/agents/` removed
- [ ] `pwsh build/Generate-Agents.ps1` still works
- [ ] Pre-commit hook triggers correctly
- [ ] CI workflow passes
- [ ] VS Code loads agents from `src/vs-code-agents/` (manual test)
