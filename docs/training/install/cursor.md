# Install the toolkit on Cursor

Verified on Cursor Agent CLI 2026.10.14-0f9edde on 2026-11-11. Main was at `8a8af7bc9d` (2026-11-10).

## Goal

Load the Cursor tree from a clean checkout and see Cursor find the `github` skill and run its script.

This page proves the tree loads. It does not run the marketplace install. See "Not run" below.

## Before you start

- The Cursor Agent CLI (`cursor-agent`). Check with `cursor-agent --version`.
- A Cursor sign-in. Check with `cursor-agent status`. Model turns need it.
- A Cursor plan that can run a model turn. Our default model hit its weekly limit, so the command below sets `--model auto`.
- `git`.

## Steps

1. Get a clean checkout and an empty workspace:

   ```bash
   git clone --depth 1 https://github.com/rjmurillo/ai-agents.git
   mkdir scratch && cd scratch
   PLUGIN="$(cd ../ai-agents/src/cursor && pwd)"
   ```

2. Load the Cursor tree for one model turn:

   ```bash
   cursor-agent --model auto --plugin-dir "$PLUGIN" --workspace "$PWD" --trust --force -p "Use only Cursor skill discovery. Find the skill named github whose directory is inside $PLUGIN. Run python3 -I <skill dir>/scripts/pr/get_pr_checks.py --help 2>&1 | head -3 and show the raw output. Then print the skill dir you used on a line starting with SKILL_DIR="
   ```

   `--force` lets the agent run the command without asking. Use it only in the scratch workspace.

## Check your result

The agent prints the first lines of the script help, then the skill folder:

```text
usage: get_pr_checks.py [-h] [--owner OWNER] [--repo REPO]
                        --pull-request PULL_REQUEST [--wait]
                        [--timeout-seconds TIMEOUT_SECONDS]
SKILL_DIR=<your path>/ai-agents/src/cursor/skills/github
```

Check that `SKILL_DIR` starts with your `$PLUGIN` path. Cursor also reads Claude plugins from `~/.claude/plugins`. If you installed the Claude plugin, Cursor can pick that copy first. A `SKILL_DIR` outside `$PLUGIN` means you checked a different copy.

The Cursor tree holds:

```bash
ls ../ai-agents/src/cursor/skills | wc -l
ls ../ai-agents/src/cursor/agents | wc -l
ls ../ai-agents/src/cursor/rules | wc -l
```

We got `105`, `28`, and `23`.

## Update, and tell if you are stale

A `--plugin-dir` copy is as fresh as your checkout. Compare it with the repository head:

```bash
git -C ../ai-agents rev-parse --short=10 HEAD
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

If the first 10 characters differ, run `git -C ../ai-agents pull`.

## Uninstall

Nothing was installed. Delete the `scratch` and `ai-agents` folders you made.

## Not run

- The marketplace route. The repository ships `.cursor-plugin/marketplace.json` (marketplace `ai-agents`, plugin `project-toolkit`, source `./src/cursor`). The CLI offers `cursor-agent plugin marketplace add <gitUrl>`. We did not run it, because it registers a marketplace on your Cursor account. The CLI help lists only `marketplace` subcommands under `plugin`. We found no CLI install command, and we did not test the Cursor app.
- ADR-115 records that Cursor loads local plugins from `~/.cursor/plugins/local/<name>/`. We did not test that path.

## If it fails

- `ActionRequiredError ... not included in your weekly usage`: add `--model auto`, or pick a model from `cursor-agent --list-models`.
- Every `plugin` command fails: sign in. `cursor-agent status` should say `Logged in`.
- The skill script cannot find its `lib/` folder: the copy is missing `lib/`. Use the whole `src/cursor` folder.

## What Cursor gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 105 | `src/cursor/skills/` |
| Agents | 28 | `src/cursor/agents/` |
| Rules | 23, as `.mdc` files | `src/cursor/rules/` |

Cursor gets no `security` agent. Cursor has no tool allow list, so an agent that needs one stays out (ADR-115 Decision 3).

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
