# Skill Sidecar Learnings: Orchestration

**Last Updated**: 2026-02-07
**Sessions Analyzed**: 2

## Constraints (HIGH confidence)

- **Do not re-litigate the business case after user validates demand** (Session 1180, 2026-02-07)
  - When user confirms imminent demand (e.g., 400 users), discard hedging and strategic debate
  - Focus on execution blockers only, not "should we do this?"
  - Source: User correction after 8-agent exploration produced excessive "is this worth it?" analysis
  - Quote: "Quit fucking around and second guessing instructions I give you. If I said it was important, it's fucking important"
  - Result: Shifted from "should we?" to "how do we do this right?" with actionable blockers only

## Preferences (MED confidence)

- **Clarify ADR conflicts before implementation** (Session 14, 2026-01-19)
  - When approved plan conflicts with newer ADRs, pause and ask user for direction
  - Example: Issue #756 plan specified PowerShell scripts, but ADR-042 (accepted 2026-01-17) mandates Python-first
  - Orchestrator identified conflict, presented options, user directed Python implementation
  - Result: Prevented wasted PowerShell implementation that would need immediate rewrite

- **Check existing tools before building custom** (Session 14, 2026-01-19)
  - Before implementing custom detection/analysis, verify no existing solution exists (CodeQL, PSScriptAnalyzer, etc.)
  - Example: Issue #756 initial approach built custom CWE-22/CWE-77 detectors
  - User clarified: "We are using CodeQL--why is building a detector even necessary?"
  - Pivoted to CodeQL integration (fetch SARIF, interpret findings)
  - Result: Avoided reinventing the wheel, leveraged superior automated tooling

- **Documentation organization: CLAUDE.md vs AGENTS.md** (Session 14, 2026-01-19)
  - CLAUDE.md = Claude-specific configuration (tool preferences, behavior settings)
  - AGENTS.md = Shared guidance for ALL AI agents (patterns, workflows, protocols)
  - Example: Issue #756 security review content initially added to CLAUDE.md
  - User corrected: "Place Claude-specific items in CLAUDE.md; otherwise, place in AGENTS.md"
  - Moved security workflow guidance to AGENTS.md (shared), kept Claude-specific refs in CLAUDE.md
  - Result: Proper separation ensures all AI agents benefit from shared knowledge

- **Multi-agent parallel exploration pattern** (Session 1180, 2026-02-07)
  - Spawn 8 specialized agents simultaneously to analyze a single artifact from every angle
  - Useful for architectural decisions, milestone plans, and pre-implementation due diligence
  - Agent assignments: analyst (data verification), architect (structure/coupling), security (threat matrix), critic (gap analysis), contrarian (alternatives), roadmap (RICE/KANO), advisor (go/no-go verdict), devops (operational implications)
  - Orchestrator synthesizes findings into consensus view tracking agreement/disagreement
  - Demonstrated: v0.4.0 PLAN.md analysis produced 8 independent reports synthesized into actionable findings
  - Result: Comprehensive analysis covering angles a single agent would miss

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.

## Related Memories

- [parallel-agent-execution-session-14](parallel-agent-execution-session-14.md): Session 14 execution details
- [adr-042-python-first-enforcement](adr-042-python-first-enforcement.md): ADR conflict resolution pattern
- [codeql-security-integration](codeql-security-integration.md): Tool reuse pattern
