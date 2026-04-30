#!/usr/bin/env python3
"""
Analyze Skill - Step-by-step codebase analysis with exploration and deep investigation.

Six-phase workflow:
1. EXPLORATION: Process Explore sub-agent results
2. FOCUS SELECTION: Classify investigation areas
3. INVESTIGATION PLANNING: Commit to specific files and questions
4. DEEP ANALYSIS (1-N): Progressive investigation with evidence
5. VERIFICATION: Validate completeness before synthesis
6. SYNTHESIS: Consolidate verified findings

Usage:
    python3 analyze.py --step-number 1 --total-steps 6 --thoughts "Explore found: ..."
"""

import argparse
import sys


def get_phase_name(step: int, total_steps: int) -> str:
    """Return the phase name for a given step number."""
    if step == 1:
        return "EXPLORATION"
    elif step == 2:
        return "FOCUS SELECTION"
    elif step == 3:
        return "INVESTIGATION PLANNING"
    elif step == total_steps - 1:
        return "VERIFICATION"
    elif step == total_steps:
        return "SYNTHESIS"
    else:
        return "DEEP ANALYSIS"


def get_state_requirement(step: int) -> list[str]:
    """Return state accumulation requirement for steps 2+."""
    if step < 2:
        return []

    return [
        "",
        "<state_requirement>",
        "CRITICAL: Your --thoughts for this step MUST include:",
        "",
        "1. FOCUS AREAS: Each area identified and its priority (from step 2)",
        "2. INVESTIGATION PLAN: Files and questions committed to (from step 3)",
        "3. FILES EXAMINED: Every file read with key observations",
        "4. ISSUES BY SEVERITY: All [CRITICAL]/[HIGH]/[MEDIUM]/[LOW] items",
        "5. PATTERNS: Cross-file patterns identified",
        "6. HYPOTHESES: Current theories and supporting evidence",
        "7. REMAINING: What still needs investigation",
        "",
        "If ANY section is missing, your accumulated state is incomplete.",
        "Reconstruct it before proceeding.",
        "</state_requirement>",
    ]


