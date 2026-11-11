# Install the toolkit on your host

Pick your AI coding tool, follow its page, and finish with a check that shows the toolkit loaded.

Counts on these pages come from the tree at `8a8af7bc9d` (2026-11-10). Each page names the host version and the date we ran its commands.

## Pick your host

| Host | Page | What you get | Install route | Run end to end |
|------|------|--------------|---------------|----------------|
| Claude Code | [claude-code.md](claude-code.md) | 105 skills, 29 agents, 1 Stop hook | Marketplace | Yes |
| GitHub Copilot CLI | [copilot-cli.md](copilot-cli.md) | 104 skills, 29 agents | Marketplace | Yes |
| VS Code and Visual Studio | [vs-code-visual-studio.md](vs-code-visual-studio.md) | 29 agents, repository instructions | Copy files into your repo | No |
| Codex | [codex.md](codex.md) | 105 skills | Marketplace | Yes |
| Cursor | [cursor.md](cursor.md) | 105 skills, 28 agents, 23 rules | Local plugin directory | Partly |
| Grok Build | [grok-build.md](grok-build.md) | Claude tree: skills, agents, 1 Stop hook | Marketplace | Yes |
| Pi | [pi.md](pi.md) | 105 skills | `pi install` from git | Yes |
| Hermes | [hermes.md](hermes.md) | 91 skills in two packs | `hermes plugins install` per pack | Yes |
| Muse | [muse.md](muse.md) | 105 skills | Copy skill folders | No |

Devin and Grok Bot have no page. Devin has no tree in this repository. Grok Bot is unsupported (ADR-115 Decision 8).

## How we checked these pages

We ran each install in a scratch home directory. Your real host settings were not touched. Pages note anything we could not run.

"Yes" in the last column means the install, check, update, and uninstall commands shown on the page all ran. A model turn that needs your sign-in is the exception. Pages link to those steps and mark them "Not run".

"No" and "Partly" hosts have a "Not run" note on their page. Read it before you rely on that page.

## How to tell an install is stale

The plugin manifests carry no `version` field (ADR-092). Freshness comes from the commit SHA.

1. Read the SHA of the repository head:

   ```bash
   git ls-remote https://github.com/rjmurillo/ai-agents HEAD
   ```

2. Read the SHA your host holds. Each page shows where.
3. If the first 10 characters differ, your install is behind. Each page lists the update command.

Not every host shows its SHA. Where one does not, the page says so and gives the safe update command.

## Sources

- [ADR-115: native plugin support per host](../../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md)
- [ADR-092: omit plugin manifest version](../../../.project-toolkit/architecture/ADR-092-omit-plugin-manifest-version.md)
- [Installation guide](../../installation.md)

## Next

Pick a host page above. After you install, try [Getting started](../../getting-started.md).
