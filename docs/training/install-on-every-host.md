# Install the toolkit on your host and check it loaded

<!-- # taste-lint: ignore file-size, ten hosts share one page because the training folder is flat and the index holds one entry per issue. -->

## Goal

Install `project-toolkit` on your AI coding tool and finish with a check that shows it loaded. This page is for new users on any of ten hosts.

We ran the commands on 2026-11-11 with main at `d34536c95c`. Counts come from the tree at that commit. The Codex agent install step is newer. It ran on 2026-11-11 on the branch that adds it, against codex 0.166.0 and 0.167.0, through `test_codex_agents_install_and_load`.

| Host | Version we ran | Skills | Agents | Route | Ran end to end |
|------|----------------|--------|--------|-------|----------------|
| Claude Code | 2.1.319 | 105 | 29 | Marketplace | Yes |
| GitHub Copilot CLI | 1.0.108 | 104 | 29 | Marketplace | Yes |
| VS Code and Visual Studio | Not run | None | 29 | Copy files into your repo | No |
| Codex | 0.167.0 | 105 | 25, from a script | Marketplace, then `install_agents.py` | Yes |
| Cursor | Agent CLI 2026.10.14-0f9edde | 105 | 28 | Local plugin directory | Partly |
| Grok Build | 1.0.77 | 105 | 29 | Marketplace | Yes |
| Pi | 1.5.0 | 105 | None | `pi install` from git | Yes |
| Hermes | Agent v0.23.0 | 91, in two packs | None | `hermes plugins install` per pack | Yes |
| Muse personal agent | Not run | 105 | None | Copy skill folders | No |
| Muse Code | 1.4.15, at `fc91afcf2` | 105 | 25; a signed-in run spawned all 25 | Copy skill and agent folders | Partly |

"Yes" means the install, check, update, and uninstall commands on this page all ran. A model turn that needs your sign-in is the exception. We mark those "Not run".

Devin and Grok Bot have no section. This repository has no Devin tree, and Grok Bot is unsupported ([ADR-115](../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md) Decision 8).

## Before you start

- `git`, and network access to github.com.
- Your host installed. Each section says how to check its version.
- A scratch home folder, if you want to try an install without touching your real host settings. We did this for every host.
- A read of the "Not run" notes for your host. They say what we could not check.

The plugin manifests carry no `version` field. Freshness comes from the commit SHA ([ADR-092](../../.project-toolkit/architecture/ADR-092-omit-plugin-manifest-version.md)). To compare your install with the repository head, read this SHA and use the first 10 characters:

