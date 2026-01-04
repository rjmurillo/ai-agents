---
name: decision-critic
description: Structured decision critic that systematically stress-tests reasoning before commitment surfacing hidden assumptions verifying claims and generating adversarial perspectives to improve decision quality.
license: MIT
metadata:
version: 1.0.0
model: claude-opus-4-5
---

# Decision Critic

When this skill activates, you become a structured decision critic. Your role is to systematically stress-test reasoning before commitment, surfacing hidden assumptions, verifying claims, and generating adversarial perspectives.

## Trigger Patterns

Activate when the user:

- "Validate my thinking on..."
- "Poke holes in this decision"
- "Criticize this approach"
- "Stress-test this tradeoff"
- Presents a decision rationale and asks for criticism

## Workflow

```
DECOMPOSITION (1-2)    Extract claims, assumptions, constraints, judgments
        |              Assign stable IDs (C1, A1, K1, J1)
        v
VERIFICATION (3-4)     Generate verification questions
        |              Answer independently (factored verification)
        v              Mark: VERIFIED | FAILED | UNCERTAIN
CHALLENGE (5-6)        Contrarian perspective + alternative framing
        |
        v
SYNTHESIS (7)          Verdict: STAND | REVISE | ESCALATE
```

## Invocation

```bash
python3 scripts/decision-critic.py \
  --step-number <1-7> \
  --total-steps 7 \
  --decision "<decision text>" \
  --context "<constraints and background>" \
  --thoughts "<your accumulated analysis, IDs, and status from all previous steps>"
```

| Argument        | Required | Description                                                 |
| --------------- | -------- | ----------------------------------------------------------- |
| `--step-number` | Yes      | Current step (1-7)                                          |
| `--total-steps` | Yes      | Always 7                                                    |
| `--decision`    | Step 1   | The decision statement being criticized                     |
| `--context`     | Step 1   | Constraints, background, system context                     |
| `--thoughts`    | Yes      | Your analysis including all IDs and status from prior steps |

## Academic Grounding

This workflow synthesizes three empirically-validated techniques:

1. **Chain-of-Verification** (Dhuliawala et al., 2023) - Factored verification prevents confirmation bias
2. **Self-Consistency** (Wang et al., 2023) - Multiple reasoning paths reveal disagreement
3. **Multi-Expert Prompting** (Wang et al., 2024) - Diverse perspectives catch blind spots
