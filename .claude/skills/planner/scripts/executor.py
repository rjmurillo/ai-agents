#!/usr/bin/env python3
"""
Plan Executor - Execute approved plans through delegation.

Seven-phase execution workflow with JIT prompt injection:
  Step 1: Execution Planning (analyze plan, detect reconciliation)
  Step 2: Reconciliation (conditional, validate existing code)
  Step 3: Milestone Execution (delegate to agents, run tests)
  Step 4: Post-Implementation QR (quality review)
  Step 5: QR Issue Resolution (conditional, fix issues)
  Step 6: Documentation (TW pass)
  Step 7: Retrospective (present summary)

Usage:
    python3 executor.py --plan-file PATH --step-number 1 --total-steps 7 --thoughts "..."
"""

import argparse
import re
import sys


def detect_reconciliation_signals(thoughts: str) -> bool:
    """Check if user's thoughts contain reconciliation triggers."""
    triggers = [
        r"\balready\s+(implemented|done|complete)",
        r"\bpartially\s+complete",
        r"\bhalfway\s+done",
        r"\bresume\b",
        r"\bcontinue\s+from\b",
        r"\bpick\s+up\s+where\b",
        r"\bcheck\s+what'?s\s+done\b",
        r"\bverify\s+existing\b",
        r"\bprior\s+work\b",
    ]
    thoughts_lower = thoughts.lower()
    return any(re.search(pattern, thoughts_lower) for pattern in triggers)


def get_step_1_guidance(plan_file: str, thoughts: str) -> dict:
    """Step 1: Execution Planning - analyze plan, detect reconciliation."""
    reconciliation_detected = detect_reconciliation_signals(thoughts)

    actions = [
        "EXECUTION PLANNING",
        "",
        f"Plan file: {plan_file}",
        "",
        "Read the plan file and analyze:",
        "  1. Count milestones and their dependencies",
        "  2. Identify file targets per milestone",
        "  3. Determine parallelization opportunities",
        "  4. Set up TodoWrite tracking for all milestones",
        "",
        "<execution_rules>",
        "",
        "RULE 0 (ABSOLUTE): You NEVER implement code yourself",
        "",
        "You coordinate and validate. You delegate code work to specialized agents.",
        "",
        "If you find yourself about to:",
        "  - Write a function -> STOP. Delegate to @agent-developer",
        "  - Fix a bug -> STOP. Delegate to @agent-debugger then @agent-developer",
        "  - Modify any source file -> STOP. Delegate to @agent-developer",
        "",
        "The ONLY code you touch: trivial fixes under 5 lines (missing imports,",
        "typos) where delegation overhead exceeds fix complexity.",
        "",
        "---",
        "",
        "RULE 1: Execution Protocol",
        "",
        "Before ANY phase:",
        "  1. Use TodoWrite to track all plan phases",
        "  2. Analyze dependencies to identify parallelizable work",
        "  3. Delegate implementation to specialized agents",
        "  4. Validate each increment before proceeding",
        "",
        "You plan HOW to execute (parallelization, sequencing). You do NOT plan",
        "WHAT to execute -- that's the plan's job.",
        "",
        "---",
        "",
        "RULE 1.5: Model Selection",
        "",
        "Agent defaults (sonnet) are calibrated for quality. You may adjust ONLY",
        "upward.",
        "",
        "  | Action               | Allowed | Rationale                        |",
        "  |----------------------|---------|----------------------------------|",
        "  | Upgrade to opus      | YES     | Challenging tasks need reasoning |",
        "  | Use default (sonnet) | YES     | Baseline for all delegations     |",
        "  | Downgrade to haiku   | NEVER   | Quality degradation unacceptable |",
        "",
        "</execution_rules>",
        "",
        "<dependency_analysis>",
        "",
        "Parallelizable when ALL conditions met:",
        "  - Different target files",
        "  - No data dependencies",
        "  - No shared state (globals, configs, resources)",
        "",
        "Sequential when ANY condition true:",
        "  - Same file modified by multiple tasks",
        "  - Task B imports or depends on Task A's output",
        "  - Shared database tables or external resources",
        "",
        "Before delegating ANY batch:",
        "  1. List tasks with their target files",
        "  2. Identify file dependencies (same file = sequential)",
        "  3. Identify data dependencies (imports = sequential)",
        "  4. Group independent tasks into parallel batches",
        "  5. Separate batches with sync points",
        "",
        "</dependency_analysis>",
        "",
        "<milestone_type_detection>",
        "",
        "Before delegating ANY milestone, identify its type from file extensions:",
        "",
        "  | Milestone Type | Recognition Signal              | Delegate To             |",
        "  |----------------|--------------------------------|-------------------------|",
        "  | Documentation  | ALL files are *.md or *.rst    | @agent-technical-writer |",
        "  | Code           | ANY file is source code        | @agent-developer        |",
        "",
        "Mixed milestones: Split delegation -- @agent-developer first (code),",
        "then @agent-technical-writer (docs) after code completes.",
        "",
        "</milestone_type_detection>",
        "",
        "<delegation_format>",
        "",
        "EVERY delegation MUST use this structure:",
        "",
        "  <delegation>",
        "    <agent>@agent-[developer|debugger|technical-writer|quality-reviewer]</agent>",
        "    <mode>[For TW/QR: plan-scrub|post-implementation|plan-review|reconciliation]</mode>",
        "    <plan_source>[Absolute path to plan file]</plan_source>",
        "    <milestone>[Milestone number and name]</milestone>",
        "    <files>[Exact file paths from milestone]</files>",
        "    <task>[Specific task description]</task>",
        "    <acceptance_criteria>",
        "      - [Criterion 1 from plan]",
        "      - [Criterion 2 from plan]",
        "    </acceptance_criteria>",
        "  </delegation>",
        "",
        "For parallel delegations, wrap multiple blocks:",
        "",
        "  <parallel_batch>",
        "    <rationale>[Why these can run in parallel]</rationale>",
        "    <sync_point>[Command to run after all complete]</sync_point>",
        "    <delegation>...</delegation>",
        "    <delegation>...</delegation>",
        "  </parallel_batch>",
        "",
        "Agent limits:",
        "  - @agent-developer: Maximum 4 parallel",
        "  - @agent-debugger: Maximum 2 parallel",
        "  - @agent-quality-reviewer: ALWAYS sequential",
        "  - @agent-technical-writer: Can parallel across independent modules",
        "",
        "</delegation_format>",
    ]

    if reconciliation_detected:
        next_step = (
            "RECONCILIATION SIGNALS DETECTED in your thoughts.\n\n"
            "Invoke step 2 to validate existing code against plan requirements:\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 2 '
            '--total-steps 7 --thoughts "Starting reconciliation..."'
        )
    else:
        next_step = (
            "No reconciliation signals detected. Proceed to milestone execution.\n\n"
            "Invoke step 3 to begin delegating milestones:\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 3 '
            '--total-steps 7 --thoughts "Analyzed plan: N milestones, '
            'parallel batches: [describe], starting execution..."'
        )

    return {
        "actions": actions,
        "next": next_step,
    }


