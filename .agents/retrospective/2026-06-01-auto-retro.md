# Retrospective: 2026-06-01

> UNFILLED SKELETON written by invoke_auto_retrospective.py (Stop hook).
> The sections below are empty placeholders, not a completed retrospective.
> Run the retrospective agent to populate them, then delete this banner.

## Session Context

### Work Items
- Issue #2205: Copilot CLI preToolUse/sessionStart hooks failed on Windows with 'can't open file C:\Users\user\hooks\sessionStart\...py: No such file or directory'. The generated hooks.json invoked scripts via python3 -u "./hooks/<event>/<script>.py" with cwd ".", which Copilot CLI resolves against the user's working directory, not the vendored plugin install location.


## What Went Well

- _UNFILLED. Run the retrospective agent to populate this section._

## What Could Improve

- _UNFILLED. Run the retrospective agent to populate this section._

## Key Learnings

- _UNFILLED. Run the retrospective agent to populate this section._

## Failure Patterns

- _UNFILLED. Run the retrospective agent to populate this section (check .agents/failure-modes/)._
