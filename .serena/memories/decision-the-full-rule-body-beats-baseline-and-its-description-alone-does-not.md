# The full rule body beat baseline in 7 of 8 eval runs, but only 3 of 8 gaps exceed the noise floor

**Atomicity**: 90%
**Category**: Eval design, rule activation
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E060, E021. State checked on main at 1be533c496 (2026-11-26).

## Question

Can an always-on rule body be cut to its description without losing activation quality?

## Conventional answer

The Anthropic progressive disclosure doctrine and vault guidance say to minimize prompts, cutting over 80 percent. A rule description should suffice, and trimmed bodies lose nothing. The eval doc claimed every cell used the full 3 sample judge and that the full body beats description only retrieval.

## First-principles position

Across 8 identical runs the full body beat baseline 7 times, and the description alone beat it once. That blocks the planned cut. A later audit found the headline overstated. Judge failures were undercounted, and only 3 of 8 full minus description gaps exceed the noise floor.

## Evidence with limits

- E021 (2026-07-30), 8 identical runs on Opus 5 and Sol 5.6, 4 runs each: description only beat baseline 1 of 8 with pooled mean delta -0.13. The full body beat it 7 of 8 with +0.67. Sign test p about 0.035.
- E021: the run to run spread of the full delta was 0.94 on Opus and 1.11 on Sol, against a committed noise floor of about 0.3.
- E060 (2026-07-30): Opus cells had 1 of 3 judge samples. Failed samples were 6, 8, 4, 6 against the reported 4, 6, 3, 4.
- E060: full minus description deltas were 0.44, 0.89, 1.22, 1.22, -0.22, 0.89, 0.78, 1.22. Only 3 of 8 exceed the document's own noise floor of about 1.0. The sign count p = 0.0703 was chosen after seeing data.
- Limits: One rule file, one fixture, two models, LLM judge scoring through copilot-cli. Run spread exceeds the noise floor, and the sign test treats the 8 runs as independent. The priming path was tested, not the production loading path. The doc and its false claims are already corrected on main.
- State on main at 1be533c496 (2026-11-26): fixed. `src/claude/skills/context-optimizer/references/model-context-doctrine.md:112` says the available evidence does not support cutting the body. `rule-audit-procedure.md:172` checks judge failures and the noise floor.

## Decision

Do not cut a rule body to its description on the strength of progressive disclosure doctrine alone. Replicate the full versus description comparison across runs first, and report the spread. Carry these caveats: 7 of 8 positive by sign, 3 of 8 above the noise floor, and judge failures counted by sample. Do not call the full over description gap resolved.

## Related

- `.serena/memories/eval/eval-held-out-gated-optimization.md`
- `.serena/memories/eval-harness-observations.md`
