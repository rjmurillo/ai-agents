# Migrating from v0.6.0 to v0.7

## Goal

Move a working v0.6.0 install to the current `main` build of `project-toolkit`. You finish with one plugin, the old command names mapped to skills, and a checklist that proves it worked.

v0.7.0 has no release tag yet. This guide was run against `main` at commit `b959011e3f60`. Plugin versions are commit SHAs now, so your install shows its own SHA.

This guide checks Claude Code. For GitHub Copilot CLI, use the Copilot sections in [docs/installation.md](../installation.md).

## Before you start

- You have `claude-agents@ai-agents` and `project-toolkit@ai-agents` installed from v0.6.0.
- You can run `/plugin` in Claude Code, or `claude plugin` in a shell. The shell form is what this guide shows.
- Contributors only: a clone with `uv` installed. [CONTRIBUTING.md](../../CONTRIBUTING.md) has the full setup.

Your plugin list at v0.6.0 looks like this:

```text
claude-agents@ai-agents
  Version: 0.3.34
project-toolkit@ai-agents
  Version: 0.6.0
```

## Steps

The steps follow the order you hit each change.

### 1. Repoint the plugin

v0.6.0 shipped two plugins. `claude-agents` held the agents. `project-toolkit` held commands, hooks, and skills from `./.claude`.

