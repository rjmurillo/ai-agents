# SkillForge Phase 1: Deep Analysis - Code Qualities Assessment

## Input Expansion

### Explicit Requirements
- Assess 5 code qualities: cohesion, coupling, encapsulation, testability, non-redundancy
- Scoring rubric for each quality (quantifiable)
- Works at method, class, and module levels
- Language-agnostic (C#, Python, TypeScript, etc.)
- Integration with Serena for symbol-level analysis (optional)
- Produces markdown report + JSON scores
- Triggers: "assess code quality", "evaluate maintainability", "check code qualities", "testability review"
- Tier 1 foundational design principle (9/10 timelessness)
- Programming by intention pattern (sergeant methods directing privates)

### Implicit Requirements
- Must be teachable to junior engineers (scoring should be objective)
- Should detect anti-patterns automatically
- Needs concrete examples for each quality level
- Should provide actionable remediation guidance
- Must integrate with existing code review workflows
- Output should be diffable across runs (for trend tracking)
- Should handle incremental analysis (changed files only)
- Needs to work in CI/CD pipelines
- Should support multiple programming paradigms (OOP, FP, procedural)

### Unknown Requirements (Questions to Explore)

1. **Scope granularity**: Should we assess individual functions within a class separately or aggregate?
2. **Weighting**: Are all 5 qualities equally important, or should they be weighted?
3. **Thresholds**: What scores constitute "pass" vs "needs improvement" vs "critical"?
4. **Historical tracking**: Should we track quality trends over time?
5. **Team calibration**: How do we ensure consistent scoring across different reviewers?
6. **Integration depth**: Should this trigger automated refactoring suggestions?
7. **Composite scoring**: Should there be an overall "maintainability index"?
8. **Context awareness**: Should scoring differ for tests vs production code?

## 11 Thinking Models Analysis

### 1. First Principles
**Core truth**: Code qualities are observable properties, not subjective opinions.

- **Cohesion**: How related are elements within a boundary?
- **Coupling**: How dependent are boundaries on each other?
- **Encapsulation**: How hidden are implementation details?
- **Testability**: How easily can behavior be verified in isolation?
- **Non-redundancy**: How unique is each piece of knowledge?

These map to fundamental software engineering theorems (Conway's Law, Law of Demeter, DRY principle).

### 2. Inversion Thinking
**What if we measured code BADNESS instead of GOODNESS?**

Anti-metrics:
- High coupling score = LOW quality
- Low cohesion score = LOW quality
- Exposed internals = LOW encapsulation
- Hard to mock = LOW testability
- Copy-paste detected = LOW non-redundancy

This suggests we should have both positive and negative indicators per quality.

### 3. Second-Order Consequences
**What happens after assessment?**

- Engineers see bad scores → defensive behavior?
- Management uses scores for performance reviews → gaming the system?
- Automated rejection in CI → circumvention attempts?
- Trends tracked over time → quality debt becomes visible?

**Design constraint**: Scores should inform, not punish. Focus on trend improvement, not absolute values.

### 4. Systems Thinking
**How does this fit into the broader system?**

```
Code Quality Assessment
    ↓ informs
Architecture Decisions (ADRs)
    ↓ influences
Code Reviews (pr-comment-responder)
    ↓ feeds into
Refactoring Plans (planner skill)
    ↓ validated by
Test Coverage (qa agent)
```

**Integration points**:
- Should trigger `decision-critic` when quality degrades
- Should feed `planner` for refactoring roadmaps
- Should inform `adr-review` with quality impact analysis
- Should integrate with `analyze` skill for comprehensive reports

### 5. Constraints-Based Thinking
**What are the hard constraints?**

- **Time**: Must complete assessment in <30 seconds for CI
- **Accuracy**: False positives destroy trust
- **Scope**: Cannot analyze entire codebase every commit
- **Languages**: Must work across 5+ languages without language-specific parsers
- **Tooling**: Cannot require external dependencies (should use Serena when available)

### 6. Probabilistic Thinking
**Where is certainty impossible?**

- Cohesion assessment requires understanding *intent* (probabilistic)
- Testability depends on testing *strategy* chosen (context-dependent)
- Non-redundancy across file boundaries (requires global knowledge)

**Mitigation**: Provide confidence scores alongside assessments.

### 7. Analogical Thinking
**What's similar?**

- Medical diagnostic rubrics (symptom → diagnosis → treatment)
- Building inspection checklists (structural soundness scoring)
- Code review checklists (but automated + quantified)
- Linters (but for design, not syntax)

**Insight**: Like medical diagnostics, we need differential diagnosis capability - multiple quality issues can have similar symptoms.

### 8. Ecosystem Thinking
**What's the broader context?**

Existing tools:
- SonarQube: Complexity metrics
- CodeClimate: Maintainability scores
- NDepend (.NET): Dependency analysis
- Pylint: Code quality for Python

**Gap**: None provide unified, language-agnostic quality assessment across all 5 qualities with educational rubrics.

### 9. Risk Analysis
**What can go wrong?**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| False positives | High | Medium | Require manual review flag |
| Gaming metrics | Medium | High | Use composite indicators |
| Analysis too slow | Medium | Medium | Incremental analysis only |
| Language-specific edge cases | High | Low | Graceful degradation |
| Disagreement on scoring | High | Medium | Calibration examples |

### 10. Time Horizons
**How does this evolve?**

- **Year 1**: Manual execution, educational focus
- **Year 3**: CI integration, automated blocking
- **Year 5**: ML-based pattern recognition for quality
- **Year 10**: Still relevant (qualities are timeless)

**Timelessness score: 9/10** - The 5 qualities are foundational principles that won't change.

### 11. Incentive Analysis
**What behaviors does this encourage?**

- Positive: Deliberate design, testable code, knowledge sharing
- Negative: Over-engineering, excessive abstraction, metric gaming

**Design principle**: Reward improvement velocity, not absolute scores.

## Automation Lens Analysis

### Automation Opportunities

1. **Symbol extraction** (Serena integration)
   - Auto-detect class/method boundaries
   - Map dependency graphs
   - Identify coupling patterns

2. **Pattern matching** (scripts/detect_antipatterns.py)
   - God objects (>500 LOC classes)
   - Feature envy (methods using other class data)
   - Primitive obsession
   - Shotgun surgery patterns

3. **Metric calculation** (scripts/calculate_scores.py)
   - Cyclomatic complexity
   - Coupling metrics (afferent/efferent)
   - Method length distribution
   - Duplication detection

4. **Report generation** (scripts/generate_report.py)
   - Markdown summary
   - JSON scores (for CI)
   - Trend charts (if historical data)
   - Remediation suggestions

5. **CI integration** (scripts/ci_check.py)
   - Quality gate enforcement
   - PR comment generation
   - Historical comparison
   - Failure/warning thresholds

### Scripts to Create

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `assess.py` | Main orchestrator | 0=pass, 1=fail, 10=quality degraded |
| `score_cohesion.py` | Cohesion scoring | 0=analyzed |
| `score_coupling.py` | Coupling scoring | 0=analyzed |
| `score_encapsulation.py` | Encapsulation scoring | 0=analyzed |
| `score_testability.py` | Testability scoring | 0=analyzed |
| `score_nonredundancy.py` | Duplication scoring | 0=analyzed |
| `generate_report.py` | Report creation | 0=success |
| `ci_check.py` | CI gate enforcement | 0=pass, 10=degraded, 11=threshold |

## Regression Questions (3 Rounds)

### Round 1: Clarification

**Q1**: How do we handle quality trade-offs? (e.g., high cohesion + high coupling in a monolith)
**A**: Score each quality independently, let users interpret trade-offs based on context.

**Q2**: Should we differentiate between test code and production code scoring?
**A**: Yes - testability matters less in test code; add context parameter.

**Q3**: How do we handle generated code (protobuf, OpenAPI)?
**A**: Exclude via configuration; provide .qualityignore pattern matching.

**Q4**: What about legacy code with no tests?
**A**: Low testability score, but provide "legacy exemption" flag for tracking without blocking.

**Q5**: How granular should remediation suggestions be?
**A**: File-level for overview, symbol-level for details (leverage Serena).

### Round 2: Edge Cases

**Q6**: How do we score functional programming code (no classes)?
**A**: Adapt rubrics - assess modules instead of classes, functions instead of methods.

**Q7**: What if a file has mixed paradigms (class + free functions)?
**A**: Score each paradigm element separately, aggregate at file level.

**Q8**: How do we handle dynamic languages (Python duck typing)?
**A**: Encapsulation scoring adapts - focus on naming conventions (private via `_`).

**Q9**: Should we penalize large files?
**A**: Indirectly - large files often have low cohesion, score that instead.

**Q10**: How do we detect coupling across repositories?
**A**: Out of scope for v1 - focus on intra-repo coupling only.

### Round 3: Integration

**Q11**: How does this integrate with existing linters (pylint, eslint)?
**A**: Complementary - linters check syntax/style, this checks design. Run both.

**Q12**: Should this replace code review checklists?
**A**: No - augments them. Automated checks + human judgment.

**Q13**: How do we calibrate scoring across teams?
**A**: Provide reference examples (good/bad for each score level) in `references/calibration-examples.md`.

**Q14**: Should we expose raw metrics (LOC, CC) or just derived scores?
**A**: Both - scores for quick assessment, raw metrics for deep dives.

**Q15**: How do we prevent alert fatigue?
**A**: Focus on regressions (delta), not absolute values. Only warn on degradation.

## No New Insights After Round 3

Iteration stops - requirements sufficiently explored.

## Key Design Decisions

1. **Scoring scale**: 1-10 (not percentages) for clarity
2. **Granularity**: Symbol-level raw scores → file-level aggregated → module-level summary
3. **Context awareness**: `--context production|test|generated` flag
4. **Incremental mode**: `--changed-only` for CI performance
5. **Serena integration**: Optional but recommended for accuracy
6. **Output formats**: Markdown (human), JSON (machine), HTML (dashboard)
7. **Quality gates**: Configurable thresholds via `.qualityrc.json`
8. **Trend tracking**: JSON output includes timestamp + git SHA for historical analysis
9. **Remediation**: Auto-link to relevant ADRs, patterns, refactoring guides
10. **Education**: Embed "why this matters" explanations in reports

## Timelessness Validation

**Score: 9/10**

Reasons:
- Code qualities are computer science fundamentals (decades old)
- Language-agnostic design (survives language shifts)
- Principle-based, not tool-based
- Applies to all programming paradigms
- Educational value transcends trends

Potential obsolescence risk (-1):
- If AI fully automates refactoring (humans stop caring about metrics)
- Mitigation: Scores still useful for AI-driven refactoring prioritization

## Next Steps → Phase 2: Specification

Requirements are fully expanded. Ready to generate XML specification.
