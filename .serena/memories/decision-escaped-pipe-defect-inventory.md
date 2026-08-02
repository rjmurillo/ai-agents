# Escaped-pipe census and defect inventory at `8150dbb38`

Evidence annex for `decision-escaped-pipe-defect-lives-only-in-table-cells.md`. That memory holds the engine taxonomy, the
distinguishing test, and the remedy order. This file holds only the
measurement and the work list, which go stale as fixes land.

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
in Python `re`, so they are correct. The 2 Markdown ones are inline `grep -n`
commands outside any table, with no `-E` or `-P`, so they run under BRE where
`\|` is the alternation their authors intended. Both buckets are correct, which
is why the defect count for this row is 0.

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

- `.serena/memories/jq/jq-010-handling-pagination-results.md:110` (**second
  occurrence only**; the first is the documented token), then `:128,129,132,133,140,141`
- `.serena/memories/jq/jq-quick-reference.md:10` (**second occurrence only**;
  same reason), then `:28,29,32,33,40,41`

The first line in each jq list is the row that documents the pipe operator
itself, and it demonstrates the occurrence rule: the row holds **two**
occurrences with **opposite verdicts**.

    | `\|` | Pipe | `.[] \| .name` |
        ^                ^
        |                +-- a jq program; broken; DEFECT
        +------------------- the documented token; correct; do not touch

Verified: `jq '.[] \| .name'` exits 3 with `syntax error, unexpected
INVALID_CHARACTER`; `jq '.[] | .name'` returns `"alpha"`.

Regex alternations inside table cells:

- `.serena/memories/security/security-secret-detection.md:18,19,20` document
  `` (password\|pwd)=[^;]+ ``, `` (api_key\|apikey)=[A-Za-z0-9]+ ``, and
  `` -----BEGIN (RSA\|OPENSSH\|EC) PRIVATE KEY----- ``. These are broken in
  **every** engine, so no reading of them is correct. Under PCRE, Python `re`,
  and ERE, `\|` is a literal pipe, so the group matches the literal string
  `password|pwd` and never the intended alternation. Under BRE, `\|` would be
  alternation but `(`, `)`, and `+` are literals, so the pattern means
  `(password` OR `pwd)=[^;]+`. Verified in Python `re`:

      >>> re.search(r'(password\|pwd)=[^;]+', 'password=REDACTED')  -> None
      >>> re.search(r'(password\|pwd)=[^;]+', 'pwd=REDACTED')       -> None
      >>> re.search(r'(password|pwd)=[^;]+',  'password=REDACTED')  -> match

  This is the highest-severity entry in the inventory. The other rows mislead an
  agent into running a command that visibly fails. This one silently fails to
  detect the secrets it exists to catch, and a scanner built from it reports
  clean. Both GPT-5.6-sol and Gemini 3.1 Pro flagged these independently; the
  first pass of this memory recorded the GPT citation as unverifiable, which was
  a verification error on my part, not a bad citation.

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
