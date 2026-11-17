# ai-agents-build-and-env

Walks you through recreating the dev environment for this repository from a fresh clone, then checking that it works. It also lists the traps that have cost earlier contributors time.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You need to set up the repo: `set up this repo`, `bootstrap the environment`, `fresh clone setup`.
- You hit `ModuleNotFoundError: No module named yaml` or another environment error: `environment traps`.

## When not to use it

- You need to regenerate mirrors or run drift gates: use [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md) instead.
- You need to know what counts as test evidence: use [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md) instead.
- You need the full list of env vars and skip markers: use [`ai-agents-config-catalog`](ai-agents-config-catalog.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-build-and-env`. To ask for it by name, say:

```text
Use the ai-agents-build-and-env skill to set up a fresh clone of this repository and check that the environment works.
```

The agent checks prerequisites, runs the install commands, then runs the smoke probe and reports the result.

## What you get

A working `.venv/` and installed git hooks, plus a smoke probe result. The probe runs `lefthook version`, `lefthook check-install`, and a pytest collect-only on [`tests/test_paths.py`](../../tests/test_paths.py), then compares the lefthook version to the pin in [`pyproject.toml`](../../pyproject.toml). The skill also covers the MCP layer, editor and LSP behavior, a table of known traps, and a smoke checklist.

## Advanced use

The core install, from the repo root:

```bash
uv sync --frozen --extra dev
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

`--frozen` builds `.venv/` from `uv.lock` without rewriting it. The interpreter version has one source of truth, `.python-version`. Do not use `pip install`: PEP 668 blocks it, and the synced venv is the environment.

`env_probe.py` is read-only and takes one subcommand:

| Subcommand | Does |
| --- | --- |
| `pins` | Reads interpreter, lefthook, PyYAML, `requires-python`, Node major, hook syntax floor, and Serena memory count from the files that define them |
| `envfile` | Checks that `.env` is untracked (exit 1 if tracked) and lists key names in `.env.example` |
| `smoke` | Runs the smoke commands and compares against the pins (needs `uv`) |

Exit codes: 0 ok, 1 findings, 2 configuration or bad arguments, 3 external failure.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-build-and-env/scripts/env_probe.py --repo . pins
uv run python .claude/skills/ai-agents-build-and-env/scripts/env_probe.py --repo . envfile
uv run python .claude/skills/ai-agents-build-and-env/scripts/env_probe.py --repo . smoke
```

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md): the next step once the environment works.
- [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md): what counts as test evidence.
- [`ai-agents-config-catalog`](ai-agents-config-catalog.md): env vars, markers, and escape hatches.
- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): triage for failures after setup.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-build-and-env/SKILL.md)
- Reference: [`cross-os-testing.md`](../../.claude/skills/ai-agents-build-and-env/references/cross-os-testing.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
