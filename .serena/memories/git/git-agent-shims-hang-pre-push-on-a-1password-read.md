# The 1Password-backed agent shim hangs a push for about 10 minutes

## What happens

On Richard's host, `claude` and `copilot` resolve first to shims under `~/.local/share/agent-shims/`. Observed 2026-09-29, `type -a claude` lists `agent-shims/claude` ahead of `~/.local/bin/claude`.

A shim reads a secret from 1Password. With no TTY and no unlock, the read blocks. The pre-push hook runs `tests/e2e/test_plugin_load_smoke.py`, which calls both CLIs. Each call waits for its full timeout, so the push hangs about 10 minutes and then fails on a timeout unrelated to the diff. Issue #6000 tracks the test side.

## Workaround

Drop the shim directory from PATH for the push command only. All hooks still run.

```bash
PATH=$(echo $PATH | tr ':' '\n' | grep -v agent-shims | paste -sd:) git push
```

The prefix applies to that one command. The shell PATH stays unchanged.

## Live evals use the native CLI

The native `claude` CLI at `~/.local/bin/claude` runs live evals when the shims
hang on a locked or signed-out 1Password. Strip `agent-shims` from PATH and the
native CLI uses its stored login. Same prefix as above, applied to the eval
command. Evidence: PRs #6086 and #6088.

## Source

P1 triage session 2026-09-29. Related: issue #6000.
