# Install the toolkit on Hermes

Verified on Hermes Agent v0.23.0 (2026.9.24) on 2026-11-11. The commands ran with main at `b959011e3f`. The next main commit changed only Cursor files, so the Hermes packs at `8a8af7bc9d` (2026-11-10) are the same.

## Goal

Install both Hermes packs and see each one enabled and healthy.

## Before you start

- Hermes Agent with plugin support. Check with `hermes --version`.
- Network access to github.com.
- No sign-in is needed for these steps.

Hermes caps a plugin at 400 files. The toolkit does not fit in one plugin, so it ships as two packs (ADR-115 Decision 6):

| Pack | Skills | Holds |
|------|--------|-------|
| `project-toolkit-delivery` | 50 | Pull request work, build, test, quality gates, security review, operations |
| `project-toolkit-knowledge` | 41 | Memory, context, decisions, requirements, strategy, documentation |

That is 91 skills. Another 14 skills ship in no pack, so Hermes users get fewer skills than other hosts. Hermes rates 7 of them dangerous. Six more refer to an excluded skill. `skill-doctor` has a file over the 1 MiB limit. [src/hermes/README.md](../../../src/hermes/README.md) lists each one with its reason.

A skill in one pack never refers to a skill in the other pack. Install both unless you only need one area.

## Steps

1. Install the knowledge pack and enable it:

   ```bash
   hermes plugins install rjmurillo/ai-agents/src/hermes/project-toolkit-knowledge --enable
   ```

   Hermes warns that the source is custom and unreviewed. Then it prints `Plugin installed` and `Plugin project-toolkit-knowledge enabled.`

2. Install the delivery pack. Run it without extra flags first:

   ```bash
   hermes plugins install rjmurillo/ai-agents/src/hermes/project-toolkit-delivery
   ```

   Hermes scans the pack and rates it `CAUTION`, with 289 findings. In our non-interactive run it printed `Decision: BLOCKED` and `Use --force to override.` We did not test an interactive terminal. Read the findings. The ones we saw were rated `LOW` and point at reference prose and example text.

3. If you accept the findings, install over the block and enable the pack:

   ```bash
   hermes plugins install --force --enable rjmurillo/ai-agents/src/hermes/project-toolkit-delivery
   ```

   The repository smoke allows `--force` for this one pack only (`FORCE_ALLOWED_PACKS` in `tests/e2e/hermes_runtime.py`).

## Check your result

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

We got `50` and `41`.

Not run: a Hermes model turn that uses a skill. `hermes skills list` showed no plugin skills in our run, so do not use it as your check.

## Update, and tell if you are stale

Hermes does not tell you. For these packs, the check reports status `unknown`:

```bash
hermes plugins check-updates
```

The status text says there is provenance drift because the folder has no `.git`, and asks you to reinstall from the recorded source. `hermes plugins update project-toolkit-knowledge` printed `already up to date`. We do not know what it compared, so do not trust it as a freshness check.

Use the commit SHA instead. Read the head SHA, then reinstall each pack over itself:

```bash
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
hermes plugins install --force --enable rjmurillo/ai-agents/src/hermes/project-toolkit-knowledge
```

The help says `--ref COMMIT_SHA` installs one exact 40-character commit. Not run: `--force` over an existing pack, and `--ref`.

## Uninstall

```bash
hermes plugins remove project-toolkit-delivery
hermes plugins remove project-toolkit-knowledge
```

Each prints a line that the plugin was removed. `hermes plugins list` then shows no `project-toolkit` rows.

## If it fails

- `Decision: BLOCKED`: Hermes rated the pack `CAUTION`. See step 3.
- `No plugin named 'project-toolkit-delivery'` when you enable: the install was blocked, so nothing was installed. Finish step 3.
- A fresh Hermes data root sets up its Python dependencies on the first install. Let it finish.
- A skill you expect is missing: check the excluded list in [src/hermes/README.md](../../../src/hermes/README.md).

## What Hermes gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 91, in two packs | `src/hermes/project-toolkit-*/skills/` |
| Agents, rules, hooks | None | Portable plugin form carries skills only |

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
