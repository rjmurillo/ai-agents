---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-4857-matcher-shim-atomic-count.json
qaCommit: f2afec898b455e7fad5769acfb2f3c5535b2e5f1
---

# PR 4857 Matcher Shim Atomic Count QA Report

## Scope

Validates that matcher-shimmed Copilot hook shims are exempt from the
atomic-commit five-file limit when their canonical source is staged.

## Evidence

| Check | Result |
|---|---|
| Defect reproduction | Confirmed: shim path resolves to non-existent source |
| Positive (sanitized+hex suffix stripped) | PASS |
| Positive (bare hex suffix stripped) | PASS |
| Negative (companion without suffix unchanged) | PASS |
| Negative (lib path not stripped) | PASS |
| Negative (skills path not stripped) | PASS |
| Integration (shim exempt when source staged) | PASS |
| Integration (shim NOT exempt when source missing) | PASS |
| Full test suite (mirror exemption) | 41 passed |
| Ruff lint | All checks passed |
