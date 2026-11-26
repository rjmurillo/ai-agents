# Harness optimization: what a self-improvement loop may edit

Cited reference material for any loop that edits its own harness, such as the
`skillopt` skill. Source: Lilian Weng, "Harness Engineering for
Self-Improvement", Lil'Log, 2026,
<https://lilianweng.github.io/posts/2026-07-04-harness/> (read 2026-11-26).
The papers' reported gains are their claims; nothing here reproduces them.

## The optimization ladder

Weng's "Harness Optimization" section: "The progression in the object being
optimized in the harness system is roughly: instruction prompts → structured
context → workflow → harness code → optimizer code."

| Rung | Object being optimized | Example in this plugin |
|---|---|---|
| 1 | Instruction prompts | an agent prompt or a `SKILL.md` rule |
| 2 | Structured context | rules, references, memory loaded into the turn |
| 3 | Workflow | the step order a skill or orchestrator runs |
| 4 | Harness code | hooks, bundled scripts, tool wrappers |
| 5 | Optimizer code | the loop that proposes and gates edits |

Each rung up widens what one edit can break. Weng adds: "As the model becomes
more intelligent and powerful, we move toward more complex targets and
generic methods." Pick the lowest rung that owns the failure.

## AHE's seven editable components

Agentic Harness Engineering (AHE; Lin et al., arXiv:2604.25850) gives every
editable component a file, so the action space is explicit. "A harness
contains 7 components: system prompt, tool description, tool implementation,
middleware, skill, sub-agent configuration, and long-term memory." Each
failure pattern maps to one component, so the edit stays targeted.

| Component | Surface in Claude Code and Copilot CLI |
|---|---|
| System prompt | `CLAUDE.md`, `AGENTS.md`, always-on rules |
| Tool description | MCP tool descriptions, the `description` field in each SKILL.md frontmatter |
| Tool implementation | MCP servers, bundled scripts |
| Middleware | hooks (see this skill's hook contracts) |
| Skill | `SKILL.md` and its `references/` |
| Sub-agent configuration | agent files: prompt, tools, model |
| Long-term memory | memory files and memory services |

`skillopt`'s manifesto entries name one of these seven as `component`.

## The read-only boundary

AHE edits only the harness workspace: "the runs directory, tracer, verifier,
and LLM configuration are read-only." Weng notes this blocks reward hacking
such as disabling the verifier, swapping the model, or raising the reasoning
budget, and "keep[s] every recorded gain attributable to harness edits."

Her wider caution: "The editable surface needs to be properly designed and
the permission control and security layers need to live outside this loop.
All the challenges around reward hacking still remain."

For a loop in this plugin, the read-only surfaces are:

- the eval set and its splits,
- every verifier and grading script,
- the tracer or transcript store the loop reads,
- the model configuration: model name, effort, and reasoning budget,
- permissions, hook registration, and security gates.

`skillopt` pins the eval set, verifiers, and tracer files by sha256
(`skillopt.py pin`, `pin-check`). It records the model name as text, and
`pin-check --model` compares it. Effort and budget are pinned only when they
live in a config file passed as a surface. Hook registration and permissions
are not pinned by any skillopt check; keep them out of any loop's editable
set.

## Two related cautions

- **Capability gates the loop.** STOP (Zelikman et al., "Self-Taught
  Optimizer (STOP)", COLM 2024) "improved mean downstream performance across
  iterations with GPT-4 but degraded with weaker models like GPT-3.5 and
  Mixtral." Lin et al. ("Harness Updating Is Not Harness Benefit",
  arXiv:2605.30621) later measured edit-writing ability as flat across model
  sizes. Treat a weak proposer as a risk, and let a held-out gate decide.
- **Validate on two splits and keep the rejects.** Self-Harness (Zhang et
  al., arXiv:2606.09498) accepts a candidate "only if they have no regression
  on both held-in and held-out data," and "rejected candidates are logged
  without changing the active harness."
