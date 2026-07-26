---
applyTo: .claude/skills/**,src/copilot-cli/skills/**,.claude/commands/**
---

# Harness Path Resolution Rule

A skill that shells out to a helper script must resolve that script's directory before invoking it. The resolver walks a candidate ladder: harness environment variables first, then a repo-relative path, then installed-plugin copies under `$HOME`. Every rung after the repo-relative one points at a *different copy of the code*, usually an older one.

This rule exists because `src/copilot-cli/skills/pr-autofix/SKILL.md` contains a `resolve_pr_scripts_dir()` whose repo-relative rung is the bare string `.claude`. A bare relative path only resolves when the process cwd is the repository root. Executed from `repo/src/`, the `.claude` probe misses and the resolver silently returns `$HOME/.copilot/installed-plugins/_direct/project-toolkit/skills/github/scripts/pr`.

The consequence measured on `9768d541`: that installed copy was dated one month earlier than the repo, and its `check_pr_live_state.py` was 495 lines against the repo's 560, a 215-line difference. `check_pr_live_state.py` is the blocking per-PR live-state gate (issue #2455) that `pr-autofix` runs before every tier action. From a subdirectory, the skill enforced its primary safety gate using a month-old implementation, with no warning and no version check. The resolver fails open and fails silent.

## What a resolver MUST do

1. **Anchor the repo-relative rung absolutely.** Derive the repository root rather than assuming cwd is it:

   ```sh
   repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
   ```

   Probe `"$repo_root/.claude/skills/..."`, never bare `.claude/skills/...`. A resolver whose correctness depends on cwd is correct only by accident.

2. **Order in-repo copies ahead of installed-plugin copies.** The working tree is the source of truth during development. An installed plugin is a snapshot of some earlier commit. Falling through from the former to the latter is a silent downgrade, not a fallback.

3. **Not fail open on a set-but-wrong harness variable.** If `COPILOT_PLUGIN_ROOT` or `CLAUDE_PLUGIN_ROOT` is set and the path it names does not contain the expected script, that is a misconfiguration. Continuing down the ladder converts an explicit configuration error into a silent use of a different codebase.

4. **Emit the resolved path when it is not the in-repo copy.** One line on stderr naming which rung matched. Silence is what turns a stale-copy execution into an undiagnosable behavioral difference.

## What the reviewer MUST verify

When a diff adds or edits a resolver function in a `SKILL.md`, a command file, or a helper script:

- Extract the resolver and execute it from at least three working directories: the repo root, a subdirectory of the repo, and a path outside the repo. Reading the ladder is not sufficient. The bare-`.claude` defect is invisible on inspection and obvious on execution.
- Confirm the repo-relative rung is anchored to `git rev-parse --show-toplevel` or an equivalent absolute derivation.
- If an installed-plugin rung exists, confirm it is ordered last and that selecting it is announced.

## Verifying a stale copy is in play

When a skill behaves differently than its scripts read, compare the copies directly before theorizing:

```bash
diff <(wc -l < "$repo_root/.claude/skills/github/scripts/pr/check_pr_live_state.py") \
     <(wc -l < "$HOME/.copilot/installed-plugins/_direct/project-toolkit/skills/github/scripts/pr/check_pr_live_state.py")
```

A line-count difference between the two copies means the resolver's choice is load-bearing and the ladder must be audited.
