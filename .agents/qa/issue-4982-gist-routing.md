---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14707-bf63100b0-fix-issue-4982-routing-gist.json
qaCommit: 35126cef58bd48286e8f44001abbf41b0cc5bb6b
---

# Issue 4982 Gist Routing QA Report

## Scope

Validated gist URL parsing, API routing, content selection, generated mirror
parity, and rejection of unsafe input.

## Evidence

| Check | Result |
|---|---|
| Targeted routing tests | 87 passed |
| Full skill test suite | 2,389 passed |
| Statement coverage | 100% across 3 routing modules |
| Branch coverage | 100% across 124 branches |
| Ruff | Passed on routing modules and tests |
| mypy | Passed on 5 Python files |
| Generated artifacts | `build_all.py --check` exited 0 |
| CWE-78 scan | 0 findings across 5 files |
| Code review | GPT-5.6 Sol PASS |
| Security review | GPT-5.6 Sol PASS |

## Behavior

- Routes numeric, 20-character, and 32-character gist IDs.
- Preserves immutable gist revisions.
- Routes raw URLs directly over HTTPS.
- Returns only explicitly selected files for embed and file-fragment URLs.
- Rejects traversal, placeholders, control characters, duplicate selectors,
  malformed authorities, and ambiguous file matches.
- Loads through direct path imports in canonical and Copilot plugin copies.

## Follow-up Findings

Non-gist defects found during review are tracked in issues 4992, 4993, and
4994. They are outside issue 4982.

## Review Fix (PR #4996 threads)

| Fix | File | Test |
|-----|------|------|
| Reject `?file=` + `#file-` ambiguous embed selector | `gist_routing.py:78` | `test_gist_parser_rejects_incomplete_or_unsupported_urls[?file=safe.txt#file-evil-txt]` |
| Replace hardcoded `.claude` with `${COPILOT_PLUGIN_ROOT}` | Both `SKILL.md` copies | Visual inspection |

Tests: 55 passed (including new negative case). `build_all.py --check` exit 0.

## Verdict

PASS. Issue 4982 behavior is implemented and independently reviewed.
