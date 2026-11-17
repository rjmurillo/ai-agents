# ai-agents-config-catalog

Lists every configuration axis in this repository: env vars, commit markers, frontmatter keys, QA skip verdicts, and escape hatches. Each row has its enforcement point and how it has been abused.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You ask what a flag or skip does: `what does a skip flag do`, `what does the drift allowlist do`.
- You want the escape hatches: `list escape hatches`, `can I skip this gate`, `is this skip marker allowed`.
- You are adding a flag: `add a config flag`.

## When not to use it

- You need hook runtime behavior: use [`agent-harness-reference`](agent-harness-reference.md) instead.
- You need the policy for when a gate may be bypassed: use [`ai-agents-change-control`](ai-agents-change-control.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-config-catalog`. To ask for it by name, say:

```text
Use the ai-agents-config-catalog skill to tell me what the drift allowlist does and whether I can use it here.
```

The agent finds the row for that flag, reads its effect and guard, and tells you whether the use is allowed.

## What you get

A catalog organized by axis type: git hook configuration, removed and stale flags, test and tooling env vars, `.env` keys, commit markers, text directives, skill frontmatter keys, QA skip verdicts (ADR-034), the plugin manifest version ban, and hook registration surfaces. It ends with a checklist for adding a new flag. Removed flags such as `SKIP_PREPUSH` and `SKIP_TESTS` are marked do not reintroduce.

## Advanced use

`flag_locator.py` has three subcommands:

| Subcommand | Does |
| --- | --- |
| `locate <id or name>` | Prints `file:line` for each file attributed to the flag. `locate --list` prints the known ids |
| `markers` | Lists pytest markers from `pyproject.toml` |
| `retired` | Confirms retired flags are absent from `CONTRIBUTING.md` and `scripts/validation/pre_pr.py` |

Exit codes: 0 ok, 1 findings or a missing file, 2 bad arguments or unreadable config, 3 external failure. Exit 1 from `locate` means the flag moved or died, so fix the catalog first. Use `instruments.py` to list or run the linked checks.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-config-catalog/scripts/flag_locator.py --repo . locate --list
uv run python .claude/skills/ai-agents-config-catalog/scripts/flag_locator.py --repo . markers
uv run python .claude/skills/ai-agents-config-catalog/scripts/flag_locator.py --repo . retired
uv run python .claude/skills/ai-agents-config-catalog/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-config-catalog/scripts/instruments.py --repo . run pytest-markers
```

Replace `pytest-markers` with any instrument id. The ids are `flag-locate`, `pytest-markers`, `retired-flags`, `hook-counts`, `manifest-version`, `lefthook-validate`, `qa-investigation-eligible`, `qa-docs-only-eligible`, `drift-allowlist`, `drift-self-check`. `list` prints each one with the question it answers. Some instruments need more arguments after `--`; `list` shows each one's command.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-change-control`](ai-agents-change-control.md): owns when a bypass is allowed.
- [`agent-harness-reference`](agent-harness-reference.md): host and hook facts.
- [`ai-agents-architecture-contract`](ai-agents-architecture-contract.md): why the gates exist.
- [`ai-agents-failure-archaeology`](ai-agents-failure-archaeology.md): the abuse stories behind removed flags.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-config-catalog/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
