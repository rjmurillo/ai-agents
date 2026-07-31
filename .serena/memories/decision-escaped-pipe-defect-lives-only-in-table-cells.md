# The escaped-pipe defect lives only in table cells

> Scope of the title: this is the **measured** result of the census below, not
> a law. Every defect found sat in a table cell, because that is the only place
> Markdown *forces* the escape. Nothing prevents the same broken text inside a
> fence; none was found there.

## Question

A Markdown table cell cannot hold a bare `|`, so authors write `\|`. Agents read
skill and memory files raw, not rendered, so an agent that copies such a cell
hands the escaped text to an engine that may read it differently than the
author meant. How much of the corpus is affected, and which occurrences are
actually wrong?

## Conventional answer

"Escaped pipes in shipped agent-facing files are a defect; find and fix them."

That framing is wrong in one direction, and the correction to it was wrong in
the other. Two frontier models applied the blanket framing and produced wrong
answers: one proposed rewriting `str \| None` in an API parameter table, which
is inert prose. The first version of this memory over-corrected, ruling that
regex alternation is always correct and citing `grep -E "a\|b"` as an example
to preserve. That is backwards: in ERE, `\|` is a literal pipe, so unescaping
that command *fixes* it. The correct rule is neither blanket-fix nor
blanket-preserve; it is per-occurrence and engine-aware.

## First-principles position

`\|` is not one thing. Its meaning is set by **the engine that finally consumes
the string**, and the engines disagree.

| Engine that consumes the string | `\|` means | Escaped form is correct when |
|---------------------------------|-----------|------------------------------|
| POSIX BRE: `grep`, `sed`, `git grep` with no `-E`/`-P` | alternation | the author wants alternation |
| POSIX ERE: `grep -E`, `egrep` | **literal pipe** | the author wants a literal pipe |
| PCRE: `grep -P`, Python `re`, .NET `-replace` | **literal pipe** | the author wants a literal pipe |
| A shell, jq, or PowerShell pipeline | **syntax error** | never |
| A Jinja filter | **syntax error** | never |
| Nothing; it is prose (`str \| None`) | renders as `|` | always |

So the question is never "is this regex or shell?" It is the **distinguishing
test**: *does `\|` mean what the author intended, in the engine that will
finally consume it?* Note that "an engine" includes a template renderer and a
config parser, not just a shell. Getting that scope wrong is how the first
version of this memory wrongly cleared the Jinja rows inventoried below.

The escape is *mandatory* in a Markdown table cell, because a bare `|` splits
the cell. That is why the escape is not itself the defect and why unescaping in
place is never the fix. The defect is that a reader who copies the raw cell
hands the escaped text to an engine that reads it differently than the author
meant.

Measured on GNU grep 3.11:

~~~text
$ printf 'aaa\nbbb\naaa|bbb\n' | grep -E 'aaa\|bbb'
aaa|bbb
$ printf 'aaa\nbbb\naaa|bbb\n' | grep 'aaa\|bbb'
aaa
bbb
~~~

Same escaped pattern, opposite meanings, decided only by `-E`.

**The unit of classification is the occurrence, not the cell or the file.** One
cell can hold occurrences with different verdicts.
`.claude/skills/ai-agents-change-control/references/provenance.md:21` reads:

    | ... | `ls .agents/retrospective/ \| grep -E "908\|1187\|1887\|1965\|2205"` |

All five are defects, for two different reasons. The first is a shell pipeline
that never pipes. The other four sit inside `grep -E`, where `\|` is a literal
pipe, so the pattern searches for the single string `908|1187|1887|1965|2205`
and matches nothing:

~~~text
$ ls .          # 908-a.md 1187-b.md 1887-c.md other.md
$ ls . | grep -E "908\|1187\|1887"   ; echo rc=$?
rc=1
$ ls . | grep -E "908|1187|1887"     ; echo rc=$?
1187-b.md
1887-c.md
908-a.md
rc=0
~~~

Had this row used plain `grep`, those four would have been correct. This is the
row that makes the occurrence-level rule non-negotiable, and it is the row an
engine-blind reading gets wrong in both directions.

## The failure is worse than a clean error

A pasted escaped pipe does not fail loudly. Bash strips the backslash during
quote removal and never sees an operator, so the first command receives a
literal `|` argument followed by the rest of the intended pipeline. Measured on
GNU bash 5.2.21, with `-x` to show the real argv:

    $ bash -x -c 'ls . \| wc -l'
    + ls . '|' wc -l
    ls: cannot access '|': No such file or directory
    ls: cannot access 'wc': No such file or directory
    .:
    total 0
    -rw-rw-r-- 1 richard richard 0 Jul 30 20:36 a
    rc=2

Note the trace: `ls` is handed `|`, not `\|`. The pipe silently does not happen,
and the command still emits a plausible directory listing on stdout alongside
the errors on stderr. An agent that copies `ls .agents/retrospective/ \| wc -l`
expecting a count receives a file listing. If it reads stdout without checking
the exit code it proceeds on garbage.

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

Census pinned to commit `8150dbb38`, over `.serena/memories`, `.claude/skills`,
`.claude/agents`, `.claude/rules`, `.claude/commands`. Reported two ways,
because the classification unit is the occurrence but a per-line view is what
you triage from:

| Where | Lines | Occurrences | Defects found |
|-------|-------|-------------|---------------|
| Fenced code blocks | 14 | 30 | 0 |
| Markdown table cells | 61 | 76 | inventoried below |
| Elsewhere | 26 | 69 | 0 |

