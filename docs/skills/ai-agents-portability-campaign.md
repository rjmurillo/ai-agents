# ai-agents-portability-campaign

Runs a cross-harness hook change for Claude Code and GitHub Copilot CLI. It uses the settled official contract, versioned probes, the generators, and runtime tests.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You are porting hooks: `run the portability campaign`, `port hooks to a new harness`.
- A Copilot hook times out or a new CLI release may change the contract: `copilot hook timeout regression`, `verify the copilot runtime contract`, `new copilot cli release, recheck the contract`.

## When not to use it

- You only need a fact about hooks: use [`agent-harness-reference`](agent-harness-reference.md) instead.
- You need the release and mirror-generation procedure: use [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In a Claude Code session inside this repository you can still type `/ai-agents-portability-campaign`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the ai-agents-portability-campaign skill to port the new PreToolUse hook to Copilot CLI and verify the shipped artifacts.
```

The agent loads the settled contract, classifies the source hook, edits the canonical sources, tests, regenerates all mirrors, and tests the shipped artifacts.

## What you get

One coherent change that holds the canonical sources and every generated artifact, plus passing contract and end-to-end hook tests. If the runtime matches the settled contract, the skill creates no new research artifact. If it differs, you pin the CLI version, state the expected result, and probe in an isolated plugin.

## Advanced use

The phases are: load the settled contract, classify the source hook, change canonical sources, test before generation, regenerate all mirrors, test shipped artifacts, and refresh knowledge only when the runtime differs. The test phases run the pytest suites under `tests/build_scripts/` and `tests/e2e/`. Regenerate with `uv run python build/scripts/build_all.py`.

`hook_inventory.py` has three subcommands: `counts` (events and registrations per hook manifest), `phase-tests` (checks that the pytest paths named in `SKILL.md` exist), and `qualifiers` (checks the repository qualifier). Exit codes: 0 ok, 1 findings, 2 bad arguments, 3 external failure.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-portability-campaign/scripts/hook_inventory.py --repo . counts
uv run python .claude/skills/ai-agents-portability-campaign/scripts/hook_inventory.py --repo . phase-tests
uv run python .claude/skills/ai-agents-portability-campaign/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-portability-campaign/scripts/instruments.py --repo . run hook-counts
```

Replace `hook-counts` with any instrument id. The ids are `hook-counts`, `phase-tests`, `qualifiers`, `event-map`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`agent-harness-reference`](agent-harness-reference.md): owns hook facts and the settled contract.
- [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md): owns probe design.
- [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md): owns mirror generation and release.
- [`repository-consumer-proof`](repository-consumer-proof.md): proves the installed hook runs from a foreign directory.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-portability-campaign/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
