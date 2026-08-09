---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10021-fix-4547-ai-review-context-retry.json
qaCommit: cdb3c8a1b36580dc2cba6e09f26d7755e1e0256d
---

# QA Report: PR #4775 AI Review Context Retry

## Scope

Validated bounded GitHub context retries, rate-limit-aware waits, permanent
authentication rejection, infrastructure classification, deadline enforcement,
collision-safe outputs, stale-verdict prevention, credential redaction
across context, model, and artifact sinks, separator backtracking defense, and token-only URL userinfo redaction.
Full PR diffs now use the REST diff media type so real rate-limit response headers reach retry classification.
Authorization wrappers support both colon and assignment syntax.

## Results

| Gate | Result |
|------|--------|
| Final redactor and parity tests | [PASS], 167 tests |
| Copilot invoker tests | [PASS], 18 tests |
| Artifact context tests | [PASS], 9 tests |
| Shared redactor tests | [PASS], 158 tests |
| Direct-action budget and deadline tests | [PASS], 20 tests |
| Plain-script import tests | [PASS], 294 tests |
| Bundled redactor parity tests | [PASS], 6 tests |
| Separator backtracking negative control | [PASS], pre-fix failed and post-fix passed |
| URL userinfo negative control | [PASS], pre-fix failed and post-fix passed |
| False-positive redaction guards | [PASS], 3 tests |
| Complete Python suite | [PASS], 25,216 passed and 36 skipped |
| ADR-006 run-block ratchet | [PASS], 0 violations |
| Ruff | [PASS] |
| Changed-file mypy | [PASS] |
| Pre-PR validations | [PASS], 50 checks |
| Independent DevOps review | [PASS], no Critical or High findings |
| GPT-5.6 Sol adversarial review | [PASS], no Critical or High findings |

## Reconciliation

```text
Promised: Bounded retry for transient primary and secondary refusals;
          rate-limit-aware waits; no retry for permanent authentication;
          truthful INFRASTRUCTURE_FAILURE after exhaustion or missing context;
          no false success; credential redaction.
Delivered: Three bounded context attempts; Retry-After and X-RateLimit-Reset;
           210-second shared context budget within one 570-second absolute
           review deadline; permanent authentication short-circuit; fail-closed
           issue, PR, spec, session, invocation, and artifact context paths;
           action-local deadlines for direct callers; exact-value, wrapper,
           URL, token-shape, and assignment redaction before every external
           sink; parse-before-redact for successful structured responses;
           collision-safe GitHub outputs; stale verdict removal.
           Composite-action deadline logic extracted into a tested Python
           helper with exact inherited-deadline input validation.
           Full diff requests use `gh api --include` with GitHub's diff media
           type, making real Retry-After and quota-reset headers observable.
           Quota-reset timestamps are ignored while resource quota remains.
           Assignment redaction bounds quoted and unquoted scalar values,
           preserves trailing fields, fails closed across a twelve-case
           raw and escaped JSON backslash matrix, and keeps credential
           namespace separator alternatives disjoint from namespace characters
           so long hyphen or underscore runs complete within the review budget.
           URL userinfo redaction now masks token-only credentials before `@`
           as `url-credential`, while URLs without userinfo pass through unchanged.
           Unicode-escaped Authorization keys and wrappers redact at arbitrary
           JSON serialization depth without changing source assignments.
           Authorization assignment forms redact the complete Basic, Token,
           or Bearer credential while preserving trailing structured fields.
Gap: None.
Result: PASS
```

## Status

**QA COMPLETE**
