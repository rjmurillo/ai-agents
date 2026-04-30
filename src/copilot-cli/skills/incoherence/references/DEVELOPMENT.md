# skills/incoherence/

## Overview

Incoherence detection skill using parallel agents for exploration and confirmation.

## Index

| File/Directory           | Contents                                       | Read When                                   |
| ------------------------ | ---------------------------------------------- | ------------------------------------------- |
| `SKILL.md`               | Workflow overview, step guide, quick reference | Using the incoherence skill                 |
| `scripts/incoherence.py` | Step orchestration with guidance output        | Debugging skill behavior, modifying prompts |

## Workflow Summary

22-step process with parallel agent phases:

**Detection Phase (Steps 1-13):**

- Steps 1-3: Survey, dimension selection, exploration dispatch (parent)
- Steps 4-7: Broad sweep, coverage check, gap-fill, format (exploration sub-agents)
- Step 8: Synthesis & candidate selection (parent)
- Step 9: Deep-dive dispatch (parent)
- Steps 10-11: Deep-dive exploration and format (deep-dive sub-agents)
- Steps 12-13: Verdict analysis and report generation (parent)

**Reconciliation Phase (Steps 14-22):** Apply user resolutions

## Agent Requirements

- Step 3: Launch haiku Explore agents (one per dimension) in ONE message
  - Sub-agents invoke steps 4-7 for multi-phase exploration
- Step 9: Launch sonnet Explore agents (one per candidate) in ONE message
  - Sub-agents invoke steps 10-11 for deep-dive verification

## Backtracking

Supported at any step. Common patterns:

- Step 8 empty -> Step 1 with broader dimensions
- Step 12 all false positives -> Step 8 with stricter criteria