The "elsewhere" bucket is 24 `.py` lines and 2 `.md` lines. The Python ones are
raw-string regexes matching a literal `|` in Markdown, which is what `\|` means
in Python `re`, so they are correct.

Reproduce:

~~~python
import subprocess, collections
REF = "8150dbb38"
roots = [".serena/memories", ".claude/skills", ".claude/agents",
         ".claude/rules", ".claude/commands"]
files = subprocess.run(["git", "ls-tree", "-r", "--name-only", REF, *roots],
                       capture_output=True, text=True).stdout.split()
lines, occ = collections.Counter(), collections.Counter()
for f in files:
    blob = subprocess.run(["git", "show", f"{REF}:{f}"], capture_output=True)
    try:
        body = blob.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        continue
    fence = False
    for i, line in enumerate(body, 1):
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        n = line.count("\\|")
        if n:
            where = "fence" if fence else "table" if line.strip().startswith("|") else "other"
            lines[where] += 1
            occ[where] += n
            print(f"{where}\t{f}:{i}\t{line.strip()[:100]}")
print("lines", dict(sorted(lines.items())), "occurrences", dict(sorted(occ.items())))
~~~

Do not census with `grep '\|'`. That is an empty BRE alternation and matches
every line in every file. Use `grep -F '\|'`.

Every fenced occurrence in this census turned out to be correct: BRE
alternations in `grep`/`git grep`, `grep -P` and Python patterns wanting a
literal pipe, and one .NET `-replace` stripping a literal pipe. **That is a
measurement, not a guarantee.** A fence removes the *reason* to escape, but
nothing stops an author from writing or keeping `\|` inside one, and a fenced
escaped pipeline breaks exactly like a table one. A fence passes its body
through verbatim, backslash included:

    $ cat fencetest.md
    ```bash
    ls . \| wc -l
    ```
    $ pandoc -f gfm -t plain fencetest.md
        ls . \| wc -l

Claiming the defect "cannot exist inside a fence" would be false. What is true
is that conversion removes the requirement that produced the escape, so the
defect stops being *introduced by the format*.

## Decision

Fix by structure, not substitution. Three remedies, in order of preference:

1. **Keep the table, add a structural test** that asserts no `\|` in its rows.
   This is what `ai-agents-docs-of-record` does. Best when the table is
   load-bearing, because it makes the fix permanent.
2. **Convert to a fenced block.** A short procedural list of commands converts
   cleanly; column labels survive as comments. This is what PR #4062 did to
   `session-log-fixer`, replacing a 6-row table with one `powershell` fence.
   A fence removes the *requirement* to escape, so the format stops producing
   the defect. It does not prevent someone writing `\|` inside the fence
   anyway, which is why remedy 1 is preferred where the table must stay.
3. **Replace the command with a pipe-free equivalent** when a wide N-column
   lookup table must stay and a fence would destroy it.

Never unescape in place. Removing the backslash from a table cell splits the
cell and silently corrupts the row.

## Known-remaining defects at `8150dbb38`

Shell pipelines inside table cells:

- `.claude/agents/pr-comment-responder.md:75`
- `.claude/skills/ai-agents-change-control/references/provenance.md:21` (**all
  five occurrences**, for two different reasons: one broken shell pipeline plus
  four inside `grep -E`, where `\|` is a literal pipe and the pattern matches
  nothing)
- `.claude/skills/ai-agents-failure-archaeology/SKILL.md:164,165`
- `.claude/skills/ai-agents-generation-and-release/SKILL.md:229`
- `.claude/skills/ai-agents-research-frontier/SKILL.md:51` (4 occurrences)
- `.claude/skills/ai-agents-research-methodology/SKILL.md:277`

jq programs inside table cells:

- `.serena/memories/jq/jq-010-handling-pagination-results.md:110,128,129,132,133,140,141`
- `.serena/memories/jq/jq-quick-reference.md:10,28,29,32,33,40,41`

The first line in each jq list is the row that documents the pipe operator
itself, and it demonstrates the occurrence rule: the row holds **two**
occurrences with **opposite verdicts**.

    | `\|` | Pipe | `.[] \| .name` |
        ^                ^
        |                +-- a jq program; broken; DEFECT
        +------------------- the documented token; correct; do not touch

Verified: `jq '.[] \| .name'` exits 3 with `syntax error, unexpected
INVALID_CHARACTER`; `jq '.[] | .name'` returns `"alpha"`.

PowerShell pipelines inside table cells:

- `.serena/memories/powershell/powershell-observations.md:69` reads
  `` @($raw) \| Where-Object { $_ } ``. `pwsh` rejects it with
  `ParserError: Unexpected token '\'`. Not covered by any open PR.

Template filters inside table cells:

- `.serena/memories/git/git-worktree-worktrunk-hooks.md:74,75` document
  `` {{ branch \| sanitize }} `` and `` {{ branch \| hash_port }} ``. The memory
  does not name the engine, but `{{ var | filter }}` is Jinja-family syntax and
  every engine in that family treats `\` as an illegal character there.
  Verified on Jinja2: the escaped form raises
  `TemplateSyntaxError: unexpected char '\'`, the bare form renders.
  These were classified "correct" in the first version of this memory on the
  reasoning that they are not shell commands. That reasoning was wrong, and it
  is why the distinguishing test above is phrased around *any* engine, not just
  a shell.

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
