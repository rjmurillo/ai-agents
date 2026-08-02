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
| GNU BRE: `grep`, `sed`, `git grep` with no `-E`/`-P` | alternation, as a GNU extension | the author wants alternation *and* GNU tooling is guaranteed |
| POSIX ERE: `grep -E`, `egrep` | **literal pipe** | the author wants a literal pipe |
| PCRE: `grep -P`, Python `re`, .NET `-replace` | **literal pipe** | the author wants a literal pipe |
| A shell pipeline (`bash`) | **a literal `\|` argument**; the pipe never happens and the shell reports no error | never |
| A `jq` or PowerShell pipeline | **syntax error** | never |
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
aaa|bbb
~~~

Same escaped pattern, opposite meanings, decided only by `-E`. Under ERE the
pattern is the literal string `aaa|bbb`, so only the third line matches. Under
BRE it is the alternation `aaa` OR `bbb`, so every line matches, including the
third, because it contains both substrings.

The BRE row is a GNU extension, not a portable guarantee. POSIX defines no
alternation operator for basic regular expressions, so a strictly conforming
`grep` is free to read `\|` as a literal pipe instead. Measured: GNU grep 3.11
and BusyBox grep both return 2 matches for `grep -c 'aaa\|bbb'` against `aaa`
and `bbb`, so both take the alternation reading. Treat the escaped BRE form as
GNU-only rather than as something the standard blesses.

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


## Evidence and inventory

The census at `8150dbb38`, the script that reproduces it, and the list of
known-remaining defects live in `decision-escaped-pipe-defect-inventory.md`. They are split out because they are
volatile: the inventory empties as fixes land, while the classification above
does not change.

## Refs

PR #4062 (session-log-fixer table to fence), PR #4063 (qa Pester examples),
issue #4079 (the separate prohibited-dash sweep, same "guard exists but only
inspects what it was pointed at" shape).
Existing guard: `test_provenance_table_has_no_escaped_pipes` in
`.claude/skills/ai-agents-docs-of-record/tests/test_structure_ai_agents_docs_of_record.py`.
Rule: `.claude/rules/canonical-source-mirror.md` for the mirror-regeneration
requirement when a `.claude/skills/` source changes.
