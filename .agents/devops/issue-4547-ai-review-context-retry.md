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

`Retry-After` and `X-RateLimit-Reset` override fallback waits within the shared budget.
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
Authorization headers and credentials embedded in URLs receive separate pattern-based redaction.

## Validation

| Gate | Result |
|------|--------|
| Focused context tests | [PASS], 78 tests |
| Focused invocation tests | [PASS], 11 tests |
| Full Python suite | [PASS], 24,863 passed and 34 skipped |
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
