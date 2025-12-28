# ADR Debate Log: ADR-020 Feature Request Review Step

## Summary

- **Rounds**: 1
- **Outcome**: Consensus with conditions
- **Final Status**: NEEDS REVISION (proceed after addressing P0/P1 issues)

## Round 1 Summary

### Agent Reviews

| Agent | Position | Key Concern |
|-------|----------|-------------|
| **Architect** | Approve with P1 issues | Role mismatch, workflow size violation, output format undefined |
| **Critic** | NEEDS REVISION | 5 P0 issues - missing action steps, agent role conflict |
| **Independent-Thinker** | BLOCK (role mismatch) | Analyst agent already has Feature Request Review capability |
| **Security** | Approve with required changes | P0: Parsing functions undefined, need hardened regex |
| **Analyst** | PROCEED with modifications | MCP claims incorrect, prompt file exists, pattern is sound |
| **High-Level-Advisor** | DEFER | No success metrics, P2 platform investment, PR queue backlog |

### Consensus Points (All Agree)

1. **Parsing functions don't exist** - `Get-FeatureReviewRecommendation`, `Get-FeatureReviewAssignees`, `Get-FeatureReviewLabels` are referenced but not implemented
2. **Implementation follows ADR-005/ADR-006 patterns** - Uses thin workflow with PowerShell modules
3. **Conditional execution is correct** - Only runs for `category=enhancement`
4. **Prompt file already exists** - `.github/prompts/issue-feature-review.md` (170 lines, well-structured)
5. **Security validation required** - Hardened regex patterns needed for assignee/label parsing

### Conflicts Identified

#### Conflict 1: Agent Choice (Critic vs Analyst)

| Agent | Position | Evidence |
|-------|----------|----------|
| ADR-020 | Use critic | "Constructively skeptical" matches tone |
| Independent-Thinker | Use analyst | Analyst lines 178-215 already define Feature Request Review |
| Architect | Role mismatch concern | Critic scoped to "plan validation" not feature evaluation |
| High-Level-Advisor | Persona mismatch | Critic is skeptical; prompt wants polite thanks |
| Analyst | Critic acceptable | Prompt creates "friendly critic" persona effectively |

**Resolution**: Use analyst agent.
- Analyst already has Feature Request Review template
- Analyst has richer tool access (web search, DeepWiki)
- Critic's constraints explicitly exclude feature evaluation
- If critic is used, its role definition must be expanded (requires separate ADR)

#### Conflict 2: Proceed vs Defer

| Agent | Position | Rationale |
|-------|----------|-----------|
| High-Level-Advisor | DEFER | 9 PRs waiting, Copilot CLI is P2, no success metrics |
| Analyst | PROCEED with mods | Real gap exists, 7-8 hours implementation |
| Critic | Address P0s first | Missing action steps block automation |
| Architect | Address P1s first | Workflow size, output format issues |
| Security | Approve with changes | Security patterns must be implemented |

**Resolution**: PROCEED with conditions.
- The feature addresses a real gap (inconsistent feature evaluation)
- Implementation effort is modest (7-8 hours)
- P2 platform investment is acceptable given infrastructure reuse
- Must address P0 issues before merge

#### Conflict 3: Issue Priority Classification

**Consolidated Priority Classification**:

| Issue | Final Priority | Rationale |
|-------|---------------|-----------|
| Agent role conflict (critic vs analyst) | P0 | Core architectural decision affects implementation |
| Parsing functions undefined | P0 | Blocks implementation entirely |
| Output format not parseable | P0 | Current Markdown format hard to parse |
| ADR documentation inaccuracy (MCP claims) | P0 | Misleads future readers |
| Assignee/label validation | P1 | Security requirement per existing patterns |
| No action steps for parsed outputs | P1 | Automation value unclear without this |
| Parse error handling | P1 | Failure mode undefined |
| Test coverage (Pester tests) | P1 | ADR-006 requires 80% coverage |
| Workflow size (481 lines) | P1 | Violates ADR-006 100-line guidance |
| Success metrics undefined | P2 | Nice to have for measuring effectiveness |
| NEEDS_RESEARCH outcome handler | P2 | Edge case can be deferred |

