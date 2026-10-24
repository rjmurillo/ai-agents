# The PR body file must pass the strict reader, and body paths must be in the diff

## What happens

`new_pr.py` accepts an inline `--body`. Its `--body-file` takes a plain file you own under the repo root or a temp directory, read by `read_body_file_text`. That reader refuses symlinks, hard-linked or world-writable files, and paths through a dot-named directory other than `.project-toolkit/scratch`. A path from `--prepare-body-file` passes those checks and avoids name collisions between sessions.

`scripts/validation/pr_description.py` flags "File mentioned but not in diff" as a critical issue. A backticked path in the body that the diff does not touch fails the check. A description that names a file it did not change reads as a false claim.

On PR #6367 the body named `build_all.py` in two places: backticked under `## Changes`, and as a list item `` - `build_all.py --check` `` under `## Testing`. Both failed CI runs still had the `## Changes` backtick, and dedupe reported the two mentions as one CRITICAL. The list-item pattern in `FILE_MENTION_PATTERNS` matches a bullet that starts with a file name in any section. Only the headings in `_CONTEXTUAL_SECTION_NAMES` are stripped first, and that list has `Test Plan` but not `Testing`. A local run after removing the `## Changes` backtick still reported the CRITICAL until the Testing bullet was reworded.

The validator does not expand shell braces. On PR #6911, `src/{claude,codex,copilot-cli,cursor}/skills/security-scan/SKILL.md` under `## Changes` was flagged as not in the diff, though all four files were. List each path in full. PRs #6911 and #6912 also each failed once on a `build_all.py` path under `## Changes`.

The validator can run before the PR exists. PR #6592 added a local mode: `--body-file F --base REF` reads the body file and diffs `REF...HEAD` with no network call. Any CRITICAL finding exits 1. Local mode checks file mentions only; dash and closing-keyword checks still need `--pr-number`. The `/validate-pr-description` skill runs `validate_pr_description.py`, which checks the title, keywords, and template only.

## Practice

Name in backticks only the files the diff changes. Describe other files in plain words without a path. Use a prepared body file for long bodies. Before `new_pr.py` opens the PR, run `python3 scripts/validation/pr_description.py --body-file <body> --base origin/main` and fix every CRITICAL. Local mode checks file mentions only, so after `new_pr.py` opens the PR, also run `python3 scripts/validation/pr_description.py --pr-number <N> --ci` to catch dash and closing-keyword CRITICALs. After a later body edit, run the local check again before `edit_pr_body.py`.

## Source

`scripts/validation/pr_description.py` lines 5 and 1149 to 1156, and `new_pr.py` lines 237 to 298, read 2026-09-29. PR #6367, `Validate PR` runs 38260879320 and 38262091187, observed 2026-10-12. `FILE_MENTION_PATTERNS` and `_CONTEXTUAL_SECTION_NAMES` in `pr_description.py`, read 2026-10-13. `pr_description.py --help` shows `--pr-number` as required, read 2026-10-13. `new_pr.py --body-file` help and `extract_mentioned_files` brace behavior checked 2026-10-24 at 4b6bec49d4. PR #6911 brace case observed 2026-10-24. Local mode checked 2026-10-24 at 7118371daf: a body naming `build/scripts/build_all.py` under `## Changes` gave the CRITICAL, and a body naming only diff files passed. `run_local` calls only `validate_pr_description`; `validate_no_dashes` and the closing-link checks run on the `--pr-number` path only, read 2026-10-24.
