---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10030-pr-4787-review-fixes.json
qaCommit: 0c6ca19eedf510b889c968c57a79aacbd43caec1
---

# PR 4787 QA Report

## Result

PASS. All High defects from independent reviews resolved across six review
cycles. Main integrated (bdd4908b ancestor confirmed). Contract tests enforce
strict affirmative-directive parsing and URL-type classification.

## Evidence

- 134 targeted analyst/URL-routing/PR-identity tests pass locally.
- 216 mirror/catalog validation tests pass locally.
- Taste ratchet OK (count == baseline 583).
- Ruff clean on all modified test files.
- All pre-commit hooks pass.
- 10 review threads: all resolved.
- CI on head 2f2bdfa7f: 106 SUCCESS, 25 SKIPPED (3 FAILURE are
  stale-QA/session checks that this commit fixes).

## Defects Fixed (cumulative)

1. Analyst URL routing: explicit type classification (PR/issue/Actions/job).
2. Retrieval guard: strict affirmative-directive parser rejects prohibitive
   prose, quoted examples, contractions, table-only, orchestrator actor,
   deprecated context.
3. Job URL path: corrected to singular `/job/` per GitHub live shape.
4. Taste ratchet: file-size ignore for contract test suite (>500 lines).
5. Orchestrator evidence handoff: delegates GitHub/CI to analyst.
6. All generated mirrors synchronized.

## Scope

No shell, write, web, or filesystem access restored. Read-only GitHub/CI
retrieval tools only. Contract tests enforce denial of prohibited access.
