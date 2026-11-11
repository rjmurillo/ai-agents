# Install the toolkit on GitHub Copilot CLI

Verified on GitHub Copilot CLI 1.0.108 on 2026-11-11. Main was at `8a8af7bc9d` (2026-11-10).

## Goal

Install `project-toolkit` and see Copilot CLI load 104 plugin skills.

## Before you start

- Copilot CLI with plugin support. Check with `copilot --version`.
- A GitHub Copilot subscription, for model turns. The install and the checks below need no sign-in.
- Network access to github.com.

## Steps

1. Register the marketplace and install the plugin from a shell:

   ```bash
   copilot plugin marketplace add rjmurillo/ai-agents
   copilot plugin install project-toolkit@ai-agents
   ```

   Inside a Copilot CLI session, use `/plugin marketplace add rjmurillo/ai-agents` and `/plugin install project-toolkit@ai-agents`. We ran the shell form.

2. You do not need to restart Copilot CLI.

## Check your result

```bash
copilot plugin list
copilot skill list
```

The install prints:

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

Not run: asking an agent a question with `copilot --agent analyst --prompt "Hello, are you available?"`. That needs a signed-in session. See [Verify Installation](../../installation.md#verify-installation).

## Update, and tell if you are stale

`copilot plugin list` prints no version, and the update does not compare versions (ADR-092). You cannot read a SHA from the list output. Update whenever you want the latest:

```bash
copilot plugin update project-toolkit
```

It prints:

```text
Plugin "project-toolkit" updated successfully. Updated 104 skills.
```

To see how old your copy is, find the install folder under `~/.copilot/installed-plugins/ai-agents/project-toolkit`. We did not check whether that folder records a commit SHA.

## Uninstall

```bash
copilot plugin uninstall project-toolkit
copilot plugin marketplace remove ai-agents
```

## If it fails

- `No plugin.json found in repository`: add the marketplace first with the first command in Steps.
- `/plugin` or `copilot plugin` is not recognized: update Copilot CLI to a recent stable release.
- Other fixes: [Installation troubleshooting](../../installation.md#troubleshooting).
- The Copilot token that CI uses is a different topic. See [Copilot CLI setup](../../copilot-cli-setup.md).

## What Copilot CLI gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 104 | `src/copilot-cli/skills/` |
| Agents | 29 | `src/copilot-cli/agents/` |
| Instruction files | 23 | `src/copilot-cli/instructions/` |
| Hooks | None | ADR-097 |

The Copilot tree has one skill fewer than the Claude tree. It omits `merge-resolver`.

The skill and agent counts for the install come from the tree. The install output confirms the 104 skills. We did not list agents from the host.

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