def get_step_guidance(step: int, total_steps: int) -> dict:
    """Return step-specific guidance and actions."""

    next_step = step + 1 if step < total_steps else None
    phase = get_phase_name(step, total_steps)
    is_final = step >= total_steps

    # Minimum steps: exploration(1) + focus(2) + planning(3) + analysis(4) + verification(5) + synthesis(6)
    min_steps = 6

    # PHASE 1: EXPLORATION
    if step == 1:
        return {
            "phase": phase,
            "step_title": "Process Exploration Results",
            "actions": [
                "STOP. Before proceeding, verify you have Explore agent results.",
                "",
                "If your --thoughts do NOT contain Explore agent output, you MUST:",
                "",
                "<exploration_delegation>",
                "Assess the scope and delegate appropriately:",
                "",
                "SINGLE CODEBASE, FOCUSED SCOPE:",
                "  - One Explore agent is sufficient",
                "  - Use Task tool with subagent_type='Explore'",
                "  - Prompt: 'Explore this repository. Report directory structure,",
                "    tech stack, entry points, main components, observed patterns.'",
                "",
                "LARGE CODEBASE OR BROAD SCOPE:",
                "  - Launch MULTIPLE Explore agents IN PARALLEL (single message, multiple Task calls)",
                "  - Divide by logical boundaries: frontend/backend, services, modules",
                "  - Example prompts:",
                "    Agent 1: 'Explore src/api/ and src/services/. Focus on API structure.'",
                "    Agent 2: 'Explore src/core/ and src/models/. Focus on domain logic.'",
                "    Agent 3: 'Explore tests/ and config/. Focus on test patterns and configuration.'",
                "",
                "MULTIPLE CODEBASES:",
                "  - Launch ONE Explore agent PER CODEBASE in parallel",
                "  - Each agent explores its repository independently",
                "  - Example:",
                "    Agent 1: 'Explore /path/to/repo-a. Report structure and patterns.'",
                "    Agent 2: 'Explore /path/to/repo-b. Report structure and patterns.'",
                "",
                "WAIT for ALL agents to complete before invoking this step again.",
                "</exploration_delegation>",
                "",
                "Only proceed below if you have concrete Explore output to process.",
                "",
                "=" * 60,
                "",
                "<exploration_processing>",
                "From the Explore agent(s) report(s), extract and document:",
                "",
                "STRUCTURE:",
                "  - Main directories and their purposes",
                "  - Where core logic lives vs. configuration vs. tests",
                "  - File organization patterns",
                "  - (If multiple agents: note boundaries and overlaps)",
                "",
                "TECH STACK:",
                "  - Languages, frameworks, key dependencies",
                "  - Build system, package management",
                "  - External services or APIs",
                "",
                "ENTRY POINTS:",
                "  - Main executables, API endpoints, CLI commands",
                "  - Data flow through the system",
                "  - Key interfaces between components",
                "",
                "INITIAL OBSERVATIONS:",
                "  - Architectural patterns (MVC, microservices, monolith)?",
                "  - Obvious code smells or areas of concern?",
                "  - Parts that seem well-structured vs. problematic?",
                "</exploration_processing>",
            ],
            "next": (
                f"Invoke step {next_step} with your processed exploration summary. "
                "Include all structure, tech stack, and initial observations in --thoughts."
            ),
        }

    # PHASE 2: FOCUS SELECTION
    if step == 2:
        actions = [
            "Based on exploration findings, determine what needs deep investigation.",
            "",
            "<focus_classification>",
            "Evaluate the codebase against each dimension. Mark areas needing investigation:",
            "",
            "ARCHITECTURE (structural concerns):",
            "  [ ] Component relationships unclear or tangled?",
            "  [ ] Dependency graph needs mapping?",
            "  [ ] Layering violations or circular dependencies?",
            "  [ ] Missing or unclear module boundaries?",
            "",
            "PERFORMANCE (efficiency concerns):",
            "  [ ] Hot paths that may be inefficient?",
            "  [ ] Database queries needing review?",
            "  [ ] Memory allocation patterns?",
            "  [ ] Concurrency or parallelism issues?",
            "",
            "SECURITY (vulnerability concerns):",
            "  [ ] Input validation gaps?",
            "  [ ] Authentication/authorization flows?",
            "  [ ] Sensitive data handling?",
            "  [ ] External API integrations?",
            "",
            "QUALITY (maintainability concerns):",
            "  [ ] Code duplication patterns?",
            "  [ ] Overly complex functions/classes?",
            "  [ ] Missing error handling?",
            "  [ ] Test coverage gaps?",
            "</focus_classification>",
            "",
            "<priority_assignment>",
            "Rank your focus areas by priority (P1 = most critical):",
            "",
            "  P1: [focus area] - [why most critical]",
            "  P2: [focus area] - [why second]",
            "  P3: [focus area] - [if applicable]",
            "",
            "Consider: security > correctness > performance > maintainability",
            "</priority_assignment>",
            "",
            "<step_estimation>",
            "Estimate total steps based on scope:",
            "",
            f"  Minimum steps: {min_steps} (exploration + focus + planning + 1 analysis + verification + synthesis)",
            "  1-2 focus areas, small codebase:  total_steps = 6-7",
            "  2-3 focus areas, medium codebase: total_steps = 7-9",
            "  3+ focus areas, large codebase:   total_steps = 9-12",
            "",
            "You can adjust this estimate as understanding grows.",
            "</step_estimation>",
        ]
        actions.extend(get_state_requirement(step))
        return {
            "phase": phase,
            "step_title": "Classify Investigation Areas",
            "actions": actions,
            "next": (
                f"Invoke step {next_step} with your prioritized focus areas and "
                "updated total_steps estimate. Next: create investigation plan."
            ),
        }

    # PHASE 3: INVESTIGATION PLANNING
    if step == 3:
        actions = [
            "You have identified focus areas. Now commit to specific investigation targets.",
            "",
            "This step creates ACCOUNTABILITY. You will verify against these commitments.",
            "",
            "<investigation_commitments>",
            "For EACH focus area (in priority order), specify:",
            "",
            "---",
            "FOCUS AREA: [name] (Priority: P1/P2/P3)",
            "",
            "Files to examine:",
            "  - path/to/file1.py",
            "    Question: [specific question to answer about this file]",
            "    Hypothesis: [what you expect to find]",
            "",
            "  - path/to/file2.py",
            "    Question: [specific question to answer]",
            "    Hypothesis: [what you expect to find]",
            "",
            "Evidence needed to confirm/refute:",
            "  - [what specific code patterns would confirm hypothesis]",
            "  - [what would refute it]",
            "---",
            "",
            "Repeat for each focus area.",
            "</investigation_commitments>",
            "",
            "<commitment_rules>",
            "This is a CONTRACT. In subsequent steps, you MUST:",
            "",
            "  1. Read every file listed (using Read tool)",
            "  2. Answer every question posed",
            "  3. Document evidence with file:line references",
            "  4. Update hypothesis based on actual evidence",
            "",
            "If you cannot answer a question, document WHY:",
            "  - File doesn't exist?",
            "  - Question was wrong?",
            "  - Need different files?",
            "",
            "Do NOT silently skip commitments.",
            "</commitment_rules>",
        ]
        actions.extend(get_state_requirement(step))
        return {
            "phase": phase,
            "step_title": "Create Investigation Plan",
            "actions": actions,
            "next": (
                f"Invoke step {next_step} with your complete investigation plan. "
                "Next: begin executing the plan with the highest priority focus area."
            ),
        }

    # PHASE 5: VERIFICATION (step N-1)
    if step == total_steps - 1:
        actions = [
            "STOP. Before synthesizing, verify your investigation is complete.",
            "",
            "<completeness_audit>",
            "Review your investigation commitments from Step 3.",
            "",
            "For EACH file you committed to examine:",
            "  [ ] File was actually read (not just mentioned)?",
            "  [ ] Specific question was answered with evidence?",
            "  [ ] Finding documented with file:line reference and quoted code?",
            "",
            "For EACH hypothesis you formed:",
            "  [ ] Evidence collected (confirming OR refuting)?",
            "  [ ] Hypothesis updated based on evidence?",
            "  [ ] If refuted, what replaced it?",
            "</completeness_audit>",
            "",
            "<gap_detection>",
            "Identify gaps in your investigation:",
            "",
            "  - Files committed but not examined?",
            "  - Focus areas declared but not investigated?",
            "  - Issues referenced without file:line evidence?",
            "  - Patterns claimed without cross-file validation?",
            "  - Questions posed but not answered?",
            "",
            "List each gap explicitly:",
            "  GAP 1: [description]",
            "  GAP 2: [description]",
            "  ...",
            "</gap_detection>",
            "",
            "<gap_resolution>",
            "If gaps exist:",
            "  1. INCREASE total_steps by number of gaps that need investigation",
            "  2. Return to DEEP ANALYSIS phase to fill gaps",
            "  3. Re-enter VERIFICATION after gaps are filled",
            "",
            "If no gaps (or gaps are acceptable):",
            "  Proceed to SYNTHESIS (next step)",
            "</gap_resolution>",
            "",
            "<evidence_quality_check>",
            "For each [CRITICAL] or [HIGH] severity finding, verify:",
            "  [ ] Has quoted code (2-5 lines)?",
            "  [ ] Has exact file:line reference?",
            "  [ ] Impact is clearly explained?",
            "  [ ] Recommended fix is actionable?",
            "",
            "Findings without evidence are UNVERIFIED. Either:",
            "  - Add evidence now, or",
            "  - Downgrade severity, or",
            "  - Mark as 'needs investigation'",
            "</evidence_quality_check>",
        ]
        actions.extend(get_state_requirement(step))
        return {
            "phase": phase,
            "step_title": "Verify Investigation Completeness",
            "actions": actions,
            "next": (
                "If gaps found: invoke earlier step to fill gaps, then return here. "
                f"If complete: invoke step {next_step} for final synthesis."
            ),
        }

    # PHASE 6: SYNTHESIS (final step)
    if is_final:
        return {
            "phase": phase,
            "step_title": "Consolidate and Recommend",
            "actions": [
                "Investigation verified. Synthesize all findings into actionable output.",
                "",
                "<final_consolidation>",
                "Organize all VERIFIED findings by severity:",
                "",
                "CRITICAL ISSUES (must address immediately):",
                "  For each:",
                "    - file:line reference",
                "    - Quoted code (2-5 lines)",
                "    - Impact description",
                "    - Recommended fix",
                "",
                "HIGH ISSUES (should address soon):",
                "  For each: file:line, description, recommended fix",
                "",
                "MEDIUM ISSUES (consider addressing):",
                "  For each: description, general guidance",
                "",
                "LOW ISSUES (nice to fix):",
                "  Summarize patterns, defer to future work",
                "</final_consolidation>",
                "",
                "<pattern_synthesis>",
                "Identify systemic patterns:",
                "",
                "  - Issues appearing across multiple files -> systemic problem",
                "  - Root causes explaining multiple symptoms",
                "  - Architectural changes that would prevent recurrence",
                "</pattern_synthesis>",
                "",
                "<recommendations>",
                "Provide prioritized action plan:",
                "",
                "IMMEDIATE (blocks other work / security risk):",
                "  1. [action with specific file:line reference]",
                "  2. [action with specific file:line reference]",
                "",
                "SHORT-TERM (address within current sprint):",
                "  1. [action with scope indication]",
                "  2. [action with scope indication]",
                "",
                "LONG-TERM (strategic improvements):",
                "  1. [architectural or process recommendation]",
                "  2. [architectural or process recommendation]",
                "</recommendations>",
                "",
                "<final_quality_check>",
                "Before presenting to user, verify:",
                "",
                "  [ ] All CRITICAL/HIGH issues have file:line + quoted code?",
                "  [ ] Recommendations are actionable, not vague?",
                "  [ ] Findings organized by impact, not discovery order?",
                "  [ ] No findings lost from earlier steps?",
                "  [ ] Patterns are supported by multiple examples?",
                "</final_quality_check>",
            ],
            "next": None,
        }

    # PHASE 4: DEEP ANALYSIS (steps 4 to N-2)
    # Calculate position within deep analysis phase
    deep_analysis_step = step - 3  # 1st, 2nd, 3rd deep analysis step
    remaining_before_verification = total_steps - 1 - step  # steps until verification

    if deep_analysis_step == 1:
        step_title = "Initial Investigation"
        focus_instruction = [
            "Execute your investigation plan from Step 3.",
            "",
            "<first_pass_protocol>",
            "For each file in your P1 (highest priority) focus area:",
            "",
            "1. READ the file using the Read tool",
            "2. ANSWER the specific question you committed to",
            "3. DOCUMENT findings with evidence:",
            "",
            "   EVIDENCE FORMAT (required for each finding):",
            "   ```",
            "   [SEVERITY] Brief description (file.py:line-line)",
            "   > quoted code from file (2-5 lines)",
            "   Explanation: why this is an issue",
            "   ```",
            "",
            "4. UPDATE your hypothesis based on what you found",
            "   - Confirmed? Document supporting evidence",
            "   - Refuted? Document what you found instead",
            "   - Inconclusive? Note what else you need to check",
            "</first_pass_protocol>",
            "",
            "Findings without quoted code are UNVERIFIED.",
        ]
    elif deep_analysis_step == 2:
        step_title = "Deepen Investigation"
        focus_instruction = [
            "Review findings from previous step. Go deeper.",
            "",
            "<second_pass_protocol>",
            "For each issue found in the previous step:",
            "",
            "1. TRACE to root cause",
            "   - Why does this issue exist?",
            "   - What allowed it to be introduced?",
            "   - Are there related issues in connected files?",
            "",
            "2. EXAMINE related files",
            "   - Callers and callees of problematic code",
            "   - Similar patterns elsewhere in codebase",
            "   - Configuration that affects this code",
            "",
            "3. LOOK for patterns",
            "   - Same issue in multiple places? -> Systemic problem",
            "   - One-off issue? -> Localized fix",
            "",
            "4. MOVE to P2 focus area if P1 is sufficiently investigated",
            "</second_pass_protocol>",
            "",
            "Continue documenting with file:line + quoted code.",
        ]
    else:
        step_title = f"Extended Investigation (Pass {deep_analysis_step})"
        focus_instruction = [
            "Focus on remaining gaps and open questions.",
            "",
            "<extended_investigation_protocol>",
            "Review your accumulated state. Address:",
            "",
            "1. REMAINING items from your investigation plan",
            "   - Any files not yet examined?",
            "   - Any questions not yet answered?",
            "",
            "2. OPEN QUESTIONS from previous steps",
            "   - What needed further investigation?",
            "   - What dependencies weren't clear?",
            "",
            "3. PATTERN VALIDATION",
            "   - Cross-file patterns claimed but not verified?",
            "   - Need more examples to confirm systemic issues?",
            "",
            "4. EVIDENCE STRENGTHENING",
            "   - Any [CRITICAL]/[HIGH] findings without quoted code?",
            "   - Any claims without file:line references?",
            "</extended_investigation_protocol>",
            "",
            "If investigation is complete, reduce total_steps to reach verification.",
        ]

    actions = focus_instruction + [
        "",
        "<scope_check>",
        "After this step's investigation:",
        "",
        f"  Remaining steps before verification: {remaining_before_verification}",
        "",
        "  - Discovered more complexity? -> INCREASE total_steps",
        "  - Remaining scope smaller than expected? -> DECREASE total_steps",
        "  - All focus areas sufficiently covered? -> Set next step = total_steps - 1 (verification)",
        "</scope_check>",
    ]
    actions.extend(get_state_requirement(step))

    return {
        "phase": phase,
        "step_title": step_title,
        "actions": actions,
        "next": (
            f"Invoke step {next_step}. "
            f"{remaining_before_verification} step(s) before verification. "
            "Include ALL accumulated findings in --thoughts. "
            "Adjust total_steps if scope changed."
        ),
    }


