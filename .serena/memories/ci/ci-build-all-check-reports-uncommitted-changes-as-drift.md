# build_all.py --check reports drift on uncommitted changes

## What happens

`uv run python build/scripts/build_all.py --check` finds stale generated files by asking git. `_git_diff_paths` in `build/scripts/build_all.py` unions `git diff --name-only` with untracked files. Any edit you have not committed appears in that set.

Edit a template, run the generator, and run `--check` before committing. The check then reports drift even though the generated files are correct.

## Practice

Commit the template and the regenerated mirrors first. Then run `--check`. A clean result after the commit is the real signal.

## The full pre_pr.py run hides the file list

The `Generated Artifact Staleness` gate in `pre_pr.py` runs this check. When it
fails there, the report carries the reason `legacy.boolean_contract`
(`scripts/validation/evidence.py:530`). That tag only means the validator
returned a bare boolean. It names no file. Run the gate script directly:

```bash
uv run python scripts/validation/check_generated_staleness.py
```

It echoes the tail of the `build_all.py` output, where the `STALENESS DETECTED`
block lists the stale paths (`_echo_tail` in that script). Commit the
regenerated output first, so the drift you chase is real and not uncommitted work.

Source for this section: the 2026-10-12 sweep, where 10 runs read about 900
lines of output to find the cause. Code paths re-read on `origin/main` at `ec3214659`.

## Source

Read from `build/scripts/build_all.py` on 2026-09-29 and observed during the P1 triage session.
