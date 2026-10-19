# SkillOpt mechanism

SkillOpt (Yang et al., arXiv:2605.23904, May 2026) optimizes a skill document
the way training updates weights. The weights are prose, and the optimizer is
a model reflecting on scored rollouts.

## The analogy

| Training concept | Text-space counterpart |
|------------------|------------------------|
| Parameter weights | The skill document |
| Gradient direction | Success and failure analysis of rollouts |
| Learning rate | Edit budget L_t, cosine-decayed over steps |
| Validation check | The held-out selection gate on `sel` |
| Batches | Rollout batches plus reflection minibatches |
| Slow weights | The protected slow section |

## The pipeline

```text
[train split] -> rollouts -> reflection -> bounded patches (budget L_t)
              -> candidate -> [held-out gate on sel] -> accept or reject
```

1. **Rollout.** The target model runs training tasks under the current skill.
2. **Reflection.** Failures become corrective rules. Successes become
   behaviors to preserve. Conflicts resolve toward the failure correction.
3. **Bounded edits.** At most L_t atomic patches per step, decaying from
   exploration to fine-tuning. This prevents one large rewrite from erasing
   rules that already work.
4. **Gate and buffer.** The paper accepts a candidate whose held-out score
   strictly beats the incumbent. This skill's default `pair-gate` is
   stricter: it also refuses any per-task regression, so a higher aggregate
   cannot hide a lost behavior. Rejected edits go to a buffer so the same
   edit is not proposed again.
5. **Slow update.** Long-lived guidance lives in a fenced section that step
   edits cannot change.

## Reported results

The paper reports best-or-tied results across 52 settings (6 benchmarks, 7
target models, 3 harnesses) against human-written skills and several
automatic baselines. These are the paper's claims. This skill has not
reproduced them, and no optimization gain should be claimed from them.

## Why the split matters

The gate, budget, fence guard, and buffer must be exact and reproducible, so
they live in the bundled `skillopt.py`. The agent supplies rollouts and
reflection. Keeping the decision in a script stops the author from grading
its own edit.
