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
| R2 enumeration subset | A closed language or path enumeration omits a collection member. | high |
| R3 JSON key contents | A claimed noun disagrees with identifiers assigned to its JSON key. | high |
| R4 collection count | A count beside a named literal collection differs from its length. | high |

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
- A missing, `-`-led, or placeholder name suppresses nothing and yields a
  high `invalid_external_sdk_marker` finding.
- `claims.json` records `sdk`, `reason`, and `line`. Phase 3 counts suppressed
  symbols, and `summary` and `markdown` print one exemption line per file.
