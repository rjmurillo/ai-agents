# Script Integration Framework

<!-- vendor-portability-exec: example invocations only; scripts referenced here are mostly illustrative; the one real script is get_unresolved_review_threads.py in the github skill -->

Scripts transform skills from documentation-only guides into executable, verifiable systems. This framework provides decision criteria for when to create scripts, how to integrate them effectively, and patterns for making skills autonomous and independently verifiable.

---

## Overview

### Why Scripts Matter for Skills

| Without Scripts | With Scripts |
|----------------|--------------|
| Manual execution | Automated, repeatable |
| Human verification | Independent verification |
| Session-bound state | Persistent state |
| Error-prone | Deterministic |
| Hard to compose | Easily orchestrated |

**Principle:** A skill with well-designed scripts can run unattended for scoped, user-approved operations, hand its outcome to an independent check, and recover from errors.

---

## Decision Tree: Script vs No Script

### Primary Decision

```
Does this operation require...?
│
├─► Deterministic reliability (same input → same output)?
│   └── YES → Script recommended
│
├─► Repeated execution (same logic needed >2 times)?
│   └── YES → Script recommended
│
├─► State persistence across sessions?
│   └── YES → Script required (JSON/YAML state files)
│
├─► Autonomous verification (outcome must be checked without the agent's opinion)?
│   └── YES → Script or existing instrument required (executor script plus an independent postcondition check)
│
├─► Complex calculations or transformations?
│   └── YES → Script recommended
│
├─► Integration with external tools/APIs?
│   └── YES → Script recommended (abstraction layer)
│
├─► Progress tracking or visualization?
│   └── YES → Script recommended
│
└── All NO → Prose instructions sufficient
```

### Quick Decision Matrix

| Scenario | Script? | Rationale |
|----------|---------|-----------|
| "Validate the output matches X" | Yes | Verification must be deterministic |
| "Run this command once" | No | One-off, simple instruction |
| "Track progress across phases" | Yes | State persistence needed |
| "Calculate a score based on criteria" | Yes | Complex logic, reproducible |
| "Read this file and understand it" | No | Cognitive task, not automatable |
| "Transform JSON to YAML" | Yes | Deterministic transformation |
| "Decide which approach to use" | No | Requires human judgment |
| "Check if all tests pass" | Yes | Counts as verification through its reported results (count, names), not exit 0 alone |
| "Count the unresolved threads on a PR" | Existing instrument | Exact computable fact; an existing tool already answers it |
| "Choose between two designs with different costs" | No (map) | Ambiguous tradeoff; the agent decides from observations |
| "Collect CI evidence, pick a fix, apply and re-check" | Partial (hybrid) | Scripts gather and validate; the agent decides in between |

### Design Selection: Map, GPS, or Hybrid

The tree above answers "script or prose". Before choosing, name who decides. This is a design choice, not a section every skill carries. Record it in a generated skill only where it changes the workflow.

Ask these five questions about the operation:

| Question | Points toward |
|----------|---------------|
| Is the input ambiguous, or do branch criteria need judgment? | Map |
| Can a program check the postcondition without the agent's opinion? | GPS or hybrid |
| Can the action be undone cheaply? | GPS is safer when yes; keep a review step when no |
| What does a wrong action cost? | High cost keeps a reviewed decision in the path |
| Does an instrument already perform the operation? | Reuse it; do not write a script |

| Design | Use when | Shape |
|--------|----------|-------|
| **Map** | The case is ambiguous and judgment decides | Give observations, instruments, branch criteria, and accepted outcomes. The agent decides. |
| **GPS** | Inputs and postconditions are deterministic | A program runs the specified operation. The agent makes no decision that a program could make. |
| **Hybrid** | Facts are measurable, the choice needs judgment, and the action is checkable | Deterministic evidence collection, then an agent decision, then deterministic validation or execution. |

Routing examples:

| Task | Design | Why |
|------|--------|-----|
| Report the number of unresolved review threads on a PR | GPS, through the existing instrument | Exact computable fact. `get_unresolved_review_threads.py` returns `unresolved_count`. Read it, and accept it only when `fetched_pages_complete` is true. Exit 0 can accompany an incomplete snapshot. |
| Pick between two architectures with different maintenance costs | Map | Ambiguous tradeoff. No program can score it. Give criteria and let the agent decide. |
| Gather failing-check logs, decide the fix, apply it, re-run the checks | Hybrid | Measured facts, then judgment, then a validated action. |

Counter-examples:

| Anti-pattern | Correct design |
|--------------|----------------|
| Replace an ambiguous, consequential decision with unreviewed deterministic automation (for example, a script that auto-merges on a heuristic score) | Map or hybrid: keep a reviewed decision before the action |
| Write a new script for an operation an existing tool already performs | Reuse the tool. Add a script only after you verify the capability gap. |

