---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14695-becfc98b8-fix-issue-4950-forgetful-exporter.json
qaCommit: fa6b62a07bd0fa50af40dc90f904a1a8bb879792
---

# QA Validation: PR 4957, Issue 4950 Forgetful Export Security

## Scope

- Positional scanner CLI invocation from the Forgetful exporter
- Positional scanner CLI invocation from all three Claude-Mem exporters
- Generic secret detection around Forgetful `id` and `user_id` UUID values
- Explicit Forgetful export mode for the identifier UUID policy
- Fail-closed behavior when the mandatory scanner is absent

## Evidence

| Check | Result |
|---|---|
| Focused tests | 57 passed |
| Scanner tests | 29 passed |
| Scanner branch coverage | 98%, with only the `__main__` dispatch line uncollected |
| Real CLI boundary | Forgetful clean, sensitive, whitespace, and dash-leading paths plus all three Claude-Mem callers exercised |
| UUID inverse cases | Default scans, neutral fields, malformed values, extended values, duplicate UUIDs, and same-line tokens remain detected |
| Sensitive output | Matched values and detection expressions are absent from reports |
| Ruff | Seven review follow-up Python files passed |
| Taste lints | Seven review follow-up files scanned, no violations |
| CWE-78 scan | Seven review follow-up files scanned, no findings |
| Repository tests | 27,952 passed, 37 skipped, 2 warnings at `fa6b62a07bd0fa50af40dc90f904a1a8bb879792` |

The real subprocess tests execute the scanner entry point that in-process
coverage reports as the single uncovered line. Focused tests passed again at
`fa6b62a07bd0fa50af40dc90f904a1a8bb879792` after scoping the UUID exception
and migrating the remaining callers.

## Positive, Negative, and Edge Selectors

- Positive: `TestRunSecurityReviewForgetful::test_clean_export_passes_real_cli_boundary`
- Negative: `TestRunSecurityReviewForgetful::test_sensitive_export_fails_real_cli_boundary`
- Edge: `TestRunSecurityReviewForgetful::test_dash_leading_relative_path_passes_real_cli_boundary`
- Positive detection and output safety: `TestScanFile::test_generic_34_character_token_returns_1_without_logging_secret`
- Negative detection: `TestScanFile::test_forgetful_uuid_returns_0`
- Edge detection: `TestScanFile::test_uuid_like_token_returns_1`
- Default-mode detection: `TestScanFile::test_forgetful_uuid_without_export_mode_returns_1`
- Sibling boundaries: `TestSecurityReviewBoundary::test_passes_export_path_positionally`

## Verdict

PASS. The changed behavior meets issue 4950 and preserves detection for
generic and UUID-like tokens outside the two Forgetful identifier fields.
Reports contain categories, counts, and line numbers without secret values or
detection expressions. Generic scans retain UUID detection unless the Forgetful
exporter explicitly selects its measured identifier policy.
