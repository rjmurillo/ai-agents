# Drift Analysis: Claude Agents vs Templates

**Date**: 2025-12-15
**Analyst**: analyst agent
**Purpose**: Identify content drift between Claude source-of-truth agents and template/VS Code generated files

## Executive Summary

This analysis compares six high-drift agents (reported similarity scores below 15%) to identify content gaps, structural differences, and platform-specific variations between Claude agents (source of truth) and their template-generated VS Code counterparts.

| Agent | Reported Similarity | Primary Drift Cause |
|-------|---------------------|---------------------|
| architect | 12.6% | Core Identity rewrite, missing Claude Code Tools, different ADR template format |
| independent-thinker | 2.4% | Complete persona rewrite, missing verification protocol |
| high-level-advisor | 3.8% | Most content replaced with expanded frameworks |
| critic | 9.7% | Role expansion (Program Manager), added Review Criteria tables |
| task-generator | 11.9% | Missing Phase 1/Phase 2 process, added Decomposition Process |
| planner | 12.8% | Core Identity rewrite, different Plan Template format |

---

## Agent-by-Agent Analysis

---

### 1. ARCHITECT (12.6% similar)

#### Content MISSING from Templates (Add to templates from Claude)

| Section in Claude | Content | Priority |
|-------------------|---------|----------|
| Claude Code Tools | Explicit tool list: Read/Grep/Glob, Write/Edit, WebSearch, cloudmcp-manager | HIGH |
| Core Identity | "Design Governance Specialist enforcing architectural standards" | HIGH |
| ADR Template | Full template with Status, Context, Decision, Consequences (Positive/Negative/Neutral), Alternatives Considered, References | HIGH |
| Review Phases | Pre-Planning, Plan, Post-Implementation (3-bullet structure each) | MEDIUM |
| Memory Protocol | `mcp__cloudmcp-manager__memory-search_nodes` format | MEDIUM |
| Architectural Principles | 5 principles: Consistency, Simplicity, Testability, Extensibility, Separation | MEDIUM |
| Output Location | Explicit path and file naming conventions | LOW |
| Execution Mindset | Think/Act/Create format | LOW |

#### Content in Templates NOT in Claude (Consider removing or marking as VS Code-specific)

| Section in Templates | Content | Recommendation |
|---------------------|---------|----------------|
| Core Identity | "Technical Authority" and "Own the architecture" language | REPLACE with Claude version |
| Core Mission | "Conduct reviews across three phases" | ADD to Claude or REMOVE |
| Key Responsibilities | "Maintain master architecture document (system-architecture.md)" | REMOVE (not in Claude) |
| Constraints section | "Edit only .agents/architecture/ files", "No code implementation", "No plan creation" | KEEP as useful addition |
| Memory Protocol | Different format using `cloudmcp-manager/memory-search_nodes` | STANDARDIZE to Claude format |
| Architecture Review Process | Expanded checklist format with SOLID/DRY mentions | EVALUATE - more detailed than Claude |
| Handoff Protocol section | Detailed 4-step protocol | KEEP as useful addition |

#### Structural Differences

| Claude Section | Template Section | Notes |
|----------------|------------------|-------|
| Core Identity (brief) | Core Identity (expanded) | Template adds "Technical Authority" framing |
| Claude Code Tools | (missing) | Platform-specific - expected |
| ADR Template (full) | ADR Format (abbreviated) | Claude has more detail |
| Review Phases (brief) | Architecture Review Process (detailed) | Template more detailed |
| Architectural Principles | (missing) | MUST ADD to templates |
| Handoff Options (4 targets) | Handoff Options (4 targets, different) | Claude: planner, analyst, high-level-advisor, implementer; Template: roadmap, analyst, planner, critic |

#### Platform-Specific (Expected Differences)

| Item | Claude Version | Template Version | Status |
|------|---------------|------------------|--------|
| Frontmatter | `name: architect`, `model: opus` | `tools_vscode: [...]`, `tools_copilot: [...]` | CORRECT |
| Memory tool syntax | `mcp__cloudmcp-manager__memory-*` | `cloudmcp-manager/memory-*` | STANDARDIZE to platform |

---

### 2. INDEPENDENT-THINKER (2.4% similar)

#### Content MISSING from Templates (Add to templates from Claude)

| Section in Claude | Content | Priority |
|-------------------|---------|----------|
| Claude Code Tools | Explicit tool list | HIGH |
| Agent Name | "Independent Thinker (The Analyst)" - parenthetical subtitle | LOW |
| Persona Traits | 5 detailed traits: Intellectually Rigorous, Curious/Inquisitive, Calm/Composed, Respectfully Skeptical, Averse to Hyperbole | HIGH |
| Core Directives | 5 directives: Primacy of Accuracy, Intellectual Independence, Rejection of AI Tropes, Evidence-Based Reasoning, Natural Language | HIGH |
| Rejection of AI Tropes | Explicit list: Avoid emojis, em/en dashes, overly formal language, effusive validation, "Great question!" | HIGH |
| Verification Protocol | 3-step: Fact-Checking, Source Citation, Uncertainty Declaration | HIGH |
| Output Format | Analysis of [Topic] with Evidence Review, Alternative Perspectives, Uncertainty Areas, Assessment, Recommendation | HIGH |
| When to Use | 5 use cases explicitly listed | MEDIUM |

