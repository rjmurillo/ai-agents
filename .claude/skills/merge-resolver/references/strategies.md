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

**Resolution:**
```
import { featureA } from './a';
import { featureB } from './b';
```

**Validation:** Check for duplicate imports. Sort alphabetically if convention exists.

## Moved Code

One side moves code, other modifies it.

**Pattern:**
1. Identify the move via `git log --follow`
2. Apply modifications to new location
3. Verify no duplicate definitions

```bash
# Trace file movement
git log --follow --diff-filter=R -- <file>
```

## Import Conflicts

Common in JavaScript/TypeScript, C#, Python.

**Patterns:**
- **Duplicate imports** - Deduplicate, prefer named over default
- **Renamed imports** - Check usage in file, keep the one being used
- **Conflicting aliases** - Pick one, update all usages

```bash
# Find usages in file
grep -n "<import-name>" <file>
```

## Deleted Code

One side deletes, other modifies.

**Investigation:**
1. Why was it deleted? Check commit message
2. Is the modification still relevant?
3. Was it moved elsewhere?

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
2. Are they mutually exclusive?
3. Can they be combined?

**Resolution Priority:**
1. Bugfix over feature
2. Security fix over everything
3. More recent over older (if both are features)
4. Better tested over untested

```bash
# Check test coverage for each version
git show <commit>:tests/<test-file>
```

## Formatting Conflicts

Whitespace, line endings, indentation.

**Pattern:** Accept the version matching project conventions.

```bash
# Check project formatting rules
cat .editorconfig
cat .prettierrc
```

**Resolution:**
1. Accept either version
2. Run formatter on result
3. Verify no functional changes

## Package Lock Conflicts

`package-lock.json`, `yarn.lock`, `packages.lock.json`

**Pattern:** Regenerate, do not manually merge.

```bash
# Accept base, regenerate
git checkout --theirs package-lock.json
npm install

# Or accept head, regenerate
git checkout --ours package-lock.json
npm install
```

## Configuration File Conflicts

JSON, YAML, TOML configs.

**Pattern:**
1. Identify what each side adds/changes
2. Merge at the semantic level (not line level)
3. Validate JSON/YAML syntax

```bash
# Validate JSON
cat <file> | jq .

# Validate YAML
python -c "import yaml; yaml.safe_load(open('<file>'))"
```

## Database Migration Conflicts

Migration files with sequence numbers.

**Pattern:**
1. Never merge migration content
2. Renumber one set of migrations
3. Ensure migration order is correct

**Resolution:**
1. Accept both migration files
2. Rename conflicting numbers
3. Update migration dependencies if needed