```bash
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

## Steps

Follow the section for your host.

### Install on Claude Code

1. Register the marketplace and install the plugin:

   ```bash
   claude plugin marketplace add rjmurillo/ai-agents
   claude plugin install project-toolkit@ai-agents
   ```

   Inside a session, the same steps are `/plugin marketplace add rjmurillo/ai-agents` and `/plugin install project-toolkit@ai-agents`. We ran the shell form.

2. Restart Claude Code so it loads the new agents and skills.

Update:

```bash
claude plugin marketplace update ai-agents
claude plugin update project-toolkit@ai-agents
```

Uninstall:

```bash
claude plugin uninstall project-toolkit@ai-agents
claude plugin marketplace remove ai-agents
```

### Install on GitHub Copilot CLI

1. Register the marketplace and install the plugin from a shell:

   ```bash
   copilot plugin marketplace add rjmurillo/ai-agents
   copilot plugin install project-toolkit@ai-agents
   ```

   Inside a session, use `/plugin marketplace add rjmurillo/ai-agents` and `/plugin install project-toolkit@ai-agents`. We ran the shell form.

2. You do not need to restart Copilot CLI.

Update:

```bash
copilot plugin update project-toolkit
```

Uninstall:

```bash
copilot plugin uninstall project-toolkit
copilot plugin marketplace remove ai-agents
```

### Install on VS Code and Visual Studio

Not run end to end. We had no VS Code or Visual Studio on the machine. We ran only the file copy, in a scratch folder.

These hosts have no plugin install. They read agent files from `.github/agents/` in your repository. See [Installation paths](../installation.md#installation-paths) and the [Visual Studio notes](../installation.md#visual-studio-20222026-notes). The repository documents no copy command for other repositories. These steps copy the generated files from `src/vs-code-agents/` into that path.

1. Clone the toolkit next to your repository:

   ```bash
   git clone --depth 1 https://github.com/rjmurillo/ai-agents.git
   ```

2. From the root of your repository, copy the agents and the instructions file. `cp -i` asks before it overwrites a file you already have:

   ```bash
   mkdir -p .github/agents
   cp -i ../ai-agents/src/vs-code-agents/*.agent.md .github/agents/
   cp -i ../ai-agents/src/vs-code-agents/copilot-instructions.md .github/copilot-instructions.md
   ```

   If you already have a `.github/copilot-instructions.md`, answer `n` and merge the two files by hand.

3. Reload the VS Code window, or restart Visual Studio.

Update: run `git -C ../ai-agents pull`, then repeat step 2 and answer `y` to overwrite.

Uninstall: delete the `.agent.md` files you copied from `.github/agents/`. Delete `.github/copilot-instructions.md` too, unless it held your own text first.

### Install on Codex

1. Register the marketplace and install the plugin:

   ```bash
   codex plugin marketplace add rjmurillo/ai-agents
   codex plugin add project-toolkit@ai-agents
   ```

   Codex reads `.agents/plugins/marketplace.json` from the repository. It points at the `src/codex` tree ([ADR-115](../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md) Decision 7). No sign-in is needed.

2. Install the agents. A Codex plugin cannot ship agents, so the plugin carries a script that copies them. Run it from the installed plugin folder:

   ```bash
   cache="${CODEX_HOME:-$HOME/.codex}/plugins/cache/ai-agents/project-toolkit"
   python3 -I "$cache/$(ls "$cache" | sort -V | tail -n 1)/install_agents.py"
   ```

   The cache folder is the plugin version. Codex 0.162.1 and 0.167.0 install a manifest with no version field as `1.0.0`, so the folder is normally `1.0.0`. The `sort -V | tail -n 1` part still picks the newest if another folder is there. The script is at `<cache>/<version>/install_agents.py`.

   On Windows the shell lines above do not run. In PowerShell, use `$env:CODEX_HOME` when it is set, otherwise `$env:USERPROFILE\.codex`. List the folders under `<that path>\plugins\cache\ai-agents\project-toolkit`, then run `python -I <that folder>\install_agents.py`. Not verified: the installer on a Windows host.

   With no flag it installs into `.codex/agents/` of the current directory. Use `--project DIR` for another project, or `--user` for `$CODEX_HOME/agents` (`~/.codex/agents` when `CODEX_HOME` is unset). The two flags exclude each other. The script ships 25 agents. It leaves out `analyst`, `code-reviewer`, `comment-analyzer`, and `security`, because Codex agent files cannot limit tools (sandbox_mode, approval_policy, and mcp_servers do not override the parent). Each installed agent says so, and tells the model to do that step itself.

   Things to know:

   - Trust. Codex loads project agents only for trusted projects (measured on codex 0.167.0, 2026-11-11). The script warns when the project is not listed with `trust_level = "trusted"` in `config.toml`. It still installs. A `--user` install needs no trust.
   - Ownership. The script records a SHA-256 for each file it writes in `.project-toolkit-agents.json` next to the agents. It upgrades or removes a file only while the file still matches that record. If you edit a plain-name agent, a later run treats that file as yours and refuses (exit 1, nothing written) until you resolve it: restore the file, delete it, or rerun with `--namespace PREFIX` so the shipped agent installs beside yours as `PREFIX-<name>`. If you edit a `PREFIX-<name>` copy, a later run keeps your edit and its record, warns, and exits 0.
   - Conflicts. If a file with the same name exists and the script did not write it, the script prints the conflict, writes nothing, and exits 1. Pass `--namespace PREFIX` (lowercase letters, digits, hyphens) to install that agent as `PREFIX-<name>` instead. The agents' handoffs still name the unprefixed agent, so they reach your own agent, and the script warns about each one.
   - Cloned repositories. A repository can commit its own `.codex/agents/.project-toolkit-agents.json`, and `--uninstall` deletes the files that file lists. Before you run `--uninstall` (or any install) in a repository you did not create, read that file and run with `--dry-run` first. The script rejects unsafe names, symlinks, and junctions, but it cannot know which listed files you meant to keep.
   - `--dry-run` prints the plan and writes nothing. `--uninstall` removes the files that still match their record and leaves edited files with a warning.
   - Spawn reviewers with `fork_turns="none"`, so a reviewer does not inherit the parent's context.
   - Subagents. Codex cannot enforce the Claude-only `disallowedTools: Agent` line, so the build drops it. Instead, 24 of the 25 shipped bodies carry a `Subagents` section that tells the model not to start subagents. That is a prompt instruction, not a block. A Codex subagent inherits the parent's permissions, which is the bound ADR-115 Decision 3 relies on.
   - Trust path. The warning checks the exact project path. If Codex trusts a parent folder, the warning can be a false alarm.

Update:

```bash
codex plugin marketplace upgrade ai-agents
```

Then run the step 2 command again. The upgrade does not touch `.codex/agents/`, so installed agents stay at the old version until you do. The script upgrades only files that still match its record.

Not verified: whether `codex plugin add project-toolkit@ai-agents` run again copies new files into the installed folder. Check the skill count after an upgrade.

Uninstall:

```bash
# First remove the agents. Add --user, or --project DIR, to match how you installed.
# Without a flag the script looks in the current directory's .codex/agents.
# The script lives in the plugin folder that the next command deletes.
cache="${CODEX_HOME:-$HOME/.codex}/plugins/cache/ai-agents/project-toolkit"
python3 -I "$cache/$(ls "$cache" | sort -V | tail -n 1)/install_agents.py" --uninstall
codex plugin remove project-toolkit@ai-agents
codex plugin marketplace remove ai-agents
```

### Install on Cursor

This section proves the Cursor tree loads from a clean checkout. It does not run the marketplace install. See "Not run" below.

Cursor sign-in is required: check with `cursor-agent status`. Our default model hit its weekly limit, so the command uses `--model auto`.

1. Get a clean checkout and an empty workspace:

   ```bash
   git clone --depth 1 https://github.com/rjmurillo/ai-agents.git
   mkdir scratch && cd scratch
   PLUGIN="$(cd ../ai-agents/src/cursor && pwd)"
   ```

2. Load the Cursor tree for one model turn:

   ```bash
   cursor-agent --model auto --plugin-dir "$PLUGIN" --workspace "$PWD" --trust --force -p "Use only Cursor skill discovery. Find the skill named github whose directory is inside $PLUGIN. Run uv run python -I <skill dir>/scripts/pr/get_pr_checks.py --help 2>&1 | head -3 and show the raw output. Then print the skill dir you used on a line starting with SKILL_DIR="
   ```

   `--force` lets the agent run the command without asking. Use it only in the scratch workspace.

Update: a `--plugin-dir` copy is as fresh as your checkout. Run `git -C ../ai-agents pull`.

Uninstall: nothing was installed. Delete the `scratch` and `ai-agents` folders you made.

Not run:

- The marketplace route. The repository ships `.cursor-plugin/marketplace.json` (marketplace `ai-agents`, plugin `project-toolkit`, source `./src/cursor`). The CLI offers `cursor-agent plugin marketplace add <gitUrl>`. We did not run it, because it registers a marketplace on your Cursor account. The CLI help lists only `marketplace` subcommands under `plugin`. We found no CLI install command, and we did not test the Cursor app.
- ADR-115 records that Cursor loads local plugins from `~/.cursor/plugins/local/<name>/`. We did not test that path.

### Install on Grok Build

Grok Build reuses the Claude tree at `src/claude`. The only Grok file is `.grok-plugin/marketplace.json`, which lists `project-toolkit` at `./src/claude` ([ADR-115](../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md) Decision 4). No sign-in is needed.

1. Register the marketplace:

   ```bash
   grok plugin marketplace add rjmurillo/ai-agents
   ```

2. Install the plugin. Grok asks for trust first. Without `--trust` it stops with this message:

   ```text
   Plugins can run hooks, MCP servers, and skills on your machine, so installation needs explicit trust.
   ```

   The plugin has one advisory Stop hook and runs skill scripts. Read the [Trust Boundary](../../README.md#trust-boundary) first. If you accept, run:

   ```bash
   grok plugin install project-toolkit@ai-agents --trust
   ```

   It prints `Installed 1 plugin(s) from ai-agents: project-toolkit`.

Update:

```bash
grok plugin marketplace update ai-agents
grok plugin update project-toolkit
```

Uninstall:

```bash
grok plugin uninstall project-toolkit
grok plugin marketplace remove ai-agents
```

### Install on Pi

Pi reads the `package.json` at the repository root. Its `pi.skills` key points at `./src/claude/skills`. Pi loads skills only ([ADR-115](../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md) Decision 5). No sign-in is needed.

We used `@earendil-works/pi-coding-agent` 1.5.0, installed from the lockfile in `.github/cli-smoke/pi/` with `npm ci --ignore-scripts`.

1. Install the package from git:

   ```bash
   pi install git:github.com/rjmurillo/ai-agents
   ```

   It prints `Installed git:github.com/rjmurillo/ai-agents`.

Update:

```bash
pi update git:github.com/rjmurillo/ai-agents
```

Uninstall:

```bash
pi remove git:github.com/rjmurillo/ai-agents
```

### Install on Hermes

Hermes caps a plugin at 400 files. The toolkit does not fit in one plugin, so it ships as two packs ([ADR-115](../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md) Decision 6):

| Pack | Skills | Holds |
|------|--------|-------|
| `project-toolkit-delivery` | 50 | Pull request work, build, test, quality gates, security review, operations |
| `project-toolkit-knowledge` | 41 | Memory, context, decisions, requirements, strategy, documentation |

That is 91 skills. Another 14 skills ship in no pack. Hermes rates 7 of them dangerous. Six more refer to an excluded skill. `skill-doctor` has a file over the 1 MiB limit. [src/hermes/README.md](../../src/hermes/README.md) lists each one with its reason. A skill in one pack never refers to a skill in the other pack. No sign-in is needed.

1. Install the knowledge pack and enable it:

   ```bash
   hermes plugins install rjmurillo/ai-agents/src/hermes/project-toolkit-knowledge --enable
   ```

   Hermes warns that the source is custom and unreviewed. Then it prints `Plugin installed` and `Plugin project-toolkit-knowledge enabled.`

2. Install the delivery pack. Run it without extra flags first:

   ```bash
   hermes plugins install rjmurillo/ai-agents/src/hermes/project-toolkit-delivery
   ```

   Hermes scans the pack and rates it `CAUTION`, with 290 findings. In our non-interactive run it printed `Decision: BLOCKED` and `Use --force to override.` We did not test an interactive terminal. Read the findings. The ones we saw were rated `LOW` or `MEDIUM` and point at reference prose and ordinary calls such as `subprocess.run`.

3. If you accept the findings, install over the block and enable the pack:

   ```bash
   hermes plugins install --force --enable rjmurillo/ai-agents/src/hermes/project-toolkit-delivery
   ```

   The repository smoke allows `--force` for this one pack only (`FORCE_ALLOWED_PACKS` in `tests/e2e/hermes_runtime.py`).

Update: see "Check Hermes" below. `hermes plugins check-updates` cannot tell for these packs. Reinstall each pack with `--force`.

Uninstall:

```bash
hermes plugins remove project-toolkit-delivery
hermes plugins remove project-toolkit-knowledge
```

### Install on Muse

Muse means two hosts, and both install the same `src/muse/` tree (ADR-115 Decision 8). Muse support is experimental.

- The Muse personal agent reads `~/workspace/custom-skills/`. The steps below are for it.
- Muse Code, the `muse` CLI, does not read that folder. Use [Install on Muse Code](#install-on-muse-code) instead.

Muse personal agent: not run end to end. No CLI exists for it here. We ran the copy steps and one skill script in a scratch home folder. We did not check that the personal agent loads the skills.

Muse has no plugin manifest in this repository. ADR-115 planned a generated `.muse-plugin/plugin.json`. The tree at `d34536c95c` has none. The install path is a file copy.

1. Clone the toolkit:

   ```bash
   git clone --depth 1 https://github.com/rjmurillo/ai-agents.git
   cd ai-agents
   ```

2. Copy each skill folder. The loop skips any name Muse already has. Unlike the [src/muse/README.md](../../src/muse/README.md) block, it keeps any folder that exists:

   ```bash
   mkdir -p ~/workspace/custom-skills
   for d in src/muse/skills/*/; do
     name="$(basename "$d")"
     [ -e ~/workspace/custom-skills/"$name" ] || cp -R "$d" ~/workspace/custom-skills/"$name"
   done
   ```

3. Copy the shared `lib/` folder one level above `custom-skills`:

   ```bash
   [ -e ~/workspace/lib ] || cp -R src/muse/lib ~/workspace/lib
   ```

   Without it, skill scripts fail. The [src/muse/README.md](../../src/muse/README.md) block differs from steps 2 and 3: it copies `lib/` too, and it moves any skill folder or `lib/` already there to a backup folder instead of skipping it ([#7278](https://github.com/rjmurillo/ai-agents/issues/7278)).

Update: the step 2 loop never replaces a folder that exists, so running it again does not refresh your copy. Delete the folders named in `src/muse/skills/` from `~/workspace/custom-skills/`, and delete `~/workspace/lib`. Pull the clone and repeat steps 2 and 3.

Uninstall: delete the same folders and `~/workspace/lib`.

### Install on Muse Code

Muse Code 1.4.15 ran on 2026-11-11 with main at `fc91afcf2`. Muse Code loads user skills from `${XDG_CONFIG_HOME:-~/.config}/muse/skills/`. Skill scripts look for `lib/` one level up, at `${XDG_CONFIG_HOME:-~/.config}/muse/lib/`. Muse Code documents `~/.config/muse/agents/` for agents (ADR-115 Decision 8). This install uses `${XDG_CONFIG_HOME:-~/.config}/muse/agents/`, the same root as skills. No run shows that Muse Code reads the `XDG_CONFIG_HOME` form for agents. The personal agent has no documented agent format and gets no agents.

Do not copy these skills into the `skills` folder under `~/.agents`, or under a repository's `.agents` folder. Codex reads those folders too, and its copies differ.

1. Clone the toolkit, as in step 1 above.

2. Copy the skills, `lib/`, and agents. The block moves any file or folder already there to a backup folder. It never deletes one:

   ```bash
   root="${XDG_CONFIG_HOME:-$HOME/.config}/muse"
   backup="$root/install-backup-$(date +%Y%m%d%H%M%S)-$$"
   mkdir -p "$root/skills" "$root/agents"
   if [ ! -e "$root/lib" ] && [ ! -L "$root/lib" ] \
     || { mkdir -p "$backup" && mv "$root/lib" "$backup/lib"; }; then
     cp -R src/muse/lib "$root/lib"
   else
     echo "backup failed, kept $root/lib" >&2
   fi
   for d in src/muse/skills/*/; do
     name="$(basename "$d")"
     if [ -e "$root/skills/$name" ] || [ -L "$root/skills/$name" ]; then
       mkdir -p "$backup/skills" && mv "$root/skills/$name" "$backup/skills/$name" \
         || { echo "backup failed, kept $root/skills/$name" >&2; continue; }
     fi
     cp -R "$d" "$root/skills/$name"
   done
   for f in src/muse/agents/*.md; do
     name="$(basename "$f")"
     if [ -e "$root/agents/$name" ] || [ -L "$root/agents/$name" ]; then
       mkdir -p "$backup/agents" && mv "$root/agents/$name" "$backup/agents/$name" \
         || { echo "backup failed, kept $root/agents/$name" >&2; continue; }
       echo "moved $root/agents/$name to $backup/agents/$name"
     fi
     cp "$f" "$root/agents/$name"
   done
   ```

   On 2026-11-11 the tree shipped 25 agents. It leaves out `analyst`, `code-reviewer`, `comment-analyzer`, and `security`, because their Claude files declare a `tools` list and Muse Code tool names are not documented. Each shipped body names the agents left out. Muse Code cannot spawn an agent with an unrecognized frontmatter key, so only `name` and `description` ship. On 2026-11-12, signed-in `muse exec` runs on 1.4.15 spawned all 25 from `~/.config/muse/agents/`, and each child's session log held its agent body. Muse Code refused a control agent with an extra frontmatter key as `agent_definition_invalid`. The load test is `tests/e2e/test_muse_agents_load.py`, and it needs a Muse login. Muse Code's default sandbox hides `~/.config/muse` from the model's shell, so the model cannot run a skill script from the user folder (`Permission denied`). It can read the skill with its skill tool. Account-wide agents have unrestricted tools and apply to every workspace. The Claude deny on starting subagents does not carry over. 24 agent bodies instead carry a Subagents section that asks the model not to start subagents. That is a prompt instruction, not a block.

Update: pull the clone and run step 2 again. It moves the old copies aside.

Uninstall: move the folders named in `src/muse/skills/` out of `~/.config/muse/skills/`. Move the files named in `src/muse/agents/` out of `~/.config/muse/agents/`. Move `~/.config/muse/lib` out too. Use `$XDG_CONFIG_HOME/muse` in place of `~/.config/muse` when that variable is set.

## Check your result

Each check below proves the toolkit loaded. Each section also says how to tell a stale install and what to do if the check fails.

### Check Claude Code

```bash
claude plugin list
claude plugin details project-toolkit@ai-agents
```

You should see:

```text
Installed plugins:
  ❯ project-toolkit@ai-agents
    Version: d34536c95c29
    Scope: user
    Status: ✔ enabled
```

The details command lists the parts the host loaded:

```text
Component inventory
  Skills (105)  adr-generator, adr-review, ...
  Agents (29)  analyst, architect, ...
  Hooks (1)  Stop  (harness-only ...)
  MCP servers (0)
```

The hook line is shortened here. The host prints a longer note after `Stop`.

The tree also holds 15 rule files. The details command lists no rules, so do not expect them to load as a plugin component.

Not run: asking an agent a question. That needs a signed-in session. See [Verify Installation](../installation.md#verify-installation).

Stale check: `Version` is the commit SHA. If its first 10 characters differ from the `git ls-remote` SHA above, run the update commands. When you are current, the update prints:

```text
✔ project-toolkit is already at the latest version (d34536c95c29).
```

We did not run an update that moved to a newer commit.

If it fails:

- `claude plugin` is not recognized: update Claude Code to a build with plugin marketplaces.
- Agents or skills are missing after install: restart Claude Code.
- Agents that name `mcp__github__*` tools run without them: see the [GitHub MCP prerequisite](../installation.md#github-mcp-prerequisite).
- Other fixes: [Installation troubleshooting](../installation.md#troubleshooting).

### Check GitHub Copilot CLI

```bash
copilot plugin list
copilot skill list
```

The install printed:

```text
Marketplace "ai-agents" added successfully.
Plugin "project-toolkit" installed successfully. Installed 104 skills.
```

The list command shows the plugin:

```text
Built-in plugins:
  • browser-use (v0.1.0) [disabled]
Installed plugins:
  • project-toolkit@ai-agents
```

`copilot skill list` prints a `Plugin skills:` heading, then one line per skill. The first is `adr-generator`.

The Copilot tree has one skill fewer than the Claude tree. It omits `merge-resolver`. It holds 29 agents and 15 instruction files, and registers no hooks (ADR-097). The install output confirms the 104 skills. We did not list agents from the host.

Not run: asking an agent a question with `copilot --agent analyst --prompt "Hello, are you available?"`. That needs a signed-in session. See [Verify Installation](../installation.md#verify-installation).

Stale check: `copilot plugin list` prints no version, and the update does not compare versions (ADR-092). You cannot read a SHA from the list output. Update whenever you want the latest. The update prints:

```text
Plugin "project-toolkit" updated successfully. Updated 104 skills.
```

If it fails:

- `No plugin.json found in repository`: add the marketplace first with the first command in the install steps.
- `copilot plugin` is not recognized: update Copilot CLI to a recent stable release.
- Other fixes: [Installation troubleshooting](../installation.md#troubleshooting). The Copilot token that CI uses is a different topic. See [Copilot CLI setup](../copilot-cli-setup.md).

### Check VS Code and Visual Studio

Count the agent files:

```bash
ls .github/agents/*.agent.md | wc -l
```

We got:

```text
29
```

Then open Copilot Chat and ask:

```text
@orchestrator Hello, are you available?
```

Not run: this chat check. It needs VS Code or Visual Studio and a Copilot sign-in. If you run it, record the host version and the reply.

Stale check: the copy carries no version and no SHA. Write down your clone's SHA when you copy, with `git -C ../ai-agents rev-parse --short=10 HEAD`. Later, compare it with the `git ls-remote` SHA above.

If it fails:

- Agents do not appear: reload the window or restart the IDE.
- Visual Studio shows no agents: confirm the version and that the "Enable project specific .NET instructions" feature is on. See the [Visual Studio notes](../installation.md#visual-studio-20222026-notes).
- Other fixes: [Installation troubleshooting](../installation.md#vs-code--visual-studio).

### Check Codex

```bash
codex plugin list
codex debug prompt-input hi | grep -oE 'project-toolkit:[a-z0-9-]+' | sort -u | wc -l
```

The list shows the plugin installed and enabled (path shortened here):

```text
PLUGIN                     STATUS              VERSION  SOURCE
project-toolkit@ai-agents  installed, enabled  1.0.0    <CODEX_HOME>/.tmp/marketplaces/ai-agents/src/codex
```

The second command prints the number of toolkit skills that Codex puts in its prompt:

```text
105
```

The `VERSION` is always `1.0.0`. The tree has no version field (ADR-092), so Codex reports a default. Codex gets no rules, and registers no plugin component for agents. It loads agents only from `.codex/agents/` or `$CODEX_HOME/agents/`, which step 2 fills, and no plugin path carries rules.

To check the agents after step 2, run `codex debug prompt-input hi` and look for each agent name in the `agent_type` list of the `spawn_agent` tool. The list appears only once a custom agent exists.

Not run: a Codex model turn that uses a skill or an agent.

Stale check: the installed folder is named `1.0.0` and never changes. Codex keeps a git snapshot of the marketplace. Read its SHA and compare it with the `git ls-remote` SHA:

```bash
git -C "${CODEX_HOME:-$HOME/.codex}/.tmp/marketplaces/ai-agents" rev-parse --short=10 HEAD
```

We read `d34536c95c`. If it differs, run the upgrade. It prints:

```text
Upgraded marketplace `ai-agents` to the latest configured revision.
```

If it fails:

- `codex plugin` is not recognized: update Codex CLI.
- The skill count is not 105: run `codex plugin list` and confirm the status is `installed, enabled`.
- Codex may print a warning about PATH aliases when `CODEX_HOME` sits under a temporary directory. The install still worked in our run.

### Check Cursor

The agent prints the first lines of the script help, then the skill folder:

```text
usage: get_pr_checks.py [-h] [--owner OWNER] [--repo REPO]
                        --pull-request PULL_REQUEST [--wait]
                        [--timeout-seconds TIMEOUT_SECONDS]
SKILL_DIR=<your path>/ai-agents/src/cursor/skills/github
```

`SKILL_DIR` must start with your `$PLUGIN` path. Cursor also reads Claude plugins from `~/.claude/plugins`. If you installed the Claude plugin, Cursor can pick that copy first. A `SKILL_DIR` outside `$PLUGIN` means you checked a different copy.

Count what the Cursor tree holds:

```bash
ls ../ai-agents/src/cursor/skills | wc -l
ls ../ai-agents/src/cursor/agents | wc -l
ls ../ai-agents/src/cursor/rules | wc -l
```

We got `105`, `28`, and `15`. Cursor gets no `security` agent. Cursor has no tool allow list, so an agent that needs one stays out (ADR-115 Decision 3).

Stale check: compare your checkout with the repository head.

```bash
git -C ../ai-agents rev-parse --short=10 HEAD
```

If the first 10 characters differ from the `git ls-remote` SHA, run `git -C ../ai-agents pull`.

If it fails:

- `ActionRequiredError ... not included in your weekly usage`: add `--model auto`, or pick a model from `cursor-agent --list-models`.
- Every `plugin` command fails: sign in. `cursor-agent status` should say `Logged in`.
- The skill script cannot find its `lib/` folder: the copy is missing `lib/`. Use the whole `src/cursor` folder.

### Check Grok Build

```bash
grok plugin list
grok plugin details project-toolkit
```

The list shows the plugin under an id that starts with `claude-`. Your suffix will differ, and the path is shortened here:

```text
  claude-b4e95c70: project-toolkit [local: <GROK_HOME>/marketplace-cache/<id>/src/claude] (ai-agents)
```

The details command ends with the component line:

```text
  components: 1 skill dir(s), 0 command dir(s), 1 agent dir(s), hooks
```

Then count the installed skills and agents. Use the `path:` line from the details output:

```bash
ls -d <path>/skills/*/ | wc -l
ls <path>/agents | wc -l
```

We got `105` and `29`. `grok plugin validate <path>` prints `Plugin manifest is valid.`

Grok plugins have no rules component, so no rules load. The `model` keys in the skills are accepted and not applied (ADR-115 Decision 4).

Not run: a Grok model turn that uses a skill.

Stale check: Grok prints no versions on update, only `claude-b4e95c70: updated (? -> ?)`. Use the SHA of the marketplace cache. The cache is a git checkout under `~/.grok/marketplace-cache/<id>`:

```bash
git -C ~/.grok/marketplace-cache/<id> rev-parse --short=10 HEAD
```

We read `d34536c95c`. If it differs from the `git ls-remote` SHA, run the update commands. The marketplace update prints `ai-agents: synced`.

If it fails:

- `requires confirmation`: add `--trust` after you read the trust note above.
- `Plugin "project-toolkit" not found`: the install did not finish. Run `grok plugin list`.
- `grok plugin` is not recognized: update Grok Build.

### Check Pi

1. List the package:

   ```bash
   pi list
   ```

   You should see:

   ```text
   User packages:
     git:github.com/rjmurillo/ai-agents
       <PI_CODING_AGENT_DIR>/git/github.com/rjmurillo/ai-agents
   ```

2. Count the skills Pi loaded. The repository smoke sets `PI_OFFLINE=1` for this call, and so did we:

   ```bash
   printf '{"id":"1","type":"get_commands"}\n' | PI_OFFLINE=1 pi --mode rpc | grep -o '"name":"skill:' | wc -l
   ```

   It prints:

   ```text
   105
   ```

   Each skill shows as `skill:<name>`, such as `skill:adr-generator`.

Pi gets skills only, no agents, rules, or hooks.

Stale check: Pi keeps a git checkout of the repository. Read its SHA from the path that `pi list` printed:

```bash
git -C <path from pi list> rev-parse --short=10 HEAD
```

We read `d34536c95c`. If it differs from the `git ls-remote` SHA, run the update. It prints `Updated git:github.com/rjmurillo/ai-agents`.

If it fails:

- `pi: command not found`: install Pi first.
- The count is lower than 105: run `pi list` and confirm the package path exists.
- A subdirectory install is not documented for Pi. Install from the repository root as shown.

The repository smoke for this host is `tests/e2e/test_pi_package_smoke.py`. It also runs a skill script that imports `lib/`.

### Check Hermes

```bash
hermes plugins list
hermes plugins doctor project-toolkit-knowledge
hermes plugins doctor project-toolkit-delivery
```

The list shows both packs with status `enabled` and source `user`. Each doctor run prints:

```text
  OK: runtime discovery, manifest parsing, import, and registration passed