### Executor Success Is Not Verified Success

Separate execution authority from verification authority. The step that runs an operation reports that it ran. A separate check confirms the postcondition. Exit code 0 shows the executor finished. It does not show the task outcome holds when a check can read that outcome directly (file exists with expected content, API state changed, test count matches).

---

## Script Categories

### The 7 Script Types

| Category | Purpose | When to Use | Key Patterns |
|----------|---------|-------------|--------------|
| **Validation** | Verify artifacts meet standards | Output verification, quality gates | `ValidationResult`, exit codes 0/1 |
| **State Management** | Track progress, persist data | Multi-session workflows, progress tracking | JSON files, argparse subcommands |
| **Generation** | Create artifacts from templates | Scaffolding, boilerplate creation | Template substitution, file I/O |
| **Transformation** | Convert or process data | Format conversion, data cleaning | Input parsing, output formatting |
| **Integration** | Interface with external tools | API calls, tool orchestration | Graceful fallbacks, error handling |
| **Visualization** | Render progress or status | Dashboards, progress indicators | ASCII art, progress bars |
| **Calculation** | Compute metrics or scores | Scoring rubrics, analytics | Numerical processing, aggregation |

### Category Selection Flow

```
What does the script primarily do?
│
├─► Check if something is correct/valid?
│   └── VALIDATION
│
├─► Save or load data between runs?
│   └── STATE MANAGEMENT
│
├─► Create new files from templates?
│   └── GENERATION
│
├─► Convert data from one format to another?
│   └── TRANSFORMATION
│
├─► Talk to external tools or APIs?
│   └── INTEGRATION
│
├─► Show progress or status visually?
│   └── VISUALIZATION
│
└── Compute numbers or scores?
    └── CALCULATION
```

---

## Language Selection

### Decision Guide

| Language | Best For | Pros | Cons | Use When |
|----------|----------|------|------|----------|
| **Python** | Most scripts | Readable, rich stdlib, portable | Slower startup | Default choice |
| **Bash** | Simple glue | No dependencies, native | Limited logic | <30 lines, Unix-only |
| **Go** | Performance | Fast, single binary | Compile step | Performance-critical |
| **Node.js** | Web/async | npm ecosystem, async | Heavier | Web APIs, npm tools |

### Default: Python

Python is the default language for skill scripts because:

1. **Readability** - Easy for any developer to understand
2. **Standard Library** - `argparse`, `json`, `pathlib` cover most needs
3. **Portability** - Works on macOS, Linux, Windows
4. **No Dependencies** - Standard library is sufficient for most scripts
5. **Ecosystem Alignment** - Matches existing skill scripts

**Rule:** Use Python unless you have a specific reason not to.

### When to Consider Alternatives

| Scenario | Consider |
|----------|----------|
| Wrapping 2-3 CLI commands | Bash |
| Need <10ms startup time | Go |
| Heavy npm tool integration | Node.js |
| System-level operations | Go or Bash |

---

## Agentic Script Patterns

These patterns make scripts capable of autonomous operation.

### Pattern 1: Fast-Fail Output Check

Scripts should check their own outputs and fail fast. This guard is not verification authority. An independent postcondition check still runs after the script:

```python
def execute_and_check(input_data):
    """Execute operation and fail fast on a bad result."""
    result = perform_operation(input_data)

    # Fast-fail guard - the script checks itself; an independent postcondition check still runs after it
    is_valid, reason = verify_output(result)
    if not is_valid:
        return Result(success=False, message=f"Fast-fail check failed: {reason}", errors=[reason])

    return Result(success=True, message="Operation completed", data=result)
```

**Why:** Stops a bad result early. The exit code reports executor success only. Where a postcondition can be checked independently, run a separate check and treat that result as the evidence, not exit 0.

### Pattern 2: Error Recovery

Scripts should attempt recovery before failing:

```python
def resilient_operation(max_retries=3):
    """Operation with automatic retry on recoverable errors."""
    for attempt in range(max_retries):
        try:
            result = perform_operation()
            is_valid, reason = fast_fail_check(result)
            if is_valid:
                return result
            log(f"Attempt {attempt + 1} rejected: {reason}, retrying...")
        except RecoverableError as e:
            if attempt == max_retries - 1:
                raise  # Final attempt, propagate error
            log(f"Attempt {attempt + 1} failed: {e}, retrying...")
            time.sleep(1)  # Brief delay before retry

    return fallback_result()
```

**Why:** Reduces need for human intervention on transient failures.

### Pattern 3: State Persistence

Scripts should maintain state across sessions:

```python
from pathlib import Path
import json

STATE_DIR = Path.home() / ".cache" / "skill-name"
STATE_FILE = STATE_DIR / "state.json"


def load_state() -> dict:
    """Load persisted state with graceful fallback."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {"error": "corrupted", "data": {}}
    return {"version": "1.0", "created_at": datetime.now().isoformat()}


def save_state(state: dict) -> None:
    """Save state to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))
```

