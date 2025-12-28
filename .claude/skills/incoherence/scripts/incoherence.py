#!/usr/bin/env python3
"""
Incoherence Detector - Step-based incoherence detection workflow

Usage:
    # Detection phase
    python3 incoherence.py --step-number 1 --total-steps 22 --thoughts "Analyzing project X"

    # Reconciliation phase (after user fills in resolutions)
    python3 incoherence.py --step-number 14 --total-steps 22 --thoughts "Reconciling..."

DETECTION PHASE (Steps 1-13):
    Steps 1-3 (Parent): Survey, dimension selection, exploration dispatch
    Steps 4-7 (Sub-Agent): Broad sweep, coverage check, gap-fill, format findings
    Step 8 (Parent): Synthesis & candidate selection
    Step 9 (Parent): Deep-dive dispatch
    Steps 10-11 (Sub-Agent): Deep-dive exploration and formatting
    Steps 12-13 (Parent): Verdict analysis, report generation

RECONCILIATION PHASE (Steps 14-22, after user edits report):
    Step 14 (Parent): Parse report, extract resolutions, detect already-resolved
    Step 15 (Parent): Analyze targets and select agent types
    Step 16 (Parent): Plan dispatch waves, detect file conflicts
    Step 17 (Parent): Dispatch current wave of agents
    Steps 18-19 (Sub-Agent): Apply resolution, format result
    Step 20 (Parent): Collect wave results, check for next wave
    Step 21 (Parent): Update original report with resolved status
    Step 22 (Parent): Output brief reconciliation summary

Reconciliation is idempotent - can be run multiple times on the same report.
Issues are skipped if: (a) no resolution provided, or (b) already resolved.

PREREQUISITE: User must specify report filename before step 1.
"""

import argparse
import sys
import os

DIMENSION_CATALOG = """
ABSTRACT DIMENSION CATALOG
==========================

Choose dimensions from this catalog based on Step 1 info sources.

CATEGORY A: SPECIFICATION VS BEHAVIOR
  - README/docs claim X, but code does Y
  - API documentation vs actual API behavior
  - Examples in docs that don't actually work
  Source pairs: Documentation <-> Code implementation

CATEGORY B: INTERFACE CONTRACT INTEGRITY
  - Type definitions vs actual runtime values
  - Schema definitions vs validation behavior
  - Function signatures vs docstrings
  Source pairs: Type/Schema definitions <-> Runtime behavior

CATEGORY C: CROSS-REFERENCE CONSISTENCY
  - Same concept described differently in different docs
  - Numeric constants/limits stated inconsistently
  - Intra-document contradictions
  Source pairs: Document <-> Document

CATEGORY D: TEMPORAL CONSISTENCY (Staleness)
  - Outdated comments referencing removed code
  - TODO/FIXME comments for completed work
  - References to renamed/moved files
  Source pairs: Historical references <-> Current state

CATEGORY E: ERROR HANDLING CONSISTENCY
  - Documented error codes vs actual error responses
  - Exception handling docs vs throw/catch behavior
  Source pairs: Error documentation <-> Error implementation

CATEGORY F: CONFIGURATION & ENVIRONMENT
  - Documented env vars vs actual env var usage
  - Default values in docs vs defaults in code
  Source pairs: Config documentation <-> Config handling code

CATEGORY G: AMBIGUITY & UNDERSPECIFICATION
  - Vague statements that could be interpreted multiple ways
  - Missing thresholds, limits, or parameters
  - Implicit assumptions not stated explicitly
  Detection method: Ask "could two people read this differently?"

CATEGORY H: POLICY & CONVENTION COMPLIANCE
  - Architectural decisions (ADRs) violated by implementation
  - Style guide rules not followed in code
  - "We don't do X" statements violated in codebase
  Source pairs: Policy documents <-> Implementation patterns

CATEGORY I: COMPLETENESS & DOCUMENTATION GAPS
  - Public API endpoints with no documentation
  - Functions/classes with no docstrings
  - Magic values/constants without explanation
  Detection method: Find code constructs, check if docs exist

CATEGORY J: COMPOSITIONAL CONSISTENCY
  - Claims individually valid but jointly impossible
  - Numeric constraints that contradict when combined
  - Configuration values that create impossible states
  - Timing/resource constraints that cannot all be satisfied
  Detection method: Gather related claims, compute implications, check for contradiction
  Example: timeout=30s, retries=10, max_duration=60s → 30×10=300≠60

CATEGORY K: IMPLICIT CONTRACT INTEGRITY
  - Names/identifiers promise behavior the code doesn't deliver
  - Function named validateX() that doesn't actually validate
  - Error messages that misrepresent the actual error
  - Module/package names that don't match contents
  - Log messages that lie about what happened
  Detection method: Parse names semantically, infer promise, compare to behavior
  Note: LLMs are particularly susceptible to being misled by names

SELECTION RULES:
- Select ALL categories relevant to Step 1 info sources
- Typical selection is 5-8 dimensions
- G, H, I, K are especially relevant for LLM-assisted coding
- J requires cross-referencing multiple claims (more expensive)
"""


