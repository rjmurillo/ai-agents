# Install the toolkit on Codex

Verified on Codex CLI 0.167.0 on 2026-11-11. The commands ran with main at `b959011e3f`. The next main commit changed only Cursor files, so the Codex tree at `8a8af7bc9d` (2026-11-10) is the same.

## Goal

Install `project-toolkit` and see Codex load 105 skills.

## Before you start

- Codex CLI with plugin support. Check with `codex --version`.
- Network access to github.com.
- No sign-in is needed for these steps.

## Steps

1. Register the marketplace and install the plugin:

   ```bash
   codex plugin marketplace add rjmurillo/ai-agents
   codex plugin add project-toolkit@ai-agents
   ```

   Codex reads `.agents/plugins/marketplace.json` from the repository. It points at the `src/codex` tree (ADR-115 Decision 7).

## Check your result

```bash
codex plugin list
codex debug prompt-input hi | grep -oE 'project-toolkit:[a-z0-9-]+' | sort -u | wc -l
```

The list shows the plugin installed and enabled (paths shortened here):

```text
PLUGIN                     STATUS              VERSION  SOURCE
project-toolkit@ai-agents  installed, enabled  1.0.0    <CODEX_HOME>/.tmp/marketplaces/ai-agents/src/codex
```

The second command prints the number of toolkit skills that Codex puts in its prompt:

```text
105
```

The `VERSION` is always `1.0.0`. The tree has no version field (ADR-092), so Codex reports a default.

Not run: a Codex model turn that uses a skill.

## Update, and tell if you are stale

The installed folder is named `1.0.0` and never changes, so it tells you nothing. Codex keeps a git snapshot of the marketplace. Read its SHA and compare it with the repository head:

```bash
git -C "${CODEX_HOME:-$HOME/.codex}/.tmp/marketplaces/ai-agents" rev-parse --short=10 HEAD
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

If the first 10 characters differ, refresh the snapshot:

```bash
codex plugin marketplace upgrade ai-agents
```

It prints:

```text
Upgraded marketplace `ai-agents` to the latest configured revision.
```

Not verified: whether running `codex plugin add project-toolkit@ai-agents` again copies the new files into the `1.0.0` folder. Check the skill count again after an upgrade.

## Uninstall

```bash
codex plugin remove project-toolkit@ai-agents
```

This prints ``Removed plugin `project-toolkit` from marketplace `ai-agents`.`` The list then shows `not installed`. Not run: `codex plugin marketplace remove ai-agents`, which drops the marketplace source.

## If it fails

- `codex plugin` is not recognized: update Codex CLI.
- The skill count is not 105: run `codex plugin list` and confirm the status is `installed, enabled`.
- Codex may print a warning about PATH aliases when `CODEX_HOME` sits under a temporary directory. The install still worked in our run.

## What Codex gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 105 | `src/codex/skills/` |
| Agents | None | Codex loads agents only from `.codex/agents/` |
| Rules | None | No plugin path carries them |

ADR-115 Decision 7 explains why.

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
