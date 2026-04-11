---
name: analyze
version: 1.1.0
model: claude-sonnet-4-5
description: Systematic multi-step codebase analysis producing prioritized findings with file-line evidence. Covers architecture reviews, security assessments, and code quality evaluations through guided exploration, investigation planning, and synthesis.
license: MIT
user-invocable: true
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Task
---

# Analyze Skill

When this skill activates, IMMEDIATELY invoke the script. The script IS the workflow. Do NOT explore the codebase first.

## Triggers

- `analyze this codebase` - architecture and quality focus
- `review code quality` - quality focus
- `run security assessment` - security focus
- `architecture review of this system` - architecture focus
- `find code smells` - quality focus

## Quick Reference

| Input | Focus | Minimum Steps |
|-------|-------|---------------|
| Architecture review | Structure, dependencies, layering | 6 |
| Security assessment | Input validation, auth, data handling | 7-9 |
| Code quality | Duplication, complexity, test gaps | 6-7 |
| Broad investigation | All dimensions | 9-12 |

---

## Security

When using the `Bash` tool, all arguments containing variable or user-provided input **MUST** be quoted to prevent command injection vulnerabilities. Refer to the repository style guide on Command Injection Prevention (CWE-78).

**WRONG**: `grep $PATTERN /some/path`
**CORRECT**: `grep -- "$PATTERN" /some/path`

---

## When to Use

Use this skill when:

- Investigation spans multiple files or components
- Analysis requires structured multi-step exploration
- Findings need prioritization by severity with file:line evidence

Use direct code reading instead when:

- Checking a single file or function
- The question has a known, specific location
- A quick grep or symbol search answers the question

---

## References

- [Working with Legacy Code](references/design-legacy-code.md) - Bottom-up refactoring through the Software Hierarchy of Needs
- [OODA Loop](references/strategy-ooda-loop.md) - Decision-making framework mapped to analyze phases
- [Tell, Don't Ask](references/design-tell-dont-ask.md) - Detect feature envy and getter chain code smells
- [Boy Scout Rule](references/quality-boy-scout-rule.md) - Scope improvement recommendations by size
- [Observability Pillars](references/reliability-observability-pillars.md) - Logs, metrics, traces for investigation methodology
- [Engineering Complexity Tiers](references/engineering-complexity-tiers.md) - Classify components by tier, evaluate pattern appropriateness
- [Agent Architecture Patterns](references/agent-architecture-patterns.md) - Skill budget rule, structured prompt design, diagnostic signals for agent reliability
- [Context Budget Management](references/context-budget-management.md) - Context flood prevention, Think in Code principle, hook architecture for session continuity

---

## Scripts

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `scripts/analyze.py` | Multi-step guided analysis with exploration, investigation, and synthesis | 0=success, 1=invalid input |

### Invocation

```bash
python3 scripts/analyze.py \
  --step-number 1 \
  --total-steps 6 \
  --thoughts "Starting analysis. User request: <describe what user asked to analyze>"
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--step-number` | Yes | Current step (starts at 1) |
| `--total-steps` | Yes | Minimum 6; adjust as script instructs |
| `--thoughts` | Yes | Accumulated state from all previous steps |

---

## Process

The script outputs REQUIRED ACTIONS at each step. Follow them exactly.

### Phase 1: Exploration (Step 1)

Delegate to Explore agent(s). The script determines scope and parallelism. Wait for all agents, then re-invoke `scripts/analyze.py` with `--step-number 1`, including the Explore results in `--thoughts`.

### Phase 2: Focus Selection (Step 2)

Classify investigation areas by dimension (architecture, performance, security, quality). Assign priorities P1-P3. Estimate total steps.

### Phase 3: Investigation Planning (Step 3)

Commit to specific files, questions, and hypotheses per focus area. This creates a contract verified in the verification phase.

### Phase 4: Deep Analysis (Steps 4 to N-2)

Execute the investigation plan. Read files, collect evidence with file:line references and quoted code. Trace root causes across files.

### Phase 5: Verification (Step N-1)

Audit completeness against step 3 commitments. Identify gaps. If gaps exist, increase total-steps and return to deep analysis.

### Phase 6: Synthesis (Step N)

Consolidate verified findings by severity (critical, high, medium, low). Identify systemic patterns. Produce prioritized action plan.

---

## Example Sequence

```bash
# Step 1: Start, script instructs you to explore first
python3 scripts/analyze.py --step-number 1 --total-steps 6 \
  --thoughts "Starting analysis of auth system"

# [Follow REQUIRED ACTIONS: delegate to Explore agent, wait for results]

# Step 1 again with explore results
python3 scripts/analyze.py --step-number 1 --total-steps 6 \
  --thoughts "Explore found: Flask app, SQLAlchemy, auth/ dir..."

# Step 2+: Continue following script output
python3 scripts/analyze.py --step-number 2 --total-steps 7 \
  --thoughts "[accumulated state from step 1] Focus: security P1, quality P2"
```

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
