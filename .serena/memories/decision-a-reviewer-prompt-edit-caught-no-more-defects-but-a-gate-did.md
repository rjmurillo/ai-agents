# A reviewer prompt edit showed no clear gain, while a deterministic check caught most sampled defects

**Atomicity**: 90%
**Category**: Eval design, review gaps
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E032, E014. State checked on main at 1be533c496 (2026-11-26).

## Question

Does tightening the reviewer prompt raise the defect catch rate, or do deterministic gates pay back more?

## Conventional answer

Adding checks to the review prompt, such as a prose claim check, and running /review raises recall of defects that third party bots catch. Existing gates were presumed to cover Bugbot class findings.

## First-principles position

The prompt edit showed no measurable gain. Trial to trial noise was larger than the measured effect. A deterministic gate caught most of the defect class that existing checks missed entirely. New checks belong in gates first.

## Evidence with limits

- E014, 102 jobs per arm in a held-out replay (2026-11-16): baseline caught 18 and treatment caught 21, with 9 caught by both, 9 by baseline only and 12 by treatment only.
- E014: exact McNemar p = 0.6636, against a rule of p < 0.05. Two baseline trials of the same prompt disagreed on 14 of 81 defects.
- E014: the io-portability gate caught 78 of 86 Bugbot class findings, where ruff plus existing checks caught 0 of 86.
- E032: the prose claim check, bundled in one prompt, showed no gain. Running /review barely moved the finding count. 52 percent of findings need a file outside the diff.
- E032: baseline noise (14 of 81 defects) was larger than the measured effect (21 vs 18).
- Limits: A reviewer subagent recomputed p from committed results on 2026-11-15. The 78 of 86 figure scores whole file matches, but the shipped gate checks only added lines, so shipped recall is not measured. Two trials per arm, one prompt edit, replay without tools, one corpus of 237 revisions.
- State on main at 1be533c496 (2026-11-26): no repo artifact to fix. evals/third-party-review-gap/README.md matches: line 99 says /review barely moved the count, line 228 gives McNemar p = 0.66, line 232 gives the verdict of no measurable gain, line 238 gives the 14 of 81 disagreement, and line 339 gives the 52 percent figure.

## Decision

Do not expect a reviewer prompt or contract edit to raise defect catch rate without a paired test. Do not read a few point prompt effect without repeated trials or a larger held-out set. Put recurring third party review defect classes into a deterministic gate first.

## Related

- `.serena/memories/decision-calibrate-guards-on-the-whole-corpus.md`
- `.serena/memories/eval/eval-held-out-gated-optimization.md`
