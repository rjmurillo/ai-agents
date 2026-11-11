# Install the toolkit on Muse

Not run end to end. Muse is not installed on the machine where we checked these commands. We ran the copy steps and one skill script in a scratch home folder, with main at `8a8af7bc9d` (2026-11-10) on 2026-11-11. We did not check that Muse loads the skills.

Muse support is experimental (ADR-115 Decision 8).

## Goal

Copy the toolkit skills where Muse reads custom skills, and prove a skill script runs from there.

## Before you start

- Muse, Meta's personal agent. We have no Muse version to record.
- `git` and `python3`.

Muse has no plugin manifest in this repository. ADR-115 planned a generated `.muse-plugin/plugin.json`. The tree at `8a8af7bc9d` has none. The install path is a file copy.

## Steps

1. Clone the toolkit:

   ```bash
   git clone --depth 1 https://github.com/rjmurillo/ai-agents.git
   cd ai-agents
   ```

2. Copy each skill folder. The loop skips any name Muse already has. It is the loop from [src/muse/README.md](../../../src/muse/README.md):

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

   The README loop does not include this step. Without it, skill scripts fail. See "If it fails".

## Check your result

Count the skill folders:

```bash
ls ~/workspace/custom-skills | wc -l
```

We got `105` in a fresh scratch folder. If you had skills already, your count is higher.

Run one skill script from the copy:

```bash
python3 -I ~/workspace/custom-skills/github/scripts/pr/get_pr_checks.py --help
```

It prints the usage text:

```text
usage: get_pr_checks.py [-h] [--owner OWNER] [--repo REPO]
                        --pull-request PULL_REQUEST [--wait]
                        [--timeout-seconds TIMEOUT_SECONDS]
```

Not run: asking Muse to list or use a skill.

## Update, and tell if you are stale

The copy records no SHA. Write down your clone's SHA when you copy:

```bash
git rev-parse --short=10 HEAD
```

Later, compare it with the repository head:

```bash
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

The step 2 loop never replaces a folder that exists. Running it again does not refresh your copy. To update, delete the folders named in `src/muse/skills/` from `~/workspace/custom-skills/` and `~/workspace/lib`, pull the clone, and repeat steps 2 and 3.

## Uninstall

Delete the folders named in `src/muse/skills/` from `~/workspace/custom-skills/`. Delete `~/workspace/lib` too.

## If it fails

- `Plugin lib directory not found: <home>/workspace/lib`: you skipped step 3. We hit this after the README loop alone.
- A skill folder already existed: the loop kept your copy. See the update note above.
- Muse does not list the skills: we could not test this. Check that `~/workspace/custom-skills/` is the folder your Muse build reads.

## What Muse gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 105 | `src/muse/skills/` |
| Agents, rules | None | The tree ships skills and `lib/` only |

The frontmatter keeps only `name` and `description`, the two fields Muse custom skills use.

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
