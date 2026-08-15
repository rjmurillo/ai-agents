---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14709-bda9b9020-fix-encoded-gist-fragment-selector.json
qaCommit: 250415ae96f3f83cb0411e9daf69897e97d0bbf7
---

# PR 5007 Issue 5001 Gist Fragment Hardening QA Report

## Scope

Validated gist fragment decoding, selector grammar, generated mirror parity,
and rejection of malformed input that could widen file-specific retrieval.

## Evidence

| Check | Result |
|---|---|
| Targeted routing tests | 92 passed |
| Ruff | Passed on both routing modules and tests |
| mypy | Passed on both routing modules |
| Generated artifacts | `build_all.py --check` exited 0 |
| Pre-PR validation | `pre_pr.py` exited 0 |
| CWE-78 scan | 0 findings across 3 changed files |
| Code review | GPT-5.6 Sol PASS |
| Security review | GPT-5.6 Sol PASS |

## Behavior

- Decodes the full fragment before checking the `file-` selector prefix.
- Accepts encoded file-prefix syntax when it decodes to a valid selector.
- Rejects malformed percent escapes before command construction.
- Rejects empty selectors, controls, separators, and impossible gist slugs.
- Accepts only positive ASCII line anchors with at most one range endpoint.
- Preserves query-selector control validation for embed URLs.
- Keeps canonical and Copilot routing modules identical.

## Verdict

PASS. File-specific gist URLs cannot fall through to whole-gist retrieval
through encoded or malformed fragment selectors.
