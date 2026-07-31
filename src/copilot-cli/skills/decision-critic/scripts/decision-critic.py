#!/usr/bin/env python3
"""
Decision Critic - Step-by-step prompt injection for structured decision criticism.

Grounded in:
- Chain-of-Verification (Dhuliawala et al., 2023)
- Self-Consistency (Wang et al., 2023)
- Multi-Expert Prompting (Wang et al., 2024)
"""

import argparse
import sys
from typing import Optional


def get_phase_name(step: int) -> str:
    """Return the phase name for a given step number."""
    if step <= 2:
        return "DECOMPOSITION"
    elif step <= 4:
        return "VERIFICATION"
    elif step <= 6:
        return "CHALLENGE"
    else:
        return "SYNTHESIS"


def get_step_guidance(step: int, total_steps: int, decision: Optional[str], context: Optional[str]) -> dict:
    """Return step-specific guidance and actions."""

    next_step = step + 1 if step < total_steps else None
    phase = get_phase_name(step)

    # Common state requirement for steps 2+
    state_requirement = (
        "CONTEXT REQUIREMENT: Your --thoughts from this step must include ALL IDs, "
        "classifications, and status markers from previous steps. This accumulated "
        "state is essential for workflow continuity."
    )

    # DECOMPOSITION PHASE
    if step == 1:
        return {
            "phase": phase,
            "step_title": "Extract Structure",
            "actions": [
                "You are a structured decision critic. Your task is to decompose this "
                "decision into its constituent parts so each can be independently verified "
                "or challenged. This analysis is critical to the quality of the entire workflow.",
                "",
                "Extract and assign stable IDs that will persist through ALL subsequent steps:",
                "",
                "CLAIMS [C1, C2, ...] - Factual assertions (3-7 items)",
                "  What facts does this decision assume to be true?",
                "  What cause-effect relationships does it depend on?",
                "",
                "ASSUMPTIONS [A1, A2, ...] - Unstated beliefs (2-5 items)",
                "  What is implied but not explicitly stated?",
                "  What would someone unfamiliar with the context not know?",
                "",
                "CONSTRAINTS [K1, K2, ...] - Hard boundaries (1-4 items)",
                "  What technical limitations exist?",
                "  What organizational/timeline constraints apply?",
                "",
                "JUDGMENTS [J1, J2, ...] - Subjective tradeoffs (1-3 items)",
                "  Where are values being weighed against each other?",
                "  What 'it depends' decisions were made?",
                "",
                "OUTPUT FORMAT:",
                "  C1: <claim text>",
                "  C2: <claim text>",
                "  A1: <assumption text>",
                "  K1: <constraint text>",
                "  J1: <judgment text>",
                "",
                "These IDs will be referenced in ALL subsequent steps. Be thorough but focused.",
            ],
            "next": f"Step {next_step}: Classify each item's verifiability.",
            "academic_note": None,
        }

    if step == 2:
        return {
            "phase": phase,
            "step_title": "Classify Verifiability",
            "actions": [
                "You are a structured decision critic continuing your analysis.",
                "",
                "Classify each item from Step 1. Retain original IDs and add a verifiability tag.",
                "",
                "CLASSIFICATIONS:",
                "",
                "  [V] VERIFIABLE - Can be checked against evidence or tested",
                "      Examples: \"API supports 1000 RPS\" (testable), \"Library X has feature Y\" (checkable)",
                "",
                "  [J] JUDGMENT - Subjective tradeoff with no objectively correct answer",
                "      Examples: \"Simplicity is more important than flexibility\", \"Risk is acceptable\"",
                "",
                "  [C] CONSTRAINT - Given condition, accepted as fixed for this decision",
                "      Examples: \"Budget is $50K\", \"Must launch by Q2\", \"Team has 3 engineers\"",
                "",
                "EDGE CASE RULE: When an item could fit multiple categories, prefer [V] over [J] over [C].",
                "Rationale: Verifiable items can be checked; judgments can be debated; constraints are given.",
                "",
                "Example edge case:",
                "  \"The team can deliver in 4 weeks\" - Could be [J] (judgment about capacity) or [V] (checkable",
                "  against past velocity). Choose [V] because it CAN be verified against evidence.",
                "",
                "OUTPUT FORMAT (preserve original IDs):",
                "  C1 [V]: <claim text>",
                "  C2 [J]: <claim text>",
                "  A1 [V]: <assumption text>",
                "  K1 [C]: <constraint text>",
                "",
                "COUNT: State how many [V] items require verification in the next phase.",
                "",
                state_requirement,
            ],
            "next": f"Step {next_step}: Generate verification questions for [V] items.",
            "academic_note": None,
        }

    # VERIFICATION PHASE
    if step == 3:
        return {
            "phase": phase,
            "step_title": "Generate Verification Questions",
            "actions": [
                "You are a structured decision critic. This step is crucial for catching errors.",
                "",
                "For each [V] item from Step 2, generate 1-3 verification questions.",
                "",
                "CRITERIA FOR GOOD QUESTIONS:",
                "  - Specific and independently answerable",
                "  - Designed to reveal if the claim is FALSE (falsification focus)",
                "  - Do not assume the claim is true in the question itself",
                "  - Each question should test a different aspect of the claim",
                "",
                "QUESTION BOUNDS:",
                "  - Simple claims: 1 question",
                "  - Moderate claims: 2 questions",
                "  - Complex claims with multiple parts: 3 questions maximum",
                "",
                "OUTPUT FORMAT:",
                "  C1 [V]: <claim text>",
                "    Q1: <verification question>",
                "    Q2: <verification question>",
                "  A1 [V]: <assumption text>",
                "    Q1: <verification question>",
                "",
                "EXAMPLE:",
                "  C1 [V]: Retrying failed requests creates race condition risk",
                "    Q1: Can a retry succeed after another request has already written?",
                "    Q2: What ordering guarantees exist between concurrent requests?",
                "",
                state_requirement,
            ],
            "next": f"Step {next_step}: Answer questions with factored verification.",
            "academic_note": (
                "Chain-of-Verification (Dhuliawala et al., 2023): \"Plan verification questions "
                "to check its work, and then systematically answer those questions.\""
            ),
        }

    if step == 4:
        return {
            "phase": phase,
            "step_title": "Factored Verification",
            "actions": [
                "You are a structured decision critic. This verification step is the most important "
                "in the entire workflow. Your accuracy here directly determines verdict quality. "
                "Take your time and be rigorous.",
                "",
                "Answer each verification question INDEPENDENTLY.",
                "",
                "EPISTEMIC BOUNDARY (critical for avoiding confirmation bias):",
                "",
                "  Answer using ONLY:",
                "    (a) Established domain knowledge - facts you would find in documentation,",
                "        textbooks, or widely-accepted technical references",
                "    (b) Stated constraints - information explicitly provided in the decision context",
                "    (c) Logical inference - deductions from first principles that would hold",
                "        regardless of whether this specific decision is correct",
                "",
                "  Do NOT:",
                "    - Assume the decision is correct and work backward",
                "    - Assume the decision is incorrect and seek to disprove",
                "    - Reference whether the claim 'should' be true given the decision",
                "",
                "SEPARATE your answer from its implication:",
                "  - ANSWER: The factual response to the question (evidence-based)",
                "  - IMPLICATION: What this means for the original claim (judgment)",
                "",
                "Then mark each [V] item:",
                "  VERIFIED - Answers are consistent with the claim",
                "  FAILED - Answers reveal inconsistency, error, or contradiction",
                "  UNCERTAIN - Insufficient evidence; state what additional information would resolve",
                "",
                "OUTPUT FORMAT:",
                "  C1 [V]: <claim text>",
                "    Q1: <question>",
                "      Answer: <factual answer based on epistemic boundary>",
                "      Implication: <what this means for the claim>",
                "    Status: VERIFIED | FAILED | UNCERTAIN",
                "    Rationale: <one sentence explaining the status>",
                "",
                state_requirement,
            ],
            "next": f"Step {next_step}: Begin challenge phase with adversarial analysis.",
            "academic_note": (
                "Chain-of-Verification: \"Factored variants which separate out verification steps, "
                "in terms of which context is attended to, give further performance gains.\""
            ),
        }

    # CHALLENGE PHASE
    if step == 5:
        return {
            "phase": phase,
            "step_title": "Contrarian Perspective",
            "actions": [
                "You are a structured decision critic shifting to adversarial analysis.",
                "",
                "Your task: Generate the STRONGEST possible argument AGAINST the decision.",
                "",
                "START FROM VERIFICATION RESULTS:",
                "  - FAILED items are direct ammunition - the decision rests on false premises",
                "  - UNCERTAIN items are attack vectors - unverified assumptions create risk",
                "  - Even VERIFIED items may have hidden dependencies worth probing",
                "",
                "STEEL-MANNING: Present the opposition's BEST case, not a strawman.",
                "Ask: What would a thoughtful, well-informed critic with domain expertise say?",
                "Make the argument as strong as you can, even if you personally disagree.",
                "",
                "ATTACK VECTORS TO EXPLORE:",
                "  - What could go wrong that wasn't considered?",
                "  - What alternatives were dismissed too quickly?",
                "  - What second-order effects were missed?",
                "  - What happens if key assumptions change?",
                "  - Who would disagree, and why might they be right?",
                "",
                "OUTPUT FORMAT:",
                "",
                "CONTRARIAN POSITION: <one-sentence summary of the opposition's stance>",
                "",
                "ARGUMENT:",
                "<Present the strongest 2-3 paragraph case against the decision.",
                " Reference specific item IDs (C1, A2, etc.) where applicable.",
                " Build from verification failures if any exist.>",
                "",
                "KEY RISKS:",
                "- <Risk 1 with item ID reference if applicable>",
                "- <Risk 2>",
                "- <Risk 3>",
                "",
                state_requirement,
            ],
            "next": f"Step {next_step}: Explore alternative problem framing.",
            "academic_note": (
                "Multi-Expert Prompting (Wang et al., 2024): \"Integrating multiple experts' "
                "perspectives catches blind spots in reasoning.\""
            ),
        }

    if step == 6:
        return {
            "phase": phase,
            "step_title": "Alternative Framing",
            "actions": [
                "You are a structured decision critic examining problem formulation.",
                "",
                "PURPOSE: Step 5 challenged the SOLUTION. This step challenges the PROBLEM STATEMENT.",
                "Goal: Reveal hidden assumptions baked into how the problem was originally framed.",
                "",
                "Set aside the proposed solution temporarily. Ask:",
                "  'If I approached this problem fresh, how might I state it differently?'",
                "",
                "REFRAMING VECTORS:",
                "  - Is this the right problem to solve, or a symptom of a deeper issue?",
                "  - What would a different stakeholder (user, ops, security) prioritize?",
                "  - What if the constraints (K items) were different or negotiable?",
                "  - Is there a simpler formulation that dissolves the tradeoffs?",
                "  - What objectives might be missing from the original framing?",
                "",
                "OUTPUT FORMAT:",
                "",
                "ALTERNATIVE FRAMING: <one-sentence restatement of the problem>",
                "",
                "WHAT THIS FRAMING EMPHASIZES:",
                "<Describe what becomes important under this new framing that wasn't",
                " prominent in the original.>",
                "",
                "HIDDEN ASSUMPTIONS REVEALED:",
                "<What did the original problem statement take for granted?",
                " Reference specific items (C, A, K, J) where the assumption appears.>",
                "",
                "IMPLICATION FOR DECISION:",
                "<Does this reframing strengthen, weaken, or redirect the proposed decision?>",
                "",
                state_requirement,
            ],
            "next": f"Step {next_step}: Synthesize findings into verdict.",
            "academic_note": None,
        }

    # SYNTHESIS PHASE
    if step == 7:
        return {
            "phase": phase,
            "step_title": "Synthesis and Verdict",
            "actions": [
                "You are a structured decision critic delivering your final assessment.",
                "This verdict will guide real decisions. Be confident in your analysis and precise "
                "in your recommendation.",
                "",
                "VERDICT RUBRIC:",
                "",
                "  ESCALATE when ANY of these apply:",
                "    - Any FAILED item involves safety, security, or compliance",
                "    - Any UNCERTAIN item is critical AND cannot be cheaply verified",
                "    - The alternative framing reveals the problem itself is wrong",
                "",
                "  REVISE when ANY of these apply:",
                "    - Any FAILED item on a core claim (not peripheral)",
                "    - Multiple UNCERTAIN items on feasibility, effort, or impact",
                "    - Challenge phase revealed unaddressed gaps that change the calculus",
                "",
                "  STAND when ALL of these apply:",
                "    - No FAILED items on core claims",
                "    - UNCERTAIN items are explicitly acknowledged as accepted risks",
                "    - Challenges from Steps 5-6 are addressable within the current approach",
                "",
                "BORDERLINE CASES:",
                "  - When between STAND and REVISE: favor REVISE (cheaper to refine than to fail)",
                "  - When between REVISE and ESCALATE: state both options with conditions",
                "",
                "OUTPUT FORMAT:",
                "",
                "VERDICT: [STAND | REVISE | ESCALATE]",
                "",
                "VERIFICATION SUMMARY:",
                "  Verified: <list IDs>",
                "  Failed: <list IDs with one-line explanation each>",
                "  Uncertain: <list IDs with what would resolve each>",
                "",
                "CHALLENGE ASSESSMENT:",
                "  Strongest challenge: <one-sentence summary from Step 5>",
                "  Alternative framing insight: <one-sentence summary from Step 6>",
                "  Response: <how the decision addresses or fails to address these>",
                "",
                "RECOMMENDATION:",
                "  <Specific next action. If ESCALATE, specify to whom/what forum.",
                "   If REVISE, specify which items need rework. If STAND, note accepted risks.>",
            ],
            "next": None,
            "academic_note": (
                "Self-Consistency (Wang et al., 2023): \"Correct reasoning processes tend to "
                "have greater agreement in their final answer than incorrect processes.\""
            ),
        }

    return {
        "phase": "UNKNOWN",
        "step_title": "Unknown Step",
        "actions": ["Invalid step number."],
        "next": None,
        "academic_note": None,
    }


