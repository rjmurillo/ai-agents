# SkillCreator Phases Reference

## Phase 1: Deep Analysis

### 1A: Input Expansion

Transform user's goal into comprehensive requirements:

```text
USER INPUT: "Create a skill for X"
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│ EXPLICIT REQUIREMENTS                                    │
│ • What the user literally asked for                      │
│ • Direct functionality stated                            │
├─────────────────────────────────────────────────────────┤
│ IMPLICIT REQUIREMENTS                                    │
│ • What they probably expect but didn't say               │
│ • Standard quality expectations                          │
│ • Integration with existing patterns                     │
├─────────────────────────────────────────────────────────┤
│ UNKNOWN UNKNOWNS                                         │
│ • What they don't know they need                         │
│ • Expert-level considerations they'd miss                │
│ • Future needs they haven't anticipated                  │
├─────────────────────────────────────────────────────────┤
│ DOMAIN CONTEXT                                           │
│ • Related skills that exist                              │
│ • Patterns from similar skills                           │
│ • Lessons from skill failures                            │
└─────────────────────────────────────────────────────────┘
```

**Check for overlap with existing skills:**

```bash
ls ~/.claude/skills/
# Grep for similar triggers in existing SKILL.md files
```

| Match Score | Action |
|-------------|--------|
| >7/10 | Use existing skill instead |
| 5-7/10 | Clarify distinction before proceeding |
| <5/10 | Proceed with new skill |

### 1B: Multi-Lens Analysis

Apply all 11 thinking models systematically:

| Lens | Core Question | Application |
|------|---------------|-------------|
| **First Principles** | What's fundamentally needed? | Strip convention, find core |
| **Inversion** | What guarantees failure? | Build anti-patterns |
| **Second-Order** | What happens after the obvious? | Map downstream effects |
| **Pre-Mortem** | Why did this fail? | Proactive risk mitigation |
| **Systems Thinking** | How do parts interact? | Integration mapping |
| **Devil's Advocate** | Strongest counter-argument? | Challenge every decision |
| **Constraints** | What's truly fixed? | Separate real from assumed |
| **Pareto** | Which 20% delivers 80%? | Focus on high-value features |
| **Root Cause** | Why is this needed? (5 Whys) | Address cause not symptom |
| **Comparative** | How do options compare? | Weighted decision matrix |
| **Opportunity Cost** | What are we giving up? | Explicit trade-offs |

**Minimum requirement:** All 11 lenses scanned, at least 5 applied in depth.

See: [multi-lens-framework.md](multi-lens-framework.md)

### 1C: Regression Questioning

Iterative self-questioning until no new insights emerge:

```text
ROUND N:
│
├── "What am I missing?"
├── "What would an expert in {domain} add?"
├── "What would make this fail?"
├── "What will this look like in 2 years?"
├── "What's the weakest part of this design?"
└── "Which thinking model haven't I applied?"
    │
    └── New insights > 0?
        │
        ├── YES → Incorporate and loop
        └── NO → Check termination criteria
```

**Termination Criteria:**

- Three consecutive rounds produce no new insights
- All 11 thinking models have been applied
- At least 3 simulated expert perspectives considered
- Evolution/timelessness explicitly evaluated
- Automation opportunities identified

See: [regression-questions.md](regression-questions.md)

### 1D: Automation Analysis

Identify opportunities for scripts that enable agentic operation:

```text
FOR EACH operation in the skill:
│
├── Is this operation repeatable?
│   └── YES → Consider generation script
│
├── Does this produce verifiable output?
│   └── YES → Consider validation script
│
├── Does this need state across sessions?
│   └── YES → Consider state management script
│
├── Does this involve external tools?
│   └── YES → Consider integration script
│
└── Can Claude verify success autonomously?
    └── NO → Add self-verification script
```

**Automation Lens Questions:**

| Question | Script Category if YES |
|----------|----------------------|
| What operations will be repeated identically? | Generation |
| What outputs require validation? | Validation |
| What state needs to persist? | State Management |
| Can the skill run overnight autonomously? | All categories |
| How will Claude verify correct execution? | Verification |

#### Decision: Script vs No Script

| Create Script When | Skip Script When |
|-------------------|------------------|
| Operation is deterministic | Requires human judgment |
| Output can be validated | One-time setup |
| Will be reused across invocations | Simple text output |
| Enables autonomous operation | No verification needed |
| External tool integration | Pure Claude reasoning |

