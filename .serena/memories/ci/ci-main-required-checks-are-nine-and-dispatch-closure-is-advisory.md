# Main requires nine checks; "Verify dispatch closure against base" is advisory

## Required checks on main

The branch ruleset on main (read 2026-10-12 with `gh api repos/rjmurillo/ai-agents/rules/branches/main`, rule type `required_status_checks`) lists exactly nine contexts:

- Validate Path Normalization
- Validate Generated Files
- Validate PR
- Validate PR title
- Analyze (actions)
- Analyze (python)
- Run Python Tests
- Validate Plugin Version Bump
- Check whole-tree count ratchets (blocking)

Every other red check on a PR, including pytest split jobs and the dispatch closure job, is not in that list.

## Why dispatch closure goes red

The job `dispatch-closure` in `.github/workflows/enforcement-closure.yml` runs `scripts/ci/verify_dispatch_closure.py` from the base tree and compares the PR head's verifier files byte for byte with the base ref. A difference exits 1. The workflow comment says a legitimate verifier change "reports here exactly as it halts the local gate until a human approves it."

Observed on PR #6316: "39 files examined; 3 differ" for three github skill scripts the PR did not touch. The branch was behind main, so main's newer copies differed from the branch copies. Merging origin/main into the branch clears it. A PR that edits a verifier script goes red the same way, by design.

## Sources

- Ruleset API read, 2026-10-12.
- `.github/workflows/enforcement-closure.yml` lines 87 to 130.
- `scripts/ci/verify_dispatch_closure.py` module docstring.
- Job log for PR #6316 (run 38220541103 family, job 114715445769).