def get_step_guidance(step_number, total_steps, script_path=None):
    if script_path is None:
        script_path = os.path.abspath(__file__)

    # =========================================================================
    # DETECTION PHASE: Steps 1-9
    # =========================================================================

    if step_number == 1:
        return {
            "actions": [
                "CODEBASE SURVEY",
                "",
                "Gather MINIMAL context. Do NOT read domain-specific docs.",
                "",
                "ALLOWED: README.md (first 50 lines), CLAUDE.md, directory listing, package manifest",
                "NOT ALLOWED: Detailed docs, source code, configs, tests",
                "",
                "Identify:",
                "1. CODEBASE TYPE: library/service/CLI/framework/application",
                "2. PRIMARY LANGUAGE",
                "3. DOCUMENTATION LOCATIONS",
                "4. INFO SOURCE TYPES:",
                "   [ ] README/guides  [ ] API docs  [ ] Code comments",
                "   [ ] Type definitions  [ ] Configs  [ ] Schemas",
                "   [ ] ADRs  [ ] Style guides  [ ] CONTRIBUTING.md",
                "   [ ] Test descriptions  [ ] Error catalogs",
            ],
            "next": "Invoke step 2 with survey results in --thoughts"
        }

    if step_number == 2:
        return {
            "actions": [
                "DIMENSION SELECTION",
                "",
                "Select from catalog (A-K) based on Step 1 info sources.",
                "Do NOT read files. Do NOT create domain-specific dimensions.",
                "",
                DIMENSION_CATALOG,
                "",
                "OUTPUT: List selected dimensions with rationale.",
            ],
            "next": "Invoke step 3 with selected dimensions in --thoughts"
        }

    if step_number == 3:
        return {
            "actions": [
                "EXPLORATION DISPATCH",
                "",
                "Launch one haiku Explore agent per dimension.",
                "Launch ALL in a SINGLE message for parallelism.",
                "",
                f"SCRIPT PATH: {script_path}",
                "",
                "AGENT PROMPT TEMPLATE (copy exactly, fill placeholders):",
                "```",
                "DIMENSION EXPLORATION TASK",
                "",
                "DIMENSION: {category_letter} - {dimension_name}",
                "DESCRIPTION: {description_from_catalog}",
                "",
                "Start by invoking:",
                f"  python3 {script_path} --step-number 4 --total-steps 22 \\",
                "    --thoughts \"Dimension: {category_letter} - {dimension_name}\"",
                "```",
            ],
            "next": "After all agents complete, invoke step 8 with combined findings"
        }

    # =========================================================================
    # EXPLORATION SUB-AGENT STEPS: 4-7
    # =========================================================================

    if step_number == 4:
        return {
            "actions": [
                "BROAD SWEEP [SUB-AGENT]",
                "",
                "Cast a WIDE NET. Prioritize recall over precision.",
                "Report ANYTHING that MIGHT be incoherence. Verification comes later.",
                "",
                "Your dimension (from --thoughts) tells you what to look for.",
                "",
                "SEARCH STRATEGY:",
                "  1. Start with obvious locations (docs/, README, src/)",
                "  2. Search for keywords related to your dimension",
                "  3. Check configs, schemas, type definitions",
                "  4. Look at tests for behavioral claims",
                "",
                "FOR EACH POTENTIAL FINDING, note:",
                "  - Location A (file:line)",
                "  - Location B (file:line)",
                "  - What might conflict",
                "  - Confidence: high/medium/low (low is OK!)",
                "",
                "BIAS: Report more, not fewer. False positives are filtered later.",
                "",
                "Track which directories/files you searched.",
            ],
            "next": "Invoke step 5 with your findings and searched locations in --thoughts"
        }

    if step_number == 5:
        return {
            "actions": [
                "COVERAGE CHECK [SUB-AGENT]",
                "",
                "Review your search coverage. Identify GAPS.",
                "",
                "ASK YOURSELF:",
                "  - What directories have I NOT searched?",
                "  - What file types did I skip? (.yaml, .json, .toml, tests?)",
                "  - Are there related modules I haven't checked?",
                "  - Did I only look at obvious places?",
                "  - What would a second reviewer check that I didn't?",
                "",
                "DIVERSITY CHECK:",
                "  - Are all my findings in one directory? (bad)",
                "  - Are all my findings the same file type? (bad)",
                "  - Did I check both docs AND code? Both should have claims.",
                "",
                "OUTPUT:",
                "  1. List of gaps/unexplored areas (at least 3)",
                "  2. Specific files or patterns to search next",
            ],
            "next": "Invoke step 6 with identified gaps in --thoughts"
        }

    if step_number == 6:
        return {
            "actions": [
                "GAP-FILL EXPLORATION [SUB-AGENT]",
                "",
                "Explore the gaps identified in step 5.",
                "",
                "REQUIREMENTS:",
                "  - Search at least 3 new locations from your gap list",
                "  - Use different search strategies than before",
                "  - Look in non-obvious places (tests, examples, scripts/)",
                "",
                "ADDITIONAL TECHNIQUES:",
                "  - Search for negations ('not', 'don't', 'never', 'deprecated')",
                "  - Look for TODOs, FIXMEs, HACKs near your dimension's topic",
                "  - Check git-ignored or generated files if accessible",
                "",
                "Record any new potential incoherences found.",
                "Same format: Location A, Location B, conflict, confidence.",
            ],
            "next": "Invoke step 7 with all findings (original + new) in --thoughts"
        }

    if step_number == 7:
        return {
            "actions": [
                "FORMAT EXPLORATION FINDINGS [SUB-AGENT]",
                "",
                "Consolidate all findings from your exploration.",
                "",
                "OUTPUT FORMAT:",
                "```",
                "EXPLORATION RESULTS - DIMENSION {letter}",
                "",
                "FINDING 1:",
                "  Location A: [file:line]",
                "  Location B: [file:line]",
                "  Potential conflict: [one-line description]",
                "  Confidence: high|medium|low",
                "",
                "[repeat for each finding]",
                "",
                "TOTAL FINDINGS: N",
                "AREAS SEARCHED: [list of directories/file patterns]",
                "```",
                "",
                "Include ALL findings, even low-confidence ones.",
                "Deduplication happens in step 8.",
            ],
            "next": "Output formatted results. Sub-agent task complete."
        }

    # =========================================================================
    # DETECTION PHASE CONTINUED: Steps 8-13
    # =========================================================================

    if step_number == 8:
        return {
            "actions": [
                "SYNTHESIS & CANDIDATE SELECTION",
                "",
                "Score findings (0-10): Impact + Confidence + Specificity + Fixability",
                "Select TOP 10 candidates. Deduplicate overlapping findings.",
                "",
                "Output: C1, C2, ... with location, summary, score.",
            ],
            "next": "Invoke step 9 with selected candidates in --thoughts"
        }

    if step_number == 9:
        return {
            "actions": [
                "DEEP-DIVE DISPATCH",
                "",
                "Launch sonnet agents to verify each candidate.",
                "Sub-agents will invoke THIS SCRIPT to get their instructions.",
                "",
                f"SCRIPT PATH: {script_path}",
                "",
                "AGENT PROMPT TEMPLATE (copy exactly, fill placeholders):",
                "```",
                "DEEP-DIVE VERIFICATION TASK",
                "",
                "CANDIDATE: {id} at {location}",
                "Claimed issue: {summary}",
                "",
                "YOUR WORKFLOW:",
                "",
                "STEP A: Get exploration instructions",
                f"   python3 {script_path} --step-number 10 --total-steps 22 --thoughts \"Verifying: {{id}}\"",
                "",
                "STEP B: Follow those instructions to gather evidence",
                "",
                "STEP C: Format your findings",
                f"   python3 {script_path} --step-number 11 --total-steps 22 --thoughts \"<your findings>\"",
                "",
                "IMPORTANT: You MUST invoke step 10 before exploring, step 11 to format.",
                "```",
            ],
            "next": "After all agents complete, invoke step 12 with all verdicts"
        }

    # =========================================================================
    # DEEP-DIVE SUB-AGENT STEPS: 10-11
    # =========================================================================

    if step_number == 10:
        return {
            "actions": [
                "DEEP-DIVE EXPLORATION [SUB-AGENT]",
                "",
                "You are verifying a specific candidate. Follow this process:",
                "",
                "1. LOCATE PRIMARY SOURCE",
                "   - Navigate to exact file:line",
                "   - Read 100+ lines of context",
                "   - Identify the claim being made",
                "",
                "2. FIND CONFLICTING SOURCE",
                "   - Locate the second source",
                "   - Read its context too",
                "",
                "3. EXTRACT EVIDENCE",
                "   For EACH source: file path, line number, exact quote, claim",
                "",
                "4. ANALYZE CONFLICT",
                "   - Same thing discussed?",
                "   - Actually contradictory?",
                "   - Context resolves it?",
                "",
                "5. DETERMINE VERDICT",
                "   - TRUE_INCOHERENCE: genuinely conflicting claims",
                "   - FALSE_POSITIVE: apparent conflict resolves with context",
            ],
            "next": "When done exploring, invoke step 11 with findings in --thoughts"
        }

    if step_number == 11:
        return {
            "actions": [
                "FORMAT RESULTS [SUB-AGENT]",
                "",
                "Structure your findings. This is your FINAL OUTPUT.",
                "",
                "REQUIRED FORMAT:",
                "```",
                "VERIFICATION RESULT",
                "",
                "CANDIDATE: {id}",
                "VERDICT: TRUE_INCOHERENCE | FALSE_POSITIVE",
                "",
                "SOURCE A:",
                "  File: [path]",
                "  Line: [number]",
                "  Quote: \"[exact quote]\"",
                "  Claims: [what it asserts]",
                "",
                "SOURCE B:",
                "  File: [path]",
                "  Line: [number]",
                "  Quote: \"[exact quote]\"",
                "  Claims: [what it asserts]",
                "",
                "ANALYSIS: [why they do/don't conflict]",
                "",
                "SEVERITY: critical|high|medium|low (if TRUE)",
                "RECOMMENDATION: [fix action]",
                "```",
            ],
            "next": "Output formatted result. Sub-agent task complete."
        }

    if step_number == 12:
        return {
            "actions": [
                "VERDICT ANALYSIS",
                "",
                "Tally results from deep-dive agents:",
                "  - Total verified",
                "  - TRUE_INCOHERENCE count",
                "  - FALSE_POSITIVE count",
                "  - By severity (critical/high/medium/low)",
                "",
                "Quality check each TRUE_INCOHERENCE for exact quotes.",
            ],
            "next": "Invoke step 13 with confirmed findings"
        }

    if step_number == 13:
        return {
            "actions": [
                "REPORT GENERATION",
                "",
                "Write the incoherence report to the specified file.",
                "Include Resolution sections for user input.",
                "",
                "REPORT STRUCTURE:",
                "```markdown",
                "# Incoherence Report",
                "",
                "## Executive Summary",
                "- **Issues Found**: N confirmed incoherences",
                "- **Severity Breakdown**: Critical: N | High: N | Medium: N | Low: N",
                "- **Dimensions Analyzed**: [list]",
                "",
                "---",
                "",
                "## Issues",
                "",
                "### Issue I1: [Descriptive Title]",
                "",
                "**Type**: Contradiction | Ambiguity | Gap | Policy Violation",
                "**Severity**: critical | high | medium | low",
                "**Dimension**: [A-I category name]",
                "",
                "#### Source A",
                "**File**: `path/to/file.md`",
                "**Line**: 42",
                "```",
                "[exact quote from source]",
                "```",
                "",
                "#### Source B",
                "**File**: `path/to/code.py`",
                "**Line**: 156",
                "```",
                "[exact quote from source]",
                "```",
                "",
                "#### Analysis",
                "[Explanation of why these conflict]",
                "",
                "#### Suggestions",
                "1. [First suggestion]",
                "2. [Second suggestion if applicable]",
                "",
                "#### Resolution",
                "<!-- USER: Write your decision below. Be specific. -->",
                "",
                "<!-- /Resolution -->",
                "",
                "---",
                "",
                "[Repeat for each issue I2, I3, ...]",
                "```",
            ],
            "next": "DETECTION PHASE COMPLETE. User edits report, then runs step 14."
        }

    # =========================================================================
    # RECONCILIATION PHASE: Steps 14-22
    # =========================================================================

    if step_number == 14:
        return {
            "actions": [
                "RECONCILE PARSE",
                "",
                "Extract resolutions from the report file.",
                "",
                "PROCESS:",
                "",
                "1. Read the report file (you know the path from context)",
                "",
                "2. For each issue section (I1, I2, ...):",
                "",
                "   a. Check for Status section (#### Status)",
                "      - If contains '✅ RESOLVED' → ALREADY_RESOLVED, skip",
                "",
                "   b. Find Resolution section (between <!-- USER: and <!-- /Resolution -->)",
                "      - Extract text between markers, trim whitespace",
                "      - If empty → NO_RESOLUTION, skip",
                "      - If non-empty → TO_PROCESS",
                "",
                "OUTPUT FORMAT:",
                "",
                "```",
                "PARSED RESOLUTIONS",
                "",
                "To process:",
                "  I1: \"Use the spec value (100MB)\"",
                "  I3: \"The code is correct, update docs to match\"",
                "",
                "Skipped (already resolved):",
                "  I5",
                "",
                "Skipped (no resolution provided):",
                "  I2, I4, I6, I7",
                "```",
                "",
                "If no issues to process: RECONCILIATION COMPLETE (nothing to do).",
            ],
            "next": "Invoke step 15 with issues to process in --thoughts"
        }

    if step_number == 15:
        return {
            "actions": [
                "RECONCILE ANALYZE",
                "",
                "Determine target files and agent types for each resolution.",
                "",
                "FOR EACH ISSUE WITH A RESOLUTION:",
                "",
                "1. IDENTIFY TARGET FILE(S)",
                "   - Which file(s) need to be modified?",
                "   - Use Source A/B locations from the issue as hints",
                "   - The resolution text may specify which source to change",
                "",
                "2. DETERMINE CHANGE TYPE",
                "   - Code: .py, .js, .ts, .go, .rs, etc.",
                "   - Documentation: .md, .rst, .txt, docstrings",
                "   - Configuration: .yaml, .json, .toml, .env",
                "   - Schema: .json (JSON Schema), OpenAPI specs",
                "",
                "3. SELECT AGENT TYPE",
                "   - Code changes → Developer",
                "   - Documentation changes → Technical Writer",
                "   - Config/Schema → Developer (typically)",
                "",
                "OUTPUT FORMAT:",
                "",
                "```",
                "RESOLUTION ANALYSIS",
                "",
                "| Issue | Target File(s)          | Change Type   | Agent Type       |",
                "|-------|-------------------------|---------------|------------------|",
                "| I1    | src/uploader.py         | Code          | Developer        |",
                "| I3    | docs/config.md          | Documentation | Technical Writer |",
                "| I7    | README.md, src/client.py| Both          | See note         |",
                "",
                "NOTES:",
                "- I7 requires changes to both docs AND code. List both files.",
                "```",
            ],
            "next": "Invoke step 16 with analysis in --thoughts"
        }

    if step_number == 16:
        return {
            "actions": [
                "RECONCILE PLAN",
                "",
                "Group resolutions by file and create dispatch waves.",
                "",
                "STEP A: GROUP BY TARGET FILE",
                "",
                "List all resolutions that touch each file:",
                "",
                "```",
                "FILE GROUPS",
                "",
                "src/uploader.py:",
                "  - I1 (Developer) - \"Use the spec value\"",
                "  - I6 (Developer) - \"Add validation\"",
                "",
                "docs/config.md:",
                "  - I3 (Technical Writer) - \"Update to match code\"",
                "```",
                "",
                "STEP B: DETECT CONFLICTS",
                "",
                "For each file with multiple resolutions, check agent types:",
                "",
                "  BATCH (same agent type):",
                "    Multiple resolutions, same file, same agent type",
                "    → Dispatch ONE agent with ALL resolutions for that file",
                "",
                "  SEQUENCE (different agent types):",
                "    Multiple resolutions, same file, DIFFERENT agent types",
                "    → Must run sequentially (Wave 1, then Wave 2)",
                "    → Order is at your discretion",
                "",
                "  SINGLE:",
                "    One resolution for the file → No conflict",
                "",
                "STEP C: CREATE DISPATCH PLAN",
                "",
                "```",
                "DISPATCH PLAN",
                "",
                "WAVE 1 (parallel):",
                "  - Agent 1: Developer → src/uploader.py",
                "    Issues: I1, I6 (batched)",
                "  - Agent 2: Technical Writer → docs/config.md",
                "    Issues: I3",
                "",
                "WAVE 2 (after Wave 1):",
                "  [none]",
                "```",
            ],
            "next": "Invoke step 17 with dispatch plan in --thoughts"
        }

    if step_number == 17:
        return {
            "actions": [
                "RECONCILE DISPATCH",
                "",
                "Launch agents for the current wave.",
                "",
                "WHICH WAVE?",
                "  - First time here: dispatch Wave 1",
                "  - Returned from step 20: dispatch the next wave",
                "",
                f"SCRIPT PATH: {script_path}",
                "",
                "Use the appropriate subagent_type for each agent:",
                "  - Developer agent for code changes",
                "  - Technical Writer agent for documentation changes",
                "",
                "AGENT PROMPT TEMPLATE:",
                "```",
                "RECONCILIATION TASK",
                "",
                "TARGET FILE: {file_path}",
                "",
                "RESOLUTIONS TO APPLY:",
                "",
                "--- Issue {id} ---",
                "Type: {type}",
                "Severity: {severity}",
                "Source A: {file}:{line}",
                "Source B: {file}:{line}",
                "Analysis: {analysis}",
                "User's Resolution: {resolution_text}",
                "",
                "[Repeat for batched issues]",
                "",
                "YOUR WORKFLOW:",
                f"1. python3 {script_path} --step-number 18 --total-steps 22 \\",
                "     --thoughts \"FILE: {file_path} | ISSUES: {id_list}\"",
                "2. Apply the resolution(s)",
                f"3. python3 {script_path} --step-number 19 --total-steps 22 \\",
                "     --thoughts \"<what you did>\"",
                "4. Output your formatted result",
                "```",
                "",
                "Launch all agents for THIS WAVE in a SINGLE message (parallel).",
            ],
            "next": "After all wave agents complete, invoke step 20 with results"
        }

    # =========================================================================
    # RECONCILIATION SUB-AGENT STEPS: 18-19
    # =========================================================================

    if step_number == 18:
        return {
            "actions": [
                "RECONCILE APPLY [SUB-AGENT]",
                "",
                "Apply the user's resolution(s) to the target file.",
                "",
                "PROCESS:",
                "",
                "For EACH resolution assigned to you:",
                "",
                "1. UNDERSTAND THE RESOLUTION",
                "   - What did the user decide?",
                "   - Which source is authoritative?",
                "   - What specific changes are needed?",
                "",
                "2. LOCATE THE TARGET",
                "   - Find the exact location in the file",
                "   - Read surrounding context",
                "",
                "3. APPLY THE CHANGE",
                "   - Make the edit directly",
                "   - Be precise: match the user's intent",
                "   - Preserve surrounding context and formatting",
                "",
                "4. VERIFY",
                "   - Does the change address the incoherence?",
                "   - If batched: any conflicts between changes?",
                "",
                "BATCHED RESOLUTIONS:",
                "",
                "If you have multiple resolutions for the same file:",
                "  - Apply them in logical order",
                "  - Watch for interactions between changes",
                "  - If changes conflict, note this in output",
                "",
                "UNCLEAR RESOLUTIONS:",
                "",
                "If a resolution is genuinely unclear, do your best to interpret",
                "the user's intent. Only skip if truly impossible to apply.",
                "",
                "BIAS: Apply the resolution. Interpret charitably. Skip rarely.",
            ],
            "next": "When done, invoke step 19 with results in --thoughts"
        }

    if step_number == 19:
        return {
            "actions": [
                "RECONCILE FORMAT [SUB-AGENT]",
                "",
                "Format your reconciliation result(s).",
                "",
                "OUTPUT ONE BLOCK PER ISSUE:",
                "",
                "IF SUCCESSFULLY APPLIED:",
                "```",
                "RECONCILIATION RESULT",
                "",
                "ISSUE: {id}",
                "STATUS: RESOLVED",
                "FILE: {file_path}",
                "CHANGE: {brief one-line description}",
                "```",
                "",
                "IF COULD NOT APPLY:",
                "```",
                "RECONCILIATION RESULT",
                "",
                "ISSUE: {id}",
                "STATUS: SKIPPED",
                "REASON: {why it couldn't be applied}",
                "```",
                "",
                "FOR BATCHED ISSUES: Output one block per issue, separated by ---",
                "",
                "Keep CHANGE descriptions brief (one line, ~60 chars max).",
            ],
            "next": "Output formatted result(s). Sub-agent task complete."
        }

    if step_number == 20:
        return {
            "actions": [
                "RECONCILE COLLECT",
                "",
                "Collect results from the completed wave.",
                "",
                "STEP A: COLLECT RESULTS",
                "",
                "For each sub-agent that completed:",
                "  - Issues handled",
                "  - Status (RESOLVED or SKIPPED)",
                "  - File and change (if RESOLVED)",
                "  - Reason (if SKIPPED)",
                "",
                "```",
                "WAVE N RESULTS",
                "",
                "Agent 1 (Developer → src/uploader.py):",
                "  I1: RESOLVED - Changed MAX_FILE_SIZE to 100MB",
                "  I6: RESOLVED - Added validation",
                "",
                "Agent 2 (Technical Writer → README.md):",
                "  I3: RESOLVED - Added file size definition",
                "```",
                "",
                "STEP B: CHECK FOR NEXT WAVE",
                "",
                "Review your dispatch plan from step 16:",
                "  - More waves remaining? → Invoke step 17 for next wave",
                "  - All waves complete? → Invoke step 21 to update report",
                "",
                "OUTPUT:",
                "",
                "```",
                "COLLECTION SUMMARY",
                "",
                "Wave N complete:",
                "  - RESOLVED: I1, I3, I6",
                "  - SKIPPED: [none]",
                "",
                "Remaining waves: [list or \"none\"]",
                "```",
            ],
            "next": "If more waves: invoke step 17. Otherwise: invoke step 21."
        }

    if step_number == 21:
        return {
            "actions": [
                "RECONCILE UPDATE",
                "",
                "Update the original report file with resolved status markers.",
                "",
                "FOR EACH RESOLVED ISSUE:",
                "",
                "Add a Status section immediately after the Resolution section:",
                "",
                "```markdown",
                "#### Resolution",
                "<!-- USER: Write your decision below. Be specific. -->",
                "Use the spec value (100MB) instead of the code value.",
                "<!-- /Resolution -->",
                "",
                "#### Status",
                "✅ RESOLVED — src/uploader.py:156: Changed MAX_FILE_SIZE to 100MB",
                "```",
                "",
                "FORMAT:",
                "  #### Status",
                "  ✅ RESOLVED — {file}:{line}: {brief change description}",
                "",
                "RULES:",
                "  - Only add Status section for RESOLVED issues",
                "  - Do NOT modify issues that were SKIPPED",
                "  - Do NOT modify issues with no resolution",
                "  - Do NOT modify issues already marked resolved",
                "  - Keep change description brief (~60 chars)",
                "",
                "Save the updated report file.",
            ],
            "next": "Invoke step 22 to output summary"
        }

    if step_number >= 22:
        return {
            "actions": [
                "RECONCILE COMPLETE",
                "",
                "Output a brief structured summary to the user.",
                "",
                "FORMAT:",
                "",
                "```",
                "RECONCILIATION COMPLETE",
                "",
                "┌─────┬────────────┬─────────────────────────────────────────┐",
                "│ ID  │ Status     │ Summary                                 │",
                "├─────┼────────────┼─────────────────────────────────────────┤",
                "│ I1  │ ✅ RESOLVED │ src/uploader.py: MAX_FILE_SIZE → 100MB  │",
                "│ I2  │ ⬜ SKIPPED  │ (no resolution provided)                │",
                "│ I3  │ ✅ RESOLVED │ README.md: Added size definition        │",
                "│ I5  │ ⬜ SKIPPED  │ (already resolved)                      │",
                "│ I7  │ ⬜ SKIPPED  │ (could not apply)                       │",
                "└─────┴────────────┴─────────────────────────────────────────┘",
                "",
                "Report updated: {report_filename}",
                "```",
                "",
                "RULES:",
                "  - List ALL issues from the report (resolved + skipped)",
                "  - Use ✅ RESOLVED for successfully applied",
                "  - Use ⬜ SKIPPED with reason in parentheses",
                "  - Keep summaries brief",
                "  - Do NOT create a separate file",
            ],
            "next": "RECONCILIATION COMPLETE."
        }

    return {"actions": ["Unknown step"], "next": "Check step number"}


