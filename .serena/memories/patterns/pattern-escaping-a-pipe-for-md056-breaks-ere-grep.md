# Escaping a pipe to satisfy MD056 breaks `grep -E` alternation

## Claim

A markdown table cell containing a shell command with `grep -E 'A|B'` trips
markdownlint MD056 (inconsistent column count), because the table parser splits
on `|` even inside backticks. The reflexive fix is to escape it as `\|`. That
fixes the table and silently breaks the command: in POSIX ERE, `|` is
alternation and `\|` escapes it to a **literal pipe**, so the pattern stops
matching either branch.

The failure is invisible in review. The command still runs, still exits 0 on
`grep -c`, and returns a plausible number.

## Evidence

Fixture, three lines, two of which should match:

```text
**Status**: [COMPLETE]
**Status**: [WONTFIX]
**Status**: [PENDING]
```

Patterns passed through `grep -f` so no shell quoting can distort them
(`cat -A` confirmed exactly one backslash before the pipe):

| Command | Count | Correct |
|---------|-------|---------|
| `grep -E` with `\|` | 0 | no |
| `grep -E` with bare pipe | 2 | yes, but the pipe trips MD056 |
| `grep` (BRE) with `\|` | 2 | yes |
| `grep -c -e A -e B` | 2 | yes |

Isolating probe: `grep -Ec 'X\|Y'` against the line `X|Y` returns **1**,
proving `\|` matches a literal pipe under `-E`.

## The inverse asymmetry

BRE (grep with no `-E`) is the mirror image. There, a bare `|` is literal and
`\|` is GNU alternation. So the same escape is *correct* without `-E` and
*wrong* with it. Never port a pattern between the two dialects by eye.

## Fix

Use repeated `-e` patterns. This removes the pipe from the source entirely, so
MD056 is satisfied without touching regex semantics, and it works in both
dialects:

```bash
grep -c -e "^\*\*Status\*\*: \[COMPLETE\]" -e "^\*\*Status\*\*: \[WONTFIX\]" "$FILE"
```

## Why this matters here

The affected command was a gate: it counted resolved review threads to decide
whether work was complete. With the escaped pipe it counted 0 forever, so the
gate could never pass. A fix that satisfies one checker can break the thing
being checked.

Caught during a merge of `fix/4034-pr-comment-responder-status-greps`, where
two agents had independently fixed the same MD056 break. One used `\|`, the
other used two `-e` patterns. Only a fixture distinguished them.

## Rule

When a lint fix edits the inside of a command, run the command against a
fixture with a known expected count before shipping. Reading the diff is not
enough: both versions look reasonable.
