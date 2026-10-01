# build_all.py --check reports drift on uncommitted changes

## What happens

`uv run python build/scripts/build_all.py --check` finds stale generated files by asking git. `_git_diff_paths` in `build/scripts/build_all.py` unions `git diff --name-only` with untracked files. Any edit you have not committed appears in that set.

Edit a template, run the generator, and run `--check` before committing. The check then reports drift even though the generated files are correct.

## Practice

Commit the template and the regenerated mirrors first. Then run `--check`. A clean result after the commit is the real signal.

## Source

Read from `build/scripts/build_all.py` on 2026-09-29 and observed during the P1 triage session.
