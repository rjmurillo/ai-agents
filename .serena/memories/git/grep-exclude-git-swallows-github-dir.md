# Excluding `.git` With a Prefix Match Silently Swallows `.github`

**Atomicity**: 95%
**Category**: Search and Tooling
**Source**: 2026-08-02 fleet session, while auditing rule mirrors for PR #4264

## Statement

`grep -v "^./.git"` removes `./.github/...` along with `./.git/...`, because
`.git` is a prefix of `.github`. In a repository whose generated instruction
mirrors live under `.github/instructions/`, that filter deletes exactly the
results a mirror audit exists to find, and it does so without an error.

## Context

Fires whenever a repository-wide search pipes `grep -r` through a filter meant
to drop the object database. It is worse here than in most repositories because
`.github/` holds one of the three rule trees, so a search for a rule string is
precisely the search the filter breaks.

The unescaped `.` makes it slightly worse still: in a regular expression `.`
matches any character, so `^./.git` also matches `X/Ygit` shapes. The prefix
problem is the one that bites in practice.

## Evidence

Searching for `LEFTHOOK_EXCLUDE` across the working tree returned two hits, in
`.claude/rules/universal.md` and the `src/copilot-cli/` mirror, with no hit in
`.github/instructions/universal.instructions.md`. Read literally, that says the
`.github` mirror is stale and the generator did not write it.

It was not stale. A direct read found the string at line 31 of that file, and
re-running the rule generator left `git status --porcelain` empty, which is the
check that proves the mirrors are in sync. The missing hit was the filter, not
the file.

The cost of believing the filter would have been a false defect report against
a generator that was working correctly.

The same search run four ways on the same tree, counting matched lines:

```
grep -rn "LEFTHOOK_EXCLUDE" --include=*.md .                          3
  ... | grep -v "^./.git"                                             2   <- one dropped
  ... | grep -v '^\./\.git/'                                          3
git grep -c "LEFTHOOK_EXCLUDE" -- '*.md'                              3
```

The dropped row is the `.github/instructions/` mirror. Nothing in the output
says a row was dropped.

## Pattern

Anchor the exclusion on the path separator so `.git` cannot match `.github`:

```bash
grep -rn "PATTERN" . | grep -v '^\./\.git/'
```

Better, let the tool that already understands the repository do it:

```bash
git grep -n "PATTERN"
```

`git grep` never searches the object database, so no exclusion is needed and
no prefix can collide.

## Generalization

A filter that removes rows cannot report that it removed the wrong ones. Absence
produced by a filter and absence produced by the world are the same empty
output. Before concluding that something is missing, confirm the absence with a
tool that has no filter in the path: a direct read of the file, or in this case
re-running the generator and checking for a clean tree.

## Related

- `.claude/rules/generated-artifacts.md` for the regenerate-and-commit rule that
  the false finding would have claimed was violated.