**Why:** Enables multi-session workflows and progress tracking.

### Pattern 4: Structured Output

Scripts should output structured data for automation:

```python
def main():
    result = process()

    # Structured output for automation
    if args.json:
        print(
            json.dumps(
                {
                    "success": result.success,
                    "message": result.message,
                    "data": result.data,
                    "errors": result.errors,
                }
            )
        )
    else:
        # Human-readable output
        print(f"{'Success' if result.success else 'Failed'}: {result.message}")

    sys.exit(0 if result.success else 1)
```

**Why:** Enables script composition and programmatic processing.

### Pattern 5: Graceful Degradation

Scripts should work with optional dependencies:

```python
def parse_yaml(text: str) -> dict:
    """Parse YAML with graceful fallback."""
    try:
        import yaml

        return yaml.safe_load(text)
    except ImportError:
        # Fallback: basic key-value parsing
        result = {}
        for line in text.split("\n"):
            if ":" in line and not line.strip().startswith("#"):
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        return result
```

**Why:** Reduces dependency requirements and improves portability.

---

## Script Discovery Process (Phase 1)

During Deep Analysis, apply the **Automation Lens** (Lens 12) to identify script opportunities.

### Automation Lens Questions

| Question | Purpose |
|----------|---------|
| "What operations will be repeated identically?" | Identify determinism needs |
| "What outputs require validation before proceeding?" | Identify verification scripts |
| "What state needs to persist between skill invocations?" | Identify state management |
| "How will an independent check confirm the skill's outcome?" | Enable independent verification |
| "What existing scripts in the ecosystem could be reused?" | Avoid reinventing |
| "Is this map, GPS, or hybrid (see Design Selection)?" | Decide who judges and who verifies |
| "Can this skill run overnight without human intervention?" | Assess agentic capability |
| "What would break if executed manually vs scripted?" | Identify fragile operations |
| "How would another Claude instance recover from failure?" | Design error handling |

### Research Existing Scripts

Before creating new scripts, search for reusable patterns:

```bash
# Find relevant scripts in the skills ecosystem
find ~/.claude/skills -name "*.py" -path "*/scripts/*" | xargs grep -l "<keyword>"

# List all skill scripts for reference
ls ~/.claude/skills/*/scripts/

# Check specific patterns
grep -r "ValidationResult" ~/.claude/skills/*/scripts/
grep -r "argparse" ~/.claude/skills/*/scripts/
```

### Script Decision Documentation

For each identified script, document in the specification:

```xml
<script id="S1">
  <name>validate_output.py</name>
  <category>validation</category>
  <purpose>Verify generated artifacts meet quality standards</purpose>
  <rationale>Manual verification is error-prone and inconsistent</rationale>
  <reused_from>~/.claude/skills/skillforge/scripts/validate-skill.py</reused_from>
</script>
```

---

## Integration Patterns

### How Scripts Are Called from Skills

### Pattern 1: Direct Invocation

```markdown
## Phase 2: Validation

Run the validation script:

\`\`\`bash
python ~/.claude/skills/my-skill/scripts/validate_output.py <input-file>
\`\`\`

Expected output:
- Exit code 0: Validation passed
- Exit code 1: Validation failed (see stderr for details)
```

### Pattern 2: Conditional Invocation

```markdown
If generating multiple files:

\`\`\`bash
python scripts/batch_validate.py --directory output/
\`\`\`

For single file:

\`\`\`bash
python scripts/validate_single.py output/result.json
\`\`\`
```

### Pattern 3: Piped Processing

```markdown
\`\`\`bash
cat result.json | python scripts/transform.py --format yaml > result.yaml
\`\`\`
```

### Pattern 4: Subcommand Invocation

```markdown
\`\`\`bash
# Initialize project
python scripts/tracker.py init "My Project"

# Add a step
python scripts/tracker.py add-step "First milestone" --project my-project.json

# Update status
python scripts/tracker.py update step-001 --status verified
\`\`\`
```

### Script Output Standards

| Output Type | Format | Convention |
|-------------|--------|------------|
| Success | Exit code 0 | Always for success |
| Failure | Exit code 1 | General failure |
| Validation failure | Exit code 10 | Specific to validation |
| Missing arguments | Exit code 2 | Argument errors |
| Structured data | JSON to stdout | When `--json` flag used |
| Progress messages | stderr | Keep stdout clean for data |
| Error messages | stderr | Consistent with Unix convention |

### Documentation Requirements

Every script must be documented in SKILL.md:

