# Skill Usage Pattern Analysis Report

**Date**: 2026-02-07
**Analyst**: Explore Agent
**Sources**: Session histories, analysis documents, architecture reviews, retrospectives

## Executive Summary

This report analyzes real usage patterns from session histories to inform the creation of three strategic decision-making skills:

1. **Buy vs Build Framework** - Strategic sourcing decisions
2. **Code Qualities Assessment** - Code review and maintainability analysis
3. **CVA (Commonality Variability Analysis)** - Abstraction discovery and pattern selection

### Analysis Coverage

- **Session Logs Analyzed**: 100+ JSON session files
- **Documents Reviewed**: Architecture reviews, retrospectives, analysis documents
- **Time Period**: December 2025 - February 2026
- **Total Pattern Matches**: 1,918 across all three skills

---

## 1. Buy vs Build Framework

### 1.1 Usage Frequency

**Total Matches**: 801 occurrences

**Top Keywords**:

- `TCO` (Total Cost of Ownership): 678 mentions
- `vendor`: 19 mentions
- `core vs context`: 11 mentions
- `commodity`: 10 mentions
- `third-party`: 9 mentions
- `build vs buy`: 9 mentions
- `context bloat`: 8 mentions

### 1.2 Real Decision Points

#### Case Study 1: Traceability Graph Build vs Buy (Issue #724)

**Context**: Decision on whether to build markdown-first traceability graph or buy external graph database.

**Natural Language Triggers**:

- "Programming-advisor consultation on traceability graph implementation"
- "Should we build custom or use existing graph database?"
- "What are the scaling thresholds?"

**Decision Framework Applied**:

1. **Current State Assessment**
   - Algorithmic complexity: O(n × m)
   - Performance: 500ms cold, <100ms warm cache
   - Memory: 5MB for 100 specs

2. **Build Option Analysis**
   - Pros: Markdown-first, no dependencies, simple tooling
   - Cons: Linear scan, no native graph queries, memory-bound at 10,000+ specs

3. **Buy Option Analysis**
   - Options: SQLite, Graph Libraries (NetworkX), Graph DB (Neo4j)
   - Cons: Dual source of truth, import/export overhead, context bloat

4. **Constraint Alignment**
   - Markdown-first: ✅ Build only
   - No MCP dependency: ✅ Build only
   - Simple tooling: ✅ Build only

5. **Scaling Threshold**
   - Reassess at 5,000 specs or 5s warm cache
   - Current: 30 specs (167x headroom)

**Recommendation**: BUILD - Continue markdown-first implementation

**Key Quote**: "All 'buy' options introduce unacceptable complexity for current use case."

### 1.3 Natural Language Triggers

Real phrases used in sessions:

- "Should we build custom or use existing?"
- "What are the scaling thresholds?"
- "When does this become unacceptable?"
- "Evaluate TCO of [tool/dependency]"
- "Is this core or context?"
- "Constraint alignment check"
- "What's our exit strategy?"

### 1.4 Framework Components Observed

1. **Current State Assessment**
   - Algorithmic complexity
   - Performance characteristics
   - Robustness evaluation
   - Durability guarantees

2. **Build Analysis**
   - Pros/Cons enumeration
   - When it works (ideal scenarios)
   - Breaking points (risk indicators)

3. **Buy Analysis**
   - Options evaluated (with specific tools)
   - Trade-off matrix
   - Constraint violation analysis

4. **Decision Criteria**
   - Constraint alignment (hard requirements)
   - Performance acceptable (for current/projected scale)
   - Complexity budget
   - Scaling runway
   - Exit strategy availability

5. **Scaling Threshold**
   - Quantitative triggers (spec count, execution time, memory)
   - Projected timeline
   - Reassessment conditions

### 1.5 Anti-Patterns Identified

❌ **Premature optimization**: "Speculative scaling needs"
❌ **Just-in-case dependencies**: "Might need graph queries someday"
❌ **Context bloat tolerance**: "77 GitHub tools when only 2 needed"
❌ **Dual source of truth**: "Markdown + database divergence risk"

