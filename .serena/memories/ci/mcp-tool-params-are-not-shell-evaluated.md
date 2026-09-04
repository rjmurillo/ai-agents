# MCP Tool String Params Are Not Shell-Evaluated

## The mistake

Passing `$(cat /path/to/file.md)` as the `body` argument to
`mcp__github__update_pull_request` or `mcp__github__create_pull_request`
sends the literal string `$(cat /path/to/file.md)` as the PR body.
There is no shell in between: MCP tool calls pass their string arguments
verbatim to the GitHub API. Nothing expands `$(...)`, `` `...` ``, or `$VAR`.

## Why it is easy to make twice

The failure is silent at the call site. `update_pull_request` returns a
normal-looking success payload (`{"id": ..., "url": ...}`), identical to what
a correct call returns. The only way to catch it is to read the PR back with
`pull_request_read` and look at the actual `body` field.

Confirmed recurring in one session (2026-08-27): made once on PR #5356
(caught by reading the PR back), then made again roughly 20 minutes later on
PR #5357 with the exact same `$(cat <file>)` pattern, despite already knowing
about the first instance. The instinct to write a big body to a scratch file
and shell-substitute it in is a bash reflex that does not carry over to a
tool call.

## Fix

Read the file's content with the `Read` tool and paste the actual text into
the `body` (or `body-file`-less) parameter. There is no `body-file` parameter
on these MCP tools; the full text must go inline. After every
`update_pull_request` / `create_pull_request` call with a body sourced from a
file, immediately call `pull_request_read` (`method: "get"`) and confirm the
returned `body` is not a literal `$(...)` string before moving on.

## Related

- `.serena/memories/ci/ci-validate-pr-is-many-gates-only-some-read-the-body.md`.
  The PR-description validation gate this mistake most often gets caught by
  (a literal `$(cat ...)` string still often happens to pass description
  validation, since it mentions no files at all, so do not rely on that gate
  to catch this class of error).
