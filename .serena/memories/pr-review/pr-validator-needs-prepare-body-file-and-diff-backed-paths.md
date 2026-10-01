# The PR body file must be prepared, and body paths must be in the diff

## What happens

`new_pr.py` accepts an inline `--body`. Its `--body-file` reads only a path made by `--prepare-body-file`, because `read_prepared_pr_body` in `prepare_pr_body.py` rejects other body files. Run `--prepare-body-file` first, write the body to that path, then pass it as `--body-file`.

`scripts/validation/pr_description.py` flags "File mentioned but not in diff" as a critical issue. A backticked path in the body that the diff does not touch fails the check. A description that names a file it did not change reads as a false claim.

## Practice

Name in backticks only the files the diff changes. Describe other files in plain words without a path. Use a prepared body file for long bodies and rerun the validator before opening the PR.

## Source

`scripts/validation/pr_description.py` lines 5 and 1149 to 1156, and `new_pr.py` lines 237 to 298, read 2026-09-29.
