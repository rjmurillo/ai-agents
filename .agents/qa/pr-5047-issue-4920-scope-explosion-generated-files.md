---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-4920-scope-explosion-generated-files.json
qaCommit: 654fbc8022ee99698b11261c2bb5aa03a72ac7f9
---

# Issue 4920 Scope Explosion Generated Files QA Report

## Scope

Validates that generated files are excluded from scope explosion detector
threshold, aligning with atomic-commit counter behavior.

## Evidence

| Check | Result |
|---|---|
| Defect reproduction | Confirmed: 60 generated + 3 authored yields 65/50 block |
| Positive (generated excluded from count) | PASS - 7 tests |
| Negative (authored files still block) | PASS |
| Edge (only generated = 0 count) | PASS |
| Edge (merge in progress also excludes) | PASS |
| Report includes generated note | PASS |
| Report omits note when 0 generated | PASS |
| Episode files recognized | PASS |
| Full regression suite | PASS - 94 tests |
| Ruff lint | PASS |

## Verdict

PASS. Generated files correctly excluded from scope threshold.
