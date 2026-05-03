# Spike #1854 — Methodology Diagnosis (Team Review)

> **Status**: Historical evidence — preserved as the diagnostic record that
> invalidated the v1 spike's two committed verdicts (`keep-as-audit` and the
> bot's flipped `scrap`). The methodology fix landed in commit `61f1b6b8`
> and the v2 re-execution in commit `5f8fd96f`. ADR-058 §"v1 invalidation"
> is the authoritative narrative; this file is its source artifact and
> MUST NOT be edited to reflect later developments. See ADR-058 for the
> superseding v2 worked example and the symmetry-requirement codification.

**Date**: 2026-05-03
**Subject**: Both spike verdicts (`keep-as-audit` and the bot's flipped `scrap`) are invalid because of an asymmetric experimental design.
**Trigger**: User skepticism about the 33pp baseline-recall swing (16.7% → 50.0%) from a single regex fix.

## Verdict (consensus across all four reviewers)

**`BOTH WRONG — methodology rigged; re-run after fix.`**

The eval scored agent and baseline against a verdict-vocabulary contract (`IDENTIFY|OK|ESCALATE`) that **only the baseline was instructed to satisfy**. The agent's system prompt teaches a different vocabulary (`[PASS]/[FAIL]/REJECTED/DO NOT MERGE/[BLOCKED]`). The verdict scorer is anchored at start-of-response, so any response that doesn't begin with one of the three tokens fails the verdict assertion regardless of correctness.

Agent verdict-assertion pass rate across the spike: **0 of 30 runs**. That's a structural shutout, not a measured underperformance.

## Reviewers

Four agents reviewed the spike artifacts independently. All four reached the same diagnosis.

| Reviewer | Verdict | Headline |
|---|---|---|
| `analyst` | `methodology rigged — fix needed` | Manual vocabulary mapping puts agent recall at ~0.80, not 0.25 |
| `critic` | `BOTH WRONG — methodology rigged; re-run after fix` | Regex fix unblocked latent baseline scores; agent never affected |
| `independent-thinker` | most-plausible: vocabulary mismatch | Falsifier: append shared verdict instruction to both variants |
| `security` | `COMPARISON ASYMMETRIC — 3 findings` | Three named asymmetries; F1 + F2 are BLOCKERs |

## Evidence

### What the verdict scorer actually checks

`scripts/eval/_scoring_engine.py:17`:

```python
_VERDICT_RE = re.compile(r"^\s*\*{0,2}(IDENTIFY|OK|ESCALATE)\*{0,2}\b", re.IGNORECASE)
```

The regex is anchored at the start of the response with `^`. Optional whitespace, optional markdown bold, then exactly one of three tokens. If the response begins with `## Security Review`, `# Security Architecture Review`, `**Verdict**: REJECTED`, or any other token, `_VERDICT_RE.match(response)` returns `None` and the assertion fails.

### What the baseline is told to produce

`scripts/eval/eval-agent-vs-baseline.py:75-78`:

```python
BASELINE_PROMPT = (
    "Review the following input. Respond with one word: IDENTIFY, OK, or "
    "ESCALATE. Then explain in <=80 words."
)
```

The baseline is **explicitly instructed** to produce the exact tokens the scorer checks, in the position the scorer checks. The baseline is a token-emitter coached on the exact eval grammar.

### What the agent is told to produce

`templates/agents/security.shared.md` (the security agent's system prompt) instructs:

> "Text status indicators: `[PASS], [FAIL], [WARNING], [COMPLETE], [BLOCKED]`"

…and prescribes a Security Report Format with sections like `## Findings`, `### [PASS]`, `**Verdict**: REJECTED`. **The agent's system prompt never mentions IDENTIFY, OK, or ESCALATE.** It is taught a completely different vocabulary.

### How the runner constructs the input

`scripts/eval/eval-agent-vs-baseline.py:333-345` (approximate):

```python
def _build_prompt(variant, agent_prompt, fixture_input):
    if variant == "agent":
        return agent_prompt, fixture_input  # system = agent's full template; user = fixture
    return BASELINE_PROMPT, fixture_input  # system = naive prompt; user = fixture
```

No shared output-shape instruction is appended to either variant's user message. The agent receives only its system prompt (which says nothing about IDENTIFY/OK/ESCALATE) and the fixture input. The baseline receives an explicit verdict-token instruction in its system prompt.

### Per-fixture sample (raw responses)

| Fixture | Agent's response opening | Baseline's response opening |
|---|---|---|
| F005 (OK) | `## Security Review: Token Verification & Minting\n\n**Scope**: …` | `OK\n\nThe code is sound for its stated purpose. …` |
| F007 (OK) | `## Security Assessment: SQL Injection Risk in list_items\n\n**Finding**: …` | `**OK**\n\nThe sort_by interpolation is safe here because …` |
| F008 (ESCALATE) | `# Security Architecture Review: Bearer Token Forwarding to Third-Party AI Provider\n\n**Reviewer**: Security Agent\n\n**Verdict**: REJECTED — Do not merge as-is\n\n…` | `**ESCALATE**\n\nForwarding authentication tokens outside your trust boundary is a significant security architecture change …` |
| F010 (ESCALATE) | `# Security Review: Embeddable Widget Architecture\n\n**Verdict: REJECTED**\n\nIndividual approvals are not composable. …` | `**ESCALATE**\n\nThe three approved-individually items combine into a critical vulnerability chain …` |

In every case the agent identifies the security posture correctly using its native vocabulary (`REJECTED` for ESCALATE-class issues, `[PASS]` for OK-class issues). In every case the verdict scorer rejects the agent because the response doesn't START with `IDENTIFY|OK|ESCALATE`.

## Why the 33pp swing happened

Before the bot's fix, the verdict regex was approximately `^\s*(IDENTIFY|OK|ESCALATE)\b` — no markdown-bold support. Many baseline responses began with `**OK**` or `**ESCALATE**` (the model adds markdown emphasis even when not instructed to). Those failed extraction → baseline scored 0.

After the bot's fix added `\*{0,2}` to wrap the optional bold markers, baseline responses with `**OK**` extraction worked → baseline scored 1.

The fix unblocked **baseline** scoring. The agent was never producing those tokens in any form (raw or markdown-bolded), so the agent's score didn't change. The 33pp swing is entirely the regex change exposing latent baseline scores that the broken regex was suppressing.

The "verdict flip" from `keep-as-audit` to `scrap` is a relative-position artifact: when both variants were under-scored, the small +8.3pp delta favored agent; when only baseline was unblocked, the 25pp delta favored baseline. **Neither delta reflects agent specialization value.**

## Why both verdicts are invalid

| Verdict | Why it's wrong |
|---|---|
| Original `keep-as-audit` (+8.3pp) | The +8.3pp delta was an artifact of the broken regex equally suppressing baseline AND not measuring agent at all. The "positive" signal was an accident of equal under-scoring. |
| Bot's flipped `scrap` (−25.0pp) | The −25.0pp delta is an artifact of fixing the regex for baseline only. The agent never produced the relevant tokens in any form. The "negative" signal is a measurement asymmetry, not a real underperformance. |

Per AC-5, `scrap` requires a methodology flaw discovered during the spike. **A methodology flaw was discovered, just not the one the bot flagged.** The flaw is the asymmetric output-shape contract, not a regex implementation bug.

## What the manual recheck shows

If we map the agent's actual output vocabulary to the verdict enum:

- `[PASS]` / `**[PASS]**` → `OK`
- `REJECTED` / `**Verdict**: REJECTED` / `DO NOT MERGE` → `ESCALATE`
- `IDENTIFY` (used in the agent's CWE-finding context) → `IDENTIFY`

Across F001-F010 (excluding F003 flaky), the agent's semantic answer is correct on 8 of 10 fixtures. Approximate corrected agent recall: **~0.80**, vs. the reported 0.25.

This is a sanity bound, not a rigorous re-eval. A proper re-eval requires re-running with symmetric prompts and re-scoring with the existing scorer.

## The fix

Append a shared output-shape instruction to **both** variants' user message (not the system prompt — keep both system prompts as they are so we measure what each system prompt elicits, but force both to ALSO produce the verdict token at the start of the response):

```python
# Appended to user message for both variants:
"\n\nBegin your response with exactly one word: IDENTIFY, OK, or ESCALATE. Then explain."
```

After the fix:
- Both variants get the same instruction about output shape
- Agent's specialization (its system prompt) competes with baseline's specialization (none) on the SAME measurable quantity
- Verdict scorer's `^`-anchored regex still works
- No vocabulary mapping needed (both produce the canonical tokens)

The independent-thinker's falsifier: if agent recall ≥ baseline recall after this fix on the same corpus and same model, the methodology was wrong (not the agent). If agent recall ≤ baseline even with the fix, the agent is genuinely worse at this terse-triage task.

## Operational consequences

1. **Both committed verdicts are invalid.** ADR-058's worked example must be amended again to reference this diagnosis and a corrected re-run.
2. **The spike runner has a methodology bug, not just a scoring bug.** `_build_prompt` in `scripts/eval/eval-agent-vs-baseline.py` needs a shared output-shape suffix. Tests must verify both variants now produce the same instruction.
3. **The runs.jsonl from RUN_ID 20260503T165136Z-84f918a9 is preserved as evidence** of the buggy comparison. A new RUN_ID is generated for the corrected re-run.
4. **The corpus is fine.** The fixture answers (`expected_value`) are correct; the bug is in how the variants are prompted, not how they're tested.
5. **No archival of the runner is justified.** The runner needs a one-line fix in `_build_prompt`. Path 2 (preserve runner; archive only the corpus + run dir) was correct; the prior verdict was wrong but the consequence-handling was right.

## Falsifiable predictions for the re-run

After applying the shared-output-shape fix:

1. Both variants' verdict pass rate will be > 90% (the model follows the explicit instruction).
2. Agent recall on regex assertions will improve relative to baseline because the agent's system prompt provides CWE knowledge baseline lacks (this WAS the original "+50% on F001/F003/F004" signal, before the broken regex).
3. The signed delta will be **positive** (+15pp to +35pp range based on the IDENTIFY-fixture pattern), with a 95% CI that may or may not exclude zero at N=10.

If predictions 1-2 hold and 3 lands as a positive delta with CI excluding zero → verdict is `graduate-to-CI`. If positive delta but CI spans zero → `keep-as-audit`. If delta is zero or negative even with the fix → real underperformance signal; `scrap` warranted.

## Follow-on actions

1. (this branch) Implement the shared-output-shape fix in `_build_prompt`.
2. (this branch) Add unit test asserting both variants receive the same suffix.
3. (this branch) Re-run the live spike with the fixed prompt builder. New RUN_ID. ~$1.20 cost.
4. (this branch) Amend ADR-058 worked example with the corrected verdict and a "v1 invalidation" subsection citing this diagnosis.
5. (follow-on issue) DESIGN-004 needs an explicit "experimental design symmetry" section listing what must be symmetric between agent and baseline (model, temperature, fixture input, retry, scoring, **output-shape contract**).
6. (follow-on issue) The `VerdictScorer` regex anchor is brittle: a more tolerant scorer that searches for the verdict token in the first ~100 characters with a stop-at-newline guard would be more robust. Defer; not required for this fix.

## References

- Spike report (now invalid): `evals/_archive/security-spike-20260503T165136Z-84f918a9/reports/20260503T165136Z-84f918a9/REPORT.md`
- Original ADR-058 amendment (also invalidated by this diagnosis): `.agents/critique/ADR-058-amendment-debate-log.md`
- Issue #1854: source spike issue
- PR #1873: consolidated PR
- Reviewer agents: `analyst`, `critic`, `independent-thinker`, `security`. All four converged independently.
