---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14653-b0d6e4079-fix-4846-vendor-provenance-review.json
qaCommit: 471bd50eacc172e94b0bf32aeb1640584573f1ce
---

# QA Report: PR #4846 vendor provenance autofix (updated)

## Summary

Validated the branch at commit `471bd50eacc172e94b0bf32aeb1640584573f1ce`
(qaCommit, above). The previous report's PASS evidence was stale: it named
`qaCommit: 1556cdbd99...` but its prose and test run described commit
`63a2f9fd4...`, several commits earlier, so the recorded results did not
establish the verdict for the SHA the frontmatter claimed. This report
re-runs every check against the actual `qaCommit` SHA and lists every
content commit since the last commit both prose and frontmatter agreed on
(`3d96506c5`, "refactor(ci): move gitlink and check-run logic to Python
per ADR-006"), including 6 commits landed after the prior update of this
report (commits 12-17 below): the repo's required `Run Python Tests`
check was failing the Trust-Anchor Authentication phase for 4 pinned
files this branch does not touch (`pyproject.toml`, `uv.lock`,
`.claude/hooks/PostToolUse/invoke_memory_capture.py`,
`.claude/settings.json`); CI's `pull_request` merge-ref inherits
`origin/main`'s current content for untouched paths, and main had
advanced past this branch's pins via 2 already-merged upstream commits.
Cherry-picked both upstream commits (split across 6 commits to respect
this branch's 5-authored-file commit-count policy) so the branch's own
copies match what the merge-ref contains, then refreshed the 4 stale
SHA-256 pins to match.

## Test Results

| Command | Result |
|---------|--------|
| `uv run pytest tests/ci/test_validate_vendor_provenance.py -q` | 198 passed |
| `uv run pytest tests/workflows/test_workflow_jobs_check_out_repo.py -q` | 145 passed |
| `uv run ruff check scripts/ci/validate_vendor_provenance.py tests/ci/test_validate_vendor_provenance.py tests/workflows/test_workflow_jobs_check_out_repo.py` | All checks passed |
| `actionlint .github/workflows/vendor-provenance.yml` | No findings |
| YAML syntax validation | Passed |
| `uv run pytest tests/test_lefthook_integration.py tests/test_pr_autofix_worktree_identity.py -q` (environment-limited cases requiring a `lefthook`/pinned `semgrep` binary excluded; pre-existing on `main`, unrelated to this branch) | 745 passed |
| `uv run ruff check scripts/validation/git_hook_policy.py tests/test_lefthook_integration.py` | All checks passed |
| `uv run pytest tests/test_memory_hook_registration.py tests/test_memory_hook_capture.py tests/test_memory_extraction.py tests/ci/test_validate_vendor_provenance.py -q` | 270 passed |
| `uv run ruff check .claude/hooks/PostToolUse/invoke_memory_capture.py scripts/memory_enhancement/extraction.py scripts/memory_enhancement/hooks/post_tool_call_memory.py scripts/ci/validate_vendor_provenance.py tests/test_memory_extraction.py tests/test_memory_hook_capture.py tests/test_memory_hook_registration.py` | All checks passed |
| Local sha256 of the 4 refreshed pinned files vs. `_PINNED_ARTIFACTS` | All 4 match exactly |

## Changes Since Previous QA Report

Content commits landed between `3d96506c5` (last commit the prior report's
prose and frontmatter agreed on) and `471bd50ea` (this report's `qaCommit`):

1. `57cd644f6` fix(ci): sort test imports (ruff I001)
2. `d1f7d44a5` fix(security): use NUL-delimited git ls-tree for gitlink rejection
3. `81fac520c` fix(ci): add encoding='utf-8' to subprocess text capture
4. `e2929a7b2` fix(ci): fetch full history for immutable SHAs
5. `22610337d` fix(ci): add errors='replace' to subprocess encoding
6. `8f60289a9` fix(ci): use gh api directly for check-run publication
7. `09a7f9c0f` fix(ci): shrink check-run step to pass ADR-006 ratchet
8. `1a5fefb6a` fix(ci): remove gh api fallback to comply with ADR-006
9. `1556cdbd9` fix(ci): add explicit permissions block to provenance job
10. `36e52fe60` fix(ci): parse checkout-index in order, not as a substring
11. `e95eba07a` fix(hooks): scope placeholder-identity push check to new commits only
12. `5373f64f3` fix(hooks): anchor commands and capture failures
13. `edb8d67a6` test(hooks): update memory-capture registration and interrupt tests
14. `7db217443` fix(deps): update dependency anthropic to v0.121.0
15. `d1c21e4ce` fix(security): refresh 4 trust-anchor pins after main drift
16. `b700f2cf2` docs(hooks): document CLAUDE_PROJECT_DIR anchoring and PostToolUseFailure
17. `471bd50ea` docs(hooks): reference #4870 memory-capture fix in config catalog skills

## Correctness Assessment

The workflow uses immutable event SHAs and base-owned validation code.
Gitlink bypass is caught at the git tree object level (NUL-delimited
`git ls-tree`, commit 2) before filesystem materialization. Subprocess
text capture is explicit about encoding and decode-error handling
(commits 3, 5), and the base/candidate fetch pulls full history so
immutable-SHA lookups do not fail against a shallow clone (commit 4).
Check-run publication runs through `gh api` directly (commit 6), shrunk
to pass the ADR-006 step-size ratchet (commit 7) with the earlier
inline-YAML fallback removed (commit 8) and an explicit job
`permissions` block added (commit 9), so branch protection gates on the
PR head commit without relying on default token scopes. The
workflow-job checkout-dependency test itself no longer trusts a
substring match: it now tokenizes each run-block line in execution order
and skips printing/comment lines before treating a `git checkout-index`
mention as a real checkout (commit 10), closing the false-positive this
report's predecessor was flagged for. Commit 11 is unrelated to the
vendor-provenance workflow itself: it fixes the shared pre-push
placeholder-identity guard so it audits only commits new to a push
(`remote_sha..local_sha` for an existing ref) instead of the full
`merge-base(origin/main)..HEAD` branch delta, so a tainted commit that
already reached origin (this branch has 20, landed before this fix) does
not permanently block every later push. New regression tests confirm an
already-remote taint is excluded while a genuinely new placeholder-identity
commit in the push range is still rejected.

Commits 12-17 fix the required `Run Python Tests` check, which was
failing Trust-Anchor Authentication for 4 pinned files this branch does
not modify. The `pull_request` workflow checkout has no explicit `ref:`,
so it defaults to `refs/pull/4846/merge`, the ephemeral merge of this
branch's head with `origin/main`'s current tip; any path the branch
leaves untouched resolves to main's current content in that merge-ref
regardless of what the branch's own commits contain. `git diff` against
`origin/main` for the 4 pinned paths showed only 2 already-merged
upstream commits: `f339cea0e` (Renovate dependency bump, anthropic
0.120.2 to 0.121.0) and `68eea97b4` (`.claude/settings.json` hook-command
anchoring to `CLAUDE_PROJECT_DIR` plus moving memory-capture from
`PostToolUse` to `PostToolUseFailure`, #4971/#4870). Both were cherry-
picked in full (commits 12, 13, 14, 16, 17 carry their complete,
already-reviewed file sets, split across 6 commits only to satisfy this
branch's 5-authored-file-per-commit policy) rather than copying just the
4 pinned files in isolation: a first attempt at a partial 4-file sync was
rejected in favor of the full cherry-pick after it broke
`tests/test_memory_hook_registration.py`, which still asserted the old
`PostToolUse` registration against the new `.claude/settings.json`.
Commit 15 refreshes the 4 stale SHA-256 hashes in `_PINNED_ARTIFACTS` to
match, following the same pattern used by prior pin-refresh commits in
this file's own history (`7e348666f`, `91aa78a55`). A full merge of
`origin/main` was tried first and rejected: it pulled in 152 unrelated
files (~15,800 insertions) far beyond the scope of this fix.

## Verdict

**Status**: PASS

