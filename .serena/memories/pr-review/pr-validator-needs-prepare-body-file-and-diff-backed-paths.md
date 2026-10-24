# The PR body file must be prepared, and body paths must be in the diff

## What happens

`new_pr.py` accepts an inline `--body`. Its `--body-file` takes any plain file you own under the repo root or a temp directory, read by `read_body_file_text`. A path from `--prepare-body-file` works and avoids name collisions between sessions.

`scripts/validation/pr_description.py` flags "File mentioned but not in diff" as a critical issue. A backticked path in the body that the diff does not touch fails the check. A description that names a file it did not change reads as a false claim.

On PR #6367 the body named `build_all.py` in two places: backticked under `## Changes`, and as a list item `` - `build_all.py --check` `` under `## Testing`. Both failed CI runs still had the `## Changes` backtick, and dedupe reported the two mentions as one CRITICAL. The list-item pattern in `FILE_MENTION_PATTERNS` matches a bullet that starts with a file name in any section. Only the headings in `_CONTEXTUAL_SECTION_NAMES` are stripped first, and that list has `Test Plan` but not `Testing`. A local run after removing the `## Changes` backtick still reported the CRITICAL until the Testing bullet was reworded.

The validator does not expand shell braces. On PR #6911, `src/{claude,codex,copilot-cli,cursor}/skills/security-scan/SKILL.md` under `## Changes` was flagged as not in the diff, though all four files were. List each path in full. PRs #6911 and #6912 also each failed once on a `build_all.py` path under `## Changes`.

The validator cannot run before the PR exists. It requires `--pr-number` and reads the body and diff from GitHub. The `/validate-pr-description` skill runs `validate_pr_description.py`, which checks the title, keywords, and template only. No pre-open check catches this. Issue #6405 tracks a local `--body-file` mode.

## Practice

Name in backticks only the files the diff changes. Describe other files in plain words without a path. Use a prepared body file for long bodies. Run `python3 scripts/validation/pr_description.py --pr-number <N> --ci` right after `new_pr.py` opens the PR, and fix the body before CI reports.

## Source

`scripts/validation/pr_description.py` lines 5 and 1149 to 1156, and `new_pr.py` lines 237 to 298, read 2026-09-29. PR #6367, `Validate PR` runs 38260879320 and 38262091187, observed 2026-10-12. `FILE_MENTION_PATTERNS` and `_CONTEXTUAL_SECTION_NAMES` in `pr_description.py`, read 2026-10-13. `pr_description.py --help` shows `--pr-number` as required, read 2026-10-13. `new_pr.py --body-file` help and `extract_mentioned_files` brace behavior checked 2026-10-24 at 4b6bec49d4. PR #6911 brace case observed 2026-10-24.
