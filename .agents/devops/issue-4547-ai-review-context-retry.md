# AI Review Context Retry

## Purpose

Issue #4547 adds bounded retries when GitHub temporarily refuses AI review context requests.

## Runtime Contract

| Control | Value |
|---------|-------|
| Maximum attempts per `gh` call | 3 |
| Fallback waits | 60 seconds, then 120 seconds |
| Shared context retry budget | 210 seconds |
| AI review job deadline | 600 seconds |
| Review deadline marker | 570 seconds from the first job step |
| Model invocation budget | 300 seconds |
| Process kill grace | 5 seconds |
| Reserved runner startup time | 30 seconds |
| Reserved finalization time | 60 seconds |

REST metadata and full-diff calls request response headers through `gh api --include`.
`Retry-After` overrides fallback waits. `X-RateLimit-Reset` overrides fallback
only when `X-RateLimit-Remaining` is zero.
Permanent authentication and permission failures return immediately without retry.
Setup elapsed after the deadline marker reduces context time. Model retries also
use the same deadline and preserve the kill grace plus finalization reserve.

## Failure Classification

Exhausted retries, malformed responses, partial failed output, incomplete
pagination, and empty or missing PR, issue, spec, or session context produce:

```text
context_mode=error
context_infra_failure=true
INFRASTRUCTURE_FAILURE: ...
```

This contract keeps missing reviews on the blocking infrastructure path.

## Secrets

Context and model diagnostics redact values from `GH_TOKEN`, `GITHUB_TOKEN`,
`COPILOT_GITHUB_TOKEN`, and `BOT_PAT`.
Authorization headers, Unicode-escaped wrappers, and URL userinfo credentials
receive separate pattern-based redaction.

## Validation

| Gate | Result |
|------|--------|
| Context, redactor, and parity tests | [PASS], 255 tests |
| Focused invocation tests | [PASS], 22 tests |
| Focused artifact-context tests | [PASS], 9 tests |
| Full Python suite | [PASS], 25,216 passed and 36 skipped |
| Count ratchet regression | [PASS], 12 tests |
| Mypy changed files | [PASS] |
| Merge-tree ratchets | [PASS] |
| Pre-PR validation | [PASS], 50 checks |
| Independent DevOps review | [PASS], no Critical or High findings |
| GPT-5.6 Sol adversarial review | [PASS], no Critical or High findings after recursive remediation |

## Known Operational Limit

A reset beyond 210 seconds cannot complete inside one review job. The builder returns
an infrastructure failure before the job deadline, preserving a truthful review state.
The 570-second marker leaves 30 seconds for runner startup before the job's
600-second hard timeout. The invoker uses `timeout --kill-after=5s`.
