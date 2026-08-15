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

1. Higher-priority intent wins: Security > Bugfix > Feature/Refactor > Style.
2. Preserve Security over every lower-priority change; reapply the lower-priority change around it.
3. For same-tier conflicts, prefer better-tested, then more recent.

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
uv run python build/generate_agents.py

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
| Session logs | Keep both; rename ours with a distinguishing suffix |
| QA reports | Keep both; rename ours with a distinguishing suffix |
| Retrospectives | Keep both; rename ours with a distinguishing suffix |
| ADRs with same number | Renumber incoming |

## Append-Only Evidence Artifacts (Add/Add)

Session logs (`.agents/sessions/*`), QA reports (`.agents/qa/*`), and retrospectives (`.agents/retrospective/*`) are append-only evidence records. An add/add conflict on one of these means two branches wrote different records to the same filename, usually because two sessions allocated the same session number.

**Rename, never content-merge.** Keep both files: accept the base branch version at the original name, rename the head branch version with a distinguishing suffix, and update any index or report that references the renamed file. Never merge the two contents into one file. PR #4856 proved the anti-pattern: merging both sessions' prose into one file would have destroyed two accurate records to produce one false one (see `.agents/retrospective/2026-08-10-pr-4856-session-log-collision.md`). Issue #4751 tracks preventing the collision at allocation time.

For session logs, keep the session number in the renamed filename and append an issue or topic slug (for example `2026-08-10-session-14653-issue-4842-repository-name-dots.json`). The filename number parser in `scripts/validate_session_json.py` stops the digit run at a hyphen, so the suffixed name still reads as the same number and agrees with `session.number` inside the JSON. Renaming to the next available number would contradict `session.number` and require editing the record itself.

```bash
# Keep main's record at the original name
git checkout --theirs .agents/sessions/<date>-session-<N>.json

# Restore our record under a suffixed name
git show HEAD:.agents/sessions/<date>-session-<N>.json \
    > .agents/sessions/<date>-session-<N>-<slug>.json

git add .agents/sessions/<date>-session-<N>.json \
    .agents/sessions/<date>-session-<N>-<slug>.json

# Repoint anything that referenced our record (QA reports, indexes)
git grep -l "session-<N>" -- ".agents/qa/*.md"
```

<!-- vendor-portability: declared. This doc lists .agents/ artifact patterns (critique debate logs, planning PRDs, sessions/*.json) as sources for resolving ADR-related conflicts. Each is consulted only if present in the consumer repo; a vendored install without them skips those resolution heuristics. Issue #2050. -->