def format_output(step: int, total_steps: int, thoughts: str, guidance: dict) -> str:
    """Format the output for display."""
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append(f"ANALYZE - Step {step}/{total_steps}: {guidance['step_title']}")
    lines.append(f"Phase: {guidance['phase']}")
    lines.append("=" * 70)
    lines.append("")

    # Status
    is_final = step >= total_steps
    is_verification = step == total_steps - 1
    if is_final:
        status = "analysis_complete"
    elif is_verification:
        status = "verification_required"
    else:
        status = "in_progress"
    lines.append(f"STATUS: {status}")
    lines.append("")

    # Current thoughts summary (truncated for display)
    lines.append("YOUR ACCUMULATED STATE:")
    if len(thoughts) > 600:
        lines.append(thoughts[:600] + "...")
        lines.append("[truncated - full state in --thoughts]")
    else:
        lines.append(thoughts)
    lines.append("")

    # Actions
    lines.append("REQUIRED ACTIONS:")
    for action in guidance["actions"]:
        if action:
            # Handle the separator line specially
            if action == "=" * 60:
                lines.append("  " + action)
            else:
                lines.append(f"  {action}")
        else:
            lines.append("")
    lines.append("")

    # Next step or completion
    if guidance["next"]:
        lines.append("NEXT:")
        lines.append(guidance["next"])
    else:
        lines.append("WORKFLOW COMPLETE")
        lines.append("")
        lines.append("Present your consolidated findings to the user:")
        lines.append("  - Organized by severity (CRITICAL -> LOW)")
        lines.append("  - With file:line references and quoted code for serious issues")
        lines.append("  - With actionable recommendations for each category")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Skill - Systematic codebase analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow Phases:
  Step 1: EXPLORATION         - Process Explore agent results
  Step 2: FOCUS SELECTION     - Classify investigation areas
  Step 3: INVESTIGATION PLAN  - Commit to specific files and questions
  Step 4+: DEEP ANALYSIS      - Progressive investigation with evidence
  Step N-1: VERIFICATION      - Validate completeness before synthesis
  Step N: SYNTHESIS           - Consolidate verified findings

