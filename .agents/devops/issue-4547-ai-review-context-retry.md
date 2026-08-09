# AI Review Context Retry

## Purpose

Issue #4547 adds bounded retries when GitHub temporarily refuses AI review context requests.

## Runtime Contract

| Control | Value |
|---------|-------|
| Maximum attempts per `gh` call | 3 |
| Fallback waits | 60 seconds, then 120 seconds |
| Shared context retry budget | 420 seconds |
| AI review job deadline | 600 seconds |
| Reserved classification time | 180 seconds |

`Retry-After` and `X-RateLimit-Reset` override fallback waits within the shared budget.
Permanent authentication and permission failures return immediately without retry.

## Failure Classification

Exhausted retries, malformed responses, and empty PR diffs produce:

```text
context_mode=error
context_infra_failure=true
INFRASTRUCTURE_FAILURE: ...
```

This contract keeps missing reviews on the blocking infrastructure path.

## Secrets

Diagnostics redact values from `GH_TOKEN`, `GITHUB_TOKEN`, `COPILOT_GITHUB_TOKEN`, and `BOT_PAT`.
Authorization headers and credentials embedded in URLs receive separate pattern-based redaction.

## Validation

| Gate | Result |
|------|--------|
| Focused context tests | [PASS], 68 tests |
| Full Python suite | [PASS], 24,846 passed and 34 skipped after ratchet remediation |
| Count ratchet regression | [PASS], 12 tests |
| Mypy changed files | [PASS] |
| Merge-tree ratchets | [PASS] |
| Pre-PR validation | [PASS], 50 checks |
| Independent DevOps review | [PASS], no Critical or High findings |
| GPT-5.6 Sol adversarial review | [PASS], no Critical or High findings after two remediations |

## Known Operational Limit

A reset beyond 420 seconds cannot complete inside one review job. The builder returns
an infrastructure failure before the job deadline, preserving a truthful review state.
