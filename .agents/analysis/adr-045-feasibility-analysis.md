# Analysis: ADR-045 Framework Extraction Feasibility

## 1. Objective and Scope

**Objective**: Evaluate the technical feasibility, evidence quality, and hidden costs of extracting the multi-agent framework from rjmurillo/ai-agents into rjmurillo/awesome-ai as a Claude Code plugin marketplace.

**Scope**:
- Evidence verification for key claims (65% split, zero coupling, session estimates)
- Hidden cost identification (maintenance overhead, migration complexity)
- Prerequisite dependency assessment (v0.3.1 timeline)
- Risk evaluation for plugin architecture

## 2. Context

ADR-045 proposes extracting the reusable framework from ai-agents into a standalone plugin marketplace with 4 plugins: core-agents, framework-skills, session-protocol, and quality-gates. The ADR claims this represents ~65% of the codebase and estimates 15-22 sessions. v0.3.1 (PowerShell-to-Python migration, 12 months) is listed as a hard prerequisite.

## 3. Approach

**Methodology**: Evidence-based verification using repository analysis, code inspection, and dependency mapping.

**Tools Used**:
- File system analysis (find, wc, grep)
- Repository structure inspection
- Cross-reference with v0.3.1 plan
- Plugin marketplace research document verification
- Historical session data sampling

**Limitations**:
- Cannot verify actual extraction complexity without attempting migration
- Session estimates based on plan document, not empirical data from similar work
- No existing inventory document to validate the 65% claim

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| 41 skills exist | `.claude/skills` directory count | High |
| 18 agent templates with .agents paths | `templates/agents/*.shared.md` grep | High |
| 14 agent templates reference `.agents/` paths | grep output | High |
| v0.3.1 has 16 open issues, 2 closed | GitHub API milestone 7 | High |
| v0.3.1 timeline: 12 months (ends 2027-01-25) | PowerShell-migration.md Gantt chart | High |
| v0.4.0 has 7 open issues, 0 closed | GitHub API milestone 8 | High |
| No pre-existing inventory classification | find command for *inventory* files | Medium |
| Current .claude-plugin/marketplace.json exists | File read | High |
| 142 PowerShell scripts remain | v0.3.1 plan inventory | High |
| 40 PowerShell files in github skill alone | find .claude/skills/github | High |

### Facts (Verified)

- **Skill count**: 41 skills confirmed via SKILL.md file count, matching ADR claim.
- **Agent templates**: 18 shared templates confirmed, matching ADR claim.
- **Path coupling**: 14 of 18 agent templates contain hard-coded `.agents/` paths in "Save to:" directives, contradicting "zero coupling" claim.
- **v0.3.1 prerequisite**: 16 open issues with 12-month timeline ending January 2027, blocking v0.4.0 start.
- **PowerShell migration scope**: 142 non-test .ps1 files + 14 .psm1 modules remain, requiring full migration before extraction.
- **GitHub skill complexity**: 40 PowerShell scripts in github skill alone, representing significant migration effort.

### Hypotheses (Unverified)

- **65% framework split**: No rigorous inventory document found. Claim appears to be estimated from plan tables, not file-by-file classification.
- **15-22 session estimate**: Based on plan phase estimates (Phase 0: 1-2, Phase 1: 2-3, Phase 2: 4-6, etc.), but no empirical validation against similar past work.
- **"Zero coupling" for core-agents**: Agent templates contain hard-coded output paths (`.agents/analysis/`, `.agents/architecture/`), requiring parameterization.
- **Hook migration is straightforward**: Plan claims hooks.json format translation is simple, but .claude/settings.json shows 12+ hooks with complex matchers and PowerShell invocations requiring Python migration first.

## 5. Results

### Claim 1: "~65% framework, ~25% domain, ~10% hybrid"

**Finding**: Unsubstantiated estimate. No rigorous inventory document exists.

Evidence:
- Plan document provides classification table (line 127-136) but no detailed file-by-file inventory
- Categories show round percentages (100%, 68%, 75%, 70%) suggesting estimation, not counting
- No cross-reference to a complete classification document

**Data gap**: Requires file-by-file classification with explicit criteria before claiming 65%.

### Claim 2: "15-22 sessions estimated"

**Finding**: Plausible but optimistic. Based on phase estimates, not empirical data.

Evidence:
- Phase 0: 1-2 sessions (foundation)
- Phase 1: 2-3 sessions (agents)
- Phase 2: 4-6 sessions (skills)
- Phase 3: 3-4 sessions (protocol + gates)
- Phase 4: 3-4 sessions (wiring)
- Phase 5: 2-3 sessions (docs)
- Total: 15-22 sessions

**Risk**: GitHub skill extraction alone (Phase 2, moderate-coupling) requires migrating 40 PowerShell scripts from v0.3.1 first. Historical session count shows 529 total sessions, suggesting complex work often takes more sessions than planned.

### Claim 3: "Zero coupling" for core-agents