```

Then count the skills on disk:

```bash
ls -d "${HERMES_HOME:-$HOME/.hermes}"/plugins/project-toolkit-delivery/skills/*/ | wc -l
ls -d "${HERMES_HOME:-$HOME/.hermes}"/plugins/project-toolkit-knowledge/skills/*/ | wc -l
```

We got `50` and `41`. Hermes gets skills only.

Not run: a Hermes model turn that uses a skill. `hermes skills list` showed no plugin skills in our run, so do not use it as your check.

Stale check: Hermes does not tell you. For these packs, `hermes plugins check-updates` reports status `unknown`. The status text says there is provenance drift because the folder has no `.git`, and asks you to reinstall from the recorded source. `hermes plugins update project-toolkit-knowledge` printed `already up to date`. We do not know what it compared, so do not trust it as a freshness check. Read the head SHA with `git ls-remote`, then reinstall each pack over itself:

```bash
hermes plugins install --force --enable rjmurillo/ai-agents/src/hermes/project-toolkit-knowledge
```

The help says `--ref COMMIT_SHA` installs one exact 40-character commit. Not run: `--force` over an existing pack, and `--ref`.

If it fails:

- `Decision: BLOCKED`: Hermes rated the pack `CAUTION`. See step 3 of the install.
- `No plugin named 'project-toolkit-delivery'` when you enable: the install was blocked, so nothing was installed. Finish step 3.
- A fresh Hermes data root sets up its Python dependencies on the first install. Let it finish.
- A skill you expect is missing: check the excluded list in [src/hermes/README.md](../../src/hermes/README.md).

### Check Muse

Count the skill folders:

```bash
ls ~/workspace/custom-skills | wc -l
```

We got `105` in a fresh scratch folder. If you had skills already, your count is higher.

Run one skill script from the copy:

```bash
cd ~ && uv run python -I ~/workspace/custom-skills/github/scripts/pr/get_pr_checks.py --help
```

It prints the usage text:

```text
usage: get_pr_checks.py [-h] [--owner OWNER] [--repo REPO]
                        --pull-request PULL_REQUEST [--wait]
                        [--timeout-seconds TIMEOUT_SECONDS]
