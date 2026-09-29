# The PR validator wants a prepared body and diff-backed paths

## What happens

`new_pr.py` takes the body through `--prepare-body-file`. A body passed another way fails the validator.

`scripts/validation/pr_description.py` flags "File mentioned but not in diff" as a critical issue. A backticked path in the body that the diff does not touch fails the check. A description that names a file it did not change reads as a false claim.

## Practice

Name in backticks only the files the diff changes. Describe other files in plain words without a path. Build the body with `--prepare-body-file` and rerun the validator before opening the PR.

## Source

`scripts/validation/pr_description.py` lines 5 and 1149 to 1156, and `new_pr.py` line 240, read 2026-09-29.
