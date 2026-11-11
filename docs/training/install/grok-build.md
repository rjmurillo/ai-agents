# Install the toolkit on Grok Build

Verified on Grok Build 1.0.77 on 2026-11-11. The commands ran with main at `b959011e3f`. The next main commit changed only Cursor files, so the `src/claude` tree that Grok reads is the same at `8a8af7bc9d` (2026-11-10).

## Goal

Install `project-toolkit` and see Grok Build hold 105 skills and 29 agents.

## Before you start

- Grok Build with plugin support. Check with `grok --version`.
- Network access to github.com.
- No sign-in is needed for these steps.

Grok Build reuses the Claude tree at `src/claude`. It has no tree of its own. The only Grok file is `.grok-plugin/marketplace.json`, which lists `project-toolkit` at `./src/claude` (ADR-115 Decision 4).

## Steps

1. Register the marketplace:

   ```bash
   grok plugin marketplace add rjmurillo/ai-agents
   ```

2. Install the plugin. Grok asks for trust first:

   ```bash
   grok plugin install project-toolkit@ai-agents
   ```

   Without `--trust` it stops with this message:

   ```text
   Plugins can run hooks, MCP servers, and skills on your machine, so installation needs explicit trust.
   ```

   The plugin has one advisory Stop hook and runs skill scripts. Read the [Trust Boundary](../../../README.md#trust-boundary) first. If you accept, run:

   ```bash
   grok plugin install project-toolkit@ai-agents --trust
   ```

   It prints `Installed 1 plugin(s) from ai-agents: project-toolkit`.

## Check your result

```bash
grok plugin list
grok plugin details project-toolkit
```

The list shows the plugin under an id that starts with `claude-`. Your suffix will differ:

```text
  claude-5339c939: project-toolkit [local: <GROK_HOME>/marketplace-cache/<id>/src/claude] (ai-agents)
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

We got `105` and `29`.

`grok plugin validate <path>` prints `Plugin manifest is valid.`

Not run: a Grok model turn that uses a skill.

## Update, and tell if you are stale

Grok prints no versions on update (`? -> ?`), so use the SHA of the marketplace cache. The cache is a git checkout under `~/.grok/marketplace-cache/<id>`:

```bash
git -C ~/.grok/marketplace-cache/<id> rev-parse --short=10 HEAD
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

We read `b959011e3f` from a fresh cache. If the first 10 characters differ, update:

```bash
grok plugin marketplace update ai-agents
grok plugin update project-toolkit
```

The marketplace update prints `ai-agents: synced`. The plugin update prints:

```text
claude-5339c939: updated (? -> ?)
```

## Uninstall

```bash
grok plugin uninstall project-toolkit
grok plugin marketplace remove ai-agents
```

The first prints `Uninstalled 1 plugin(s): project-toolkit`.

## If it fails

- `requires confirmation`: add `--trust` after you read the trust note above.
- `Plugin "project-toolkit" not found`: the install did not finish. Run `grok plugin list`.
- `grok plugin` is not recognized: update Grok Build.

## What Grok Build gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 105 | `src/claude/skills/` |
| Agents | 29 | `src/claude/agents/` |
| Hooks | 1 advisory Stop hook | `src/claude/hooks/` |
| Rules | None | Grok plugins have no rules component |

The `model` keys in the skills are accepted and not applied (ADR-115 Decision 4).

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