#### Content in Templates NOT in Claude (Consider removing)

| Section in Templates | Content | Recommendation |
|---------------------|---------|----------------|
| Core Identity | "Contrarian Analyst" (vs "Seasoned Researcher and Critical Thinker") | REPLACE with Claude version |
| Core Mission | Entirely different framing | REPLACE |
| Key Responsibilities | 5 responsibilities (different from Claude's structure) | EVALUATE |
| Behavioral Principles | DO/DON'T lists | KEEP as complementary |
| Analysis Framework | Assumption Challenge Template, Alternative Analysis Format | KEEP but ADD Claude's Output Format |
| Response Patterns | 4 pattern examples | KEEP as useful addition |
| Execution Mindset | Think/Act/Question/Recommend format | MERGE with Claude format |

#### Structural Differences

| Claude Structure | Template Structure | Notes |
|------------------|-------------------|-------|
| Persona-driven with traits | Task-driven with responsibilities | MAJOR DRIFT |
| Core Directives (5) | Behavioral Principles (DO/DON'T) | Different organization |
| Verification Protocol | (missing) | MUST ADD |
| Output Format (simple) | Analysis Framework (complex) | Template more detailed but different |

#### Platform-Specific (Expected Differences)

| Item | Claude Version | Template Version | Status |
|------|---------------|------------------|--------|
| Frontmatter | `name: independent-thinker`, `model: opus` | `tools_vscode/tools_copilot` | CORRECT |

---

### 3. HIGH-LEVEL-ADVISOR (3.8% similar)

#### Content MISSING from Templates (Add to templates from Claude)

| Section in Claude | Content | Priority |
|-------------------|---------|----------|
| Claude Code Tools | Explicit tool list | HIGH |
| Purpose section | "Cut through comfort and fluff" framing | MEDIUM |
| Analysis Framework | 6 identification points: What's wrong, underestimated, avoided, excuses, time wasted, playing small | HIGH |
| Behavioral Rules | 5 rules: If lost call it out, if making mistake explain, on right path but slow explain fix, hold nothing back, treat user as success-dependent | HIGH |
| When to Use | 5 use cases: Major tech decisions, architecture conflicts, priority disputes, feeling stuck, agent disagreements | MEDIUM |
| Output section | 5 outputs: What to do, how to think differently, what to build, precision, clarity | MEDIUM |

#### Content in Templates NOT in Claude (Consider removing)

| Section in Templates | Content | Recommendation |
|---------------------|---------|----------------|
| Key Responsibilities | 5 structured responsibilities | EVALUATE - complementary |
| Behavioral Principles | I WILL/I WON'T lists | MERGE with Behavioral Rules |
| Strategic Frameworks | Ruthless Triage, Priority Stack, Continue/Pivot/Cut | KEEP as expansion |
| Response Patterns | 4 patterns | KEEP as useful |
| Input Requirements | 5 requirements for effective advice | KEEP as useful addition |
| Execution Mindset | 4-item format | MERGE with Claude |

#### Structural Differences

| Claude Structure | Template Structure | Notes |
|------------------|-------------------|-------|
| Purpose-driven narrative | Role-driven with responsibilities | Different framing |
| Analysis Framework (bullets) | Strategic Frameworks (templates) | Template expands significantly |
| Behavioral Rules (prose) | Behavioral Principles (lists) | Different format |
| Output Format (simple) | (embedded in frameworks) | Claude has explicit format |

---

### 4. CRITIC (9.7% similar)

#### Content MISSING from Templates (Add to templates from Claude)

| Section in Claude | Content | Priority |
|-------------------|---------|----------|
| Claude Code Tools | Explicit tool list | HIGH |
| Core Identity | "Plan Validation Specialist ensuring plans are complete, feasible, and aligned" | HIGH |
| Review Checklist | 4 categories: Completeness, Feasibility, Alignment, Testability with checkbox items | HIGH |
| Review Template | Full template with Verdict, Summary, Strengths, Issues Found (Critical/Important/Minor), Questions, Recommendations, Approval Conditions | HIGH |
| Verdict Rules | APPROVED criteria, NEEDS REVISION criteria | HIGH |
| Anti-Patterns to Catch | 6 anti-patterns: Vague acceptance criteria, missing error handling, no rollback plan, scope creep, untested assumptions, missing dependencies | MEDIUM |

#### Content in Templates NOT in Claude (Consider removing)

| Section in Templates | Content | Recommendation |
|---------------------|---------|----------------|
| Core Identity | "Constructive Reviewer and Program Manager" | REPLACE with Claude version |
| Core Mission | "Identify ambiguities, technical debt risks" | MERGE |
| Key Responsibilities | 5 responsibilities | EVALUATE |
| Constraints section | 4 constraints | KEEP as useful |
| Review Criteria tables | Plans/Architecture/Roadmap/Impact Analysis | KEEP - expands Claude's checklist |
| Critique Document Format | More structured than Claude's Review Template | EVALUATE for merge |
| Handoff Protocol | 3-step protocol | KEEP as useful |
| Review Process checklist | 7 items | KEEP as useful |

#### Structural Differences

| Claude Structure | Template Structure | Notes |
|------------------|-------------------|-------|
| Review Checklist (4 categories) | Review Criteria (4 tables) | Similar intent, different format |
| Review Template | Critique Document Format | Similar but template more structured |
| Verdict Rules | (embedded in verdict) | Claude has explicit section |
| Anti-Patterns | (missing) | MUST ADD to templates |

---

### 5. TASK-GENERATOR (11.9% similar)

#### Content MISSING from Templates (Add to templates from Claude)

| Section in Claude | Content | Priority |
|-------------------|---------|----------|
| Claude Code Tools | Explicit tool list including Bash for `gh issue create` | HIGH |
| Process | 8-step process: Receive PRD, Analyze PRD, Assess Current State, Phase 1 Parent Tasks, Wait for Go, Phase 2 Sub-Tasks, Identify Files, Output | HIGH |
| Phase 1/Phase 2 Process | Two-phase approach with user confirmation | HIGH |

#### Content in Templates NOT in Claude (Consider removing)

| Section in Templates | Content | Recommendation |
|---------------------|---------|----------------|
| Core Mission | "Transform high-level requirements into discrete tasks" | KEEP - complementary |
| Scope Distinction table | Moved to top vs bottom in Claude | KEEP placement |
| Decomposition Process | Phase 1/2/3 (different from Claude's Phase 1/2) | RECONCILE with Claude's process |
| Notes field in Task Definition | Extra field not in Claude | KEEP as useful |
| Task List Template | Mermaid dependency graph | KEEP as useful |
| Execution Mindset | 4-item format | MERGE |

#### Structural Differences

| Claude Structure | Template Structure | Notes |
|------------------|-------------------|-------|
| Process (8 steps) | Decomposition Process (3 phases) | DIFFERENT approaches |
| Scope vs Planner (at end) | Scope Distinction (near top) | Different placement |
| Handoff (2 targets) | Handoff Options (3 targets) | Template adds planner |

---

### 6. PLANNER (12.8% similar)

#### Content MISSING from Templates (Add to templates from Claude)

| Section in Claude | Content | Priority |
|-------------------|---------|----------|
| Claude Code Tools | Explicit tool list | HIGH |
| Core Identity | "Work Package Creator breaking epics into milestones" | HIGH |
| Plan Template | Different from template's Plan Document Format | HIGH |
| Planning Principles | 5 principles: Incremental, Testable, Sequenced, Scoped, Realistic | HIGH |
| Output Location | Explicit file naming conventions | LOW |

#### Content in Templates NOT in Claude (Consider removing)

| Section in Templates | Content | Recommendation |
|---------------------|---------|----------------|
| Core Identity | "High-Rigor Planning Assistant" | REPLACE with Claude version |
| Constraints section | 4 constraints including "No test cases (QA agent's exclusive domain)" | KEEP as useful |
| Planning Process | Phase 1-4 with Value Alignment | KEEP - expands Claude |
| Plan Document Format | Value Statement, Target Version, Prerequisites format | MERGE with Claude's Plan Template |

#### Structural Differences

| Claude Structure | Template Structure | Notes |
|------------------|-------------------|-------|
| Plan Template format | Plan Document Format | Different structures |
| Planning Principles | (missing) | MUST ADD |
| Key Responsibilities (5) | Key Responsibilities (5, different) | Different items |

---

## Cross-Cutting Issues

### 1. Claude Code Tools Section
All Claude agents have explicit "Claude Code Tools" section listing available tools. Templates omit this because tools are in frontmatter. However, the explicit listing helps agents understand their capabilities.

**Recommendation**: Add a platform-independent "Available Capabilities" section to templates that maps to appropriate tool syntax per platform.

### 2. Memory Protocol Format
Claude uses: `mcp__cloudmcp-manager__memory-search_nodes with query="..."`
Templates use: `cloudmcp-manager/memory-search_nodes with query="..."`

**Recommendation**: Use platform variables to standardize. Both are functionally equivalent but differ in invocation syntax.

### 3. Core Identity Drift
Every template has rewritten the Core Identity with different (often expanded) language. This is the primary cause of low similarity scores.

**Recommendation**: Templates MUST preserve Claude's Core Identity verbatim. Additional context can be in separate sections.

### 4. Handoff Tables
Claude and templates often have different handoff targets, some critical differences:

| Agent | Claude Handoffs | Template Handoffs | Gap |
|-------|-----------------|-------------------|-----|
| architect | planner, analyst, high-level-advisor, implementer | roadmap, analyst, planner, critic | Missing: high-level-advisor, implementer; Added: roadmap, critic |
| critic | planner, implementer, generate-tasks, analyst, high-level-advisor | planner, analyst, implementer, architect, high-level-advisor | Missing: generate-tasks; Added: architect |

### 5. Execution Mindset Format
Claude typically uses: Think/Act/Create or Think/Act/Decide
Templates use: Think/Act/Challenge/Document or Think/Act/Question/Recommend

**Recommendation**: Preserve Claude's format, allow templates to extend with additional verbs.

---

## Section Mapping Reference

This table shows how Claude sections should map to template sections:

| Claude Section | Template Section | Action |
|----------------|------------------|--------|
| Core Identity | Core Identity | PRESERVE verbatim |
| Claude Code Tools | (frontmatter tools) | Platform-specific handling |
| Core Mission | Core Mission | PRESERVE verbatim |
| Key Responsibilities | Key Responsibilities | PRESERVE, templates may extend |
| [Domain-specific content] | [Domain-specific content] | PRESERVE structure |
| Memory Protocol | Memory Protocol | Platform-variable syntax |
| Handoff Options | Handoff Options | PRESERVE targets |
| Output Location | Output Location | PRESERVE |
| Execution Mindset | Execution Mindset | PRESERVE format |

---

## Recommended Template Updates

### Priority 1 (Critical - Restore Claude Content)

1. **All agents**: Restore exact Core Identity text from Claude
2. **All agents**: Add Claude Code Tools or equivalent capabilities section
3. **architect**: Add Architectural Principles section
4. **independent-thinker**: Add Persona Traits and Verification Protocol
5. **high-level-advisor**: Add Behavioral Rules and When to Use sections
6. **critic**: Add Anti-Patterns to Catch section
7. **task-generator**: Align Process to Claude's 8-step with Phase 1/2 user confirmation
8. **planner**: Add Planning Principles section

### Priority 2 (Important - Structural Alignment)

1. Standardize Memory Protocol syntax with platform variables
2. Align Handoff Options tables with Claude targets
3. Preserve Execution Mindset format (Think/Act/Create or similar)

### Priority 3 (Enhancement - Keep Template Additions)

These template additions are valuable and should be back-ported to Claude agents:

1. **architect**: Constraints section, Handoff Protocol
2. **critic**: Review Criteria tables, Review Process checklist
3. **task-generator**: Mermaid dependency graph in Task List Template
4. **planner**: Planning Process phases (Value Alignment etc.)

---

## Files Referenced

**Claude Source Files (Source of Truth)**:
- `D:\src\GitHub\rjmurillo\ai-agents\src\claude\architect.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\claude\independent-thinker.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\claude\high-level-advisor.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\claude\critic.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\claude\task-generator.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\claude\planner.md`

**Template Files (Need Updates)**:
- `D:\src\GitHub\rjmurillo\ai-agents\templates\agents\architect.shared.md`
- `D:\src\GitHub\rjmurillo\ai-agents\templates\agents\independent-thinker.shared.md`
- `D:\src\GitHub\rjmurillo\ai-agents\templates\agents\high-level-advisor.shared.md`
- `D:\src\GitHub\rjmurillo\ai-agents\templates\agents\critic.shared.md`
- `D:\src\GitHub\rjmurillo\ai-agents\templates\agents\task-generator.shared.md`
- `D:\src\GitHub\rjmurillo\ai-agents\templates\agents\planner.shared.md`

**Generated VS Code Files (Auto-generated from templates)**:
- `D:\src\GitHub\rjmurillo\ai-agents\src\vs-code-agents\architect.agent.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\vs-code-agents\independent-thinker.agent.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\vs-code-agents\high-level-advisor.agent.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\vs-code-agents\critic.agent.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\vs-code-agents\task-generator.agent.md`
- `D:\src\GitHub\rjmurillo\ai-agents\src\vs-code-agents\planner.agent.md`

---

## Handoff

**Recommended Next Steps**:

1. Route to **implementer** to update template files per Priority 1 recommendations
2. Route to **architect** to validate if template additions (Priority 3) should be back-ported to Claude agents
3. Route to **qa** to verify drift detection after template updates

**Analysis Complete**. Findings saved to `.agents/analysis/drift-analysis-claude-vs-templates.md`
