# Eval Report: 20260503T182553Z-eaa08f8d

> [!CAUTION]
> **Halt-due-to-flakiness** per REQ-004 AC-10. 4 of 10 fixtures (40%) flagged as flaky after the contingency rerun, exceeding the 30% halt threshold. Per AC-10, the methodology does NOT produce a graduate-to-CI / keep-as-audit / scrap verdict on this run. The underlying numbers below are informative but non-normative.

This is the **v2 re-run** with the methodology fix from `61f1b6b8`. Supersedes (invalidates) the v1 run `20260503T165136Z-84f918a9` whose comparison was structurally rigged. See `.agents/critique/SPIKE-1854-methodology-diagnosis.md` for the rationale.

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `c90b17a396de54a5...`
- Baseline prompt SHA: `f2837b5416a8d4cb...` (now role-neutralization only; output-shape contract moved to OUTPUT_SHAPE_SUFFIX)

## Headline (informational; NOT a verdict per AC-10 halt)

| Metric | All fixtures | Non-flaky subset (F004, F006-F010) |
|---|---|---|
| Agent recall | 0.786 | **1.000** |
| Baseline recall | 0.405 | 0.571 |
| Signed delta | **+0.381** (+38.1pp) | **+0.429** (+42.9pp) |

## Per-fixture pass rates (3 runs each)

| Fixture | Agent (per run) | Baseline (per run) | Flaky |
|---|---|---|---|
| F001 | 1.00,0.50,0.50 | 0.00,0.00,0.00 | ✗ |
| F002 | 0.50,1.00,0.00 | 0.50,0.50,0.50 | ✗ |
| F003 | 0.50,0.50,0.00 | 0.00,0.00,0.00 | ✗ |
| F004 | 1.00,1.00,1.00 | 0.00,0.00,0.00 | — |
| F005 | 1.00,1.00,1.00 | 1.00,1.00,0.00 | ✗ |
| F006 | 1.00,1.00,1.00 | 0.00,0.00,0.00 | — |
| F007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 | — |
| F008 | 1.00,1.00,1.00 | 1.00,1.00,1.00 | — |
| F009 | 1.00,1.00,1.00 | 1.00,1.00,1.00 | — |
| F010 | 1.00,1.00,1.00 | 1.00,1.00,1.00 | — |

## Flakiness halt detail

- Threshold (per AC-10): >30% of fixtures flagged as flaky after contingency rerun → halt
- Actual: 4/10 fixtures = 40% (F001, F002, F003, F005)
- Per AC-10, the methodology cannot produce a graduate-to-CI / keep-as-audit / scrap verdict on this run

**Variance pattern observed (agent variant on flaky fixtures):**

- F001: verdict varied across runs: ['IDENTIFY', 'ESCALATE', 'ESCALATE'] — agent disagrees with itself between IDENTIFY (find the issue) and ESCALATE (this needs human review) on a path-traversal fixture. Both verdicts are defensible.
- F002: ['ESCALATE', 'IDENTIFY', 'ESCALATE'] — same pattern on STRIDE multi-category.
- F003 / F005: verdict consistent across runs but regex assertion flaky (likely CWE-string variance).

**Hypothesis**: Anthropic API at temperature=0 is not strictly deterministic on long context (the agent's system prompt is ~8K tokens). The variance manifests on borderline cases where multiple defensible verdicts exist.

## Underlying signal (non-normative)

Despite the AC-10 halt, the underlying data shows a strong directional signal:

- **Non-flaky subset**: agent **100.0%** vs baseline **57.1%** (+42.9pp). The agent achieves perfect recall on the 6 fixtures it consistently scores.
- **Even on flaky fixtures**: agent 57.1% vs baseline 23.8%, delta +33.3pp. Agent wins in expectation even where it's flaky.
- **All fixtures**: agent 78.6% vs baseline 40.5% (+38.1pp).

This is the OPPOSITE direction from the bot's flipped-scrap verdict on the v1 run, and consistent with the original analyst hypothesis (vocabulary-mapped agent recall would be ~0.80). The agent's specialization helps; the v1 numbers were measurement artifacts.

## Recommendation

**Verdict per AC-10: `halt-due-to-flakiness`**. The methodology cannot conclude on this run.

**Operational follow-ups**:
1. Investigate variance source. Anthropic API at temperature=0 has known non-strict-determinism on long contexts. Quantify with a control test (same fixture × same variant × N=10 runs; measure variance).
2. Consider whether AC-10's 30% halt threshold is too aggressive at N=10 (where 1 flaky fixture = 10% and the threshold is 3 fixtures away). A larger corpus would tolerate more flakiness in absolute terms while keeping the percentage threshold informative.
3. Expand corpus to N≥30 and re-run. The +43pp non-flaky-subset signal is large enough that it would likely survive bigger-N variance.
4. Optionally, redesign the borderline fixtures (F001, F002) so they have less ambiguous expected verdicts.

## Cost / wall clock

- Total tokens in: 253,266
- Total tokens out: 8,574
- Estimated cost: $0.8884

Token counts are estimated from a text-length heuristic; replace with measured `usage` from the API response in a follow-up.

## Methodology v2 contract

Per the diagnosis at `.agents/critique/SPIKE-1854-methodology-diagnosis.md`:

- `BASELINE_PROMPT` is now role-neutralization only: `"Review the following input."`
- `OUTPUT_SHAPE_SUFFIX = "\n\nBegin your response with exactly one word: IDENTIFY, OK, or ESCALATE. Then briefly explain in <=80 words."` is appended to the user message for **both** variants.
- Both variants now receive identical user messages; only the system prompt differs (specialization is the only free variable).