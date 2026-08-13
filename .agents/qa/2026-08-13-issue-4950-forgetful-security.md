---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14695-becfc98b8-fix-issue-4950-forgetful-exporter.json
qaCommit: 3ddc2952ecf0a7ddd90c19db7e6eb1efa9560225
---

# QA Validation: Issue 4950 Forgetful Export Security

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
| Ruff | Changed Python files passed |
| Taste lints | Six changed files scanned, no violations |
| CWE-78 scan | Four changed Python files scanned, no findings |
| Repository tests | 27,947 passed, 37 skipped, 2 warnings on the implementation parent before the scanner-only complexity extraction |

The real subprocess tests execute the scanner entry point that in-process
coverage reports as the single uncovered line. Focused tests passed again at
`3ddc2952ecf0a7ddd90c19db7e6eb1efa9560225` after the extraction.

## Positive, Negative, and Edge Selectors

- Positive: `TestRunSecurityReviewForgetful::test_clean_export_passes_real_cli_boundary`
- Negative: `TestRunSecurityReviewForgetful::test_sensitive_export_fails_real_cli_boundary`
- Edge: `TestRunSecurityReviewForgetful::test_dash_leading_relative_path_passes_real_cli_boundary`
- Positive detection: `TestScanFile::test_generic_34_character_token_returns_1`
- Negative detection: `TestScanFile::test_forgetful_uuid_returns_0`
- Edge detection: `TestScanFile::test_uuid_like_token_returns_1`

## Verdict

PASS. The changed behavior meets issue 4950 and preserves detection for
generic and UUID-like tokens outside the two Forgetful identifier fields.
