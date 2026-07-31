# The escaped-pipe defect lives only in table cells

## Question

A Markdown table cell cannot hold a bare `|`, so authors write `\|`. Agents read
skill and memory files raw, not rendered, so an agent that copies such a cell
gets a backslash the shell rejects. How much of the corpus is affected, and
which occurrences are actually wrong?

## Conventional answer

"Escaped pipes in shipped agent-facing files are a defect; find and fix them."

Two frontier models independently applied that framing to this repo and both
produced wrong answers. One proposed rewriting `str \| None` in an API
parameter table. The other proposed unescaping a `grep -E "a\|b"` alternation,
which would have broken a working command. The framing is wrong because `\|`
is legal and load-bearing in several contexts that have nothing to do with
Markdown escaping.

## First-principles position

`\|` means at least four different things. Only one of them is a defect.

| Context | Meaning of `\|` | Verdict |
|---------|-----------------|---------|
| Markdown table cell containing a shell, jq, or PowerShell pipeline | Markdown escape; the shell never pipes | **DEFECT** |
| POSIX BRE / `grep -E` / `git grep` pattern | Alternation operator; required | Correct |
| Python raw-string regex, PowerShell `-replace` | Escaped literal pipe; required | Correct |
| Markdown prose describing a type union (`str \| None`) | Markdown escape around a type, never executed | Correct |
| A table row whose subject *is* the pipe operator | Markdown escape around the documented token | Correct |
| Jinja-style template filter (`{{ branch \| sanitize }}`) | Markdown escape around template syntax, not shell | Correct |

The distinguishing test is not the syntax. It is: **would an agent paste this
into a shell?** A type annotation, a regex alternation, and a template filter
all fail that test, so their escaping is inert.

**The unit of classification is the occurrence, not the cell or the file.** One
cell can hold both. `.claude/skills/ai-agents-change-control/references/provenance.md:21`
reads:

    | ... | `ls .agents/retrospective/ \| grep -E "908\|1187\|1887\|1965\|2205"` |

The first `\|` is a shell pipeline and is broken. The four inside the quoted
pattern are ERE alternation and are correct. A file-level or cell-level
verdict gets this row wrong in both directions.

## The failure is worse than a clean error

A pasted escaped pipe does not fail loudly. Bash does not see an operator at
all; it passes `\|` and everything after it as **arguments to the first
command**. Measured on bash 5.2:

    $ bash -c 'ls . \| wc -l'
    ls: cannot access '|': No such file or directory
    ls: cannot access 'wc': No such file or directory
    .:
    total 0
    -rw-rw-r-- 1 richard richard 0 Jul 30 20:36 a
    ...
    rc=2

The pipe silently does not happen, and the command still emits a plausible
directory listing on stdout alongside the errors on stderr. An agent that
copies `ls .agents/retrospective/ \| wc -l` expecting a count receives a file
listing. If it reads stdout without checking the exit code it proceeds on
garbage.

The escape also **buries the real error**. `ls /nonexistent \| wc -l` reports
three failures, only the first of which is the actual problem; the other two
are artifacts of the escape. That masking is the mechanism the existing
regression guard was written against.

## Prior art: a scoped guard already exists

`.claude/skills/ai-agents-docs-of-record/tests/test_structure_ai_agents_docs_of_record.py`
already contains `test_provenance_table_has_no_escaped_pipes`, which asserts
`"\\|" not in row` for every row of that one skill's provenance table. The
defect class was recognized and fixed there, but the guard is scoped to a
single table in a single skill. It does not generalize, and nothing extends it
to the rest of the corpus.

That guard is also the third remedy shape, and the strongest one: **keep the
table and add a structural test that forbids the escape in it.** Prefer it
whenever the table is load-bearing.

## Evidence

Census against `origin/main` at `8150dbb38`, over `.serena/memories`,
`.claude/skills`, `.claude/agents`, `.claude/rules`, `.claude/commands`:

- **in fenced code blocks: 14 occurrences, 0 defects**
- in Markdown table cells: 61 occurrences, defects inventoried below
- elsewhere (Python `.py` raw-string regexes): 26 occurrences, 0 defects

Reproduce:

~~~python
import subprocess
REF = "origin/main"
roots = [".serena/memories", ".claude/skills", ".claude/agents",
         ".claude/rules", ".claude/commands"]
files = subprocess.run(["git", "ls-tree", "-r", "--name-only", REF, *roots],
                       capture_output=True, text=True).stdout.split()
for f in files:
    blob = subprocess.run(["git", "show", f"{REF}:{f}"], capture_output=True)
    try:
        lines = blob.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        continue
    fence = False
    for i, line in enumerate(lines, 1):
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if "\\|" in line:
            where = "fence" if fence else "table" if line.strip().startswith("|") else "other"
            print(f"{where}\t{f}:{i}\t{line.strip()[:100]}")
~~~

Do not census with `grep '\|'`. That is an empty BRE alternation and matches
every line in every file. Use `grep -F '\|'`.

The zero-in-fences result is the structural finding: **a fence removes the
escaping requirement, so the defect cannot exist inside one.** That is why the
remedy is structural rather than a search-and-replace.

## Decision

Fix by structure, not substitution. Three remedies, in order of preference:

1. **Keep the table, add a structural test** that asserts no `\|` in its rows.
   This is what `ai-agents-docs-of-record` does. Best when the table is
   load-bearing, because it makes the fix permanent.
2. **Convert to a fenced block.** A short procedural list of commands converts
   cleanly; column labels survive as comments. This is what PR #4062 did to
   `session-log-fixer`, replacing a 6-row table with one `powershell` fence.
   A fence removes the escaping requirement structurally, so the defect cannot
   be reintroduced by a later edit.
3. **Replace the command with a pipe-free equivalent** when a wide N-column
   lookup table must stay and a fence would destroy it.

Never unescape in place. Removing the backslash from a table cell splits the
cell and silently corrupts the row.

## Known-remaining defects at `8150dbb38`

Shell pipelines inside table cells:

- `.claude/agents/pr-comment-responder.md:75`
- `.claude/skills/ai-agents-change-control/references/provenance.md:21` (first occurrence only)
- `.claude/skills/ai-agents-failure-archaeology/SKILL.md:164,165`
- `.claude/skills/ai-agents-generation-and-release/SKILL.md:229`
- `.claude/skills/ai-agents-research-frontier/SKILL.md:51` (4 occurrences)
- `.claude/skills/ai-agents-research-methodology/SKILL.md:277`

jq programs inside table cells:

- `.serena/memories/jq/jq-010-handling-pagination-results.md:128,129,132,133,140,141`
- `.serena/memories/jq/jq-quick-reference.md:28,29,32,33,40,41`

In both jq files the row documenting the pipe operator itself is correct and
must not be touched. It is the row whose first cell is the escaped pipe and
whose second cell reads `Pipe`.

PowerShell pipelines in `.claude/agents/qa.md` and
`.serena/memories/quality/quality-test-criteria-patterns.md` are addressed by
PR #4063.

## Refs

PR #4062 (session-log-fixer table to fence), PR #4063 (qa Pester examples),
issue #4079 (the separate prohibited-dash sweep, same "guard exists but only
inspects what it was pointed at" shape).
Existing guard: `test_provenance_table_has_no_escaped_pipes` in
`.claude/skills/ai-agents-docs-of-record/tests/test_structure_ai_agents_docs_of_record.py`.
Rule: `.claude/rules/canonical-source-mirror.md` for the mirror-regeneration
requirement when a `.claude/skills/` source changes.
