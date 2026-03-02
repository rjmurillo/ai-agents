# ADR-045 Framework Extraction Feasibility Analysis

**Statement**: ADR-045 proposes extracting the ai-agents framework into awesome-ai as a plugin marketplace, but contains P0 blocking issues: (1) v0.3.1 prerequisite creates 11-month delay not acknowledged, (2) "zero coupling" claim is false (14 of 18 agent templates have hard-coded paths), (3) 65% framework claim lacks rigorous inventory, (4) session estimate (15-22) is 50% underestimated.

**Evidence**:
- v0.3.1 timeline: 12 months ending January 2027 (PowerShell-migration.md Gantt chart, 16 open issues)
- Agent template coupling: 14 of 18 templates contain "Save to: .agents/[path]" directives (grep verification)
- No inventory document: find command confirms no *inventory* or *classification* files exist
- Skill migration complexity: github skill has 40 PowerShell scripts, memory skill has 13 (requires v0.3.1 first)
- Hook migration underestimated: 12+ hooks in .claude/settings.json are all PowerShell-based (require v0.3.1 Phase 4)

## Details

### Critical Findings

1. **v0.3.1 Prerequisite Blocker**: ADR-045 lists v0.3.1 as prerequisite but does not acknowledge 11-month timeline. Starting v0.4.0 now means extracting PowerShell code only to re-extract it as Python in 2027 (double effort).

2. **False "Zero Coupling" Claim**: Agent templates (Phase 1, claimed cleanest extraction) contain hard-coded `.agents/` paths:
   - analyst.shared.md line 383: `Save to: .agents/analysis/NNN-[topic]-analysis.md`
   - architect.shared.md line 224: `Save to: .agents/architecture/ADR-NNNN-[decision-name].md`
   - 14 of 18 templates affected

3. **Missing Inventory Rigor**: 65% framework claim based on plan table estimates (100%, 68%, 75% round numbers), not file-by-file classification. No inventory document exists to validate claim.

4. **Session Estimate Underestimated**: 15-22 sessions based on phase estimates, but evidence shows:
   - 14 agent templates need path parameterization (not in plan)
   - 10 moderate-coupling skills are ALL PowerShell-heavy (github, memory, session-*, adr-review)
   - Namespace migration across 1700+ files (minimal effort allocated)
   - Realistic estimate: 30-40 sessions

5. **Hook Migration Complexity**: Plan claims hooks.json format translation is straightforward, but all 12+ hooks invoke PowerShell scripts. Requires v0.3.1 Phase 4 completion (months 9-12).

### Verdict

**NEEDS-REVISION** with P0 blocking issues.

Required revisions:
1. Add explicit timeline dependency: "v0.4.0 start date: February 2027 (post-v0.3.1 completion)"
2. Remove "zero coupling" claim; replace with "low coupling pending path parameterization"
3. Add rigorous file-by-file inventory with classification criteria
4. Revise session estimate to 30-40 sessions
5. Evaluate 2-plugin model vs 4-plugin model for maintenance optimization

### Cross-Session Context

- Analysis document: `.agents/analysis/adr-045-feasibility-analysis.md`
- Related: adr-042-python-first-enforcement.md (v0.3.1 prerequisite)
- Related: v0.3.1 PowerShell migration plan (12-month timeline, 16 open issues)
- Related: claude-code-plugin-marketplaces.md (plugin architecture research)

### Lessons Learned

1. **Verify coupling claims empirically**: "Zero coupling" requires grep verification, not assumptions.
2. **Prerequisite timelines must be explicit**: An 11-month blocking dependency should be in the decision summary, not buried in prerequisites.
3. **Inventory rigor before architecture**: 65% framework claim requires file-by-file classification, not round-number estimates.
4. **Session estimates require historical calibration**: 15-22 sessions for extracting 65% of codebase across 4 plugins is optimistic; similar work (v0.3.1 migration) shows 12-month timeline.

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-017-quantitative-analysis](adr-017-quantitative-analysis.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
