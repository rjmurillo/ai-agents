# How Copilot CLI resolves an agent `model:` field

Evidence for the ADR-080 Amendment 2026-08-12. The `model:` resolution
measurements below were run against the real binary; the skill-fallback claim
and the corpus counts further down are inferred from source inspection, not
independently measured.

## Environment

```console
$ copilot --version
GitHub Copilot CLI 1.0.79.
```

Single account, single entitlement set, Linux. The session default resolved to
`claude-opus-5` throughout, which matters: every fallback below lands on that
model, and an account whose entitlement excludes it may behave differently.

## Method

A throwaway git repository, one agent per candidate value under
`.github/agents/`, differing only in the `model:` line:

```text
---
description: probe
model: <candidate>
---
Reply: PROBE
```

Driven with:

```bash
copilot -p "say PROBE" --agent <name> --allow-all-tools --no-color
```

The delegation probe adds a parent agent carrying no `model:` and asks it to use
the task tool, with `--model claude-opus-5 --log-level debug`, then reads the
resolution lines out of the debug log. Treatment and control each write to
their own `--log-dir` (`./logs-treatment` and `./logs-control`, detailed under
"Delegation probe, with control" below) so the two runs cannot combine into a
single extraction.

## Result table

| `model:` value | Shape | Outcome |
| --- | --- | --- |
| `claude-opus-4.6` | versioned, current | accepted |
| `claude-sonnet-4.6` | versioned, current | accepted |
| `Claude Opus 4.6 (copilot)` | VS Code display name | **accepted** |
| `claude-opus-4.5` | versioned, genuinely retired | `not available; using "claude-opus-5" instead` |
| `claude-opus-9-9-retired` | never registered | `not available; using "claude-opus-5" instead` |
| `Claude Opus 4.6 (anthropic)` | VS Code display name, wrong vendor suffix | `not available; using "claude-opus-5" instead` |
| `sonnet` | bare rolling alias | `not available; using "claude-opus-5" instead` |
| *absent* | inherit | accepted, inherits |

Every row exited 0. No value produced a non-zero exit or a hard error.

Two rows exist specifically to separate cases an earlier draft conflated.
`claude-opus-4.5` is the id the ADR Context names as the one that broke CI, and
it behaves identically to a string that never existed, which is what makes the
retirement claim *narrowed* rather than confirmed either way.
`Claude Opus 4.6 (copilot)` versus `(anthropic)` shows the suffix, not the
display-name shape, decides acceptance.

## Delegation probe, with control

Exact fixture, so another reviewer can rerun the override measurement without
guessing at the missing pieces. Two agent files in a throwaway repository's
`.github/agents/`:

Parent (`parent.agent.md`, carries no `model:`):

```text
---
description: probe parent, delegates to pinnedworker via the task tool
---
Use the task tool to delegate to the pinnedworker agent with the instruction
"say PROBE". Report back exactly what pinnedworker replied.
```

Worker (`pinnedworker.agent.md`, pinned `claude-opus-4.6`):

```text
---
description: probe worker, pinned model
model: claude-opus-4.6
---
Reply: PROBE
```

Treatment invocation, worker's `model:` line present, its own log
directory so the control run below cannot land in the same file:

```bash
mkdir -p logs-treatment
copilot -p "delegate to pinnedworker: say PROBE" --agent parent \
  --allow-all-tools --model claude-opus-5 \
  --log-dir ./logs-treatment --log-level debug --no-color
```

Log extraction:

```bash
grep -E "Using model|definitionModel|resolved to candidate|capabilities override" \
  logs-treatment/process-*.log
```

Treatment transcript:

```text
[DEBUG] Using model: claude-opus-5
[DEBUG] Applied model capabilities override: {"family":"claude-opus-5", ...}
[DEBUG] Using model: claude-opus-5
[DEBUG] Agent "pinnedworker": definitionModel="claude-opus-4.6", sessionModel="claude-opus-5", availableModels=[...]
[DEBUG] Agent "pinnedworker": resolved to candidate "claude-opus-4.6" → "claude-opus-4.6"
[DEBUG] Using model: claude-opus-4.6
[DEBUG] Applied model capabilities override: {"family":"claude-opus-4.6", ...}
[DEBUG] Using model: claude-opus-4.6
```

Control: worker's `model:` line deleted (`sed -i '/^model:/d'
pinnedworker.agent.md`), otherwise the identical command but pointed at
a second, distinct log directory (`--log-dir ./logs-control`) so
extraction cannot combine the two runs:

```bash
mkdir -p logs-control
copilot -p "delegate to pinnedworker: say PROBE" --agent parent \
  --allow-all-tools --model claude-opus-5 \
  --log-dir ./logs-control --log-level debug --no-color
```

```bash
grep -E "Using model|definitionModel|resolved to candidate|capabilities override" \
  logs-control/process-*.log
