# Default AI Review

Extract findings from the provided diff. Rank by severity. Produce a structured review. Emit one recommendation. Follow the communication style in [src/STYLE-GUIDE.md](/src/STYLE-GUIDE.md).

## Reasoning Protocol

Before producing any finding, work through three steps in order:

1. What does this diff change? Read the diff, not the description.
2. What invariant does this finding protect (correctness, security, performance, contract, test integrity)?
3. What evidence in the diff supports or contradicts the finding?

Do not include a finding without working through all three steps. Quote the exact diff line or hunk as evidence. Do not assert a vulnerability or bug without citing the diff text that supports it.

## Output Shape

Emit four sections in this exact order, followed by the required verdict block (see Verdict Line section). The verdict block includes `VERDICT:`, `MESSAGE:`, and the optional `LABEL:` and `MILESTONE:` follow-on lines as one unit. No preamble. No prose between the four sections and the verdict block. No content after the last line of the verdict block.

**Summary** (3 sentences max): What the diff does. The single most significant finding. Whether the change is safe to merge as-is.

**Findings** (10 items max, one per line, format below):

```text
<location>: [SEVERITY] one-sentence description. Evidence: [quoted diff line or hunk text].
```

`<location>` is `file:line` when the provided context contains explicit line numbers. When the context only contains hunk headers (for example `file @@ -a,b +c,d @@`), use `file @@hunk@@` instead and do not invent line numbers.

Severities: `critical` (must fix before merge), `high` (should fix before merge), `medium` (fix in follow-up), `low` (nit, optional).

**Recommendation** (1 action sentence): one of:

- `APPROVE` (change is safe to merge as-is)
- `CONDITIONAL APPROVE: <X must change>` (small fix required, name the fix)
- `BLOCK: <Y must resolve>` (deeper rework required, name the blocker)

**Confidence** (0-100 numeric score on its own line): Rate confidence in this review based on context completeness and code clarity. Below 70 with verdict PASS triggers escalation per `.agents/governance/AI-REVIEW-MODEL-POLICY.md`.

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

Summary: 3 sentences max. Findings: at most 10 items, 1 sentence each with a location (`file:line` when context has line numbers, otherwise `file @@hunk@@`). Recommendation: 1 sentence. Confidence: 1 numeric score (0-100) on its own line.

## Skip / Ask First

The harness runs non-interactively, so the model cannot ask a follow-up question. Every degraded-context path below ("ask first" cases included) produces the four required sections plus the verdict block as the deterministic output. Treat "ask first" as "emit WARN with the missing context named in MESSAGE", never as a no-op.

No diff supplied: emit `VERDICT: WARN` with `MESSAGE: No diff supplied`. Summary and Findings sections may be empty placeholders; Recommendation is `CONDITIONAL APPROVE: re-run with a diff`.

Summary-only or partial context: if the `## Changes` section begins with markers like `[Large PR -` (no full diff), the `PASS` verdict is forbidden. Emit `WARN`, `CRITICAL_FAIL`, or `REJECTED` and note the limited context in `MESSAGE`. Prefer `WARN` unless the available evidence justifies escalation to `CRITICAL_FAIL` or `REJECTED`.

Repository context unclear (cannot infer language, framework, or test strategy from the diff): emit `VERDICT: WARN` with `MESSAGE: Insufficient repository context; state the missing pieces.` Do not assume; state in `MESSAGE` which context elements were missing.

## Verdict Line (REQUIRED by harness)

End your response with the following required block, replacing the bracketed placeholders with real values:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL|REJECTED]
MESSAGE: [Brief explanation, one sentence]
```

Optional follow-on lines. Each is independent: append a line only when that specific value applies, omit it otherwise. Use a real label name and a real milestone name; do not emit the literal strings `label-name` or `milestone-name`:

- `LABEL: <existing GitHub label>`: apply this label to the PR. Append only when a real label applies.
- `MILESTONE: <existing GitHub milestone>`: assign this milestone to the PR. Append only when a real milestone applies.

The harness parses each field on its own line and accepts label-only, milestone-only, both, or neither. Do not merge or reorder the fields.
