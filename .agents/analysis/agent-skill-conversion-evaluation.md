# Agent-to-Skill Conversion Evaluation

## Purpose

Evaluate all 19 agents against ADR-033 (Routing-Level Enforcement Gates) and SKILL-CREATION-CRITERIA.md to determine which should/must be converted to skills.

## Evaluation Criteria

From SKILL-CREATION-CRITERIA.md, the Decision Matrix:

| Question | Yes → Skill | No → LLM |
|----------|-------------|----------|
| Is there a documented procedure? | Create skill | Handle directly |
| Do failures come from skipping steps? | Add phase gates | Trust LLM judgment |
| Is the output format fixed? | Skill standardizes | LLM adapts |
| Does it repeat >3x per week? | Skill amortizes cost | One-off handling |
| Can success be programmatically verified? | Skill enforces | LLM validates |

**Threshold**: If ≥3 answers are "Yes → Skill", create a skill.

**Anti-Patterns**:

- NOT creating skill for one-time task
- NOT duplicating existing skill capability
- NOT wrapping simple tool invocation
- NOT adding skill for subjective judgment tasks

From ADR-033 (Routing-Level Enforcement Gates):

- "Do Router" pattern: Force routing to specialists before high-stakes actions
- Gates operate at tool invocation layer, blocking until prerequisites met
- MANDATORY routing for security-sensitive, architecture-changing, or protocol-compliance actions

---

## Evaluation Results

### Summary Table

| Agent | Score | Verdict | Reason | Existing Skill? |
|-------|-------|---------|--------|-----------------|
| **orchestrator** | 2/5 | LLM + Gates | Routing judgment requires LLM; ADR-033 gates enforce | No |
| **planner** | 4/5 | SKILL | Already exists as /planner | Yes |
| **task-generator** | 5/5 | MUST SKILL | Fixed format, verifiable, frequent | No |
| **spec-generator** | 4/5 | SHOULD SKILL | 3-tier output, EARS format, traceable | No |
| **implementer** | 2/5 | LLM | Subjective code generation | No |
| **devops** | 4/5 | SHOULD SKILL | Pipeline patterns, YAML validation | No |
| **security** | 4/5 | HYBRID SKILL | Orchestrates checklist, LLM provides judgment | No |
| **critic** | 4/5 | SHOULD SKILL | Fixed verdict format, review checklist | No |
| **qa** | 5/5 | MUST SKILL | Test reports, coverage validation, frequent | No |
| **independent-thinker** | 0/5 | LLM | Pure judgment, no procedure | No |
| **architect** | 3/5 | HYBRID SKILL | ADR creation = skill; design review = LLM | No |
| **analyst** | 2/5 | LLM | Novel each time, research varies | No |
| **explainer** | 4/5 | SHOULD SKILL | PRD template, fixed sections | No |
| **high-level-advisor** | 0/5 | LLM | Strategic judgment, verdicts vary | No |
| **roadmap** | 3/5 | BORDERLINE | RICE/KANO framework could be skill | No |
| **retrospective** | 4/5 | SHOULD SKILL | Five Whys, structured output | No |
| **memory** | 5/5 | NO (Anti-pattern) | Wraps simple tool invocation | No |
| **skillbook** | 5/5 | NO (Anti-pattern) | Wraps tool invocation | No |
| **pr-comment-responder** | 5/5 | SKILL | Already exists as skill | Yes |

---

## Detailed Evaluations

### MUST Convert to Skill (5/5 Score, High Impact)

#### task-generator

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | TASK-NNN format, acceptance criteria template |
| Failures from skipping steps? | Yes | Missing estimates, missing deps |
| Fixed output format? | Yes | Atomic tasks with complexity (XS/S/M/L/XL) |
| Repeats frequently? | Yes | Every feature breakdown |
| Programmatically verifiable? | Yes | Task format validation |

**Recommendation**: MUST create skill using SkillCreator
**Gate Requirement**: ADR-033 QA gate could require task-generator for PR creation
**Use SkillCreator**: `SkillCreator: create a skill for atomic task generation from milestones`

#### qa

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | Test strategy template |
| Failures from skipping steps? | Yes | Missing coverage, skipped scenarios |
| Fixed output format? | Yes | Test reports in .agents/qa/ |
| Repeats frequently? | Yes | Every implementation |
| Programmatically verifiable? | Yes | Test pass/fail, coverage % |