See: [script-integration-framework.md](script-integration-framework.md)

---

## Phase 2: Specification

### Specification Structure

The specification captures all analysis insights in XML format:

```xml
<skill_specification>
  <metadata>
    <name>skill-name</name>
    <analysis_iterations>N</analysis_iterations>
    <timelessness_score>X/10</timelessness_score>
  </metadata>

  <context>
    <problem_statement>What + Why + Who</problem_statement>
    <existing_landscape>Related skills, distinctiveness</existing_landscape>
  </context>

  <requirements>
    <explicit>What user asked for</explicit>
    <implicit>Expected but unstated</implicit>
    <discovered>Found through analysis</discovered>
  </requirements>

  <architecture>
    <pattern>Selected pattern with WHY</pattern>
    <phases>Ordered phases with verification</phases>
    <decision_points>Branches and defaults</decision_points>
  </architecture>

  <scripts>
    <decision_summary>needs_scripts + rationale</decision_summary>
    <script_inventory>name, category, purpose, patterns</script_inventory>
    <agentic_capabilities>autonomous, self-verify, recovery</agentic_capabilities>
  </scripts>

  <evolution_analysis>
    <timelessness_score>X/10</timelessness_score>
    <extension_points>Where skill can grow</extension_points>
    <obsolescence_triggers>What would break it</obsolescence_triggers>
  </evolution_analysis>

  <anti_patterns>
    <pattern>What to avoid + WHY + alternative</pattern>
  </anti_patterns>

  <success_criteria>
    <criterion>Measurable + verification method</criterion>
  </success_criteria>
</skill_specification>
```

See: [specification-template.md](specification-template.md)

### Specification Validation

Before proceeding to Phase 3:

- [ ] All sections present with no placeholders
- [ ] Every decision includes WHY
- [ ] Timelessness score ≥ 7 with justification
- [ ] At least 2 extension points documented
- [ ] All requirements traceable to source
- [ ] Scripts section complete (if applicable)
- [ ] Agentic capabilities documented (if scripts present)

---

## Phase 3: Generation

**Context:** Fresh, clean (no analysis artifacts polluting)
**Standard:** Zero errors, every section verified before proceeding

### Generation Order

```bash
1. Create directory structure
   mkdir -p ~/.claude/skills/{skill-name}/references
   mkdir -p ~/.claude/skills/{skill-name}/assets/templates
   mkdir -p ~/.claude/skills/{skill-name}/scripts  # if scripts needed

2. Write SKILL.md
   • Frontmatter (YAML - allowed properties only)
   • Title and brief intro
   • Quick Start section
   • Triggers (3-5 varied phrases)
   • Quick Reference table
   • How It Works overview
   • Commands
   • Scripts section (if applicable)
   • Validation section
   • Anti-Patterns
   • Verification criteria
   • Deep Dive sections (in <details> tags)

3. Generate reference documents (if needed)
   • Deep documentation for complex topics
   • Templates for generated artifacts
   • Checklists for validation

4. Create assets (if needed)
   • Templates for skill outputs

5. Create scripts (if needed)
   • Use script-template.py as base
   • Include Result dataclass pattern
   • Add self-verification
   • Document exit codes
   • Test before finalizing
```

### Quality Checks During Generation

| Check | Requirement |
|-------|-------------|
| Frontmatter | Only allowed properties (name, description, license, allowed-tools, metadata) |
| Name | Hyphen-case, ≤64 chars |
| Description | ≤1024 chars, no angle brackets |
| Triggers | 3-5 distinct, natural language |
| Phases | 1-3 max, not over-engineered |
| Verification | Concrete, measurable |
| Tables over prose | Structured information in tables |
| No placeholder text | Every section fully written |
| Scripts (if present) | Shebang, docstring, argparse, exit codes, Result pattern |
| Script docs | Scripts section in SKILL.md with usage examples |

---

## Phase 4: Multi-Agent Synthesis

**Panel:** 3-4 Opus agents with distinct evaluative lenses
**Requirement:** Unanimous approval (all agents)
**Fallback:** Return to Phase 1 with feedback (max 5 iterations)

### Panel Composition

