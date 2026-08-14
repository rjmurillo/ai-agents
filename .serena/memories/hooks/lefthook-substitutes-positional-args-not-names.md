# Lefthook substitutes positional args, not names you invent

## Question

A pre-push job needs the remote git is pushing to. Does `{remote}` in a
lefthook `run:` body resolve to it?

## Conventional answer

The token reads like every other lefthook template (`{staged_files}`,
`{push_files}`), so it looks supported. `lefthook validate` accepts it and the
job runs green, which reinforces the reading.

## First-principles position

No. Lefthook 2.1.10 substitutes file templates and positional hook arguments
only. An unknown name is passed through verbatim, so the script receives the
seven characters `{remote}` as its argument.

## Evidence

Enumerated from the pinned binary that `uv` installs, not from recall:

```text
strings .venv/lib/python3.14/site-packages/lefthook/bin/lefthook-linux-x86_64/lefthook \
  | grep -oE '\{[a-z_]*files\}' | sort -u
{all_files}
{files}
{push_files}
{staged_files}
```

Scratch-repo probes on the same binary: `{0}` expands to all hook arguments,
`{1}`..`{n}` expand to positional arguments, an absent positional stays literal
(`lefthook run pre-push` with no args leaves `{1}` as `{1}`), and `{remote}`
passes through unchanged. A raw `.git/hooks/pre-push` confirmed the git side:
`git push -u origin main` and a bare `git push` both pass
`ARGS=[origin <url>]`, and `git push <url> main` passes `ARGS=[<url> <url>]`.
Argument 1 is always a remote name or a URL `git ls-remote` accepts.

## Decision

Pass `"{1}"`, quoted, to read the pre-push remote (issue #4634, PR for
`fix/4634-duplicate-push-ref-staleness`). Quoting mirrors `commit-message-policy`
at `lefthook.yml` line 10 and prevents word splitting on remote URLs.

## Why this stayed green for so long

`git ls-remote "{remote}" <ref>` fails, `push_ref_staleness.py` read the empty
result as "new branch, no race", and the job exited 0 on every push. A check
that cannot resolve its target must not report success:
`scripts/validation/push_ref_staleness.py::_resolve_remote` now warns on stderr
and falls back to `origin` when its argument is still a literal `{...}`.

The duplicate job hid it further. `lefthook.yml` declared `push-ref-staleness`
twice; the second copy passed no argument and worked, so the summary printed
one green line and one real result under the same name. Both config readers in
the test suite collapse duplicates:
`tests/test_lefthook_integration.py::_job_map` keeps the last copy and
`tests/ci/test_lefthook_ratchet_wiring.py::_find_job` returns the first.
`tests/ci/test_lefthook_config_integrity.py` now walks jobs as a list, so a
duplicate name in any hook fails, and scans the whole config for placeholder
tokens outside the enumerated set.
