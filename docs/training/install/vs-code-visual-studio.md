# Install the toolkit on VS Code and Visual Studio

Not run end to end. We had no VS Code or Visual Studio on the machine where we checked these commands. We ran only the file copy steps, in a scratch folder, with main at `8a8af7bc9d` (2026-11-10) on 2026-11-11. The chat check at the end is not run.

## Goal

Put the 29 toolkit agents in your repository so Copilot Chat lists them.

## Before you start

- VS Code with GitHub Copilot Chat, or Visual Studio 2022 17.14 or later, or Visual Studio 2026. See [Visual Studio notes](../../installation.md#visual-studio-20222026-notes) for the requirements.
- A GitHub Copilot subscription.
- A git repository you want the agents in.
- `git`.

These hosts have no plugin install. They read agent files from `.github/agents/` in your repository (see [Installation paths](../../installation.md#installation-paths)). The repository does not document a copy command for other repositories. These steps copy the generated files from `src/vs-code-agents/` into that path.

## Steps

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

## Check your result

Count the agent files:

```bash
ls .github/agents/*.agent.md | wc -l
```

We got `29`.

Then open Copilot Chat and ask:

```text
@orchestrator Hello, are you available?
```

Not run: this chat check. It needs VS Code or Visual Studio and a Copilot sign-in. If you run it, record the host version and the reply.

## Update, and tell if you are stale

The copy carries no version and no SHA. Note the SHA of your clone when you copy:

```bash
git -C ../ai-agents rev-parse --short=10 HEAD
```

Later, compare it with the repository head:

```bash
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

If the first 10 characters differ, run `git -C ../ai-agents pull` and repeat step 2. Answer `y` to overwrite.

## Uninstall

Delete the `.agent.md` files you copied from `.github/agents/`. Delete `.github/copilot-instructions.md` too, unless it held your own text first.

## If it fails

- Agents do not appear: reload the window or restart the IDE.
- Visual Studio shows no agents: confirm the version and that the "Enable project specific .NET instructions" feature is on. See [Visual Studio notes](../../installation.md#visual-studio-20222026-notes).
- Other fixes: [Installation troubleshooting](../../installation.md#vs-code--visual-studio).

## What you get

| Part | Count | Source |
|------|-------|--------|
| Agents | 29 | `src/vs-code-agents/*.agent.md` |
| Instructions | 1 file | `src/vs-code-agents/copilot-instructions.md` |
| Skills | None | The source folder holds only agents and one instructions file |

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