def get_step_2_guidance(plan_file: str) -> dict:
    """Step 2: Reconciliation - validate existing code against plan."""
    return {
        "actions": [
            "RECONCILIATION PHASE",
            "",
            f"Plan file: {plan_file}",
            "",
            "Validate existing code against plan requirements BEFORE executing.",
            "",
            "<reconciliation_protocol>",
            "",
            "Delegate to @agent-quality-reviewer for each milestone:",
            "",
            "  Task for @agent-quality-reviewer:",
            "  Mode: reconciliation",
            "  Plan Source: [plan_file.md]",
            "  Milestone: [N]",
            "",
            "  Check if the acceptance criteria for Milestone [N] are ALREADY",
            "  satisfied in the current codebase. Validate REQUIREMENTS, not just",
            "  code presence.",
            "",
            "  Return: SATISFIED | NOT_SATISFIED | PARTIALLY_SATISFIED",
            "",
            "---",
            "",
            "Execution based on reconciliation result:",
            "",
            "  | Result              | Action                                    |",
            "  |---------------------|-------------------------------------------|",
            "  | SATISFIED           | Skip execution, record as already complete|",
            "  | NOT_SATISFIED       | Execute milestone normally                |",
            "  | PARTIALLY_SATISFIED | Execute only the missing parts            |",
            "",
            "---",
            "",
            "Why requirements-based (not diff-based):",
            "",
            "Checking if code from the diff exists misses critical cases:",
            "  - Code added but incorrect (doesn't meet acceptance criteria)",
            "  - Code added but incomplete (partial implementation)",
            "  - Requirements met by different code than planned (valid alternative)",
            "",
            "Checking acceptance criteria catches all of these.",
            "",
            "</reconciliation_protocol>",
        ],
        "next": (
            "After collecting reconciliation results for all milestones, "
            "invoke step 3:\n\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 3 '
            "--total-steps 7 --thoughts \"Reconciliation complete: "
            'M1: SATISFIED, M2: NOT_SATISFIED, ..."'
        ),
    }


