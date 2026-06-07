# Rule-Activation Baseline: Conditional Loading (2026-06-06)

Live `eval-rule-activation.py` run over the 7 heavy `.claude/rules` that have
scenario files. Question: does a rule's one-line frontmatter `description` trigger
the same behavior as its full body? If yes, the body can move off always-on
context and load on demand via Claude Code's `paths` frontmatter, with no behavior loss, reclaiming rule budget. (The repo currently uses `applyTo`/`alwaysApply`, which Claude Code does not read, so every rule body loads unconditionally today.) This is the empirical basis for the conditional-loading proposal (add `paths:` frontmatter to the Claude rules; ADR-069 open question: telemetry-of-influence).

Model: judge `claude-sonnet-4`. 7 rules x ~24 calls. Raw: `rule-activation-conditional-loading-2026-06-06.json`.

Scoring: per-mechanism average of activation/citation/behavior (1-5).
"Conditional-load SAFE" = description within 0.5 of full AND description beats
baseline by >= 0.5 (the body adds nothing the description does not).

| rule | baseline | description | full | desc-vs-full gap | verdict |
|---|---|---|---|---|---|
| clean-architecture | 2.33 | 5.0 | 5.0 | 0.0 | SAFE |
| domain-driven-design | 3.33 | 4.67 | 5.0 | 0.33 | SAFE |
| release-it | 1.33 | 4.67 | 5.0 | 0.33 | SAFE |
| working-with-legacy-code | 1.78 | 4.67 | 4.67 | 0.0 | SAFE |
| philosophy-of-software-design | 1.0 | 3.17 | 5.0 | 1.83 | KEEP BODY (sharpen description) |
| unified-software-engineering | 2.33 | 3.33 | 5.0 | 1.67 | KEEP BODY (sharpen description) |
| refactoring | 4.89 | 5.0 | 4.56 | -0.44 | PRUNE CANDIDATE (baseline already high; rule adds nothing) |

## Findings

- 4 of 7 heavy rules are conditional-load safe. Their bodies (~68 KB / ~17K
  tokens) can move on-demand with no measured behavior change.
- 2 rules (philosophy, unified-software-engineering) have load-bearing bodies and
  weak descriptions. Per the repo playbook, sharpen the `description` until it is
  within 0.5 of full, then they become conditional-load safe too.
- 1 rule (refactoring) shows baseline 4.89: the model already does refactoring
  well without the rule, and full (4.56) does not beat baseline. This is a prune
  candidate for always-on context regardless of the loading mechanism.

## Reproduce

```bash
python3 scripts/eval/eval-rule-activation.py \
  --scenarios tests/evals/rule-scenarios/*.json \
  --output evals/reports/rule-activation-conditional-loading-<date>.json
```

Churn-side baseline (where the commits go in degenerate PRs) is reproduced with:

```bash
python3 scripts/eval/analyze-pr-churn.py --high 60 --low 10 --output churn.json
```