**Finding**: FALSE. Agent templates contain hard-coded project paths.

Evidence:
- 14 of 18 agent templates contain "Save to: `.agents/[subdirectory]`" directives
- Example (analyst.shared.md line 383): `Save to: .agents/analysis/NNN-[topic]-analysis.md`
- Example (architect.shared.md line 224): `Save to: .agents/architecture/ADR-NNNN-[decision-name].md`

**Implication**: Agent templates require path parameterization before extraction. This contradicts "zero coupling" and adds work to Phase 1.

### Claim 4: "28 framework skills" extractable with path parameterization

**Finding**: Partially verified count, but migration complexity underestimated.

Evidence:
- 41 total skills confirmed
- Plan claims 28 framework, 13 domain-specific
- BUT: github skill has 40 PowerShell scripts, memory skill has 13 PowerShell files
- v0.3.1 must complete first, which is 12 months away

**Risk**: "Moderate-coupling skills" (10 skills per plan line 297) include github, memory, adr-review, session-*, security-detection. These are ALL PowerShell-heavy and depend on v0.3.1 completing first.

### Claim 5: "Hook migration to hooks.json" is straightforward

**Finding**: Underestimated complexity. Hooks are PowerShell-based with complex matchers.

Evidence:
- .claude/settings.json shows 12+ hooks across 7 lifecycle events
- All hooks invoke PowerShell scripts: `pwsh -NoProfile -Command ...`
- Hooks reference .claude/hooks/*.ps1 scripts, not Python
- v0.3.1 Phase 4 (#1065) migrates hook scripts, estimated 10 days + dependency on #1053 (HookUtilities.psm1)

**Implication**: Hook extraction requires v0.3.1 Phase 4 completion (months 9-12), not just format translation.

### Claim 6: "Prerequisites: v0.3.0 + v0.3.1" timeline compatibility

**Finding**: CRITICAL BLOCKER. v0.3.1 ends January 2027, 11 months from now.

Evidence:
- v0.3.1 Gantt chart (PowerShell-migration.md lines 89-123) shows Phase 5 retirement milestone: 2027-01-25
- v0.3.1 has 16 open issues, 2 closed (12.5% complete by issue count)
- v0.3.1 includes 5 phases with sequential dependencies (P0 → P1 → P2 → P3 → P4 → P5)
- Skills extraction (Phase 2) depends on P1 completion (shared modules migration)
- Hooks extraction (Phase 3) depends on P4 completion (hook scripts migration, months 9-12)

**Implication**: v0.4.0 cannot realistically start before Q1 2027. ADR-045 does not acknowledge this 11-month delay.

### Claim 7: "4 plugins" maintenance overhead

**Finding**: Maintenance cost underestimated. 4 manifests + namespace migration impact.

Evidence:
- 4 plugin.json manifests to maintain (one per plugin)
- 1 marketplace.json manifest
- Namespace changes break all skill references: `/skill` → `/awesome-ai:skill`
- Plan (line 78-83) identifies breaking changes in SKILL.md files, CLAUDE.md, AGENTS.md, agent prompts, and CI workflows
- No automated migration tooling mentioned

**Hidden cost**: Every skill reference across 1489 .agents files, 245 skill files, and CI workflows requires manual or scripted update.

## 6. Discussion

### Feasibility Assessment

The extraction is **technically feasible** but **significantly riskier and costlier** than presented:

1. **Prerequisite blocker**: v0.3.1 is 11 months away. Starting v0.4.0 now would mean extracting PowerShell code only to immediately re-extract it as Python in 2027. This doubles effort.

2. **Coupling underestimated**: Agent templates are NOT zero-coupling. They embed hard-coded paths. Skills are NOT low-coupling; they depend on PowerShell modules that must migrate first.

3. **Session estimate unrealistic**: 15-22 sessions assumes clean separation. Evidence shows:
   - 14 agent templates need path parameterization
   - 40+ GitHub scripts need Python migration
   - 13 memory skill files need Python migration
   - 12+ hooks need PowerShell-to-Python conversion
   - All namespace references need updating

4. **Inventory rigor missing**: 65% framework claim is unsupported by file-by-file classification. Spot-checking reveals more coupling than claimed.

5. **Maintenance burden**: 4 plugins mean 4 version releases, 4 CHANGELOG files, 4 testing cycles. Namespace changes create permanent fork (consumers must update all `/skill` invocations).

### What the Evidence Shows

| ADR Claim | Reality |
|-----------|---------|
| "Zero coupling" agents | 14 of 18 templates have hard-coded paths |
| "15-22 sessions" | Likely 30-40+ given Python migration prerequisite |
| "v0.3.1 prerequisite" | Ends January 2027 (11 months), not mentioned as timeline blocker |
| "Straightforward hook migration" | 12+ PowerShell hooks need Python conversion first |
| "~65% framework" | No rigorous inventory; spot-checks show higher coupling |
| "28 framework skills extractable" | 10 moderate-coupling skills are ALL PowerShell-heavy |

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| **P0** | Block ADR-045 until v0.3.1 completes | Extracting PowerShell only to re-extract Python doubles effort | 0 (wait) |
| **P0** | Perform file-by-file inventory with classification criteria | 65% claim is unsupported; need evidence before architectural decision | 2-3 sessions |
| **P1** | Revise session estimate to 30-40 sessions minimum | Current estimate underestimates coupling and migration complexity | 1 session |
| **P1** | Prototype path parameterization on 3 agent templates | Validate "zero coupling" claim with concrete evidence | 1 session |
| **P1** | Evaluate 2-plugin model vs 4-plugin model | 4 plugins may be over-engineering; consider core + extensions | 1 session |
| **P2** | Add automated namespace migration tooling to plan | Manual updates across 1700+ files is error-prone | 2 sessions |
| **P2** | Document maintenance overhead of 4-plugin architecture | ADR should acknowledge version release, testing, and documentation multiplication | 0.5 sessions |

## 8. Conclusion

**Verdict**: **NEEDS-REVISION** with P0 blocking issues.

**Confidence**: High (based on empirical repository analysis and cross-referenced plans).

**Rationale**: The extraction is architecturally sound but **premature and underestimated**. Blocking issues:

1. **P0**: v0.3.1 prerequisite creates 11-month delay not acknowledged in ADR. Starting now means extracting PowerShell code that must be re-extracted as Python in 2027 (double effort).
2. **P0**: "Zero coupling" claim for agents is factually incorrect. 14 of 18 templates embed hard-coded paths.
3. **P0**: No rigorous inventory supports the 65% framework claim. Spot-checking reveals higher coupling than claimed.

### User Impact

- **What changes for you**: Delaying v0.4.0 to Q1 2027 pushes framework reusability by 11 months. However, starting now means redoing all work post-v0.3.1.
- **Effort required**: 30-40 sessions realistically, not 15-22. Doubling the estimate aligns with evidence.
- **Risk if ignored**: Extracting PowerShell-heavy code now wastes effort. When v0.3.1 completes (Python migration), all extracted PowerShell code must be re-extracted as Python, duplicating work.

### Revision Requirements (P0)

1. **Add explicit timeline dependency**: "v0.4.0 start date: February 2027 (post-v0.3.1 completion)."
2. **Remove "zero coupling" claim**: Replace with "low coupling pending path parameterization (14 templates affected)."
3. **Add rigorous inventory**: File-by-file classification with explicit framework/domain/hybrid criteria. Publish as appendix or separate document.
4. **Revise session estimate**: Update to 30-40 sessions based on:
   - Path parameterization for 14 agent templates (Phase 1)
   - Python versions required for 10 moderate-coupling skills (Phase 2)
   - Hook Python conversion (Phase 3)
   - Namespace migration automation + manual verification (Phase 4)
5. **Evaluate 2-plugin model**: Consider consolidating to core (agents + templates) and extensions (skills + protocol + gates) to reduce maintenance overhead.

### Next Steps (Recommendations for Orchestrator)

1. Route to **architect** to revise ADR-045 with P0 blocking issues addressed.
2. Route to **analyst** to create rigorous file-by-file inventory with classification criteria.
3. Route to **planner** to revise v0.4.0 plan with updated timeline (start: Q1 2027) and session estimates (30-40).
4. Route to **high-level-advisor** to evaluate strategic decision: 2-plugin model vs 4-plugin model for maintenance optimization.

## 9. Appendices

### Sources Consulted

- [ADR-045: Framework Extraction via Plugin Marketplace](./../architecture/ADR-045-framework-extraction-via-plugin-marketplace.md)
- [v0.4.0 Plan](./../projects/v0.4.0/PLAN.md)
- [v0.3.1 PowerShell Migration Plan](./../projects/v0.3.1/PowerShell-migration.md)
- [Plugin Marketplace Research](./claude-code-plugin-marketplaces.md)
- `.claude/settings.json` (hook configuration)
- `templates/agents/*.shared.md` (agent template inspection)
- Repository file counts (find, wc, grep analysis)
- GitHub API milestone data (v0.3.1, v0.4.0 status)

### Data Transparency

**Found**:
- 41 skills confirmed (matches claim)
- 18 agent templates confirmed (matches claim)
- 14 agent templates with hard-coded paths (contradicts "zero coupling")
- v0.3.1 timeline: 12 months, ending January 2027
- 40 PowerShell files in github skill
- 13 PowerShell files in memory skill
- 12+ hooks in .claude/settings.json (all PowerShell-based)

**Not Found**:
- File-by-file inventory supporting 65% framework claim
- Empirical session data validating 15-22 session estimate
- Analysis of 2-plugin vs 4-plugin maintenance trade-offs
- Automated namespace migration tooling plan
- Impact analysis of 11-month prerequisite delay