```

Control transcript:

```text
[DEBUG] Using model: claude-opus-5
[DEBUG] Applied model capabilities override: {"family":"claude-opus-5", ...}
[DEBUG] Using model: claude-opus-5
[DEBUG] Agent "pinnedworker": definitionModel=(none), sessionModel="claude-opus-5", availableModels=[...]
[DEBUG] Using model: claude-opus-5
[DEBUG] Applied model capabilities override: {"family":"claude-opus-5", ...}
[DEBUG] Using model: claude-opus-5     (all four resolutions)
```

Both transcripts above were reproduced against this exact fixture on
2026-08-15 (`GitHub Copilot CLI 1.0.81-0`), each run writing to its own
`--log-dir` (`logs-treatment/process-1786825491354-1918035.log` and
`logs-control/process-1786825522428-1919913.log` respectively, one file
per directory, confirming the two runs cannot combine into a single
extraction), confirming the original 1.0.79 run: the treatment resolves
to `claude-opus-4.6` once (`resolved to candidate`) and the control
resolves to `claude-opus-5` for every one of the four logged
resolutions, with no other change to either transcript's shape.

## Runtime-contract check on a shipped artifact

Not a synthetic fixture. `src/copilot-cli/agents/critic.agent.md` was copied
verbatim into a scratch repository, its `model: claude-opus-4.6` line then
manually deleted (mirroring the control step above with `sed -i
'/^model:/d'`, not any generator change: the reviewed tree still ships that
pin unchanged, both in `src/copilot-cli/agents/critic.agent.md:11` and in
the generator input at `templates/platforms/copilot-cli.yaml:98`), and
delegated to from a parent at `--model claude-opus-5`:

```text
[DEBUG] Agent "critic": definitionModel=
[DEBUG] Using model: claude-opus-5     (all four resolutions)
```

## Where aliases actually ship unresolved

The alias problem is real but it is not where the first draft said. Generated
plugin agents are translated; repository-level agents and skills are not.

```console
$ grep -m1 -E '^(model|model_tier):' .claude/agents/quality-auditor.md
model: sonnet
$ grep -m1 -E '^(model|model_tier):' templates/agents/quality-auditor.shared.md
model_tier: sonnet
$ grep -m1 -E '^(model|model_tier):' src/copilot-cli/agents/quality-auditor.agent.md
model: claude-sonnet-4.6
$ grep -m1 -E '^(model|model_tier):' .github/agents/quality-auditor.agent.md
model: sonnet
```

`templates/platforms/copilot-cli.yaml` `model_tiers`, consumed by
`build/generate_agents_common.py`, resolves the tier for the generated agent.
`.github/agents` is hand-maintained and did not get the resolution, so that file
is drift, not a policy failure.

Skills have no equivalent translation and ship raw:

```console
$ grep -rhE "^\s*model:" src/copilot-cli/skills/*/SKILL.md | sed 's/^ *//' | sort | uniq -c
      7 model: haiku
      1 model: opus
```

Those eight are the genuine instance of a bare alias reaching Copilot
unresolved, and per the table above each falls back to the session default.
However, this conclusion is based on the agent-level runtime probes above; no
runtime skill probes with model observability were performed. The presence of
raw aliases in skill files establishes the corpus state, not the runtime
behavior when Copilot invokes a skill's `model:` key. Until skill-level probes
with an absent-model control are added, the fallback claim for skills is
inferred from the agent probe mechanism, not independently measured. For
the seven `haiku` units that inverts the cost intent rule 3 exists to serve.

## Corpus state at the time of measurement

```console
$ grep -rhE "^\s*model:" .claude/agents .claude/skills/*/SKILL.md .claude/commands \
    | sed 's/^ *//' | sort | uniq -c | sort -rn
     20 model: sonnet
     18 model: opus
      8 model: haiku
      1 model: sonnet|opus|haiku      # doc example
      1 model: "haiku",               # doc example
```

Zero versioned pins in the source tree. The de-versioning migration described in
ADR-080's implementation notes has already run, which is why the amendment does
not describe removal of source pins as outstanding work.

## What was not measured

State it rather than let a reader assume the coverage is wider than it is.

- **Claude Code and VS Code resolvers.** Only Copilot CLI was driven. The
  `src/vs-code-agents` tree targets VS Code and its 30 `Claude Opus 4.6 (copilot)`
  values were never tested against VS Code itself, only against Copilot CLI.
- **Other CLI versions.** 1.0.79 only. Fallback-on-unresolvable is observed
  behavior, not a documented contract, and a later release could hard-error.
- **Other entitlements.** One account. The warning text is entitlement-shaped
  (`not available`), so a different subscription tier may accept or reject
  different values.
- **`--model` flag namespace.** The flag was only ever passed a versioned id.
  Whether the flag and the frontmatter field share a namespace was not tested,
  so "aliases are invalid" is established for frontmatter only.
