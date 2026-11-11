# Install the toolkit on Pi

Verified on Pi 1.5.0 on 2026-11-11. Main was at `8a8af7bc9d` (2026-11-10).

## Goal

Install the repository as a Pi package and see Pi list 105 skills from it.

## Before you start

- The Pi CLI (`pi`). We used `@earendil-works/pi-coding-agent` 1.5.0. We installed it from the lockfile in `.github/cli-smoke/pi/` with `npm ci --ignore-scripts`.
- `git`, `python3`, and network access to github.com.
- No sign-in is needed for these steps.

Pi reads the `package.json` at the repository root. Its `pi.skills` key points at `./src/claude/skills`. Pi loads skills only. It gets no agents, rules, or hooks (ADR-115 Decision 5).

## Steps

1. Install the package from git:

   ```bash
   pi install git:github.com/rjmurillo/ai-agents
   ```

   It prints `Installed git:github.com/rjmurillo/ai-agents`.

## Check your result

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
   printf '{"id":"1","type":"get_commands"}\n' | PI_OFFLINE=1 pi --mode rpc > commands.json
   python3 -c '
   import json
   for line in open("commands.json"):
       try: d = json.loads(line)
       except ValueError: continue
       cmds = (d.get("data") or {}).get("commands") if isinstance(d, dict) else None
       if cmds: print(sum(1 for c in cmds if c.get("source") == "skill"))
   '
   ```

   It prints:

   ```text
   105
   ```

   Each skill shows as `skill:<name>`, such as `skill:adr-generator`.

## Update, and tell if you are stale

Pi keeps a git checkout of the repository. Read its SHA from the path that `pi list` printed. Compare it with the repository head:

```bash
git -C <path from pi list> rev-parse --short=10 HEAD
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
```

We read `8a8af7bc9d`. If the first 10 characters differ, update:

```bash
pi update git:github.com/rjmurillo/ai-agents
```

It prints `Updated git:github.com/rjmurillo/ai-agents`.

## Uninstall

```bash
pi remove git:github.com/rjmurillo/ai-agents
```

It prints `Removed git:github.com/rjmurillo/ai-agents`. Then `pi list` prints `No packages installed.`

## If it fails

- `pi: command not found`: install Pi first. See the list under "Before you start".
- The count is lower than 105: run `pi list` and confirm the package path exists.
- A subdirectory install is not documented for Pi. Install from the repository root as shown.

## What Pi gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 105 | `src/claude/skills/`, through the root `package.json` |

The repository smoke for this host is `tests/e2e/test_pi_package_smoke.py`. It also runs a skill script that imports `lib/`.

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
