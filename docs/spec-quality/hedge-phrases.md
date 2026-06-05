# Step 0 Hedge-Phrase Blocklist

A reusable reference for spec-quality gates. The `/spec` command runs a Step 0
First Principles Gate before it lets a change proceed to requirements. One of the
gate's blocking checks scans the author's six answers for hedge phrases: vague,
aspirational, or speculative language that masks the absence of a concrete demand
signal. An answer that hedges fails the gate and the spec does not proceed.

This page publishes that blocklist so other spec-quality communities (SPDD users,
ADR-template maintainers, teams using EARS or similar requirement formats) can
adopt or cite it. It also makes the gate auditable from outside this codebase.

## Canonical source

The blocklist on this page is a published mirror. The single source of truth is
the Step 0 hedge-phrase table in
[`.claude/commands/spec.md`](../../.claude/commands/spec.md), between the
`### Step 0: First Principles Gate` heading and the `<!-- step0:hedge-table-end -->`
marker. The deterministic test parser that checks the list lives at
[`tests/commands/step0_parser.py`](../../tests/commands/step0_parser.py)
(`HEDGE_TECHNICAL_SUFFIXES`). Runtime enforcement comes from the `/spec`
agent following the Step 0 instructions in `spec.md`.

If this page and `spec.md` disagree, `spec.md` wins. Propose changes to the list
against `spec.md`, then update this mirror in the same change. Do not edit this
page to alter gate behavior; the gate reads `spec.md`, not this document.

## How the match works

- **Case-insensitive word-boundary match**: `\bphrase\b`. A phrase matches
  regardless of letter case and only on whole-word boundaries.
- **Applied to author answers**, not to system prompts or quoted instruction
  text. The gate scans what the author wrote, not the prompt that asked the
  question.
- **A mix of multi-word phrases and a few single-word entries**. The single words
  (`probably`, `eventually`, `someday`) read as hedges in standard English, so
  they are listed even though most entries are multi-word.

## The 21-phrase blocklist

The "Why it hedges" column records the reason each phrase fails a Step 0 answer.

| Phrase | Why it hedges |
|---|---|
| `would be nice` | aspirational |
| `would be useful` | aspirational |
| `would be helpful` | aspirational |
| `we believe` | belief, not observation |
| `we expect` | prediction, not observation |
| `we anticipate` | prediction, not observation |
| `we predict` | prediction, not observation |
| `we hope` | aspiration |
| `we assume` | assumption, not evidence |
| `stakeholders want` | unnamed audience |
| `users want` | unnamed audience |
| `customers want` | unnamed audience |
| `should we` | self-questioning, not commitment |
| `might be useful` | speculation |
| `might be needed` | speculation |
| `could be useful` | speculation |
| `probably` | hedging (single word, but unambiguous) |
| `eventually` | indefinite future |
| `someday` | indefinite future |
| `down the road` | indefinite future |
| `nice to have` | low-priority aspiration |

## RFC 2119 non-hedge exemptions

The single words `should`, `might`, and `could` are NOT hedges in this list. They
conflict with RFC 2119 requirement language (`SHOULD`, `MAY`) and produce false
positives when an author writes a real requirement. The blocklist deliberately
lists only the multi-word forms (`should we`, `might be useful`, `could be useful`)
so that a bare `should` in a requirement passes.

## Technical-suffix exemption table

A few hedge words are also the first token of a settled technical term. The bare
word hedges; the technical term does not. The gate exempts the technical term
through a suffix-table lookup rather than removing the word from the blocklist.

The lookup lives in
[`tests/commands/step0_parser.py`](../../tests/commands/step0_parser.py) as
`HEDGE_TECHNICAL_SUFFIXES`. When a blocklist phrase is immediately followed by an
allowed suffix, the match flips from hedge to non-hedge.

| Hedge word | Exempt when followed by | Resulting technical term |
|---|---|---|
| `eventually` | `consistent` (plus trailing `.,;:)!?`) | `eventually consistent` |

`eventually consistent` is a distributed-systems term (a store that converges to a
single value after writes stop), not an indefinite-future hedge. The trailing
punctuation variants exist so the lookup survives `eventually consistent.` at the
end of a sentence.

## How to extend the list

The blocklist grows from evidence, not taste. A new phrase earns its place when a
real Step 0 answer hedged through a phrase the current list missed, and a
retrospective named it.

1. Propose the phrase and a one-clause "Why it hedges" reason.
2. Cite the answer or retrospective that surfaced the gap. A phrase with no
   evidence is a guess; the gate already over-blocks if you add guesses.
3. Add the row to the table in `.claude/commands/spec.md` (the canonical source),
   then mirror it here in the same change.
4. If the phrase has a legitimate technical-term form, add the exemption to
   `HEDGE_TECHNICAL_SUFFIXES` in `tests/commands/step0_parser.py` so the gate does
   not flag the technical use.

## Source attribution

The list comes from the Step 0 gate requirement and its retrospective audit.
Each phrase below maps to the gate condition it protects and the source artifact
that introduced the condition.

| Phrase | Gate condition | Source |
|---|---|---|
| `would be nice` | Aspirational demand | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-04 |
| `would be useful` | Aspirational demand | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-04 |
| `would be helpful` | Aspirational demand | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-04 |
| `we believe` | Belief without observation | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-03 |
| `we expect` | Prediction without observation | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-03 |
| `we anticipate` | Prediction without observation | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-03 |
| `we predict` | Prediction without observation | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-03 |
| `we hope` | Aspiration without demand | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-04 |
| `we assume` | Unverified premise | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and `.agents/retrospective/2025-12-26-prd-planning-workflow.md` |
| `stakeholders want` | Unnamed requester | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-04 |
| `users want` | Unnamed requester | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-04 |
| `customers want` | Unnamed requester | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-04 |
| `should we` | Self-questioning in place of commitment | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` |
| `might be useful` | Speculative value | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-03 |
| `might be needed` | Speculative need | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-03 |
| `could be useful` | Speculative value | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-03 |
| `probably` | Unverified confidence | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and `.agents/retrospective/2026-01-03-adr-generation-quality.md` |
| `eventually` | Indefinite future | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-13 review cadence |
| `someday` | Indefinite future | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-13 review cadence |
| `down the road` | Indefinite future | `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md` retrospective audit and REQ-016-13 review cadence |
| `nice to have` | Low-priority aspiration | `.agents/retrospective/2025-12-15-documentation-gap.md` and REQ-016-04 |

## References

- [`.claude/commands/spec.md`](../../.claude/commands/spec.md). Canonical Step 0
  gate and hedge-phrase table.
- [`tests/commands/step0_parser.py`](../../tests/commands/step0_parser.py).
  Deterministic test parser and `HEDGE_TECHNICAL_SUFFIXES` exemption table.
- [`.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md`](../../.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md).
  Requirement and retrospective audit that introduced Step 0.
