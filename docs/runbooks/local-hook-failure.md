# Local hook or pre-push failure

Lefthook runs the pre-commit, commit-msg, pre-merge-commit, and pre-push gates
defined in [lefthook.yml](../../lefthook.yml). This runbook covers a commit or
push that a hook blocks.

## Symptom

- `git commit` or `git push` fails, and the output ends with a block that names
  the hook, each failed job, and a rerun command.
  `scripts/validation/lefthook_failure_report.py` prints that block.
- Every git command fails with `fatal: this operation must be run in a work tree`.
- Git reports a bad line in `packed-refs`.
- The hook does not run at all.
- The pre-push `python-tests` job fails PowerShell tests with
  `You must install or update .NET to run this application`, or with
  `PowerShell parser exited 150`. The same tests fail on a clean `main`.

## Confirm

Check the hook install and the repository state. These commands only read state:

```bash
uv run --frozen lefthook check-install
uv run --frozen python scripts/validation/check_git_hook_health.py
uv run --frozen python scripts/validation/check_repo_health.py
```

A healthy checkout prints `4 of 4 found` from the hook health check and
`none set true` from the repository health check.

If PowerShell tests fail, these checks can pass while `pwsh` still cannot
start. Run the `pwsh` check under Recover as well.

## Recover

**A job failed.** Read the job output above the summary block. It names the file,
line, and finding. Fix the cause, then run the rerun command from the summary
block. It reruns only that job. For a pre-push job the command pipes the pushed
ref lines into the runner, in this shape:

```bash
printf '%s\n' '<ref lines>' | python3 scripts/validation/lefthook_runner.py run pre-push --job <job name> origin <remote url>
```

Copy the exact line from your output instead of typing it.

Run the full local gate before you push again:

```bash
uv run python scripts/validation/pre_pr.py
```

**The hooks are missing or stale.** Reinstall them:

