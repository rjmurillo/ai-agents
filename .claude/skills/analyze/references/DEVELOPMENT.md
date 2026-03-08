# skills/analyze/ Development Guide

## Overview

Systematic codebase analysis skill. The script (`scripts/analyze.py`) IS the workflow. It outputs REQUIRED ACTIONS at each step. Follow them exactly. Do NOT explore the codebase before invoking the script.

## File Index

| File/Directory | Contents | Read When |
|----------------|----------|-----------|
| `SKILL.md` | Triggers, process phases, invocation instructions | Using the analyze skill |
| `scripts/analyze.py` | Six-phase workflow engine with prompt generation | Debugging analyzer behavior or extending phases |
| `references/DEVELOPMENT.md` | This file: contributor guide | Modifying the skill |

## Architecture

The skill uses a **script-driven workflow** pattern. The Python script acts as a state machine that generates phase-appropriate prompts. The agent follows the prompts, collects evidence, and feeds accumulated state back via `--thoughts`.

```text
Agent invokes script -> Script emits REQUIRED ACTIONS -> Agent executes actions
  -> Agent re-invokes script with accumulated state -> Repeat until synthesis
```

### Phase Map

| Phase | Step | Function in analyze.py |
|-------|------|------------------------|
| Exploration | 1 | `get_step_guidance` (step == 1) |
| Focus Selection | 2 | `get_step_guidance` (step == 2) |
| Investigation Planning | 3 | `get_step_guidance` (step == 3) |
| Deep Analysis | 4 to N-2 | `get_step_guidance` (else branch) |
| Verification | N-1 | `get_step_guidance` (step == total_steps - 1) |
| Synthesis | N | `get_step_guidance` (is_final) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Invalid input (bad step-number, total-steps < 6) |

## Extending

To add a new investigation dimension (e.g., accessibility):

1. Add checklist items to the `FOCUS SELECTION` phase (step 2) in `get_step_guidance`
2. No changes needed to other phases; they operate on the focus areas selected in step 2
3. Update SKILL.md trigger list if the new dimension warrants a dedicated trigger phrase

## Testing

```bash
# Validate step 1 output
python3 scripts/analyze.py --step-number 1 --total-steps 6 --thoughts "test"

# Validate final step output
python3 scripts/analyze.py --step-number 6 --total-steps 6 --thoughts "test synthesis"

# Verify minimum step validation
python3 scripts/analyze.py --step-number 1 --total-steps 3 --thoughts "should fail"
# Expected: exit code 1
```
