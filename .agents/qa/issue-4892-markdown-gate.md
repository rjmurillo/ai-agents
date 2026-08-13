---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14693-be19f3a32-github-issue-4892-end-end.json
qaCommit: dd8dc0a65df6b0c10c11de83adb4787362a4f20e
---

# Issue 4892 Markdown Gate QA

## Scope

Validated the five-file fix in commit `ab8cd906f5c387af0a526c25415b4bb5fef3b19d`.

## Reproduction

Before the fix, `_markdown_lint_targets` selected one probe file from each of
`worktrees/`, `.agent-scratch/`, and `.scratch/`. A simulated markdownlint exit
249 with empty output printed only MD040 and MD033 guesses.

After the fix, the same three probe paths produced zero scratch targets. The
same exit 249 reported the exit code and stated that the tool produced no
stdout or stderr.

## Automated Evidence

- `uv run pytest -q tests/validation_pre_pr/test_markdown_checks.py tests/test_validation_pre_pr_markdown.py tests/validation/test_markdownlint_config.py`
  passed 60 tests.
- `uv run ruff check scripts/validation/checks_dash.py scripts/validation/checks_tooling.py tests/validation_pre_pr/test_markdown_checks.py tests/validation/test_markdownlint_config.py`
  passed.
- `SKIP_AUTOFIX=1 uv run python scripts/validation/pre_pr.py --markdown-lint-only -- README.md`
  passed against the real markdownlint process.
- `uv run python scripts/validation/pre_pr.py` completed with exit code 0.

## Review

A separate GPT-5.6 Sol reviewer found two valid issues across repeated passes:
Windows command length and later batches skipped after one failure. Both were
fixed and retested. A repeated empty-full-scan finding was invalid because the
full scan always carries `**/*.md`; that branch was made explicit. The final
review returned `CLEAN`.

## Post-review Refresh

Commit `ac2599c71d56bd9a0d3b2ed5b00608e24a6716b5` addressed all three
review threads.

- 61 targeted markdown validation tests passed.
- Ruff passed on the four changed Python files.
- The real markdownlint smoke test passed.
- Independent code review returned `CLEAN`.
- The completion gate found one suppressed non-BMP path issue. Commit
  `9b6a419b30dddbeeba9d175b5f9c071e5465092f` fixed it.
- 62 targeted tests passed after measuring Windows command length in UTF-16
  code units.