**Recommendation**: MUST create skill using SkillCreator
**Gate Requirement**: ADR-033 QA gate already requires this before PR creation
**Use SkillCreator**: `SkillCreator: create a skill for test strategy and verification reports`

---

### SHOULD Convert to Skill (4/5 Score)

#### spec-generator

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | 3-tier spec: REQ → DESIGN → TASK |
| Failures from skipping steps? | Yes | Missing traceability |
| Fixed output format? | Yes | EARS format, numbered specs |
| Repeats frequently? | Moderate | Feature specifications |
| Programmatically verifiable? | Yes | Traceability chain validation |

**Recommendation**: Create skill for structured specification generation
**Use SkillCreator**: `SkillCreator: create a skill for EARS specification generation with traceability`

#### critic

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | Review checklist, verdict format |
| Failures from skipping steps? | Yes | Missing risk assessment |
| Fixed output format? | Yes | APPROVED/REJECTED/NEEDS WORK |
| Repeats frequently? | Yes | Every plan review |
| Programmatically verifiable? | Partially | Verdict parsing |

**Recommendation**: Create skill with structured review phase gates
**Gate Requirement**: ADR-033 Critic gate for PR merge
**Use SkillCreator**: `SkillCreator: create a skill for structured plan critique with phase gates`

#### devops

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | Pipeline patterns, YAML structure |
| Failures from skipping steps? | Yes | Missing security scanning |
| Fixed output format? | Yes | Workflow YAML, .agents/devops/ |
| Repeats frequently? | Moderate | Infrastructure changes |
| Programmatically verifiable? | Yes | YAML validation, workflow syntax |

**Recommendation**: Create skill for pipeline generation and validation
**Use SkillCreator**: `SkillCreator: create a skill for GitHub Actions workflow generation`

#### explainer

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | PRD template, section requirements |
| Failures from skipping steps? | Yes | Missing user stories, acceptance criteria |
| Fixed output format? | Yes | PRD-*.md structure |
| Repeats frequently? | Moderate | Feature documentation |
| Programmatically verifiable? | Partially | Section existence |

**Recommendation**: Create skill for PRD generation
**Use SkillCreator**: `SkillCreator: create a skill for product requirements document generation`

#### retrospective

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | Five Whys, Fishbone, learning matrix |
| Failures from skipping steps? | Yes | Missing evidence, incomplete analysis |
| Fixed output format? | Yes | Structured retro reports |
| Repeats frequently? | Yes | End of every session |
| Programmatically verifiable? | Partially | Skill recommendation format |

**Recommendation**: Create skill for structured retrospective analysis
**Use SkillCreator**: `SkillCreator: create a skill for session retrospective with learning extraction`

---

### HYBRID Skill (4/5 Score, Mixed Judgment)

#### security

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | STRIDE, OWASP Top 10 |
| Failures from skipping steps? | Yes | Missing threat model |
| Fixed output format? | Yes | TM-NNN, SR-NNN reports |
| Repeats frequently? | Moderate | Security-sensitive changes |
| Programmatically verifiable? | Partially | Report existence, not quality |

