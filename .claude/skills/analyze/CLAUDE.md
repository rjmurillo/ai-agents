# skills/analyze/

## Overview

Systematic codebase analysis skill. IMMEDIATELY invoke the script - do NOT explore first.

## Index

| File/Directory       | Contents                              | Read When                   |
| -------------------- | ------------------------------------- | --------------------------- |
| `SKILL.md`           | Invocation instructions               | Using the analyze skill     |
| `scripts/analyze.py` | Complete workflow with prompt outputs | Debugging analyzer behavior |

## Key Point

The script IS the workflow. It outputs REQUIRED ACTIONS at each step. Follow them exactly. Do NOT try to follow any workflow manually - run the script and obey its output.

## Invocation

```bash
python3 scripts/analyze.py \
  --step-number 1 \
  --total-steps 6 \
  --thoughts "Starting analysis. User request: <what to analyze>"
```

The script will instruct you to delegate to Explore agent, classify focus areas, create investigation plans, and synthesize findings.
