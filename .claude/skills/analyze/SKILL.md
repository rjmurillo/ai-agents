---
name: analyze
version: 1.0.0
model: claude-sonnet-4-5
description: Analyze codebase architecture, security posture, or code quality through
  guided multi-step investigation. Use when performing architecture reviews, security
  assessments, quality evaluations, or deep technical investigations. Produces
  prioritized findings with evidence.
license: MIT
---

# Analyze Skill

When this skill activates, IMMEDIATELY invoke the script. The script IS the workflow.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `analyze the auth system` | analyze.py with security + architecture focus |
| `review code quality in src/` | analyze.py with quality focus |
| `security assessment of API layer` | analyze.py with security focus |
| `architecture review` | analyze.py with architecture focus |
| `find code smells in parser` | analyze.py with quality focus |

---

## When to Use

Use this skill when:

- A broad investigation is needed across multiple files or components
- The analysis requires structured multi-step exploration
- Findings need prioritization by severity and evidence

Use direct code reading instead when:

- Checking a single file or function
- The question has a known, specific location
- A quick grep or symbol search answers the question

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Exploring the codebase before invoking the script | Script orchestrates exploration order | Run step 1 immediately, let script direct you |
| Skipping the Explore agent delegation | Misses broad codebase context | Follow step 1 REQUIRED ACTIONS to delegate |
| Passing empty thoughts to later steps | Loses accumulated context | Include all findings from previous steps |
| Reducing total-steps below 6 | Skips verification and synthesis | Keep minimum 6, increase as script directs |
| Reporting findings without file:line evidence | Unverifiable claims | Always cite specific locations |

---

## Verification

After execution:

- [ ] All priority areas investigated with file-level evidence
- [ ] Findings include severity classification (critical/high/medium/low)
- [ ] Each finding has specific file:line references
- [ ] Synthesis step completed with prioritized recommendations
- [ ] No investigation areas left unexplored from the plan

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/analyze.py` | Multi-step guided analysis with exploration, investigation, and synthesis |

## Invocation

```bash
python3 scripts/analyze.py \
  --step-number 1 \
  --total-steps 6 \
  --thoughts "Starting analysis. User request: <describe what user asked to analyze>"
```

| Argument        | Required | Description                               |
| --------------- | -------- | ----------------------------------------- |
| `--step-number` | Yes      | Current step (starts at 1)                |
| `--total-steps` | Yes      | Minimum 6; adjust as script instructs     |
| `--thoughts`    | Yes      | Accumulated state from all previous steps |

## Process

The script outputs REQUIRED ACTIONS at each step. Follow them exactly.

```text
Step 1: EXPLORATION         - Script tells you to delegate to Explore agent
Step 2: FOCUS SELECTION     - Classify areas, assign priorities
Step 3: INVESTIGATION PLAN  - Commit to specific files and questions
Step 4+: DEEP ANALYSIS      - Progressive investigation with evidence
Step N-1: VERIFICATION      - Validate completeness
Step N: SYNTHESIS           - Consolidate findings
```

Do NOT try to follow this workflow manually. Run the script and follow its output.

## Example Sequence

```bash
# Step 1: Start - script will instruct you to explore first
python3 scripts/analyze.py --step-number 1 --total-steps 6 \
  --thoughts "Starting analysis of auth system"

# [Follow REQUIRED ACTIONS from output - delegate to Explore agent]

# Step 1 again with explore results
python3 scripts/analyze.py --step-number 1 --total-steps 6 \
  --thoughts "Explore found: Flask app, SQLAlchemy, auth/ dir..."

# Step 2+: Continue following script output
python3 scripts/analyze.py --step-number 2 --total-steps 7 \
  --thoughts "[accumulated state from step 1] Focus: security P1, quality P2"
```
