# Script design rules

Owner of the rules for scripts bundled in a skill's script directory. Read
it before you add or change a script, and when you review one. An agent runs
these scripts without a person at the keyboard, so every rule below removes a
way for a run to hang, guess, or lose information.

Source: the agentskills.io guide "Using scripts in skills", adjusted to the
runtime contract this repository ships.

## Rules every script follows

- **Never wait for a person.** No `input()`, no `getpass`, no confirmation
  prompt. Take every value from a flag, an environment variable, or stdin. When
  a script reads stdin by default and stdin is a terminal, stop with exit 2 and
  say how to pass the input:

  ```python
  if args.file is None and sys.stdin.isatty():
      print("tool: no input. Pass FILE or pipe text on stdin.", file=sys.stderr)
      return 2
  ```

- **Make `--help` the interface.** Use `argparse`, never hand-parsed `argv`, so
  `--help` prints usage and exits 0 and never runs the action. Give the parser a
  one-line `description`, a `help=` on every flag, and an `epilog` with one or
  two example commands and the exit codes. Use `RawDescriptionHelpFormatter` so
  the epilog keeps its line breaks.
- **Split the streams.** Put the result on stdout, in a form the next step can
  parse. Put progress, warnings, and errors on stderr. A caller that captures
  stdout must get only the result.
- **Write errors an agent can act on.** Say what failed, what the script
  expected, and what to try next. "unknown command: bogus; expected one of
  path, check, restore, cleanup" beats "bad input".
- **Use the shared exit codes.** 0 ok, 1 logic, 2 config or usage, 3 external,
  4 auth (ADR-035). Document them in the module docstring or epilog and in the
  `SKILL.md` table row for the script.
- **Bound the output.** A script that can print an unbounded list takes a
  `--limit`, a `--max-lines`, or an `--output FILE` flag, and says in `--help`
  what the default is. Agent harnesses truncate large output, and a truncated
  result looks like a complete one.

## Rules for scripts that change state

A script that writes a file, calls a mutating API, or deletes anything also:

- **Takes `--dry-run`.** It runs every read and every validation, then reports
  what it would do and skips only the write. Name the planned action in the
  result (`would_reopen`, `would_assign`) and set `dryRun: true`, so a caller
  can tell a plan from a change. `dryRun` is the key the shipped GitHub scripts
  use (`close_pr.py`, `merge_pr.py`, `post_pr_comment_reply.py`); a script that
  already shipped `DryRun` or `dry_run` keeps its key, so a caller does not break.
- **Keeps the same exit codes under `--dry-run`.** Invalid input, a missing
  target, or a refused precondition fails the same way. A dry run that passes
  where the real run fails is worse than none.
- **Stays idempotent.** A second run on the same target reports "already done"
  and changes nothing.
- **Defaults to the safe action.** A destructive mode needs its own flag. The
  default never overwrites or deletes.

## Dependencies and invocation

- **Ship stdlib-only scripts and run them with `python3`.** The plugin consumer
  has no guaranteed `uv`, so a shipped script's import closure is the standard
  library plus the plugin's own modules (`plugin-self-containment` rule, MUST
  4; the repository's python3 entry-point check governs entry points).
  A PEP 723 `# /// script` block with `uv run` would change that runtime
  contract, so a shipped script does not carry one.
- **Guard an optional third-party import.** Import it inside the function that
  needs it, catch `ImportError`, print the package name and the install command
  on stderr, and exit non-zero. Never let a bare traceback be the message.
- **Resolve paths from the plugin root.** `SKILL.md` invokes a script as
  `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/<script path>"`.
  Do not write a bare relative path; it resolves only when the working
  directory happens to match.

## Listing the scripts

`SKILL.md` lists every entry-point script with its purpose, key flags, and exit
codes, and tells the agent when to run it. A script the body does not name is a
script the agent never finds. When the table would push `SKILL.md` past its size
cap, put the full table in `references/` and keep one line in `SKILL.md` that
names each script and the file that holds its parameters.

## Tests

Every behavior above gets a positive, a negative, and an edge test: `--help`
exits 0 and creates nothing, an unknown flag exits 2 on stderr with empty
stdout, a terminal stdin exits 2 without reading, and `--dry-run` makes no write
call while a real run does.
