# ai-agents-architecture-contract

Gives you the design decisions of this repository as a contract. You check it before a change that touches more than one tree, a hook, a plugin surface, or a generated file.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You ask which tree is canonical for a file: `which tree is canonical`.
- You want to know why something is designed the way it is: `architecture contract`, `why is this designed this way`.
- You are about to edit a generated file and want to know which invariant you might break: `what invariant am I about to break`, `where is the source of truth for this file`.

## When not to use it

- You need to run the build pipeline: use [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md) instead.
- You need to triage a red CI check: use [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-architecture-contract`. To ask for it by name, say:

```text
Use the ai-agents-architecture-contract skill to tell me which tree is canonical for `.claude/agents/` before I edit it.
```

The agent walks its phases: locate the source of truth, load the design decisions, then read the hook failure policy, memory model, plugin surfaces, invariants, and known weak points. You see the canonical side named for your file.

## What you get

Prose guidance, not files. The skill covers the source-of-truth map, the ADR decisions that bind (with status), the hook runtime and its failure policy, the memory architecture, plugin surfaces, an invariants table with the check that enforces each one, and the known weak points.

## Advanced use

The generation seam is asymmetric: agents and the rule, skill, and hook trees have different canonical sources. A drift check shows a difference, not a direction, so answer "which side is canonical" before you edit either side. Dispatch is name-based, so "no caller found" does not mean dead code.

Hermes ships separate delivery, knowledge, quality, authoring, and azure-devops pack manifests.
These sit outside the Claude Code manifest contract.

The `instruments.py` dispatcher runs these ids:

| Id | Answers |
| --- | --- |
| `adr-status` | Status, superseded-by, and implemented flag of each cited ADR |
| `guard-lines` | Where `assert_no_claude_writes` is defined and called |
| `hook-counts` | Events and registrations per hook manifest |
| `generator-path` | Canonical source, plugin tree, install tree, and regenerate command for one path |
| `version-gate` | Whether any manifest or marketplace entry carries a version |
| `claims` | Which cited paths and test node ids no longer exist |
| `drift-self-check` | Whether the skill drifted from its `reverify.json` |

Exit codes for `instruments.py` and `contract_probe.py`: 0 ok, 1 something found (a missing file, an absent ADR, no guard definition), 2 bad arguments or configuration, 3 the target failed to start or a file was unreadable. `run` passes the child exit code through. The answers cover existence and counts only. Whether a mechanism still works stays a judgment call.

`contract_probe.py` has two subcommands, `adrs` and `guard`. Pass `generator-path` a path after `--`: `run generator-path -- <repo-path>`.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-architecture-contract/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-architecture-contract/scripts/instruments.py --repo . run adr-status
uv run python .claude/skills/ai-agents-architecture-contract/scripts/contract_probe.py --help
```

Replace `adr-status` with any instrument id. The ids are `adr-status`, `guard-lines`, `hook-counts`, `generator-path`, `version-gate`, `claims`, `drift-self-check`. `list` prints each one with the question it answers.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md): operates the build and drift gates this contract explains.
- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): triage when a gate goes red.
- [`ai-agents-failure-archaeology`](ai-agents-failure-archaeology.md): incident history behind the invariants.
- [`agent-harness-reference`](agent-harness-reference.md): host hook facts.
- [`ai-agents-config-catalog`](ai-agents-config-catalog.md): flags and escape hatches.
- [`ai-agents-change-control`](ai-agents-change-control.md): change process.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-architecture-contract/SKILL.md)
- Reference: [`adr-decisions.md`](../../.claude/skills/ai-agents-architecture-contract/references/adr-decisions.md)
- Reference: [`drift-detector.md`](../../.claude/skills/ai-agents-architecture-contract/references/drift-detector.md)
- Reference: [`hook-runtime.md`](../../.claude/skills/ai-agents-architecture-contract/references/hook-runtime.md)
- Reference: [`provenance.md`](../../.claude/skills/ai-agents-architecture-contract/references/provenance.md)
- Reference: [`source-of-truth.md`](../../.claude/skills/ai-agents-architecture-contract/references/source-of-truth.md)
- Reference: [`weak-points.md`](../../.claude/skills/ai-agents-architecture-contract/references/weak-points.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
