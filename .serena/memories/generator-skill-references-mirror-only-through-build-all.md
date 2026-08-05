# Skill references mirror only through build_all.py

Editing any file under `.claude/skills/<name>/` propagates to the shipped copy
at `src/copilot-cli/skills/<name>/` only when you run
`uv run --frozen python build/scripts/build_all.py`. Running an individual
generator does not do it.

## Why the individual generator is not enough

`build/scripts/generate_rules.py` owns two trees and only two:
`.github/instructions` and `src/copilot-cli/instructions`. It reports
`Found 27 rule(s)` and `Output targets: 2`, and says nothing about skills.

The skill copy comes from the generic directory-mirror builder inside
`build_all.py` (the `artifacts.<artifact_name>` stanza handler, near line 236).
There is no standalone script for it, so there is nothing to run by hand
instead.

## What it costs to miss

The drift is invisible locally. `git status` is clean, because the stale mirror
is committed and so is the file you edited. Nothing fails until pre-push, where
`build-all-check` compares the tree against a fresh generation.

That job runs near the end of the pre-push group, after `python-tests`, which
took 770 seconds on the run that caught this. The feedback arrives roughly 13
minutes after the push starts, and the push ends with
`error: failed to push some refs`.

## Recovery

```text
uv run --frozen python build/scripts/build_all.py
git status --porcelain          # lists the stale mirrors it just rewrote
git add <mirrored paths> && git commit
```

The generator is idempotent, so running it when there is no drift costs
nothing and prints `Written: 50`, `Skipped (all-internal scope): 4`, with a
clean status afterward.

## Reading the output

`build_all.py` prints a long run of
`WARNING: dropped internal-only glob from applyTo: ...` lines every time. Those
are normal operation, not the drift. Filter them
(`grep -v 'dropped internal-only glob'`) before reading the summary, or the
real result scrolls off.

## Related

- `.claude/rules/generated-artifacts.md` states the
  regenerate-and-commit-in-the-same-change rule. This memory records which
  command actually satisfies it for skill content, which the rule does not name.
- Issue #4426 is where it surfaced: a doctrine edit under
  `.claude/skills/context-optimizer/references/` left the plugin copy
  contradicting the repository copy about the exact fact the edit recorded.
