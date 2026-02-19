# Skill ROI Analysis: PR Reviewer Feedback Patterns

**Statement**: Analysis of 100 closed PRs (2026-01-15 to 2026-02-08) reveals Code Qualities Assessment skill would address 27% of reviewer feedback, while Buy vs Build Framework (1%) and CVA Analysis (0%) show minimal applicability to ai-agents repository workflow.

**Evidence**: 75+ substantive review comments across 30 PRs with meaningful feedback

## Key Findings

### Skill Applicability Rankings

1. **Code Qualities Assessment: HIGH ROI (27% of feedback)**
   - Error handling improvements: PRs #982, #981, #845
   - Module extraction for cohesion: PRs #1046, #830, #825
   - Test coverage gaps: PRs #989, #977, #825
   - DRY violations: PRs #1084, #989, #830

2. **Buy vs Build Framework: LOW ROI (1% of feedback)**
   - Only 1 instance found: PR #962 (skill-installer adoption)
   - Feedback focused on security (version pinning), not strategic decision
   - Repository work is internal tooling, not product development

3. **CVA Analysis: NO ROI (0% of feedback)**
   - Zero instances of wrong abstraction feedback
   - Codebase is procedural (PowerShell/Python scripts), not object-oriented
   - No domain modeling requiring abstraction analysis

### Feedback Distribution

- Security vulnerabilities: 60% (path traversal CWE-22, command injection CWE-78)
- Code quality: 27% (cohesion, coupling, testability, duplication)
- Architecture: 11% (ADR compliance, design decisions)
- Build vs buy: 1%
- CVA/abstraction: 0%

### Top 10 Reviewer Feedback Patterns

1. Path traversal vulnerability (12+ occurrences) - SECURITY, not code quality
2. Command injection risk (8+ occurrences) - SECURITY, not code quality
3. Missing/inadequate error handling (7+) - **Code Qualities Assessment**
4. Module extraction for reusability (6+) - **Code Qualities Assessment**
5. Test coverage gaps (5+) - **Code Qualities Assessment**
6. Duplication/DRY violations (4+) - **Code Qualities Assessment**
7. ADR compliance violations (4+) - Architecture governance
8. Unquoted variables in scripts (4+) - Style guide
9. Performance issues (3+) - **Code Qualities Assessment**
10. Documentation accuracy (3+) - Documentation quality

## Recommendations

**P0**: Train agents on Code Qualities Assessment skill
- Clear ROI: prevents 27% of review feedback
- Maps to Testability, Cohesion, Coupling, Non-redundancy dimensions
- Add pre-PR quality gate using this skill

**P2**: Create "when to use" guidance for Buy vs Build Framework
- Low signal (1%) suggests narrow applicability
- Clarify scope: product development decisions, not internal tooling

**P3**: Defer CVA Analysis agent training
- Zero signal in reviews
- Codebase mismatch: procedural scripts vs object-oriented domain models
- Consider for future if domain modeling increases

**P3**: Consider security-focused skill creation
- 60% of feedback is security-related
- Not addressed by current three skills
- Path traversal and command injection dominate

## Analysis Methodology

- Analyzed 100 most recent closed PRs using `gh pr list/view`
- Classified 75+ substantive review comments
- Excluded automated status messages and bot quota errors
- Focused on gemini-code-assist, copilot-pull-request-reviewer human feedback
- Time period: 2026-01-15 to 2026-02-08 (3+ weeks)

## Related

- [skills-quality-index](skills-quality-index.md)
- Full report: `.agents/analysis/closed-pr-reviewer-patterns-2026-02-08.md`