```markdown
## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `validate_output.py` | Verify generated artifacts | `python scripts/validate_output.py <path>` |
| `generate_report.py` | Create summary report | `python scripts/generate_report.py --project <name>` |
| `tracker.py` | Track progress across sessions | `python scripts/tracker.py <command> [args]` |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General failure |
| 2 | Invalid arguments |
| 10 | Validation failure |
```

---

## Agentic Capability Checklist

Before finalizing a skill with scripts, verify:

- [ ] **Autonomous Execution:** Can the skill run without user intervention?
- [ ] **Fast-Fail and Independent Check:** Do scripts fail fast, and, where the outcome can be checked independently, does a separate postcondition check confirm it?
- [ ] **Error Recovery:** Do scripts attempt recovery before failing?
- [ ] **State Persistence:** Is progress saved across sessions?
- [ ] **Structured Output:** Do scripts output machine-readable data?
- [ ] **Documentation:** Are all scripts documented in SKILL.md?
- [ ] **Exit Codes:** Do scripts use consistent exit codes?
- [ ] **Graceful Degradation:** Do scripts handle optional dependencies?

---

## Hooks Integration

Skills can leverage hooks for automatic script invocation during tool use.

### When to Use Hooks with Scripts

| Scenario | Hook | Script Pattern |
|----------|------|----------------|
| Validate before generation | PreToolUse on Write | `validation/validate_input.py` |
| Verify after generation | PostToolUse on Write | `validation/verify_output.py` |
| Log all tool activity | PostToolUse (all) | `logging/activity_log.py` |
| Cleanup on completion | Stop | `state/cleanup.py` |

### Hook + Script Integration Pattern

**Skill frontmatter:**

```yaml
---
name: validated-generator
hooks:
  PreToolUse:
    - matcher: "Bash(python:scripts/generate*)"
      hooks:
        - type: command
          command: "python scripts/validate_params.py"
  PostToolUse:
    - matcher: "Write"
      hooks:
        - type: command
          command: "python scripts/verify_artifact.py"
---
```

Read `$TOOL_INPUT` and `$TOOL_OUTPUT` from environment variables inside the script.
Avoid interpolating these values directly in shell command strings.

**Script requirements for hook integration:**

1. Accept input via `$TOOL_INPUT` or `$TOOL_OUTPUT` environment variables
2. Exit code 0 allows tool execution to proceed
3. Exit code non-0 blocks tool execution (PreToolUse) or flags error (PostToolUse)
4. Output to stderr for error messages (stdout may be captured)

### Hook Script Template

```python
#!/usr/bin/env python3
"""
hook_validator.py - Validate tool input before execution

Called by PreToolUse hook with $TOOL_INPUT containing the tool parameters.
Exit 0 to allow, exit 1 to block.
"""

import os
import sys
import json


def validate_input(tool_input: str) -> tuple[bool, str]:
    """Validate the tool input. Returns (is_valid, reason)."""
    try:
        params = json.loads(tool_input)
        # Add validation logic here
        return True, "Input valid"
    except json.JSONDecodeError:
        return False, "Invalid JSON input"


def main():
    tool_input = os.environ.get("TOOL_INPUT", "")

    if not tool_input:
        print("Warning: No TOOL_INPUT provided", file=sys.stderr)
        sys.exit(0)  # Allow by default if no input

    is_valid, reason = validate_input(tool_input)

    if not is_valid:
        print(f"Blocked: {reason}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
```

### Agentic Capability Enhancement

Hooks enable fully autonomous skill execution:

```
WITHOUT HOOKS:
  Claude runs script → Script fails → Claude notices → Claude retries
  (Multiple tool calls, potential for missed errors)

WITH HOOKS:
  PreToolUse validates → Only valid calls proceed → PostToolUse verifies
  (Single tool call, guaranteed validation)
```

| Capability | Without Hooks | With Hooks |
|------------|---------------|------------|
| Input validation | Manual check in script | Automatic gate |
| Output verification | Separate tool call | Inline verification |
| Error handling | After-the-fact | Preventive |
| Audit trail | Custom logging | Built-in hook logging |

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Hardcoded paths | Breaks on other systems | Use `Path.home()` or arguments |
| No exit codes | Can't detect failure | Use `sys.exit(0)` / `sys.exit(1)` |
| Print-only errors | Errors lost in noise | Use `sys.stderr` |
| Required external deps | Reduces portability | Use stdlib or graceful fallback |
| No independent postcondition check | Exit 0 is trusted as success | Add a separate check of the outcome |
| Monolithic scripts | Hard to reuse | Break into focused scripts |
| No state management | Lose progress | Use JSON state files |
| Hardcoded tool versions | Breaks with updates | Abstract tool invocations |

---

## Related References

- [Script Patterns Catalog](script-patterns-catalog.md) - Standard code patterns
- [Regression Questions](regression-questions.md) - Category 7: Script questions
- [Evolution Scoring](evolution-scoring.md) - Scripts and timelessness