def get_step_3_guidance(plan_file: str) -> dict:
    """Step 3: Milestone Execution - delegate to agents, run tests."""
    return {
        "actions": [
            "MILESTONE EXECUTION",
            "",
            f"Plan file: {plan_file}",
            "",
            "Execute milestones through delegation. Parallelize independent work.",
            "",
            "<error_handling>",
            "",
            "Error classification:",
            "",
            "  | Severity | Signals                          | Action                  |",
            "  |----------|----------------------------------|-------------------------|",
            "  | Critical | Segfault, data corruption        | STOP, @agent-debugger   |",
            "  | High     | Test failures, missing deps      | @agent-debugger         |",
            "  | Medium   | Type errors, lint failures       | Auto-fix, then debugger |",
            "  | Low      | Warnings, style issues           | Note and continue       |",
            "",
            "Escalation triggers -- STOP and report when:",
            "  - Fix would change fundamental approach",
            "  - Three attempted solutions failed",
            "  - Performance or safety characteristics affected",
            "  - Confidence < 80%",
            "",
            "Context anchor mismatch protocol:",
            "",
            "When @agent-developer reports context lines don't match actual code:",
            "",
            "  | Mismatch Type               | Action                         |",
            "  |-----------------------------|--------------------------------|",
            "  | Whitespace/formatting only  | Proceed with normalized match  |",
            "  | Minor variable rename       | Proceed, note in execution log |",
            "  | Code restructured           | Proceed, note deviation        |",
            "  | Context lines not found     | STOP - escalate to planner     |",
            "  | Logic fundamentally changed | STOP - escalate to planner     |",
            "",
            "</error_handling>",
            "",
            "<acceptance_testing>",
            "",
            "Run after each milestone:",
            "",
            "  # Python",
            "  pytest --strict-markers --strict-config",
            "  mypy --strict",
            "",
            "  # JavaScript/TypeScript",
            "  tsc --strict --noImplicitAny",
            "  eslint --max-warnings=0",
            "",
            "  # Go",
            "  go test -race -cover -vet=all",
            "",
            "Pass criteria: 100% tests pass, zero linter warnings.",
            "",
            "Self-consistency check (for milestones with >3 files):",
            "  1. Developer's implementation notes claim: [what was implemented]",
            "  2. Test results demonstrate: [what behavior was verified]",
            "  3. Acceptance criteria state: [what was required]",
            "",
            "All three must align. Discrepancy = investigate before proceeding.",
            "",
            "</acceptance_testing>",
        ],
        "next": (
            "CONTINUE in step 3 until ALL milestones complete:\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 3 '
            '--total-steps 7 --thoughts "Completed M1, M2. Executing M3..."'
            "\n\n"
            "When ALL milestones are complete, invoke step 4 for quality review:\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 4 '
            '--total-steps 7 --thoughts "All milestones complete. '
            'Modified files: [list]. Ready for QR."'
        ),
    }


def get_step_4_guidance(plan_file: str) -> dict:
    """Step 4: Post-Implementation QR - quality review."""
    return {
        "actions": [
            "POST-IMPLEMENTATION QUALITY REVIEW",
            "",
            f"Plan file: {plan_file}",
            "",
            "Delegate to @agent-quality-reviewer for comprehensive review.",
            "",
            "<qr_delegation>",
            "",
            "  Task for @agent-quality-reviewer:",
            "  Mode: post-implementation",
            "  Plan Source: [plan_file.md]",
            "  Files Modified: [list]",
            "  Reconciled Milestones: [list milestones that were SATISFIED]",
            "",
            "  Priority order for findings:",
            "    1. Issues in reconciled milestones (bypassed execution validation)",
            "    2. Issues in newly implemented milestones",
            "    3. Cross-cutting issues",
            "",
            "  Checklist:",
            "    - Every requirement implemented",
            "    - No unauthorized deviations",
            "    - Edge cases handled",
            "    - Performance requirements met",
            "",
            "</qr_delegation>",
            "",
            "Expected output: PASS or issues list sorted by severity.",
        ],
        "next": (
            "After QR completes:\n\n"
            "If QR returns ISSUES -> invoke step 5:\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 5 '
            '--total-steps 7 --thoughts "QR found N issues: [summary]"'
            "\n\n"
            "If QR returns PASS -> invoke step 6:\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 6 '
            '--total-steps 7 --thoughts "QR passed. Proceeding to documentation."'
        ),
    }


