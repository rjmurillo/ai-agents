# Plugin-Root Tokens in Agent and Skill Bodies: Host Probes, 2026-11-16

This file records the runtime probes behind PR #7363. That PR picks a plugin-root
form per host for the six split agents' `references/` paths. The code that reads
this record is the reference-root block in `build/generate_agents_common.py` and
the `keepClaudeReferenceRoot` key in `templates/platforms/cursor.yaml`.

It is kept here, not in `agent-harness-reference/references/probe-evidence.md`,
because that file is already past the taste-lints size warning (429 lines on
6a372da26, 2026-11-16). Moving these rows into the harness skill is an open
choice for the owner.

## Hypothesis

A host replaces a plugin-root token in an agent body before the model reads it.
No host documents this. Cursor documents its plugin-root variables for hooks and
`mcp.json` only. ADR-121 measured Claude Code (rows 2 to 7) and recorded Copilot
CLI as UNAVAILABLE.

## Versions

- cursor-agent 2026.11.13-eacade1, Linux.
- Codex CLI 0.169.0, Linux, model `gpt-6.1-sol`, sandbox read-only.
- Muse Code 1.4.20, Linux.
- Claude Code 2.1.325, Linux.

## Method

1. Write a probe agent whose body holds three lines and tells the model to quote
   them verbatim, with no tools:
   - LINE-A: `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x/references/`
   - LINE-B: `${CLAUDE_PLUGIN_ROOT}/skills/x/references/`
   - A first Cursor run used a single MARKER-AGENT line that held
     `${CLAUDE_PLUGIN_ROOT}`, `${CURSOR_PLUGIN_ROOT}`, and `${PLUGIN_ROOT}`.
   - LINE-C, Cursor and Muse Code: `$CLAUDE_PLUGIN_ROOT/skills/x`,
     `{{CLAUDE_PLUGIN_ROOT}}`, and `${CURSOR_PLUGIN_ROOT}`
   - LINE-C, Codex: `${CODEX_PLUGIN_ROOT}`, `${PLUGIN_ROOT}`, and
     `${CURSOR_PLUGIN_ROOT}`
   - LINE-C, Claude Code: `${COPILOT_PLUGIN_ROOT}/skills/x/references/`
2. Load it as each host loads agents.
   - Cursor: a local plugin through `--plugin-dir`.
   - Codex: `.codex/agents/rootprobe.toml` in a scratch workspace.
   - Muse Code: `.agents/agents/rootprobe-agent.md` in a scratch workspace
     trusted with the run flag. An untrusted run could not load the agent.
   - Claude Code, twice: as a plugin agent through `--plugin-dir`, and as a
     project agent in `.claude/agents/`.
3. For Cursor and Muse Code, ask a skill with the same tokens to quote itself.
   For Codex, read the first plugin-root line of the installed `github`
   SKILL.md. Run `env | grep PLUGIN` in the skill's shell.

## Observed

```text
host    agent LINE-A   agent LINE-B (bare Claude)   other tokens                 skill body   shell PLUGIN vars
Cursor  literal        plugin root path             CURSOR_PLUGIN_ROOT replaced  literal      none
Codex   literal        literal                      literal                      literal      none
Muse    literal        literal                      literal                      literal      none
```

Claude Code agent bodies:

```text
load mode        LINE-A    LINE-B (bare Claude)   LINE-C (bare Copilot)
plugin agent     literal   plugin root path       literal
project agent    literal   literal                literal
```

- LINE-A is the negative control. No host changed it.
- Claude Code replaced the bare Claude token only in a plugin agent. A project
  agent, the mode this repository's own `.claude/agents` load in, saw it
  literal.
- Cursor replaced only the exact `${CLAUDE_PLUGIN_ROOT}` and
  `${CURSOR_PLUGIN_ROOT}` forms. It left `$CLAUDE_PLUGIN_ROOT`,
  `{{CLAUDE_PLUGIN_ROOT}}`, and `${PLUGIN_ROOT}` literal.
- Codex read the installed skill from disk at its plugin cache path. The Codex
  install copies agents with no token rewrite.
- Muse Code installs by copy to its config folder, with no token rewrite.

Grade: EMPIRICAL, one sample per host and load mode.

## Not measured

- A Cursor marketplace install.
- A Codex agent loaded from an installed plugin.
- Copilot CLI, as a plugin agent or a repository agent. The Copilot render's bare
  `${COPILOT_PLUGIN_ROOT}` stays unproven.

## Consequences in PR #7363

- Claude Code, Copilot CLI, and Cursor renders keep their bare token and add one
  clause naming `.claude/skills/<skill>/references/` for a checkout with no
  plugin root, because a project agent sees the token literal.
- Cursor agent copies keep the bare Claude token on split-agent reference paths.
- Codex and Muse Code copies keep the nested form. No form resolves for an
  installed consumer on those hosts. That the nested form resolves to `.claude`
  in a checkout is INFERRED: a model sees it literal and must choose the default.
- Re-run on a host upgrade, and before relying on the Copilot CLI render.
