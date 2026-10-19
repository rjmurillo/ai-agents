# Line scoping with `--diff-base`

With `--diff-base`, a finding blocks only when its claim overlaps a line the
diff changed. The script reads changed new-side ranges from
`git diff --unified=0 --no-renames`. A fenced example spans its opening
through closing fence. A new file is changed on every line.

Three cases gate the whole file or the rest of it, because the diff cannot
show what changed:

- A renamed doc is an added file. A pure rename gates every claim in it, so a
  doc moved out of an unassessed path cannot carry unchecked claims.
- Adding, editing, or deleting a fence line re-pairs every later fence. Claims
  from the first changed fence to the end of the file are in scope.
- A symlinked doc, or a doc under a symlinked directory, is changed in full,
  because git diffs only the link text.

A claim in an untouched part of a changed doc still produces a finding. That
finding has `severity: "info"`, `original_severity` set to the old value, and
`in_diff: false`. It appears in the report and never affects the gate or exit
code. In-scope findings carry `in_diff: true`. Without `--diff-base`, every
claim gates and no finding carries `in_diff`.
