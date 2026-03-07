# Progress Reporting Module

Session and skill-level progress indicators to reduce user interruptions during long-running operations.

## Background

Session export analysis (Issue #670) revealed that 33% of sessions were interrupted mid-execution. Root cause hypothesis: users lack visibility into agent progress during multi-step operations.

## Quick Start

### Skill-Level Checkpoints

For operations exceeding 30 seconds, emit checkpoints to show progress:

```python
from scripts.progress import emit_checkpoint

# Simple checkpoint
emit_checkpoint("Processing files")
# Output: [CHECKPOINT] Processing files

# With progress numbers
emit_checkpoint("Scanning", current=5, total=20)
# Output: [CHECKPOINT] Scanning (5/20)

# With details
emit_checkpoint("Validating", details="config.yaml")
# Output: [CHECKPOINT] Validating: config.yaml

# Full example
emit_checkpoint("Processing files", current=5, total=20, details="src/main.py")
# Output: [CHECKPOINT] Processing files (5/20): src/main.py
```

### Session-Level Progress

For multi-step session operations:

```python
from scripts.progress import ProgressReporter

reporter = ProgressReporter(total_steps=3)

reporter.start_phase("Initialization")
# ... do work ...
reporter.complete_step()

reporter.start_phase("Processing")
reporter.invoke_skill("pr-review")
# ... do work ...
reporter.complete_step(result="5 files processed")

reporter.start_phase("Cleanup")
# ... do work ...
reporter.complete_step()

reporter.report_summary()
```

Output:

```text
[PROGRESS] [0/3] (0%) Starting: Initialization
[PROGRESS] [1/3] (33%) Completed: Initialization
[PROGRESS] [1/3] (33%) Starting: Processing
[SKILL] Invoking: pr-review
[PROGRESS] [2/3] (66%) Completed: Processing - 5 files processed
[PROGRESS] [2/3] (66%) Starting: Cleanup
[PROGRESS] [3/3] (100%) Completed: Cleanup

[SUMMARY]
  Steps: 3/3
  Duration: 0:00:45
  Skills: pr-review
```

## Configuration

### Quiet Mode

Disable progress output by setting the environment variable:

```bash
export CLAUDE_PROGRESS_QUIET=1
```

Or:

```bash
export CLAUDE_PROGRESS_QUIET=true
```

### Checking Quiet Mode

```python
from scripts.progress import is_quiet_mode

if is_quiet_mode():
    # Skip verbose logging
    pass
```

## When to Use Checkpoints

Skills SHOULD emit checkpoints when:

- Operation takes more than 30 seconds
- Processing multiple items in a loop
- Waiting for external resources (API calls, file I/O)
- Performing validation across many files

Skills SHOULD NOT emit checkpoints for:

- Quick operations (under 5 seconds)
- Single-item operations
- Operations that already have their own output

## Checkpoint Format

All checkpoints use a consistent format:

```text
[CHECKPOINT] <step_name> [(<current>/<total>)] [: <details>]
```

Where:

- `step_name`: Required. Short description of the step.
- `current/total`: Optional. Progress numbers.
- `details`: Optional. Additional context.

## Output Destination

All progress output goes to `stderr` to avoid interfering with structured output on `stdout`. This allows scripts to pipe results while still showing progress.
