# ai-agents-generation-and-release

Runs the generation and release machinery of this repository: the generators in `build_all.py`, `generate_agents.py`, the drift gates, the version-free plugin manifests, and the npm publish path.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You edited a canonical file and need to regenerate: `regenerate the mirrors`.
- You want to run or read drift gates: `run the drift checks`, `why is the drift gate red`, `why is the plugin version gate red`.
- You are releasing the CLI package: `release the npm cli`.

## When not to use it

- You need environment setup: use [`ai-agents-build-and-env`](ai-agents-build-and-env.md) instead.
- You need the reason the seam is shaped this way: use [`ai-agents-architecture-contract`](ai-agents-architecture-contract.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In a Claude Code session inside this repository you can still type `/ai-agents-generation-and-release`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the ai-agents-generation-and-release skill to regenerate the mirrors after my edit to a canonical agent template and run the drift checks.
```

The agent finds the canonical source for your file, regenerates, runs the drift gates, and reports which are green.

## What you get

A canonical edit and its regenerated output, committed together so the drift gates stay green. Plugin manifests stay free of a `version` field. The skill points to `RELEASING.md` for the npm release procedure.

## Advanced use

Run the generators with `uv run python build/scripts/build_all.py` (and `build/generate_agents.py`), then the drift gates, before you push. Never hand-edit a generated tree; the next regeneration overwrites the edit.

`generator_inventory.py` is read-only, prints JSON with an `examined` count, and has four subcommands:

| Subcommand | Does |
| --- | --- |
| `generators` | Generator order, owned prefixes, and producer count from `build_all.py` |
| `path <repo-path>` | Which tree is canonical for a path and what regenerates it |
| `skills` | Template count and repo-local skills |
| `gates` | Wiring (lefthook job or workflow job) for each drift gate. Exit 1 for an unwired gate |

Exit codes: 0 ok, 1 findings, 2 bad arguments or configuration. `instruments.py` links the build and manifest checks.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-generation-and-release/scripts/generator_inventory.py --repo . generators
uv run python .claude/skills/ai-agents-generation-and-release/scripts/generator_inventory.py --repo . path .claude/agents
uv run python .claude/skills/ai-agents-generation-and-release/scripts/generator_inventory.py --repo . gates
uv run python .claude/skills/ai-agents-generation-and-release/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-generation-and-release/scripts/instruments.py --repo . run generators
```

Replace `generators` with any instrument id. The ids are `generators`, `path`, `skills`, `gates`, `build-all-check`, `version-field`, `manifest-parity`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-architecture-contract`](ai-agents-architecture-contract.md): why the seam is asymmetric.
- [`ai-agents-build-and-env`](ai-agents-build-and-env.md): environment setup.
- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): triage a red gate.
- [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md): hook changes that need regeneration.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-generation-and-release/SKILL.md)
- Reference: [`drift-gates.md`](../../.claude/skills/ai-agents-generation-and-release/references/drift-gates.md)
- Reference: [`seam-tables.md`](../../.claude/skills/ai-agents-generation-and-release/references/seam-tables.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