def get_step_5_guidance(plan_file: str) -> dict:
    """Step 5: QR Issue Resolution - present issues, collect decisions, fix."""
    return {
        "actions": [
            "QR ISSUE RESOLUTION",
            "",
            f"Plan file: {plan_file}",
            "",
            "Present issues to user, collect decisions, delegate fixes.",
            "",
            "<issue_resolution_protocol>",
            "",
            "Phase 1: Collect Decisions",
            "",
            "Sort findings by severity (critical -> high -> medium -> low).",
            "For EACH issue, present:",
            "",
            "  ## Issue [N] of [Total] ([severity])",
            "",
            "  **Category**: [production-reliability | project-conformance | structural-quality]",
            "  **File**: [affected file path]",
            "  **Location**: [function/line if applicable]",
            "",
            "  **Problem**:",
            "  [Clear description of what is wrong and why it matters]",
            "",
            "  **Evidence**:",
            "  [Specific code/behavior that demonstrates the issue]",
            "",
            "Then use AskUserQuestion with options:",
            "  - **Fix**: Delegate to @agent-developer to resolve",
            "  - **Skip**: Accept the issue as-is",
            "  - **Alternative**: User provides different approach",
            "",
            "Repeat for each issue. Do NOT execute any fixes during this phase.",
            "",
            "---",
            "",
            "Phase 2: Execute Decisions",
            "",
            "After ALL decisions are collected:",
            "",
            "  1. Summarize the decisions",
            "  2. Execute fixes:",
            "     - 'Fix' decisions: Delegate to @agent-developer",
            "     - 'Skip' decisions: Record in retrospective as accepted risk",
            "     - 'Alternative' decisions: Apply user's specified approach",
            "  3. Parallelize where possible (different files, no dependencies)",
            "",
            "</issue_resolution_protocol>",
        ],
        "next": (
            "After ALL fixes are applied, return to step 4 for re-validation:\n\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 4 '
            '--total-steps 7 --thoughts "Applied fixes for issues X, Y, Z. '
            'Re-running QR."'
            "\n\n"
            "This creates a validation loop until QR passes."
        ),
    }


def get_step_6_guidance(plan_file: str) -> dict:
    """Step 6: Documentation - TW pass for CLAUDE.md, README.md."""
    return {
        "actions": [
            "POST-IMPLEMENTATION DOCUMENTATION",
            "",
            f"Plan file: {plan_file}",
            "",
            "Delegate to @agent-technical-writer for documentation updates.",
            "",
            "<tw_delegation>",
            "",
            "Skip condition: If ALL milestones contained only documentation files",
            "(*.md/*.rst), TW already handled this during milestone execution.",
            "Proceed directly to step 7.",
            "",
            "For code-primary plans:",
            "",
            "  Task for @agent-technical-writer:",
            "  Mode: post-implementation",
            "  Plan Source: [plan_file.md]",
            "  Files Modified: [list]",
            "",
            "  Requirements:",
            "    - Create/update CLAUDE.md index entries",
            "    - Create README.md if architectural complexity warrants",
            "    - Add module-level docstrings where missing",
            "    - Verify transcribed comments are accurate",
            "",
            "</tw_delegation>",
            "",
            "<final_checklist>",
            "",
            "Execution is NOT complete until:",
            "  - [ ] All todos completed",
            "  - [ ] Quality review passed (no unresolved issues)",
            "  - [ ] Documentation delegated for ALL modified files",
            "  - [ ] Documentation tasks completed",
            "  - [ ] Self-consistency checks passed for complex milestones",
            "",
            "</final_checklist>",
        ],
        "next": (
            "After documentation is complete, invoke step 7 for retrospective:\n\n"
            f'  python3 executor.py --plan-file "{plan_file}" --step-number 7 '
            '--total-steps 7 --thoughts "Documentation complete. '
            'Generating retrospective."'
        ),
    }