v0.7 ships one plugin. `claude-agents` is retired. `project-toolkit` now sources from `./src/claude` and carries agents and skills together (PR #5791). The manifest has no `version` field, so Claude Code uses the commit SHA as the version ([ADR-092](../../.project-toolkit/architecture/ADR-092-omit-plugin-manifest-version.md), PR #4179).

Refresh the marketplace and update:

```bash
claude plugin marketplace update ai-agents
claude plugin update project-toolkit@ai-agents
```

Expected output:

```text
Successfully updated marketplace: ai-agents
Plugin "project-toolkit" updated from 0.6.0 to b959011e3f60 for scope user. Restart to apply changes.
```

Now remove the retired plugin. Do not skip this. `claude plugin update claude-agents@ai-agents` fails, and the plugin shows `failed to load` until you uninstall it:

```bash
claude plugin uninstall claude-agents@ai-agents
```

Restart Claude Code to load the new build. If you would rather start clean, run `claude plugin uninstall project-toolkit@ai-agents` and then the two commands in [docs/installation.md](../installation.md).

Check freshness from the commit SHA. The `Version` of `project-toolkit` should match the start of `main`:

```bash
claude plugin list
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

If `Version` is an older SHA, `main` has moved since your update. Run the two update commands again.

### 2. Rename your commands to skills

`.claude/commands/` is gone ([ADR-064](../../.project-toolkit/architecture/ADR-064-commands-to-skills-migration.md), PR #5640). Every command became a skill with `user-invocable: true`, so the slash names you type still work. Only the `pr-quality/` group changed name.

| v0.6.0 command | v0.7 skill |
|---|---|
| `pr-quality/security` | `pr-quality-security` |
| `pr-quality/all` | `pr-quality-all` |
| `pr-quality/analyst` | `pr-quality-analyst` |
| `pr-quality/architect` | `pr-quality-architect` |
| `pr-quality/devops` | `pr-quality-devops` |
| `pr-quality/qa` | `pr-quality-qa` |
| `pr-quality/roadmap` | `pr-quality-roadmap` |
| `build` | `build` (unchanged) |
| `checkpoint` | `checkpoint` (unchanged) |
| `context-hub-setup` | `context-hub-setup` (unchanged) |
| `plan` | `plan` (unchanged) |
| `pr-autofix` | `pr-autofix` (unchanged) |
| `pr-review` | `pr-review` (unchanged) |
| `push-pr` | `push-pr` (unchanged) |
| `research` | `research` (unchanged) |
| `retro` | `retro` (unchanged) |
| `ship` | `ship` (unchanged) |
| `spec` | `spec` (unchanged) |
| `sync` | `sync` (unchanged) |
| `test` | `test` (unchanged) |
| `validate-pr-description` | `validate-pr-description` (unchanged) |

The four `forgetful/*` commands (`memory-explore`, `memory-list`, `memory-save`, `memory-search`) were retired, not renamed. See step 4.

To prove a skill is visible in your installed host, not only in the source tree, list the plugin parts:

```bash
claude plugin details project-toolkit@ai-agents
```

Look for `pr-quality-security` under `Skills`.

### 3. Know which hooks stopped running

The v0.6.0 plugin registered 45 hook entries (40 distinct scripts) in `.claude/hooks/hooks.json`. The v0.7 plugin registers one: a `Stop` hook that nudges you to reflect. It only informs. No hook runs before or after a tool call.

[ADR-097](../../.project-toolkit/architecture/ADR-097-zero-tool-use-hooks.md) (PR #5172) took the plugin to zero `PreToolUse` and `PostToolUse` entries. It also retired the generated Copilot hook dispatcher. Most guards went earlier, in the PRs below. ADR-097 names five hooks, but only `invoke_observation_sync.py` was registered in the v0.6.0 plugin.

| Guard group | Scripts | Removed in |
|---|---|---|
| Commit guards | `branch_context_guard`, `branch_protection_guard`, `security_commit_gate`, `adr_review_guard`, `session_log_guard`, `prompt_eval_gate` | PRs #3259, #3272, #3295, #3237 |
| Push guards | `pr_description_guard`, `plugin_version_bump_guard`, `markdownlint_guard`, `retrospective_gate`, `session_log_field_guard` | PRs #3302, #5156, #3295 |
| Write and Edit guards | `security_gate`, `topical_memory_injection`, `adr_architect_gate`, `adr_lifecycle_hook`, `markdown_auto_lint` | PRs #3295, #3237, #3240, #5156 |
| LSP steering (search, read, delegation, usage tracking) | eight `invoke_lsp_*` scripts | PR #3232 |
| Routing and skill steering | `routing_gates`, `skill_first_guard`, `correction_applier` | PRs #3246, #3293, #3237 |
| Session, prompt, and stop checks | four `SessionStart`, four `UserPromptSubmit`, `session_validator`, `skill_learning` | PRs #3295, #3237 |
| Subagent and permission | `qa_agent_validator`, `test_auto_approval` | PRs #3237, #3292 |
| Memory sync | `observation_sync` | PR #5172 |

What this means for you:

- Nothing blocks a `git commit`, `git push`, or file write from inside Claude Code anymore. Do not rely on the old guards.
- `test_auto_approval` no longer auto-approves test commands. Claude Code asks for permission as it would for any other command.
- Contributors still get commit-time checks from Lefthook. See step 7.

### 4. Switch memory to Serena only

The Forgetful MCP server is gone ([ADR-106](../../.project-toolkit/architecture/ADR-106-serena-only-memory-architecture.md), PR #5575, issue #5574). `.mcp.json` listed `serena`, `deepwiki`, and `forgetful` at v0.6.0. It lists `serena` and `deepwiki` now.

Memory is plain markdown under `.serena/memories/`. A memory's identity is its file path. No second backend exists to fall back to.

- The `forgetful/*` commands and the `using-forgetful-memory` skill are gone.
- This change does not read or move data in a Forgetful server you ran yourself. If you want those notes, export them before you remove the server, and save what you keep as `.serena/memories/` files.
- If your own `.mcp.json` or user settings still point at `forgetful`, remove that entry. Nothing in the plugin starts it.

The `memory` and `memory-search` skills still exist. They work from the Serena memory files.

### 5. Stop using session skills

PR #5179 removed `session`, `session-init`, `session-end`, and `session-log-fixer`, plus `.agents/SESSION-PROTOCOL.md`. Session log creation is discontinued. Long-running work keeps its state in the per-issue handoff, per the shipped rule `universal.md` (MUST NOT 10).

If a script or note of yours calls `/session-init` or reads `SESSION-PROTOCOL.md`, delete the call.

### 6. Move `.agents/` write targets to `.project-toolkit/`

PR #5887 (issue #5420) moved every write target from `.agents/<sub>` to `.project-toolkit/<sub>`, keeping the relative path. For example, the `qa` folder is now `.project-toolkit/qa`. Runtime writers use the new root with no fallback to the old one. Issue #5421 then moved the generated `context` and `skills` folders too.

`.agents/` now holds only read-only inputs: `governance`, `steering`, `schemas`, `templates`, `dictionaries`, `guides`, `hooks`, `archive`, `plugins`, and the top-level files. The source list is `_KEEP_DIRS` in `scripts/validation/check_agents_write_targets.py`.

If you are a contributor in this repo, pull and you are done. If you ran the old `scripts/init_project.py` in your own repo, nothing migrates your folders. That script is deleted (PR #6024). New tool output lands in `.project-toolkit/`. To keep old output beside it, move each folder you use. This loop moves two:

```bash
for sub in sessions qa; do git mv ".agents/$sub" ".project-toolkit/$sub"; done
```

Add every folder you own to the list. PR #5887 moved 29 subtrees, and its body names them all.

Check that nothing in the repo still writes to `.agents/`:

```bash
uv run --frozen python scripts/validation/check_agents_write_targets.py
```

### 7. Contributors: replace `.githooks` with Lefthook

v0.6.0 set `core.hooksPath` to `.githooks` through `scripts/install_git_hooks.py`. Both are gone. Lefthook runs the hooks now ([ADR-086](../../.project-toolkit/architecture/ADR-086-lefthook-local-hook-orchestration.md), PR #3259). `lefthook.yml` defines the commit-time checks: branch rules, commit message format, markdown lint, dash checks, and conflict markers.

Run setup again. The `--reset-hooks-path` flag clears your old `.githooks` setting:

```bash
uv sync --frozen --extra dev
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

On a clone that still had `core.hooksPath` set to `.githooks`, the install printed:

```text
core.hooksPath is set locally to '.githooks'
local core.hooksPath has been unset.
sync hooks: (pre-merge-commit, pre-push, commit-msg, pre-commit)
```

`.claude/` in this repo is now a generated copy of `src/claude/`. Edit `src/claude/` and `templates/`, then build. [.claude/AGENTS.md](../../.claude/AGENTS.md) has the rules.

### 8. Use the skill, not the agent, for review comments

The `pr-comment-responder` agent is retired (PR #7169). The skill of the same name is now the only owner. Replace calls like `Task(subagent_type="pr-comment-responder")` with `/pr-comment-responder`. For several PRs at once, or a merge verdict, use `/pr-review`.

One default changed. The skill now sorts review threads by domain first, then by reviewer. A security comment from a bot runs before a human style comment.

## Check your result

Run these. Each line says what you should see.

```bash
claude plugin list
```

`project-toolkit@ai-agents` shows a 12 character SHA as `Version` and `Status: enabled`. `claude-agents@ai-agents` is not listed.

```bash
claude plugin details project-toolkit@ai-agents
```

`Skills` includes `pr-quality-security`, `pr-quality-all`, and `pr-comment-responder`. `Agents` does not include `pr-comment-responder`. `Hooks (1)` shows `Stop`. At commit `b959011e3f60` the counts were 105 skills, 29 agents, and 1 hook.

Contributors also run these in a clone:

```bash
test -d .claude/commands && echo exists || echo gone
python3 -c "import json;print(sorted(json.load(open('.mcp.json'))['mcpServers']))"
git config --get core.hooksPath
uv run --frozen lefthook check-install
uv run --frozen python scripts/validation/check_agents_write_targets.py
```

Expected:

```text
gone
['deepwiki', 'serena']
```

`git config --get core.hooksPath` prints nothing. `lefthook check-install` exits 0 with no output. The write-target check ends with `agents-write-targets: 0 violation(s)`.

## If it fails

- **`claude-agents` shows `failed to load`.** Run `claude plugin uninstall claude-agents@ai-agents`.
- **`Version` still reads `0.6.0`.** Run `claude plugin marketplace update ai-agents`, then update again. Restart Claude Code.
- **`/plugin` is not recognized.** Update Claude Code to a build that supports plugin marketplaces. See [Troubleshooting](../installation.md#troubleshooting).
- **A `/pr-quality/...` command is not found.** Use the hyphen name from the table in step 2.
- **`lefthook check-install` fails.** Rerun `uv run --frozen lefthook install --reset-hooks-path`. In a linked worktree, check the shared hooks instead. [CONTRIBUTING.md](../../CONTRIBUTING.md#pre-commit-hooks) explains why.
- **A script still writes to `.agents/`.** Change its path to `.project-toolkit/`, using step 6.

## Next

- Install the toolkit on another host: [docs/installation.md](../installation.md).
- Learn the skills that replaced the commands: [docs/skill-reference.md](../skill-reference.md).
- Write your own skill: [docs/SKILL-AUTHORING.md](../SKILL-AUTHORING.md).