### 1.6 Skill Gap Analysis

**Current Behavior**: Manual application of framework in analysis documents

**Needed Capability**:

- Structured decision template
- Constraint alignment checklist
- Scaling threshold calculator
- Trade-off matrix generator
- Exit strategy documenter

**Suggested Implementation**:

```powershell
pwsh .claude/skills/buy-vs-build/scripts/Invoke-BuildVsBuyAnalysis.ps1 `
    -Decision "Traceability graph implementation" `
    -BuildOption "Markdown-first PowerShell" `
    -BuyOptions "SQLite,Neo4j,NetworkX" `
    -Constraints "markdown-first,no-mcp,simple-tooling" `
    -OutputPath ".agents/analysis/build-vs-buy-[decision-slug].md"
```

---

## 2. Code Qualities Assessment

### 2.1 Usage Frequency

**Total Matches**: 623 occurrences

**Top Keywords**:

- `complexity`: 142 mentions
- `SOLID`: 106 mentions
- `refactor`: 86 mentions
- `code review`: 68 mentions
- `code quality`: 48 mentions
- `maintainability`: 40 mentions
- `technical debt`: 34 mentions
- `testability`: 22 mentions
- `coupling`: 20 mentions
- `single responsibility`: 15 mentions

### 2.2 Real Usage Patterns

#### Case Study 2: CVA Install Scripts Refactoring

**Context**: 6 duplicated install scripts (768 lines, 46.6% duplication)

**Quality Issues Identified**:

1. **Duplication**: 358 lines duplicated across 6 scripts
2. **Coupling**: Environment-specific logic embedded in each script
3. **Cohesion**: Mixed concerns (validation, copying, configuration)
4. **Testability**: Difficult to test due to mixed responsibilities

**Refactoring Applied**:

- Extract common patterns to module
- Configuration-driven architecture
- Thin wrapper pattern for backward compatibility
- Function-per-concern design

**Outcome**:

- Duplication: 46.6% → <5%
- Unique logic locations: 6 → 1
- Configuration in code: Yes → No (extracted to Config.psd1)

### 2.3 Natural Language Triggers

Real phrases from sessions:

- "This is hard to test"
- "Should I refactor this?"
- "Is this too complex?"
- "How can I improve maintainability?"
- "Code review concerns"
- "Refactor for loose coupling and high cohesion"
- "Achieve programming by intention"

### 2.4 Quality Assessment Framework Observed

**CLAUDE.md Constraints Applied**:

1. Cyclomatic complexity ≤ 10
2. Methods ≤ 60 lines
3. No nesting (deep conditional logic)
4. SOLID principles
5. DRY (Don't Repeat Yourself)
6. YAGNI (You Aren't Gonna Need It)

**Software Hierarchy of Needs** (bottom-up):

1. **Qualities**: Cohesion, Coupling, DRY, Encapsulation, Testability
2. **Principles**: Open-Closed, Separate Use from Creation
3. **Practices**: Programming by Intention, CVA, Encapsulate Constructors
4. **Wisdom**: GoF patterns
5. **Patterns**: Emerge from above (Strategy, Bridge, Adapter, Factory)

**Testability as Leverage**:
> "Hard to test indicates: poor encapsulation, tight coupling, Law of Demeter violation, weak cohesion, or procedural code."

### 2.5 Quality Metrics Observed

From actual sessions:

- Duplication rate: 46.6% (before) → <5% (after)
- Lines per function: 15-18 (90 lines duplicated in copy loop)
- Unique logic locations: 6 scripts → 1 module
- Configuration extraction: 0% → 100% (all env variations in Config.psd1)

### 2.6 Decision Points

**When to Refactor** (observed triggers):

1. Duplication exceeds 30%
2. Functions exceed 60 lines
3. Hard to write tests
4. Environment-specific logic embedded in multiple files
5. Configuration mixed with code logic

### 2.7 Skill Gap Analysis

**Current Behavior**: Manual code review with CLAUDE.md constraints

**Needed Capability**:

- Automated duplication detection
- Complexity scoring
- Testability assessment
- Coupling/cohesion analysis
- Refactoring recommendations

**Suggested Implementation**:

```powershell
pwsh .claude/skills/code-qualities/scripts/Invoke-QualityAssessment.ps1 `
    -Path "scripts/" `
    -Metrics "duplication,complexity,testability,coupling" `
    -Threshold @{ Duplication=30; Complexity=10; MethodLines=60 } `
    -OutputPath ".agents/analysis/code-quality-[component].md"
