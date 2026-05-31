# Variance Control Findings: Anthropic API determinism at temperature=0 on long context

Follow-on note to **ADR-058 (Agent Eval Discipline)**, AC-10 `halt-due-to-flakiness`.
Resolves the variance-source question raised by issue #1877 (which followed the v2
re-run of issue 1854, run `20260503T182553Z-eaa08f8d`).

- **Control run**: `20260531T184905Z-60538bcf`
- **Harness**: `scripts/eval/variance-control.py` (issue #1877 AC-1)
- **Fixture / variant**: F002 (the most-flaky agent-discriminating fixture) / `security` agent
- **Model**: `claude-sonnet-4-6`
- **Reps**: 20 at `temperature=0`, single `(fixture, variant)`, ~7,402 input tokens per call (the agent system prompt is the long context under test)
- **Errors**: 0 of 20

## Result

| Metric | Value |
|--------|-------|
| Verdict distribution | `ESCALATE` x 20 |
| Distinct verdicts | 1 (stable) |
| Pass rate vs expected `IDENTIFY` | 0.000 (0/20), pass variance 0.0000 |
| Unique responses (text) | 20 / 20 |
| Mean consecutive normalized edit distance | 0.636 |
| Max consecutive normalized edit distance | 0.786 |

## Interpretation

This is the issue's second expected outcome: **responses vary but the verdict is stable.**

1. **The verdict is deterministic on long context.** Across 20 independent calls
   at `temperature=0` with a ~7.4K-token system prompt, the extracted verdict was
   `ESCALATE` every time (distinct count 1, variance 0). The original v2 re-run
   observed `['ESCALATE', 'IDENTIFY', 'ESCALATE']` for F002 across N=3; that single
   `IDENTIFY` was small-sample noise (1 flip in 3, or a since-changed prompt), not a
   reproducible verdict-level non-determinism. At N=20 there is zero verdict variance.

2. **The response text is NOT bit-deterministic.** Every one of the 20 responses was
   unique, with a mean consecutive normalized edit distance of 0.636 (max 0.786).
   Two responses even differed in structure: most led with prose ("This design carries
   multiple High/Critical threats requiring architectural changes..."), while at least
   one led with a formatted "Threat Model" header. So the API does carry output-text
   non-determinism at `temperature=0` on long context, but the first-token verdict
   extractor (`_scoring_engine._VERDICT_RE`) is robust to it.

3. **The 0/20 pass rate is a fixture-label dispute, not flakiness.** F002 declares
   `expected_value: IDENTIFY`, but the security agent deterministically returns
   `ESCALATE` (a no-authentication webhook that applies database writes from an
   IP-trusted source is arguably an escalate-to-human case, not a mere identify-and-list
   case). Pass variance is 0.0: the agent is perfectly consistent, it simply disagrees
   with the fixture's label. This is the borderline-fixture problem the issue named, not
   API non-determinism.

## What this means for ADR-058 AC-10

The `halt-due-to-flakiness` gate halted the v2 re-run at 40% flakiness (F001, F002,
F003, F005). This control shows that "flakiness," as AC-10 measured it, **conflated
three distinct variance sources**:

- **Verdict variance** (the real eval signal): ~0 at N=20 for F002. The AC-10 worked
  example already noted F003 "verdict consistent; regex assertion flaky" and F005
  "agent perfect; baseline flaky on third run." The flakiness was rarely in the verdict.
- **Assertion variance** (e.g. regex/CWE-string matching): real, but orthogonal to whether
  the agent's judgment is stable.
- **Small-N pass-rate noise on borderline / mislabeled fixtures** (F002, F005-baseline):
  a single flip in N=3 reads as 33% pass-rate variance, which is an artifact of N, not of
  the model.

**Recommendation (for architect ratification, not applied here):**

1. **Gate AC-10 on verdict variance, not on any-assertion pass-rate variance.** A run
   whose verdicts are stable across reps is not flaky in the sense that threatens a
   verdict-grade eval, even if its response text varies or a regex assertion is noisy.
2. **Raise N for borderline fixtures.** The issue's own `N >= 30` suggestion absorbs the
   small-sample pass-rate noise that drove the 40% reading. At N=20 here, F002's verdict
   variance already collapsed to 0.
3. **Relabel or redesign the contested fixtures (F001, F002).** Their `expected_value`
   is disputable; the agent's stable `ESCALATE` on F002 suggests the label, not the agent,
   is the outlier. (Redesign is a separate workstream per the issue's out-of-scope note;
   flagged here as the complementary mitigation.)

This note does not amend ADR-058. Promoting recommendation 1 into AC-10 is a methodology
change and must be ratified by an architect-tier reviewer through `adr-review`, per
ADR-058's own ratification rule.

## Reproduce

```bash
uv run python scripts/eval/variance-control.py --fixture F002 --agent security --reps 20
# requires ANTHROPIC_API_KEY (env or repo-root .env)
```

Raw responses and per-rep verdicts are in `raw.jsonl`; aggregate metrics in `summary.json`.
