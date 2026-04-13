# Epic: 2-Variant Agent Consolidation

## Vision

A streamlined agent repository where VS Code and GitHub Copilot CLI agents share a single source of truth, with platform-specific differences handled automatically at build time. Maintainers edit once, deploy twice, and CI catches any unintended drift before it becomes technical debt.

## User Story

**As a** repository maintainer
**I want** VS Code and Copilot CLI agents consolidated into a single source
**So that** I maintain 36 files instead of 54, reducing sync burden by 33%

---

## Outcomes (not outputs)

- [ ] Maintainers never manually sync content between VS Code and Copilot CLI variants
- [ ] Platform-specific frontmatter is generated automatically, eliminating copy-paste errors
- [ ] Semantic drift between Claude and VS Code/Copilot is detected and surfaced before it accumulates
- [ ] 90-day baseline establishes whether full templating investment is justified

---

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Agent file count | 36 (reduced from 54) | `ls .agents/**/*.md \| wc -l` |
| Manual sync errors | 0 per release | PR review audit |
| Build-time generation | < 5 seconds | CI timing logs |
| Drift alerts per week | Establish baseline (90 days) | CI job metrics |
| False positive rate | < 20% of alerts | Manual classification |

---

## Scope Boundaries

### In Scope

**Phase 1: 2-Variant Consolidation (4-6 hours)**

- Merge VS Code and Copilot CLI agent files into single source files
- Implement build-time YAML frontmatter generation for each platform
- Create PowerShell/Bash script to generate platform-specific outputs
- Update `install.ps1` to use generated files
- Document the consolidation pattern for contributors

**Phase 2: Diff-Linting (4-8 hours)**

- Create CI job comparing Claude agent content sections vs generated VS Code/Copilot versions
- Implement configurable threshold for alerting (semantic vs cosmetic changes)
- Generate weekly drift reports for 90-day data collection
- Store baseline metrics for future templating decision

### Out of Scope

- **Claude agent consolidation**: Claude Code has unique tool/instruction requirements; remains separate for now
- **Full templating system (LiquidJS)**: Deferred pending 90-day data collection
- **Automated drift correction**: Alerting only; fixes remain manual
- **Cross-platform behavioral testing**: Not validating that agents behave identically
- **Internationalization**: English-only for this phase
- **New agent creation**: Only consolidating existing 18 agents

---

## Dependencies

| Dependency | Type | Status | Notes |
|------------|------|--------|-------|
| Existing agent file structure | Prerequisite | Complete | 54 files across 3 platforms |
| Build script infrastructure | Prerequisite | Complete | `install.ps1` already exists |
| CI/CD pipeline | Prerequisite | Complete | GitHub Actions configured |
| None blocking | - | - | Can proceed immediately |

---

## KANO Classification

**Performance** - Directly improves maintainability satisfaction proportionally to effort invested.

Rationale: Users expect agent consistency across platforms. This reduces the maintenance burden that directly correlates with satisfaction. Not a must-be (system works without it) but clearly performance-enhancing.

---

## RICE Score

| Factor | Value | Rationale |
|--------|-------|-----------|
| Reach | 3 users/quarter | Maintainers (1-3 active contributors) |
| Impact | 2 (High) | 33% file reduction, eliminates manual sync errors |
| Confidence | 80% | Clear implementation path, validated by CVA analysis |
| Effort | 0.5 person-months | 8-14 hours estimated |
| **Score** | **9.6** | (3 x 2 x 0.8) / 0.5 |

---

## Rumsfeld Matrix Assessment

| Quadrant | Items |
|----------|-------|
| **Known Knowns** | VS Code and Copilot CLI share 99%+ content; only YAML frontmatter differs |
| **Known Unknowns** | Will semantic drift detection catch meaningful vs cosmetic differences? |
| **Unknown Unknowns** | Platform-specific edge cases we haven't encountered yet |
| **Unknown Knowns** | We may already have patterns that should differ but don't |

---

## Assumptions and Validation

| Type | Assumption | Validation Status | Validation Method |
|------|------------|-------------------|-------------------|
| Assumption | VS Code and Copilot CLI tool lists are functionally equivalent | Validated | Manual diff comparison |
| Assumption | 90-day data collection sufficient to identify drift patterns | Untested | Will measure during Phase 2 |
| Known Unknown | Optimal diff-linting threshold for alerts | Needs calibration | Iterative tuning during 90-day period |
| Assumption | Build-time generation adds negligible CI time | Untested | Measure during implementation |

---

## Phased Delivery

### Phase 1: 2-Variant Consolidation

**Duration**: 4-6 hours

**Deliverables**:

1. Single-source agent files with frontmatter markers
2. Build script generating VS Code and Copilot CLI variants
3. Updated installation script integration
4. Contributor documentation

**Acceptance Criteria**:

- [ ] All 18 agents have single source files
- [ ] Build script generates correct frontmatter for each platform
- [ ] Installation script uses generated outputs
- [ ] Existing functionality unchanged

### Phase 2: Diff-Linting CI

**Duration**: 4-8 hours

**Deliverables**:

1. GitHub Actions workflow for drift detection
2. Comparison logic (Claude vs generated variants)
3. Configurable alert thresholds
4. Weekly drift report generation
5. 90-day metrics collection

**Acceptance Criteria**:

- [ ] CI job runs on every PR modifying agent files
- [ ] Alerts generated for content drift above threshold
- [ ] Weekly reports generated and stored
- [ ] Metrics tracked for 90-day decision point

---

## Priority

**P1 (Important, Should Have)**

Rationale:
- High RICE score (9.6) relative to effort
- Reduces ongoing maintenance burden
- Enables data-driven decision for full templating
- No blockers; can proceed immediately

---

## Target Release

**v1.1 (Maintainability)**

---

## Opportunity Cost

If we do this epic now:

| Gained | Delayed |
|--------|---------|
| 33% file reduction (54 to 36) | Pre-PR Security Gate by approximately 1 week |
| CI drift detection infrastructure | Any new feature work |
| Stepping stone toward templating | - |

**Recommended Sequencing**:

1. Pre-PR Security Gate (documentation-focused Phase 1, approximately 1 day)
2. 2-Variant Consolidation (Phase 1)
3. Diff-Linting CI (Phase 2)

---

## Future Considerations

This epic sets up the decision point for **Full Agent Templating System (LiquidJS)**.

**Conditions to proceed to full templating**:

- [ ] Drift-linting shows Claude diverging from VS Code/Copilot variants
- [ ] Maintenance burden still significant after consolidation
- [ ] Contributor feedback requests single-source editing

If drift is minimal after 90 days, the 2-Variant solution may be sufficient long-term.

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-15 | Epic created from ideation validation | Roadmap Agent |

---

*Generated by Roadmap Agent*
