# repository-consumer-proof

Verifies that hooks, installed dispatch, and agent behavior work for a consumer of this repository, beyond a green build.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You want to prove a capability works: `prove an ai-agents capability works`.
- A plugin starts but a command never runs: `plugin initializes but never executes`.
- A hook works only from the repo directory: `hook fails from foreign cwd`.

## When not to use it

- The PR is blocked: use [`repository-pr-recovery`](repository-pr-recovery.md) instead.
- You need PR completion proof: use [`repository-completion-proof`](repository-completion-proof.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/repository-consumer-proof`. To ask for it by name, say:

```text
Use the repository-consumer-proof skill to prove the installed completion hook runs from a foreign working directory.
```

The agent writes the expected observation and a negative control, picks the lowest layer that lacks evidence, and runs the matching suite.

## What you get

Observed evidence for the selected layer, with unmeasured behavior and operator-owned work kept visible. An artifact build does not count as proof of publication or consumer adoption. If live runtime access is unavailable, the agent reports runtime impact as unmeasured.

## Advanced use

`artifact_owner.py` reports which layer owns a repo path according to `templates/platforms/binplace.yaml`:

```bash
uv run python .claude/skills/repository-consumer-proof/scripts/artifact_owner.py --repo . .claude/hooks
```

It prints each manifest row that covers the path, the layer (source, plugin, installed), and whether the row links, copies, or only renders it. Exit 1 means no row covers the path. It does not say whether installed bytes are stale; use `build_all.py --check` for that.

The skill selects existing suites such as the hook runtime-contract and plugin-root tests under `tests/build_scripts/` and `tests/test_run_completion_gate_install.py`. For behavior, it predicts positive and negative observations, validates controls with the runtime evaluator's `--dry-run`, then runs live samples. Dry-run controls do not execute behavior assertions.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/repository-consumer-proof/scripts/artifact_owner.py --repo . .claude/hooks
uv run python .claude/skills/repository-consumer-proof/scripts/instruments.py --repo . list
uv run python .claude/skills/repository-consumer-proof/scripts/instruments.py --repo . run generated-output-check
```

Replace `generated-output-check` with any instrument id. The ids are `generated-output-check`, `installed-dispatcher`, `hook-runtime-contract`, `runtime-parity-dry-run`, `artifact-owner`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`repository-pr-recovery`](repository-pr-recovery.md): PR blockers.
- [`repository-completion-proof`](repository-completion-proof.md): PR completion.
- [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md): hook adaptation.
- [`agent-harness-reference`](agent-harness-reference.md): current host contract.
- [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md): evidence at the final head.
- Source: [`SKILL.md`](../../.claude/skills/repository-consumer-proof/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