```

---

## 3. CVA (Commonality Variability Analysis)

### 3.1 Usage Frequency

**Total Matches**: 494 occurrences

**Top Keywords**:

- `extract`: 210 mentions
- `duplication`: 102 mentions
- `what changes`: 53 mentions
- `abstract`: 29 mentions
- `duplicated`: 27 mentions
- `abstraction`: 26 mentions
- `variation`: 25 mentions
- `CVA`: 11 mentions (explicit methodology reference)

### 3.2 Real Usage Pattern: Install Scripts CVA

**Context**: Consolidate 6 install scripts using CVA methodology

**Step 1: Identify Commonalities**

9 common patterns across all scripts:

1. Parameter declaration (~5 lines each)
2. Source directory resolution (~3 lines)
3. Source validation (~4 lines)
4. Destination directory creation (~4 lines)
5. Agent file discovery (~5 lines)
6. File copy loop (~15 lines)
7. Git repository validation (~7 lines)
8. .agents directory creation (~15 lines)
9. Instructions file handling (~18 lines)

**Total Commonality**: 358 duplicated lines

**Step 2: Identify Variabilities**

| Variability Dimension | Values | Location |
|----------------------|--------|----------|
| **Environment** | Claude, Copilot, VSCode | Source dir, file pattern, dest paths |
| **Scope** | Global, Repo | Path params, validation logic |
| **File Pattern** | `*.md`, `*.agent.md` | Discovery logic |
| **Instructions Handling** | Simple copy, Append with markers | Copy logic |

**Step 3: Build Matrix**

| Environment | Scope | Source Dir | File Pattern | Dest Dir |
|-------------|-------|------------|--------------|----------|
| Claude | Global | src/claude | *.md | ~/.claude/agents |
| Claude | Repo | src/claude | *.md | .claude/agents |
| Copilot | Global | src/copilot-cli | *.agent.md | ~/.copilot/agents |
| Copilot | Repo | src/copilot-cli | *.agent.md | .github/agents |
| VSCode | Global | src/vs-code-agents | *.agent.md | %APPDATA%/Code/User/prompts |
| VSCode | Repo | src/vs-code-agents | *.agent.md | .github/agents |

**Step 4: Extract Abstractions**

**Rows → Functions** (commonalities):

- `Test-SourceDirectory` (pattern 3)
- `Initialize-Destination` (pattern 4)
- `Get-AgentFiles` (pattern 5)
- `Copy-AgentFile` (pattern 6)
- `Test-GitRepository` (pattern 7)
- `Initialize-AgentsDirectories` (pattern 8)
- `Install-InstructionsFile` (pattern 9)

**Columns → Configuration** (variabilities):

- Environment configs in `Config.psd1`
- Scope-specific paths
- File patterns
- Instructions handling strategies

**Module Structure**:

```
scripts/
  install.ps1              # Unified entry point
  lib/
    Install-Common.psm1    # Common functions (rows)
    Config.psd1            # Environment configs (columns)
