# Line scoping with `--diff-base`

With `--diff-base`, a finding blocks only when its claim overlaps a line the
diff changed. The script reads changed new-side ranges from
`git diff --unified=0 --no-renames`. A fenced example spans its opening
through closing fence. A new file is changed on every line.

Three cases gate the whole file or the rest of it, because the diff cannot
show what changed:

- A renamed doc is an added file. A pure rename gates every claim in it, so a
  doc moved out of an unassessed path cannot carry unchecked claims.
- Adding or removing a column-0 backtick fence line flips fence pairing only
  where the count of such changed lines above is odd. Only those stretches come
  into scope, so a balanced new block leaves later examples out of scope. A
  changed tilde or indented fence still puts the rest of the file in scope. A
  change to an ignored external-sdk marker line, or to the first fence-like
  line above it, keeps the file's `unresolved_symbol` findings in scope,
  because only those edits can flip the marker's status. Each such finding
  carries `scope_reason: "ignored_external_sdk_marker"` and
  `scope_marker_line`.
- A symlinked doc, or a doc under a symlinked directory, is changed in full,
  because git diffs only the link text.

A claim in an untouched part of a changed doc still produces a finding. That
finding has `severity: "info"`, `original_severity` set to the old value, and
`in_diff: false`. It appears in the report and never affects the gate or exit
code. In-scope findings carry `in_diff: true`. Without `--diff-base`, every
claim gates and no finding carries `in_diff`.

## Same-PR mode

A PR that changes prose and code can leave the prose wrong about the code beside
it, and the scan above never sees that: it reads documentation files and checks
code examples. Same-PR mode runs when you pass `--same-pr`, which needs
`--diff-base` (without it the script exits 2). Run it before you open a PR
whenever the branch changes both prose and code:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do
  if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then
    exec python3 "$d/lib/ptk_run.py" skills/doc-accuracy/scripts/doc_accuracy.py \
      --target . --diff-base origin/main --same-pr
  fi
done; exit 2 )
```

**What it reads.** The changed hunks of files with a known suffix, up to 1 MB
each. A changed line is prose when it is a `.md`, `.mdx`, or `.tmpl` line (table
rows included), a Python docstring or comment, or a `.json`, `.yaml`, or `.yml`
string of at least four words. Changed lines in `.py`, `.cs`, `.ts`, `.tsx`,
`.js`, `.ps1`, and `.sh` files are code: Python lines are tagged with the
function or class that holds them, or `<module>` when none does, and other code
files get one `<module>` region. Files with any other suffix are counted as
skipped and never read. Each prose line is paired with up to six changed code
symbols: the same file first, then symbols whose names share the most words with
the line (plus five when the line names the file), then the longest shared
directory prefix. The scan reads the working tree, so commit before you run it.

**Rules.** Each rule needs a paired script or record it can identify, and stays
quiet when it cannot judge. A finding carries the rule id, the prose file and
line, the paired code file and line, evidence, and a severity.

| Rule | Fires when | Severity |
|------|------------|----------|
| R1 exit-code set | A touched exit table omits a literal process exit. Dynamic exits remain unjudged. | high |
| R2 enumeration subset | A closed language or path enumeration omits a collection member. A path list binds only when its line names the collection or its script, or sits in that script. | high |
| R3 JSON key contents | JSON prose names a value that its paired writer never assigns. | high |
| R4 collection count | A count beside a named literal collection differs from its length. | high |

R2 and R4 need a file reference for collections named in lowercase.
Prose within the collection's own script also counts as a file reference.
R4 treats empty lowercase collections as initializers.
R3 prefers a writer named by the prose or found in its own file.
When prose names no script, R3 needs one source file for the key.

Touched exit tables include unchanged rows.
Explicit script paths can resolve unchanged literal collections.
Other unchanged behavior remains a review task.

The repository pre-PR integration also loads `nl_cardinality.py`.
It checks changed `.md`, `.tmpl`, JSON, and YAML counts against explicit structures.
Installed plugins run R1 through R4 without that repository integration.

**Checklist.** Any other changed prose that looks like a verifiable claim (a
number or count word, "only", "identical", "every", "never", a backticked symbol,
Exit, JSON, raises, or returns vocabulary) is written to `same-pr-checklist.json`
with its reasons and paired code locations. Nothing that looks checkable is
dropped. The Phase 4 prompt takes this file as input: verify each entry against
its paired code, and read the unchanged files the prose depends on. Unchanged prose naming changed functions, flags, or deleted headings also enters the checklist.
Deleted-heading references stay within the same skill or document directory.

**Artifacts and gate.** `same-pr-findings.json` and `same-pr-checklist.json` land
in the output directory, and `--format summary` prints their counts. A finding at
or above `--severity-threshold` makes the gate FAIL (exit 10), like any other
finding.

## Documenting another product's SDK

The marker is `<!-- doc-accuracy: external-sdk <name> -- <reason> -->`.

- `<name>` is required. A missing `<reason>` stays valid and records "".
- Put it right after the H1. It is honored only when `<!--` starts at column 0
  and no earlier line contains three backticks or tildes. A marker below any
  code fence is ignored. The first valid marker wins.
- It silences `unresolved_symbol` for that file only. Other checks still run.
- Without a marker, a code example's own declared names are not reported as
  unresolved. In C# these are types, namespaces, properties, and methods with
  an access modifier. In Python they are classes and functions. In JavaScript
  and TypeScript they are classes, interfaces, enums, functions, and type
  aliases (`type X =`), so `import type X` and `import { type X }` stay claims.
  A declaration counts only at the start of a line, after any attributes and
  modifiers. Comments, strings, and text in the middle of a line, such as a
  regex literal, declare nothing. A C# method needs a return type before its
  name, and a modifier word never counts as one. So a constructor or a
  conversion operator does not declare its type. Each skip is counted under
  `declared_name_suppressed`, which maps a doc path to its count. Method
  signature claims get no exemption.
- A missing, `-`-led, or placeholder name suppresses nothing and yields a
  high `invalid_external_sdk_marker` finding.
- `claims.json` records `sdk`, `reason`, and `line`. Phase 3 counts suppressed
  symbols, and `summary` and `markdown` print one exemption line per file.