def format_output(step: int, total_steps: int, guidance: dict) -> str:
    """Format the output for display."""
    lines = []

    # Header
    lines.append(f"DECISION CRITIC - Step {step}/{total_steps}: {guidance['step_title']}")
    lines.append(f"Phase: {guidance['phase']}")
    lines.append("")

    # Actions
    for action in guidance["actions"]:
        lines.append(action)
    lines.append("")

    # Academic note if present
    if guidance.get("academic_note"):
        lines.append(f"[{guidance['academic_note']}]")
        lines.append("")

    # Next step or completion
    if guidance["next"]:
        lines.append(f"NEXT: {guidance['next']}")
    else:
        lines.append("WORKFLOW COMPLETE - Present verdict to user.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Decision Critic - Structured decision criticism workflow"
    )
    parser.add_argument(
        "--step-number",
        type=int,
        required=True,
        help="Current step number (1-7)",
    )
    parser.add_argument(
        "--total-steps",
        type=int,
        required=True,
        help="Total steps in workflow (always 7)",
    )
    parser.add_argument(
        "--decision",
        type=str,
        help="The decision being criticized (required for step 1)",
    )
    parser.add_argument(
        "--context",
        type=str,
        help="Relevant constraints and background (required for step 1)",
    )
    parser.add_argument(
        "--thoughts",
        type=str,
        required=True,
        help="Your analysis, findings, and progress from previous steps",
    )

    args = parser.parse_args()

    # Validate step number
    if args.step_number < 1 or args.step_number > 7:
        print("ERROR: step-number must be between 1 and 7", file=sys.stderr)
        sys.exit(1)

    # Validate step 1 requirements
    if args.step_number == 1:
        if not args.decision:
            print("ERROR: --decision is required for step 1", file=sys.stderr)
            sys.exit(1)

    # Get guidance for current step
    guidance = get_step_guidance(
        args.step_number,
        args.total_steps,
        args.decision,
        args.context,
    )

    # Print decision context on step 1
    if args.step_number == 1:
        print("DECISION UNDER REVIEW:")
        print(args.decision)
        if args.context:
            print("")
            print("CONTEXT:")
            print(args.context)
        print("")

    # Print formatted output
    print(format_output(args.step_number, args.total_steps, guidance))


if __name__ == "__main__":
    main()