| Agent | Focus | Key Criteria | When Active |
|-------|-------|--------------|-------------|
| **Design/Architecture** | Structure, patterns, correctness | Pattern appropriate, phases logical, no circular deps | Always |
| **Audience/Usability** | Clarity, discoverability, completeness | Triggers natural, steps unambiguous, no assumed knowledge | Always |
| **Evolution/Timelessness** | Future-proofing, extension, ecosystem | Score ≥7, extension points clear, ecosystem fit | Always |
| **Script/Automation** | Agentic capability, verification, quality | Scripts follow patterns, self-verify, documented | When scripts present |

### Script Agent (Conditional)

The Script Agent is activated when the skill includes a `scripts/` directory. Focus areas:

| Criterion | Checks |
|-----------|--------|
| **Pattern Compliance** | Result dataclass, argparse, exit codes |
| **Self-Verification** | Scripts can verify their own output |
| **Error Handling** | Graceful failures, actionable messages |
| **Documentation** | Usage examples in SKILL.md |
| **Agentic Capability** | Can run autonomously without human intervention |

**Script Agent Scoring:**

| Score | Meaning |
|-------|---------|
| 8-10 | Fully agentic, self-verifying, production-ready |
| 6-7 | Functional but missing some agentic capabilities |
| <6 | Requires revision, insufficient automation quality |

### Agent Evaluation

Each agent produces:

```markdown
## [Agent] Review

### Verdict: APPROVED / CHANGES_REQUIRED

### Scores
| Criterion | Score (1-10) | Notes |
|-----------|--------------|-------|

### Strengths
1. [Specific with evidence]

### Issues (if CHANGES_REQUIRED)
| Issue | Severity | Required Change |
|-------|----------|-----------------|

### Recommendations
1. [Even if approved]
```

### Consensus Protocol

```text
IF all agents APPROVED (3/3 or 4/4):
    → Finalize skill
    → Run validate-skill.py
    → Update registry
    → Complete

ELSE:
    → Collect all issues (including script issues)
    → Return to Phase 1 with issues as input
    → Re-apply targeted questioning
    → Regenerate skill and scripts
    → Re-submit to panel

IF 5 iterations without consensus:
    → Flag for human review
    → Present all agent perspectives
    → User makes final decision
```

See: [synthesis-protocol.md](synthesis-protocol.md)

---

## Evolution/Timelessness

Every skill is evaluated through the evolution lens:

### Temporal Projection

| Timeframe | Key Question |
|-----------|--------------|
| 6 months | How will usage patterns evolve? |
| 1 year | What ecosystem changes are likely? |
| 2 years | What new capabilities might obsolete this? |
| 5 years | Is the core problem still relevant? |

### Timelessness Scoring

| Score | Description | Verdict |
|-------|-------------|---------|
| 1-3 | Transient, will be obsolete in months | Reject |
| 4-6 | Moderate, depends on current tooling | Revise |
| **7-8** | **Solid, principle-based, extensible** | **Approve** |
| 9-10 | Timeless, addresses fundamental problem | Exemplary |

**Requirement:** All skills must score ≥7.

### Anti-Obsolescence Patterns

| Do | Don't |
|----|-------|
| Design around principles | Hardcode implementations |
| Document the WHY | Only document the WHAT |
| Include extension points | Create closed systems |
| Abstract volatile dependencies | Direct coupling |
| Version-agnostic patterns | Pin specific versions |

See: [evolution-scoring.md](evolution-scoring.md)

---

## Architecture Pattern Selection

Select based on task complexity:

| Pattern | Use When | Structure |
|---------|----------|-----------|
| **Single-Phase** | Simple linear tasks | Steps 1-2-3 |
| **Checklist** | Quality/compliance audits | ☐ Item verification |
| **Generator** | Creating artifacts | Input → Transform → Output |
| **Multi-Phase** | Complex ordered workflows | Phase 1 → Phase 2 → Phase 3 |
| **Multi-Agent Parallel** | Independent subtasks | Launch agents concurrently |
| **Multi-Agent Sequential** | Dependent subtasks | Agent 1 → Agent 2 → Agent 3 |
| **Orchestrator** | Coordinating multiple skills | Meta-skill chains |

### Selection Decision Tree

```text
Is it a simple procedure?
├── Yes → Single-Phase
└── No → Does it produce artifacts?
    ├── Yes → Generator
    └── No → Does it verify/audit?
        ├── Yes → Checklist
        └── No → Are subtasks independent?
            ├── Yes → Multi-Agent Parallel
            └── No → Multi-Agent Sequential or Multi-Phase
```
