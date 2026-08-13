---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14695-becfc98b8-fix-issue-4950-forgetful-exporter.json
qaCommit: a1ddfa0ef7906df9d6d807e1a40349ba67a6d582
---

# QA Validation: PR 4957, Issue 4950 Forgetful Export Security

## Scope

- Positional scanner CLI invocation from the Forgetful exporter
- Generic secret detection around Forgetful `id` and `user_id` UUID values
- Fail-closed behavior when the mandatory scanner is absent

## Evidence

| Check | Result |
|---|---|
| Focused tests | 42 passed |
| Scanner tests | 27 passed |
| Scanner branch coverage | 98%, with only the `__main__` dispatch line uncollected |
| Real CLI boundary | Clean, sensitive, whitespace, and dash-leading paths exercised |
| UUID inverse cases | Neutral fields, malformed values, extended values, duplicate UUIDs, and same-line tokens remain detected |
| Sensitive output | Matched values and detection expressions are absent from reports |
| Ruff | Changed Python files passed |
| Taste lints | Six changed files scanned, no violations |
| CWE-78 scan | Four changed Python files scanned, no findings |
| Repository tests | 27,947 passed, 37 skipped, 2 warnings at `a1ddfa0ef7906df9d6d807e1a40349ba67a6d582` |

The real subprocess tests execute the scanner entry point that in-process
coverage reports as the single uncovered line. Focused tests passed again at
`a1ddfa0ef7906df9d6d807e1a40349ba67a6d582` after the clear-text reporting
hardening.

## Positive, Negative, and Edge Selectors

- Positive: `TestRunSecurityReviewForgetful::test_clean_export_passes_real_cli_boundary`
- Negative: `TestRunSecurityReviewForgetful::test_sensitive_export_fails_real_cli_boundary`
- Edge: `TestRunSecurityReviewForgetful::test_dash_leading_relative_path_passes_real_cli_boundary`
- Positive detection and output safety: `TestScanFile::test_generic_34_character_token_returns_1_without_logging_secret`
- Negative detection: `TestScanFile::test_forgetful_uuid_returns_0`
- Edge detection: `TestScanFile::test_uuid_like_token_returns_1`

## Verdict

PASS. The changed behavior meets issue 4950 and preserves detection for
generic and UUID-like tokens outside the two Forgetful identifier fields.
Reports contain categories, counts, and line numbers without secret values or
detection expressions.