Examples:
  # Step 1: After Explore agent returns
  python3 analyze.py --step-number 1 --total-steps 6 \\
    --thoughts "Explore found: Python web app, Flask, SQLAlchemy..."

  # Step 2: Focus selection
  python3 analyze.py --step-number 2 --total-steps 7 \\
    --thoughts "Structure: src/, tests/. Focus: security (P1), quality (P2)..."

  # Step 3: Investigation planning
  python3 analyze.py --step-number 3 --total-steps 7 \\
    --thoughts "P1 Security: auth/login.py (Q: input validation?), ..."

  # Step 4: Initial investigation
  python3 analyze.py --step-number 4 --total-steps 7 \\
    --thoughts "FILES: auth/login.py read. [CRITICAL] SQL injection at :45..."

  # Step 5: Deepen investigation
  python3 analyze.py --step-number 5 --total-steps 7 \\
    --thoughts "[Previous state] + traced to db/queries.py, pattern in 3 files..."

  # Step 6: Verification
  python3 analyze.py --step-number 6 --total-steps 7 \\
    --thoughts "[All findings] Checking: all files read, all questions answered..."

  # Step 7: Synthesis
  python3 analyze.py --step-number 7 --total-steps 7 \\
    --thoughts "[Verified findings] Ready for consolidation..."
"""
    )

    parser.add_argument(
        "--step-number",
        type=int,
        required=True,
        help="Current step number (starts at 1)",
    )
    parser.add_argument(
        "--total-steps",
        type=int,
        required=True,
        help="Estimated total steps (adjust as understanding grows)",
    )
    parser.add_argument(
        "--thoughts",
        type=str,
        required=True,
        help="Accumulated findings, evidence, and file references",
    )

    args = parser.parse_args()

    # Validate inputs
    if args.step_number < 1:
        print("ERROR: step-number must be >= 1", file=sys.stderr)
        sys.exit(1)

    if args.total_steps < 6:
        print("ERROR: total-steps must be >= 6 (minimum workflow)", file=sys.stderr)
        sys.exit(1)

    if args.total_steps < args.step_number:
        print("ERROR: total-steps must be >= step-number", file=sys.stderr)
        sys.exit(1)

    # Get guidance for current step
    guidance = get_step_guidance(args.step_number, args.total_steps)

    # Print formatted output
    print(format_output(args.step_number, args.total_steps, args.thoughts, guidance))


if __name__ == "__main__":
    main()