def get_step_7_guidance(plan_file: str) -> dict:
    """Step 7: Retrospective - present execution summary."""
    return {
        "actions": [
            "EXECUTION RETROSPECTIVE",
            "",
            f"Plan file: {plan_file}",
            "",
            "Generate and PRESENT the retrospective to the user.",
            "Do NOT write to a file -- present it directly so the user sees it.",
            "",
            "<retrospective_format>",
            "",
            "================================================================================",
            "EXECUTION RETROSPECTIVE",
            "================================================================================",
            "",
            "Plan: [plan file path]",
            "Status: COMPLETED | BLOCKED | ABORTED",
            "",
            "## Milestone Outcomes",
            "",
            "| Milestone  | Status               | Notes                              |",
            "| ---------- | -------------------- | ---------------------------------- |",
            "| 1: [name]  | EXECUTED             | -                                  |",
            "| 2: [name]  | SKIPPED (RECONCILED) | Already satisfied before execution |",
            "| 3: [name]  | BLOCKED              | [reason]                           |",
            "",
            "## Reconciliation Summary",
            "",
            "If reconciliation was run:",
            "  - Milestones already complete: [count]",
            "  - Milestones executed: [count]",
            "  - Milestones with partial work detected: [count]",
            "",
            "If reconciliation was skipped:",
            '  - "Reconciliation skipped (no prior work indicated)"',
            "",
            "## Plan Accuracy Issues",
            "",
            "[List any problems with the plan discovered during execution]",
            "  - [file] Context anchor drift: expected X, found Y",
            "  - Milestone [N] requirements were ambiguous: [what]",
            "  - Missing dependency: [what was assumed but didn't exist]",
            "",
            'If none: "No plan accuracy issues encountered."',
            "",
            "## Deviations from Plan",
            "",
            "| Deviation      | Category        | Approved By      |",
            "| -------------- | --------------- | ---------------- |",
            "| [what changed] | Trivial / Minor | [who or 'auto']  |",
            "",
            'If none: "No deviations from plan."',
            "",
            "## Quality Review Summary",
            "",
            "  - Production reliability: [count] issues",
            "  - Project conformance: [count] issues",
            "  - Structural quality: [count] suggestions",
            "",
            "## Feedback for Future Plans",
            "",
            "[Actionable improvements based on execution experience]",
            "  - [ ] [specific suggestion]",
            "  - [ ] [specific suggestion]",
            "",
            "================================================================================",
            "",
            "</retrospective_format>",
        ],
        "next": "EXECUTION COMPLETE.\n\nPresent the retrospective to the user.",
    }


def get_step_guidance(step_number: int, plan_file: str, thoughts: str) -> dict:
    """Route to appropriate step guidance."""
    if step_number == 1:
        return get_step_1_guidance(plan_file, thoughts)
    elif step_number == 2:
        return get_step_2_guidance(plan_file)
    elif step_number == 3:
        return get_step_3_guidance(plan_file)
    elif step_number == 4:
        return get_step_4_guidance(plan_file)
    elif step_number == 5:
        return get_step_5_guidance(plan_file)
    elif step_number == 6:
        return get_step_6_guidance(plan_file)
    elif step_number == 7:
        return get_step_7_guidance(plan_file)
    else:
        return {
            "actions": [f"Unknown step {step_number}. Valid steps are 1-7."],
            "next": "Re-invoke with a valid step number.",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Plan Executor - Execute approved plans through delegation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start execution
  python3 executor.py --plan-file plans/auth.md --step-number 1 --total-steps 7 \\
    --thoughts "Execute the auth implementation plan"

  # Continue milestone execution
  python3 executor.py --plan-file plans/auth.md --step-number 3 --total-steps 7 \\
    --thoughts "Completed M1, M2. Executing M3..."

  # After QR finds issues
  python3 executor.py --plan-file plans/auth.md --step-number 5 --total-steps 7 \\
    --thoughts "QR found 2 issues: missing error handling, incorrect return type"
""",
    )

    parser.add_argument(
        "--plan-file", type=str, required=True, help="Path to the plan file to execute"
    )
    parser.add_argument("--step-number", type=int, required=True, help="Current step (1-7)")
    parser.add_argument(
        "--total-steps", type=int, required=True, help="Total steps (always 7)"
    )
    parser.add_argument(
        "--thoughts", type=str, required=True, help="Your current thinking and status"
    )

    args = parser.parse_args()

    if args.step_number < 1 or args.step_number > 7:
        print("Error: step-number must be between 1 and 7", file=sys.stderr)
        sys.exit(1)

    if args.total_steps != 7:
        print("Warning: total-steps should be 7 for executor", file=sys.stderr)

    guidance = get_step_guidance(args.step_number, args.plan_file, args.thoughts)
    is_complete = args.step_number >= 7

    step_names = {
        1: "Execution Planning",
        2: "Reconciliation",
        3: "Milestone Execution",
        4: "Post-Implementation QR",
        5: "QR Issue Resolution",
        6: "Documentation",
        7: "Retrospective",
    }

    print("=" * 80)
    print(
        f"EXECUTOR - Step {args.step_number} of 7: {step_names.get(args.step_number, 'Unknown')}"
    )
    print("=" * 80)
    print()
    print(f"STATUS: {'execution_complete' if is_complete else 'in_progress'}")
    print()
    print("YOUR THOUGHTS:")
    print(args.thoughts)
    print()

    if guidance["actions"]:
        print("GUIDANCE:")
        print()
        for action in guidance["actions"]:
            print(action)
        print()

    print("NEXT:")
    print(guidance["next"])
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