**Recommendation**: Hybrid skill - deterministic checklist + LLM triage
**Gate Requirement**: ADR-033 "Do Router" mandates security for **/Auth/** files
**Use SkillCreator**: `SkillCreator: create a skill for security review with STRIDE threat modeling`

#### architect

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | MADR 4.0 format |
| Failures from skipping steps? | Yes | Missing tradeoffs, reversibility |
| Fixed output format? | Yes | ADR-NNN-*.md |
| Repeats frequently? | Moderate | Design decisions |
| Programmatically verifiable? | Partially | ADR structure validation |

**Recommendation**: Split skill - ADR generation skill + LLM design review
**Gate Requirement**: ADR-033 mandates architect for ADR-*.md changes
**Use SkillCreator**: `SkillCreator: create a skill for ADR generation with MADR 4.0 format`

---

### Borderline (3/5 Score)

#### roadmap

| Criterion | Answer | Notes |
|-----------|--------|-------|
| Documented procedure? | Yes | RICE, KANO frameworks |
| Failures from skipping steps? | Yes | Missing prioritization |
| Fixed output format? | Yes | Epic structure |
| Repeats frequently? | Less | Strategic planning |
| Programmatically verifiable? | Partially | Framework application |

**Decision**: Keep as agent for now; consider skill if frequency increases
**Rationale**: Strategic judgment heavily involved; frameworks are guidance, not deterministic

---

### Keep as LLM Agent (0-2/5 Score)

#### orchestrator (2/5)

- **Why not skill**: Routing requires contextual judgment
- **ADR-033 enforcement**: Gates operate at hook level, not orchestrator skill level
- **Keep as**: Agent with hook-enforced prerequisites

#### implementer (2/5)

- **Why not skill**: Code generation is inherently subjective
- **Keep as**: Agent with steering file guidance

#### independent-thinker (0/5)

- **Why not skill**: Pure judgment, no procedure, value is unpredictability
- **Keep as**: Agent invoked for contrarian perspective

#### analyst (2/5)

- **Why not skill**: Novel research each time, no fixed procedure
- **Keep as**: Agent for investigation

#### high-level-advisor (0/5)

- **Why not skill**: Strategic verdicts require deep judgment
- **Keep as**: Agent for tie-breaking and priority decisions

---

### Anti-Pattern Violations (High Score, Wrong Pattern)

#### memory (5/5 but anti-pattern)

- **Anti-pattern**: Wraps simple tool invocation (cloudmcp-manager)
- **Recommendation**: Keep as agent, document as memory protocol
- **Reason**: Creating skill adds overhead without benefit

#### skillbook (5/5 but anti-pattern)

- **Anti-pattern**: Wraps skill storage tools
- **Recommendation**: Keep as agent
- **Reason**: Meta-skill for skill management is recursive complexity

---

## ADR-033 "Do Router" Mandatory Routing Matrix

Based on ADR-033, these agent invocations should be MANDATORY before certain actions:

| Action | Mandatory Agent | Gate Type |
|--------|-----------------|-----------|
| `**/Auth/**` file changes | security | ADR-033 Phase 4 |
| `ADR-*.md` creation/update | architect | ADR-033 Phase 4 |
| `gh pr create` | qa | ADR-033 Phase 2 |
| `gh pr merge` | critic | ADR-033 Phase 3 |
| `.github/workflows/**` | devops, security | ADR-033 Phase 4 |

---

## Implementation Priority

### Phase 1: MUST Skills (Immediate)

1. **task-generator skill** - Every feature breakdown needs this
2. **qa skill** - ADR-033 QA gate depends on this

### Phase 2: SHOULD Skills (Next)

3. **critic skill** - ADR-033 Critic gate for PR merge
4. **spec-generator skill** - Formal requirements flow
5. **retrospective skill** - Session end protocol

### Phase 3: Hybrid Skills (Later)

6. **security skill** - STRIDE checklist + LLM
7. **architect skill** - ADR generation component

### Phase 4: Optional Skills (If Needed)

8. **devops skill** - If pipeline generation becomes frequent
9. **explainer skill** - If PRD format needs enforcement

---

## SkillCreator Invocations

For Phase 1 and 2 skills, use these invocations:

```text
# Phase 1
SkillCreator: create a skill for atomic task generation from milestones with TASK-NNN format
SkillCreator: create a skill for QA verification with test strategy and coverage reports

# Phase 2
SkillCreator: create a skill for plan critique with APPROVED/REJECTED verdicts
SkillCreator: create a skill for EARS specification generation with 3-tier traceability
SkillCreator: create a skill for session retrospective with Five Whys learning extraction
```

---

## Integration with ADR-033

Skills created should integrate with ADR-033 routing-level gates:

| Skill | Gate Integration | Enforcement |
|-------|------------------|-------------|
| qa skill | QA Validation Gate | Block `gh pr create` without QA report |
| critic skill | Critic Review Gate | Block `gh pr merge` without critic verdict |
| security skill | Do Router Gate | Force security for Auth/** changes |
| architect skill | ADR Existence Gate | Force architect for feature PRs |

---

*Analysis Version: 1.0*
*Date: 2025-12-30*
*Governance References: ADR-033 (Routing-Level Enforcement Gates), SKILL-CREATION-CRITERIA.md v1.3*
