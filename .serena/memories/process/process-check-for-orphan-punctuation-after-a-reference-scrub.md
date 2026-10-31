# Check for Orphan Punctuation After a Reference Scrub

**Category**: Process
**Source**: 2026-10-31, PR #7007, `.project-toolkit/retrospective/2026-10-31-pr-7007-drive-to-merge.md`
**Atomicity**: 75%

## Statement

After deleting parenthetical refs, grep templates for lines starting with comma or '#.'.

## Why

Deleting `(issue #N)` leaves the punctuation that followed it. When the reference
ended a line, that punctuation wraps onto the next line. The reference gate checks
for references, not for what the deletion left behind.

## Evidence

- `templates/skills/sync.SKILL.md.tmpl:31` began with `    , so the dependency`.
- `templates/skills/pr-autofix.SKILL.md.tmpl:942` began with `#. Source the answer`.
- The owner caught both in review. Fixed in `738d5dbbae` (2026-10-31).

## Check

```bash
git grep -nE '^\s*(#\s*)?[,.;]\s' -- templates/
```

Read each hit before fixing it. Colon is left out on purpose: the shell `:` builtin
starts lines in 7 legitimate template lines, such as
`templates/skills/repository-completion-proof.SKILL.md.tmpl:54`. With colon left out,
the check returns 0 hits on main at `78e8145660` (2026-10-31).
