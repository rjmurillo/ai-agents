# Resolution Strategies

Detailed patterns for common conflict scenarios.

## Additive Changes

Both sides add new content (imports, methods, properties).

**Pattern:** Combine both additions.

```
<<<<<<< HEAD
import { featureA } from './a';
=======
import { featureB } from './b';
>>>>>>> main
```

**Resolution:** Keep both additions in the correct order.

## Moved or Renamed Code

One side moves code, other modifies it.

**Pattern:**

```bash
git log --follow --diff-filter=R -- <file>
```

Common in JavaScript/TypeScript, C#, Python.

**Patterns:**

- **Renamed imports** - Check usage in file, keep the one being used
- **Conflicting aliases** - Pick one, update all usages

```bash
grep -n -- "<import-name>" <file>
```

## Deleted Code

**Investigation:**

1. Why was it deleted? Check commit message
2. Is the modification still relevant?

```bash
# Find deletion commit
git log --diff-filter=D -- <file>

# Check if code exists elsewhere
git grep "<distinctive-code-fragment>"
```

**Resolution:**

- If deleted intentionally (deprecated, unused) - Accept deletion
- If deleted for refactor - Apply modification to new location
- If accidentally deleted - Restore with modifications

## Conflicting Logic

Both sides change the same logic differently.

**Analysis:**

1. What does each change accomplish?

**Resolution Priority:**

1. Bugfix over feature
2. More recent over older (if both are features)
3. Better tested over untested

```bash
# Check test coverage for each version
git show <commit>:tests/<test-file>
```

## Style/Formatting Conflicts

Whitespace, line endings, indentation.

**Pattern:** Accept the version matching project conventions.

```bash
cat .prettierrc
```

**Resolution:** Verify no functional changes mixed with style changes.

## Lock File Conflicts

```bash
# Accept base, regenerate
git checkout --theirs package-lock.json
npm install
```

## Configuration File Conflicts

1. Identify which keys changed on each side
2. Merge at the semantic level (not line level)
3. Validate JSON/YAML syntax

```bash
# Validate JSON
cat <file> | jq .

# Validate YAML
python -c "import yaml; yaml.safe_load(open('<file>'))"
```

## Database Migration Conflicts

1. Never merge migration content

**Resolution:**

1. Accept one version
2. Create a new migration for the other change
3. Update migration dependencies if needed

## Numbered Documentation Conflicts (ADR, RFC)

Architecture Decision Records or RFCs with sequence numbers (`ADR-021`, `RFC-003`).

**Symptoms:**

- Add/add conflict: both branches create `ADR-NNN-*` with same number
- Often occurs when parallel work creates ADRs independently

```bash
# Check what ADR numbers exist in each branch
git show main:".agents/architecture/" | grep "^ADR-" | sort -t'-' -k2 -n
git show HEAD:".agents/architecture/" | grep "^ADR-" | sort -t'-' -k2 -n

# Find next available number
```

1. Keep the version from `main` (canonical, already merged)
2. Renumber the incoming branch's ADR to next available

```bash
# Accept main's version of the conflicting file
git checkout --theirs .agents/architecture/ADR-021-*.md

# Rename incoming ADR to next available number (e.g., ADR-023)
git mv .agents/architecture/ADR-021-my-adr.md .agents/architecture/ADR-023-my-adr.md

sed -i 's/ADR-021/ADR-023/g' .agents/architecture/ADR-023-my-adr.md

# Find and update all references to the old number
git grep -l "ADR-021" -- "*.md" | xargs sed -i 's/ADR-021/ADR-023/g'
```

**Validation:**

- All cross-references updated (session logs, PRDs, HANDOFF.md)
- Debate logs and critique files renamed consistently

**Related Files to Update:**

- `.agents/critique/ADR-NNN-debate-log.md`
- `.agents/critique/ADR-NNN-*-critique.md`
- `.agents/planning/PRD-*.md` (References section)
- `.agents/sessions/*.json` (if ADR mentioned)

## Template-Generated File Conflicts

**Symptoms:**

- Same changes appear across multiple platform directories
- Conflict markers in files that share common sections

**Investigation:**

```bash
# Check if file is generated
head -5 src/claude/architect.md  # Look for "Generated from" comment

# Find the source template
grep -r -- "architect" templates/agents/*.shared.md

# Check template modification dates
```

**Resolution:**

1. Do NOT manually merge generated files
2. Resolve conflicts in the **template** file instead
3. Regenerate all platform-specific files

```bash
# Resolve conflict in template
# Edit templates/agents/architect.shared.md to combine changes

# Regenerate all platform files
pwsh build/Generate-Agents.ps1

git add src/claude/*.md src/copilot-cli/*.md src/vs-code-agents/*.md
```

**Anti-pattern:** Editing generated files directly will be overwritten on next regeneration.

**Template Locations:**

| Generated Pattern | Template Source |
|-------------------|-----------------|
| `src/*/architect.md` | `templates/agents/architect.shared.md` |
| `src/*/orchestrator.md` | `templates/agents/orchestrator.shared.md` |
| Platform-specific agents | `templates/agents/*.{claude,copilot,vscode}.md` |

## Rebase Add/Add Conflicts

- Error: `CONFLICT (add/add): Merge conflict in <file>`
- Both branches created the same file independently
- File didn't exist in common ancestor
- Rebase applies commits one-by-one onto new base
- Conflict appears when rebasing commit that adds file already added by new base
- Must resolve per-commit, not once for whole branch

**Investigation:**

```bash
git log --oneline -1 REBASE_HEAD

# Compare the two versions
git show REBASE_HEAD:<file> # Version being rebased
```

**Resolution Options:**

1. **Accept main's version** (most common for generated/session files):

   ```bash
   git checkout --theirs <file>
   git add <file>
   git rebase --continue
   ```

2. **Keep branch's version** (if branch has needed changes):

   ```bash
   git checkout --ours <file>
   git add <file>
   git rebase --continue
   ```

3. **Merge content** (if both versions needed):
   - Manually combine content

   ```bash
   # Keep main's version
   git checkout --theirs <file>
   # Extract branch's content to new name
   git show REBASE_HEAD:<file> > <new-file-path>
   git add <file> <new-file-path>
   git rebase --continue
   ```

**Common Add/Add Scenarios:**

| File Type | Typical Resolution |
|-----------|-------------------|
| Session logs | Keep both, different dates |
| ADRs with same number | Renumber incoming |