```

### 3.3 Natural Language Triggers

Real phrases from sessions:

- "Should I extract this?"
- "Is there duplication here?"
- "What varies between these implementations?"
- "What's common across all cases?"
- "Extract common components"
- "Identify commonalities and variabilities"
- "Build matrix where rows become [pattern]"

### 3.4 CVA Workflow Observed

**CLAUDE.md Definition**:
> For unclear requirements: identify commonalities first, then variabilities under them, then relationships. Build matrix where rows become Strategy patterns, columns become Abstract Factory. Greatest vulnerability is wrong or missing abstraction.

**Applied Steps** (from retrospective):

1. **Pattern-first analysis**: Identify duplication patterns before coding
2. **Configuration matrix**: Document variations in a matrix
3. **Phased migration**: Non-breaking additive phases
4. **Line count targets**: Explicit reduction goals (46.6% → <10%)

### 3.5 CVA Metrics

From actual refactoring:

- **Duplication identified**: 9 patterns, 358 lines
- **Duplication rate**: 46.6% before, <5% after
- **Abstractions extracted**: 11 functions
- **Configuration dimensions**: 2 (Environment × Scope)
- **Configuration values**: 6 combinations (3 envs × 2 scopes)

### 3.6 Decision Points

**When to Apply CVA**:

1. Multiple implementations with similar structure
2. Duplication rate > 30%
3. Adding new variant requires copying existing code
4. Configuration mixed with logic
5. Unclear which abstraction to use

**When CVA Succeeds** (observed):

- Requirements are unclear but patterns are visible
- Multiple variants exist with common structure
- Configuration can be extracted from code
- Matrix structure emerges naturally

### 3.7 Skill Gap Analysis

**Current Behavior**: Manual CVA application in analysis documents

**Needed Capability**:

- Duplication pattern detector
- Commonality/variability matrix builder
- Abstraction recommender
- Configuration extractor
- Migration phasing planner

**Suggested Implementation**:

```powershell
pwsh .claude/skills/cva/scripts/Invoke-CVAAnalysis.ps1 `
    -Files "scripts/install-*.ps1" `
    -OutputPath ".agents/analysis/cva-[component].md" `
    -GenerateMatrix `
    -RecommendAbstractions
