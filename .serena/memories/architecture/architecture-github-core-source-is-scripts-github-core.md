# scripts/github_core is the source of the github_core library

## What is where

The editable source is `scripts/github_core/`. The copy at `.claude/lib/github_core/` is generated. `build/scripts/lib_mirror.py` lists `github_core` in `PACKAGES` and rewrites `from scripts.github_core import` to relative imports.

An edit made under `.claude/lib/github_core/` is overwritten on the next `build_all.py` run. The same applies to `hook_utilities` and `ai_review_common`.

## Practice

Edit `scripts/github_core/`, then run `uv run python build/scripts/build_all.py` and commit both trees.

## Source

`build/scripts/lib_mirror.py` lines 2 and 54, read 2026-09-29.
