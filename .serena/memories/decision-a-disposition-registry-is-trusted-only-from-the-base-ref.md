# EUREKA: a PR can never waive its own findings, because the disposition registry is trusted only from the base ref

## Question

A review bot can leave a finding that a commit cannot clear, such as a PR description edit that never moves the head SHA. Where should the record that waives that finding live?

## Conventional answer

Keep the waiver in the PR. An in-PR file, label, or comment says "finding X is addressed, reason Y", and the gate reads it from the PR head. That is the usual shape of a lint suppression, and it costs the author one edit.

## First-principles position

The gate exists to stop the PR author from shipping an unreviewed finding. A waiver read from the PR head lets the author write the waiver in the same push. The waived PR then approves itself, and the gate checks nothing.

A waiver carries authority only when someone other than the waived PR wrote it. The registry therefore counts only once it is merged to the trusted branch. `check_suppressed_review_findings.py` documents this in its module docstring: the registry must be tracked, and the completion gate compares it to the trusted ref, so an entry takes effect after it merges, not from the PR it waives. An untracked registry is refused for the same reason.

## Evidence

- `.claude/skills/github/scripts/pr/check_suppressed_review_findings.py`, docstring lines 6 to 9, and the loader comment near line 217, read 2026-09-29.
- Issue #5485 and PR #5992 (a recorded disposition clears a suppressed finding fixed without a commit).

## Decision

Trust the disposition registry only from the base ref. Dispositions never change `active_suppressed_count`. The gate reads `undispositioned_suppressed_count`.

## Consequence

A finding on a PR that needs a waiver takes two steps: merge the registry entry, then the gate clears. That delay is the cost of a waiver the author cannot forge.