```bash
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

**Git says the repository is bare.** Something set `core.bare = true` in a git
config scope. Run `check_repo_health.py` from the Confirm step and apply the
repair it prints. It names the scope that holds the bad value. The plain
`git config core.bare false` writes only the local config, so it cannot clear a
worktree, global, or system value. See
[GOTCHAS.md](../../.agents/governance/GOTCHAS.md) for the background.

**`packed-refs` has blank lines.** This step writes. `repair_packed_refs.py`
rewrites `packed-refs` to drop blank lines and has no dry-run flag. Its only
option is `--path`. Copy the file first, from the repository root:

```bash
cp "$(git rev-parse --git-common-dir)/packed-refs" "$(git rev-parse --git-common-dir)/packed-refs.manual-backup"
uv run --frozen python scripts/maintenance/repair_packed_refs.py
```

The script also writes its own `packed-refs.before-repair` copy beside the file
and verifies refs after the rewrite. See
[Git packed-refs blank-line repair](../troubleshooting-packed-refs.md).

**PowerShell tests fail because `pwsh` cannot start.** This is a machine
fault, not a code fault. Check it before you debug the tests:

```bash
which -a pwsh
pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'; echo "exit=$?"
```

A healthy `pwsh` prints a version and `exit=0`. One known cause is the .NET
global tool shim at `~/.dotnet/tools/pwsh`. It comes from
`dotnet tool install -g PowerShell` and can sit first on `PATH`.

On 2026-11-24 a Linux workstation showed this case:

- `which -a pwsh` listed `~/.dotnet/tools/pwsh` first and `/snap/bin/pwsh` second.
- The shim (PowerShell 7.6.10) printed `You must install or update .NET` and
  exited 150. It asked for `Microsoft.NETCore.App` 10.0.0.
- `/snap/bin/pwsh` worked and reported 7.7.0.
- `dotnet --list-runtimes` listed 10.0.x runtimes under `~/.dotnet/shared`.
  The runtime was installed, but the shim did not look there.
- With `DOTNET_ROOT` unset, the shim searched `/usr/share/dotnet`. That folder
  held only 9.0.13. `COREHOST_TRACE=1` showed
  `Using dotnet root path [/usr/share/dotnet]`.

At commit 161cf5abd3 (2026-11-24) the failed run had 85 failed, 113 passed,
and 1 skipped across five files (counts at 161cf5abd3, 2026-11-24):

| File | Failed |
|---|---|
| `tests/skills/code-qualities-assessment/test_powershell_coupling.py` | 79 |
| `tests/skills/code-qualities-assessment/test_powershell_pwsh_launch.py` | 3 |
| `tests/build_scripts/test_generate_hooks_runtime_contract.py` | 1 |
| `tests/skills/github/test_check_github_transport.py` | 1 |
| `tests/skills/skill-bootstrap/test_runtime_contract.py` | 1 |

Each of the 85 failures came from the shim exit. Either prefix below made all
five files pass with 198 passed and 1 skipped at commit 161cf5abd3 (2026-11-24):

```bash
PWSH_TESTS=(
  tests/skills/code-qualities-assessment/test_powershell_coupling.py
  tests/skills/code-qualities-assessment/test_powershell_pwsh_launch.py
  tests/build_scripts/test_generate_hooks_runtime_contract.py
  tests/skills/github/test_check_github_transport.py
  tests/skills/skill-bootstrap/test_runtime_contract.py
)
PATH="/snap/bin:$PATH" uv run pytest "${PWSH_TESTS[@]}"
DOTNET_ROOT="$HOME/.dotnet" uv run pytest "${PWSH_TESTS[@]}"
```

The owner reported that a pre-push `python-tests` failure on 2026-11-24 cleared
with the `PATH` prefix below, and every hook passed. The prefix does not skip
any hook, so it is not a hook bypass. It does put `/snap/bin` first for every
command the hooks run, not only `pwsh`. On 2026-11-24 it also moved `dotnet` to
`/snap/bin/dotnet`, while `uv`, `python3`, and `git` resolved as before. Run
`ls /snap/bin` to see what else the prefix can shadow on your machine:

```bash
PATH="/snap/bin:$PATH" git push
```

The lasting fix is a machine change, and the machine owner picks it. Only the
two `pytest` prefixes above and the `~/.zshenv` fix below were measured. That
fix exports `DOTNET_ROOT` so the shim finds the runtimes it already has. The
`export` matters: without it, child processes such as the shim do not see the
value. These other changes were not tested:

- Put `/snap/bin` before `~/.dotnet/tools` on `PATH` in the shell profile.
- Remove the shim with `dotnet tool uninstall -g PowerShell`. Other tools that
  call `~/.dotnet/tools/pwsh` by full path would then break.
- Install the .NET 10 runtime where the shim looks (`/usr/share/dotnet`), for
  example from the system package manager.

**Set `DOTNET_ROOT` where non-interactive shells read it.** Agent shells and
hook subprocesses are not interactive. Zsh reads `~/.zshrc` only for
interactive shells. Bash reads `~/.bashrc` only for interactive shells too.
A `DOTNET_ROOT` export in either file can miss these shells.

On 2026-11-25 a Linux workstation with login shell zsh showed this case:

- `~/.zshrc` and `~/.bashrc` both exported `DOTNET_ROOT`.
- `zsh -i -c` printed `$HOME/.dotnet` for `DOTNET_ROOT`.
- `zsh -c` printed an empty value, so the shim exited 150.
- A bulk `pytest -n 32` run with `DOTNET_ROOT` unset had 86 failed, 77665
  passed, and 154 skipped (commit 792f6febd3, 2026-11-25). 85 failures were
  the five files above. The 86th was a path artifact, not .NET: a
  `codeql-scan` test checked for `pwsh` in text holding the checkout path.
  The branch name held `pwsh`. That test now masks the paths first.

The fix that worked was one line appended to `~/.zshenv`. Zsh reads that file
for every shell, interactive or not:

```bash
export DOTNET_ROOT="$HOME/.dotnet"
```

After that change on 2026-11-25, every measure below passed:

- `zsh -c` printed `$HOME/.dotnet`, and the shim printed 7.6.10.
- The 85 failed test IDs passed when rerun under `zsh -c`.
- The bulk run had 77775 passed, 129 skipped, and only the path artifact
  failed (commit 792f6febd3, 2026-11-25).

**Bash still has a gap.** Bash started from a zsh parent inherits the export
and works. Bash started without it does not. `bash -c` reads no startup file
unless `BASH_ENV` names one, and `BASH_ENV` was empty here. The 2026-11-25
measures were:

| Launch | `DOTNET_ROOT` | Shim exit |
|---|---|---|
| `env -u DOTNET_ROOT zsh -c 'bash -c ...'` | `$HOME/.dotnet` | 0 |
| `env -u DOTNET_ROOT bash -c ...` | empty | 150 |
| `env -u DOTNET_ROOT bash -i -c ...` | `$HOME/.dotnet` | not run |

So a process that starts `bash -c` directly can still fail the shim, with no
zsh in its parent chain. Cron, systemd units, and some IDE or agent hosts work
this way. For those, set `DOTNET_ROOT` in the launcher's own environment. Or
point `BASH_ENV` at a file that exports it. Neither bash fix was tested.

The test helper `tests/pwsh_launcher_probe.py` skips PowerShell tests when
`pwsh` cannot start (issue #7215). Its fault list does not include the .NET
host message, so on 2026-11-24 it returned `None` and the tests ran and failed.

**The pre-push gate asks for a review marker.** Follow
[the review marker guide](../../.claude/skills/review/resources/marker-and-no-task.md).

Never bypass a hook with `--no-verify` or by changing the hook settings. If a
hook blocks you for a reason unrelated to your diff, hand off the branch with the
measured reason.

## Escalate

`lefthook.yml` and `scripts/validation/` belong to `@rjmurillo`
(`.github/CODEOWNERS`). Open an issue with the full failure block when a gate
fails on a clean `main` checkout.

## Links

- [CONTRIBUTING.md: Setup Steps](../../CONTRIBUTING.md#setup-steps)
- [GOTCHAS.md](../../.agents/governance/GOTCHAS.md)
