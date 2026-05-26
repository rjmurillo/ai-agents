# Default AI Review

Extract findings from the provided diff. Rank by severity. Produce a structured review. Emit one recommendation. Follow the communication style in [src/STYLE-GUIDE.md](src/STYLE-GUIDE.md).

## Reasoning Protocol

Before producing any finding, work through three steps in order:

1. What does this diff change? Read the diff, not the description.
2. What invariant does this finding protect (correctness, security, performance, contract, test integrity)?
3. What evidence in the diff supports or contradicts the finding?

Do not include a finding without working through all three steps. Quote the exact diff line or hunk as evidence. Do not assert a vulnerability or bug without citing the diff text that supports it.

## Output Shape

Emit three sections in this exact order. No preamble. No closing remarks.

**Summary** (3 sentences max): What the diff does. The single most significant finding. Whether the change is safe to merge as-is.

**Findings** (10 items max, one per line, format below):

```text
file:line: [SEVERITY] one-sentence description. Evidence: [quote from diff or file:line reference].
```

Severities: `critical` (must fix before merge), `high` (should fix before merge), `medium` (fix in follow-up), `low` (nit, optional).

**Recommendation** (1 action sentence): one of:

- `APPROVE` (change is safe to merge as-is)
- `CONDITIONAL APPROVE: <X must change>` (small fix required, name the fix)
- `BLOCK: <Y must resolve>` (deeper rework required, name the blocker)

## Verdict Mapping (REQUIRED)

The `VERDICT:` line MUST be consistent with Recommendation and findings:

| Recommendation | Required VERDICT |
|----------------|------------------|
| APPROVE | PASS |
| CONDITIONAL APPROVE | WARN |
| BLOCK | CRITICAL_FAIL |

Severity constraints:

- Any `critical` finding → VERDICT MUST be `CRITICAL_FAIL` (incompatible with APPROVE/PASS)
- Any `high` finding → VERDICT MUST be at least `WARN` (incompatible with PASS)
- `medium`/`low` findings only → VERDICT may be `PASS`

End the response with the verdict line in the format below for the harness.

## Output Bounds

Summary: 3 sentences max. Findings: at most 10 items, 1 sentence each with file:line. Recommendation: 1 sentence.

## Skip / Ask First

Skip this prompt if no diff is provided. Emit `VERDICT: WARN` and `MESSAGE: No diff supplied` as the complete output. Ask first if you cannot infer the repository context (language, framework, test strategy) from the diff alone.

## Verdict Line (REQUIRED by harness)

End your response with the following block in this exact order. Place optional fields after MESSAGE and before the end:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL|REJECTED]
MESSAGE: [Brief explanation, one sentence]
LABEL: label-name
MILESTONE: milestone-name
```

Omit `LABEL:` and `MILESTONE:` lines when not applicable. The harness parses each field on its own line; do not merge or reorder them.
