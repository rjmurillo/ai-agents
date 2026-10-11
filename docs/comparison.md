# Claude Code and Copilot CLI agent toolkits compared

Several open-source projects package agents, skills, and plugins for Claude Code and GitHub Copilot CLI. They differ in scope: large multi-harness catalogs (wshobson/agents), plugin sets for Claude Code and Copilot CLI (St0nefish/agent-toolkit, and dspo/agent-marketplace, which also targets Codex), pipeline orchestrators (AgentMux), git-gate governance tools (Karajan Code), and orchestrated multi-agent workflows (AI Agents, this repo). This page compares them on install route, scope, and workflow, using facts from each project's own repository as of 2026-10-11.

A harness is the coding tool that loads and runs agents, such as Claude Code or Copilot CLI.

## At a glance

Every cell comes from files in the project's own repository (README, LICENSE, linked docs, or package manifest) or its package registry entry, read on 2026-10-11. The [Sources](#sources) section links each one. The table has no ranking column and no star counts. Projects change often, so check the linked README before you decide.

| Project | License | Claude Code install | Copilot CLI install | What it ships | Workflow model | Notes |
|---------|---------|---------------------|---------------------|---------------|----------------|-------|
| [AI Agents](https://github.com/rjmurillo/ai-agents) (this repo) | MIT | `/plugin marketplace add rjmurillo/ai-agents`, then `/plugin install project-toolkit@ai-agents` | `/plugin marketplace add rjmurillo/ai-agents`, then `/plugin install project-toolkit@ai-agents` | One `project-toolkit` plugin: 30 agents plus skills, generated for both CLIs from the same sources | An orchestrator routes work to specialist agents. Critic, QA, and security agents review the work before it ships | The six lifecycle steps (`spec` to `ship`) ship as user-invocable skills for both CLIs. The plugin hook files for both CLIs register no hooks as of 2026-10-11 |
| [wshobson/agents](https://github.com/wshobson/agents) | MIT | `/plugin marketplace add wshobson/agents`, then `/plugin install <plugin>@claude-code-workflows` | Clone the repo, then `make install-copilot` | 94 plugins. The local source holds 202 agents, 184 skills, and 105 commands | A catalog. You install the plugins you want, and the harness loads them by its own rules | Supports seven tools. Its README names GitHub Copilot, and the generated agent profiles and skills install to `~/.copilot/`. Its matrix lists no plugin marketplace and no hooks for Copilot |
| [St0nefish/agent-toolkit](https://github.com/St0nefish/agent-toolkit) | AGPL-3.0 (LICENSE file) | `claude plugin install St0nefish/agent-toolkit/<plugin>` | `copilot plugin install St0nefish/agent-toolkit/<plugin>` | 16 plugins in five groups (productivity, development, security, gaming, Copilot-only), plus one Copilot extension | A plugin set. Each plugin adds hooks, skills, commands, an agent, or an MCP server | Keeps a Copilot variant of each hook plugin. The README license section says MIT, which differs from the LICENSE file |
| [dspo/agent-marketplace](https://github.com/dspo/agent-marketplace) | Apache-2.0 | `/plugin marketplace add https://github.com/dspo/agent-marketplace.git`, then `/plugin install <plugin>` | `copilot plugin marketplace add https://github.com/dspo/agent-marketplace.git`, then `copilot plugin install <plugin>` | Five plugins: gitwork, mimo, exam-generator, playwright-cli, remora | A plugin set. One marketplace index serves Claude Code and Copilot CLI | Also targets OpenAI Codex through a second index file |
| [AgentMux](https://github.com/markuswondrak/AgentMux) | Not stated. No LICENSE file at the repo root and no license field in `pyproject.toml` | Not a plugin. `pipx install git+https://github.com/markuswondrak/AgentMux.git` | Same install. It drives the `copilot` CLI as one of six providers | A Python CLI (`agentmux`) that runs agent CLIs inside tmux sessions | A pipeline: PM (optional), Architect, Plan, Code, Review, Done. A file watcher advances the state machine | Needs Python 3.10 or newer and tmux. Providers: `claude`, `codex`, `gemini`, `opencode`, `copilot`, `qwen` |
| [Karajan Code](https://github.com/manufosela/karajan-code) | AGPL-3.0 | Not a plugin. `npm install -g @karajan-family/code`, or the install script in its README | Same install. The README lists GitHub Copilot as one of nine built-in agents | A CLI (`kj`) that installs git hooks and review gates around your agent | Git gates. A commit needs an approved verdict from a different AI. Tests come first | The README says synchronous blocking hooks exist today only in Claude Code. On other hosts it still governs at the git-gate level |

## How Claude Code and Copilot CLI plugins differ

Both CLIs install plugins from a marketplace file in a Git repository. The formats overlap, but they are not the same. Three differences matter when one repo serves both.

**Marketplace file location.** Claude Code reads `.claude-plugin/marketplace.json` ([Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)). Copilot CLI documents `.github/plugin/marketplace.json` and also checks `.claude-plugin/` ([Copilot CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)). A repo can ship one file or both. AI Agents and St0nefish/agent-toolkit ship both. dspo/agent-marketplace shares the `.claude-plugin/` index.

**Hook format.** The hook files differ in shape. St0nefish/agent-toolkit lists the differences in its README:

| Difference | Claude Code | Copilot CLI |
|------------|-------------|-------------|
| Plugin root variable | `${CLAUDE_PLUGIN_ROOT}` | `${COPILOT_PLUGIN_ROOT}` |
| Hook event names | PascalCase (`PreToolUse`) | camelCase (`preToolUse`) |
| Hook format | Nested `hooks` array, `command` key | Object `hooks` map, `bash` key, `version: 1` |
| Payload keys | `tool_name` and `tool_input` | `toolName` and `toolArgs` |

The vendor docs show a narrower gap than that table. GitHub says hook files "use JSON format with version 1" ([GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)). The same page documents a second, "VS Code compatible" payload format. It uses PascalCase event names and snake_case fields, matching the Claude Code column above. Claude Code defines hooks "in JSON settings files" with three levels of nesting ([Claude Code hooks](https://code.claude.com/docs/en/hooks)). Test a hook in both CLIs before you rely on it.

Projects handle the gap in different ways. St0nefish/agent-toolkit keeps a Copilot copy of each hook plugin. The wshobson/agents capability matrix lists lifecycle hooks as "none emitted" for Copilot. AI Agents registers no plugin hooks for either CLI as of 2026-10-11.

**Slash commands and agents.** Command support differs too. The wshobson/agents matrix says its commands are "converted to user-invocable skills" for Copilot. St0nefish/agent-toolkit keeps a `commands/` directory only in its Copilot variants and uses skills in Claude Code. AI Agents ships its six lifecycle steps as user-invocable skills for both CLIs, with no `commands/` directory in either plugin.

Copilot CLI custom agents are Markdown files with an `.agent.md` extension. They live in `.github/agents/` for a project or `~/.copilot/agents/` for a user ([Creating and using custom agents for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli)).

## Choosing

Pick by the job you need done.

- **A plugin catalog (94 plugins) with support for seven tools:** wshobson/agents.
- **A few focused plugins for both CLIs:** St0nefish/agent-toolkit, or dspo/agent-marketplace if you also use Codex.
- **A tmux pipeline across the AI subscriptions you already have:** AgentMux.
- **Git gates around whatever agent writes the code:** Karajan Code.
- **A plan-to-ship workflow with an orchestrator and review agents in Claude Code and Copilot CLI:** AI Agents.

These projects can coexist. A plugin catalog and a workflow toolkit solve different problems. Check each license against your own use before you adopt one.

## FAQ

### Can one repository be a plugin marketplace for both Claude Code and Copilot CLI?

Yes. AI Agents ships `.claude-plugin/marketplace.json` for Claude Code and `.github/plugin/marketplace.json` for Copilot CLI. The same repository name works in both CLIs. St0nefish/agent-toolkit uses the same two-file layout.

### Do Claude Code plugins work in Copilot CLI unchanged?

Not always. Skills and agents often carry over. Hooks and slash commands differ. St0nefish/agent-toolkit documents four hook differences, and the wshobson/agents capability matrix lists what its Copilot output leaves out. See [How Claude Code and Copilot CLI plugins differ](#how-claude-code-and-copilot-cli-plugins-differ).

### What is the largest open-source collection?

This page does not rank projects. As of 2026-10-11, wshobson/agents lists 94 plugins in its README. Its local source holds 202 agents, 184 skills, and 105 commands.

### Where do Copilot CLI custom agents live?

In `.github/agents/` inside a repository, or in `~/.copilot/agents/` for one user. Each agent is a Markdown file with an `.agent.md` extension.

## Sources

All sources were read on 2026-10-11.

Project sources:

- AI Agents: [README](../README.md) and [LICENSE](../LICENSE) in this repository.
- wshobson/agents: [README](https://raw.githubusercontent.com/wshobson/agents/main/README.md), [LICENSE](https://raw.githubusercontent.com/wshobson/agents/main/LICENSE), and [capability matrix](https://raw.githubusercontent.com/wshobson/agents/main/docs/harnesses.md).
- St0nefish/agent-toolkit: [README](https://raw.githubusercontent.com/St0nefish/agent-toolkit/master/README.md) and [LICENSE](https://raw.githubusercontent.com/St0nefish/agent-toolkit/master/LICENSE).
- dspo/agent-marketplace: [README](https://raw.githubusercontent.com/dspo/agent-marketplace/main/README.md) and [LICENSE](https://raw.githubusercontent.com/dspo/agent-marketplace/main/LICENSE).
- AgentMux: [README](https://raw.githubusercontent.com/markuswondrak/AgentMux/main/README.md) and [pyproject.toml](https://raw.githubusercontent.com/markuswondrak/AgentMux/main/pyproject.toml).
- Karajan Code: [README](https://raw.githubusercontent.com/manufosela/karajan-code/main/README.md), [LICENSE](https://raw.githubusercontent.com/manufosela/karajan-code/main/LICENSE), and [npm registry entry](https://registry.npmjs.org/@karajan-family%2fcode).

Vendor documentation:

- [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Finding and installing plugins for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-finding-installing)
- [Creating a plugin marketplace for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-marketplace)
- [Copilot CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)
- [GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)
- [Creating and using custom agents for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli)

Further reading:

- Chris Ayers, [Agent Skills, Plugins and Marketplace: The Complete Guide](https://chris-ayers.com/posts/agent-skills-plugins-marketplace/), published 2026-03-26.