def main():
    parser = argparse.ArgumentParser(description="Incoherence Detector")
    parser.add_argument("--step-number", type=int, required=True)
    parser.add_argument("--total-steps", type=int, required=True)
    parser.add_argument("--thoughts", type=str, required=True)
    args = parser.parse_args()

    script_path = os.path.abspath(__file__)
    guidance = get_step_guidance(args.step_number, args.total_steps, script_path)

    # Determine agent type and phase
    # Exploration sub-agent: 4-7, Deep-dive sub-agent: 10-11
    if args.step_number in [4, 5, 6, 7, 10, 11]:
        agent_type = "SUB-AGENT"
        phase = "DETECTION"
    # Reconciliation sub-agent: 18-19
    elif args.step_number in [18, 19]:
        agent_type = "SUB-AGENT"
        phase = "RECONCILIATION"
    elif args.step_number <= 13:
        agent_type = "PARENT"
        phase = "DETECTION"
    else:
        agent_type = "PARENT"
        phase = "RECONCILIATION"

    print("=" * 70)
    print(f"INCOHERENCE DETECTOR - Step {args.step_number}/{args.total_steps}")
    print(f"[{phase}] [{agent_type}]")
    print("=" * 70)
    print()
    print("THOUGHTS:", args.thoughts[:300] + "..." if len(args.thoughts) > 300 else args.thoughts)
    print()
    print("REQUIRED ACTIONS:")
    for action in guidance["actions"]:
        print(f"  {action}")
    print()
    print("NEXT:", guidance["next"])
    print("=" * 70)


if __name__ == "__main__":
    main()