### Key Discovery: MCP Tool Claims Incorrect

The analyst agent discovered that ADR-020's claim "MCP tools NOT available in Copilot CLI" is **incorrect**:

- Copilot CLI ships with GitHub MCP server by default
- Custom MCP servers can be added from registry
- [Source: GitHub Changelog Oct 2025](https://github.blog/changelog/2025-10-28-github-copilot-cli-use-custom-agents-and-delegate-to-copilot-coding-agent/)

However, the **prompt file** correctly handles this by:
- Not referencing MCP tools by name
- Explicitly stating tool limitations
- Instructing agent to mark unknowns as "UNKNOWN - requires manual research"

**Action**: Update ADR-020 to correct MCP availability claims.

### Agent Positions Summary

| Agent | Accept | Disagree-and-Commit | Block | Notes |
|-------|--------|---------------------|-------|-------|
| Architect | | X | | Address P1s (role, workflow size, output format) |
| Critic | | | X | 5 P0 issues unresolved |
| Independent-Thinker | | | X | Role mismatch must be fixed |
| Security | | X | | Implement hardened parsing first |
| Analyst | X | | | Proceed with modifications |
| High-Level-Advisor | | | X | DEFER until PR queue cleared |

### Consensus Status

**Not yet reached** - 3 agents blocking, 2 disagree-and-commit, 1 accept.

However, all blocking concerns are addressable:
- Critic: Address P0 issues (parsing functions, action steps)
- Independent-Thinker: Switch to analyst agent
- High-Level-Advisor: Define success metrics, acknowledge PR queue priority

## Final Recommendations

### Required Changes (P0)

1. **Switch to analyst agent** - Or formally expand critic role in separate ADR
2. **Update ADR-020 MCP tool claims** - Current documentation is incorrect
3. **Change prompt output format** - Use parseable tokens instead of Markdown

```markdown
# Before (hard to parse)
- **Assignees**: user1, user2
- **Labels**: enhancement, needs-triage

# After (parseable)
ASSIGNEES: user1,user2
LABELS: enhancement,needs-triage
```

4. **Implement parsing functions** with hardened regex per security review

### Should Fix (P1)

5. **Define action steps** - What happens with parsed assignees/labels?
6. **Add parse error handling** - Fallback for malformed AI output
7. **Write Pester tests** - 80% coverage per ADR-006
8. **Add assignee validation** - GitHub username pattern regex
9. **Consider workflow refactoring** - 481 lines vs 100-line guidance

### Nice to Have (P2)

10. **Define success metrics** - Recommendation accuracy, submitter satisfaction
11. **Handle NEEDS_RESEARCH outcome** - Route to manual review queue
12. **Evaluate analyst vs critic** - A/B test if both viable

## Implementation Path

```text
Phase 1: Update ADR (P0)
├── Correct MCP tool claims
├── Switch agent: critic → analyst
└── Update prompt output format for parsing

Phase 2: Implement Core (P1)
├── Implement 3 PowerShell parsing functions
├── Add hardened regex validation
├── Write Pester tests (80% coverage)
└── Add workflow step after categorization

Phase 3: Add Automation (P1)
├── Define action steps for parsed outputs
├── Add parse error handling
└── Integrate with comment posting

Phase 4: Enhance (P2)
├── Add success metrics collection
├── Handle NEEDS_RESEARCH routing
└── Consider workflow size refactoring
```

## Next Actions

1. **ADR Author**: Revise ADR-020 to address P0 issues
2. **Implementer**: Implement parsing functions after ADR revision
3. **QA**: Validate with sample issues after implementation
4. **Architect**: Consider separate ADR for agent role expansion if keeping critic

## Debate Artifacts

- Architect review: See agent output above
- Critic review: `.agents/critique/ADR-020-feature-request-review-critique.md`
- Analyst review: `.agents/analysis/020-adr-020-feature-request-review-analysis.md`
- Security review: See agent output above
- Independent-Thinker review: See agent output above
- High-Level-Advisor review: See agent output above

---

**Debate Version**: 1.0
**Date**: 2025-12-23
**Orchestrator**: ADR Review Skill