```

---

## 4. Cross-Cutting Patterns

### 4.1 Common Decision Workflow

All three skills follow similar pattern:

1. **Assessment** - Analyze current state
2. **Pattern Recognition** - Identify recurring structures
3. **Option Generation** - Enumerate alternatives
4. **Trade-off Analysis** - Pros/cons of each option
5. **Constraint Validation** - Check hard requirements
6. **Decision** - Recommend based on criteria
7. **Documentation** - Record decision with rationale
8. **Monitoring** - Define reassessment triggers

### 4.2 Integration with Existing Workflows

**ADR Review Integration**:

- Buy vs Build decisions → Architecture Decision Records
- ADR-003: Agent Tool Selection (buy vs build for tools)
- ADR-005: PowerShell-only (build decision)
- ADR-042: Python migration (build decision with exit strategy)

**Session Protocol Integration**:

- All three skills invoked during analysis phase
- Results documented in `.agents/analysis/`
- Decisions recorded in session logs
- Learnings extracted to retrospectives

**Agent Routing**:

- `analyst` → Research options (buy alternatives)
- `architect` → Design review (abstraction validation)
- `critic` → Plan validation (CVA matrix review)
- `implementer` → Refactoring execution

### 4.3 Memory Citations

**Usage-Mandatory Pattern**:
All three skills should update Serena memory with:

- Decision criteria applied
- Options evaluated
- Thresholds defined
- Patterns extracted

**Example Citation Format**:

```markdown
[!MEMORY: buy-vs-build-framework]
Decision: BUILD markdown-first traceability graph
Rationale: Constraint alignment (markdown-first, no MCP, simple tooling)
Scaling Threshold: 5,000 specs or 5s warm cache
Alternatives Evaluated: SQLite, NetworkX, Neo4j
Exit Strategy: Migrate to SQLite if threshold exceeded
```

---

## 5. Recommendations

### 5.1 Skill Priorities

**High Priority (Immediate Need)**:

1. **Buy vs Build Framework** - Frequent strategic decisions
   - 801 pattern matches
   - Clear decision template observed
   - Integration with ADR workflow

**Medium Priority (Frequent but Manual)**:
2. **Code Qualities Assessment** - Code review automation

- 623 pattern matches
- CLAUDE.md constraints well-defined
- Testability heuristics mature

**Medium Priority (Specialized Use)**:
3. **CVA Analysis** - Refactoring guidance

- 494 pattern matches
- Proven methodology
- Less frequent but high-impact

### 5.2 Implementation Approach

**Phase 0: Triage**

- Validate skill need against usage frequency
- Confirm triggers and natural language patterns
- Review existing manual workflows

**Phase 1: Deep Analysis**

- Extract decision frameworks from real cases
- Document metrics and thresholds
- Identify anti-patterns

**Phase 2: Specification**

- Define skill interface (SKILL.md)
- Specify scripts and parameters
- Plan integration points

**Phase 3: Generation**

- Implement PowerShell scripts
- Create templates and checklists
- Write tests

**Phase 4: Synthesis Panel**

- Route to architect, security, critic
- Validate against real cases
- Refine based on feedback

### 5.3 Natural Language Triggers

**Buy vs Build**:

- "Should we build custom or use existing [tool]?"
- "Evaluate TCO of [dependency]"
- "Is this core or context?"
- "What's our exit strategy if we build?"
- "When should we reassess this decision?"

**Code Qualities**:

- "Review code quality for [component]"
- "Is this too complex?"
- "How can I improve testability?"
- "Refactor for maintainability"
- "Check for coupling/cohesion issues"

**CVA**:

- "Identify commonalities and variabilities in [files]"
- "Should I extract this abstraction?"
- "What varies between these implementations?"
- "Build CVA matrix for [component]"
- "Recommend pattern for [variation]"

### 5.4 Success Metrics

**Adoption Metrics**:

- Skill invocation frequency (target: >5 uses/month)
- Manual analysis reduction (target: 80% automated)
- Decision quality (track reassessment rate)

**Quality Metrics**:

- Decision alignment with project constraints (target: 100%)
- Time saved per analysis (target: 60 minutes)
- Consistency of analysis format (target: 95%)

---

## 6. Appendix: Real Examples

### A.1 Buy vs Build: Traceability Graph

**File**: `.agents/analysis/traceability-build-vs-buy.md`

**Decision**: BUILD - Continue markdown-first implementation

**Key Analysis**:

- Current complexity: O(n × m), acceptable for n < 10,000
- Performance: 500ms → <100ms with caching (80% reduction)
- Constraint alignment: Markdown-first, no MCP, simple tooling
- Scaling threshold: 5,000 specs or 5s warm cache
- Projected timeline: 40 years to reach 5,000 specs (unrealistic)
- Exit strategy: SQLite migration if needed (2-3 days engineering time)

### A.2 Code Qualities: Install Scripts

**File**: `.agents/retrospective/2025-12-15-cva-install-scripts.md`

**Quality Issues**:

- Duplication: 46.6% (358/768 lines)
- Unique logic locations: 6 scripts
- Configuration in code: Yes

**Refactoring**:

- Duplication: <5% after refactoring
- Unique logic: 1 module
- Configuration: Extracted to Config.psd1

### A.3 CVA: Install Scripts

**File**: `.agents/planning/cva-install-scripts.md`

**CVA Application**:

- Commonalities: 9 patterns identified
- Variabilities: 2 dimensions (Environment × Scope)
- Matrix: 3 environments × 2 scopes = 6 combinations
- Abstractions: 11 functions extracted
- Configuration: Config.psd1 with 6 variants

---

## 7. Conclusion

All three skills have demonstrated need through frequent real-world usage:

- **Buy vs Build**: 801 matches, strategic decisions
- **Code Qualities**: 623 matches, refactoring guidance
- **CVA**: 494 matches, abstraction discovery

Natural language triggers are well-established. Decision frameworks are mature and proven. Integration points with existing workflows are clear.

**Recommendation**: Proceed with skill implementation in priority order:

1. Buy vs Build Framework (highest impact)
2. Code Qualities Assessment (automation opportunity)
3. CVA Analysis (specialized but proven)

---

*Generated by Explore Agent - Skill Usage Pattern Analysis*
*Date: 2026-02-07*
*Sources: 100+ session logs, architecture reviews, retrospectives*