```

One `src/muse` tree serves two Muse targets. The personal agent gets skills and `lib/` only. Muse Code gets skills, `lib/`, and agents. The skill frontmatter keeps only `name` and `description`. The personal agent steps are in [src/muse/README.md](../../src/muse/README.md). The Muse Code steps are in [Install on Muse Code](#install-on-muse-code): skills and `lib/` under `${XDG_CONFIG_HOME:-$HOME/.config}/muse/`, agents in `muse/agents/`. On 2026-11-12, signed-in `muse exec` runs on 1.4.15 spawned all 25 agents from `muse/agents/` (`tests/e2e/test_muse_agents_load.py` needs a Muse login). On 2026-11-11, Muse Code 1.4.15 `muse skills validate` accepted all 105 `src/muse/skills` directories with no login (`tests/e2e/test_muse_skills_validate.py`).

Not run: asking Muse to list or use a skill.

Stale check: the copy records no SHA. Write down your clone's SHA when you copy, with `git rev-parse --short=10 HEAD`. Later, compare it with the `git ls-remote` SHA.

If it fails:

- `Plugin lib directory not found: <home>/workspace/lib`: you skipped step 3.
- A skill folder already existed: the loop kept your copy. See the update note above.
- Muse does not list the skills: we could not test this. Check that `~/workspace/custom-skills/` is the folder your Muse build reads.

### Check Muse Code

Count the skills Muse Code loaded from its user folder:

```bash
muse skills list --source user --json | python3 -c "import json,sys; print(sum(s['path'].startswith('\$CONFIG_DIR/skills') for s in json.load(sys.stdin)['skills']))"
```

We got `105` in a scratch home with no other skills. Muse Code prints the path with a literal `$CONFIG_DIR` prefix.

Run one skill script from the copy:

```bash
cd ~ && python3 -I "${XDG_CONFIG_HOME:-$HOME/.config}/muse/skills/github/scripts/pr/get_pr_checks.py" --help
```

It prints the same usage text as the personal-agent check above.

Count the agent files the install copied:

```bash
ls "${XDG_CONFIG_HOME:-$HOME/.config}/muse/agents/"*.md | wc -l
```

It prints `25` in a scratch home with no other agents (2026-11-11). It counts files only. The spawn evidence is in the install step above.

We also ran one signed-in `muse exec` turn. It loaded the `github` skill and ran that script. That run used a copy in a scratch repository's project skill folder, not the user folder.

On 2026-11-12, a signed-in turn loaded the `github` skill from the user folder with the skill tool. The same turn could not run the script there: Muse Code's default sandbox answered `Permission denied` for anything under `~/.config/muse`. The script command above works from your own shell.

Not run: update or uninstall in a real home.

Muse Code trims its skill catalog to 32 KB. In a scratch home with these 105 skills and the 26 built-in and plugin skills, it loaded 131 skills. It shortened 104 descriptions and omitted no skill.

If it fails:

- The count is `0`, and the skills sit in `~/workspace/custom-skills/`: that is the personal-agent folder. Muse Code does not read it. Run the Muse Code step 2.
- `Plugin lib directory not found`: `lib/` is missing from `${XDG_CONFIG_HOME:-~/.config}/muse/`. Run step 2 again.
- `muse skills list` shows `skill-shadowed`: another root has a skill with the same name, and Muse Code loaded that one.
- The agent count is `0`: step 2 did not copy the agents. Run step 2 from the repository root.

## Next

Go to [Getting started](../getting-started.md) to use the agents you installed. The [installation guide](../installation.md) covers component installs, the GitHub MCP prerequisite, and troubleshooting.

Reference sources this page relies on:

- [ADR-115: native plugin support per host](../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md)
- [ADR-092: omit plugin manifest version](../../.project-toolkit/architecture/ADR-092-omit-plugin-manifest-version.md)
- [Hermes pack index](../../src/hermes/README.md) and [Muse tree guide](../../src/muse/README.md)
- [Pi smoke](../../tests/e2e/test_pi_package_smoke.py) and [Hermes smoke helpers](../../tests/e2e/hermes_runtime.py)
