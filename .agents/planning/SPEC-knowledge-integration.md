# Spec: Knowledge Integration into Skills and Agents

## Problem Statement

Domain knowledge from a personal wiki (227 files, 30 domains) and the addyosmani/agent-skills repo (21 skills) exists outside the ai-agents3 repo. Skills and agents lack domain-specific reference material, producing generic outputs instead of leveraging accumulated engineering wisdom. The goal is to inject curated, compressed knowledge as passive context resources that skills and agents consume when invoked.

## Context Mechanism (Decided)

- **Skills**: Use per-skill `resources/` subdirectory. Files listed in a `## Resources` table in SKILL.md. Read on invocation.
- **Agents** (`src/claude/`): Loaded as system prompt definitions. Agent resources go into the corresponding skill's `resources/` directory.
- **Format**: Summarized and optimized for LLM efficiency (not raw copy, not pipe-delimited). Each resource is a distilled reference document.
- **New skills**: When no existing skill fits, create a new skill via the SkillForge skill.

The integration mechanism is: summarized resource files in per-skill `resources/` directories, referenced from SKILL.md `## Resources` tables.

## Sources

| Source | Location | Items | Status |
|--------|----------|-------|--------|
| Personal wiki | `~/Documents/Mobile/wiki/concepts/` | 227 files | Triage needed |
| addyosmani/agent-skills | `github.com/addyosmani/agent-skills` | 21 skills | Import all |
| gstack skills | `github.com/garrytan/gstack` | 37 skills | Import all |

## Domain-to-Target Mapping

| Wiki Domain | Files | Primary Targets | Secondary Targets |
|-------------|-------|----------------|-------------------|
| Strategic Thinking | 54 | architect, high-level-advisor agents | buy-vs-build, cynefin, decision-critic skills |
| AI Productivity | 26 | prompt-engineer, context-optimizer skills | memory skill |
| Design Principles | 27 | implementer agent | cva-analysis, golden-principles, code-qualities skills |
| Architectural Patterns | 15 | architect agent | threat-modeling skill |
| Mental Models | 10 | critic agent, independent-thinker agent | chestertons-fence, decision-critic skills |
| Observability | 5 | observability skill | slo-designer skill |
| Reliability | 5 | slo-designer, chaos-experiment skills | architect agent |
| Critical Thinking | 3 | critic agent, independent-thinker agent | decision-critic skill |
| Team/Career/Leadership | 10 | high-level-advisor agent | retrospective agent |
| Prompting & AI Safety | 5 | prompt-engineer skill | security agent |
| Build/Deploy/Ops | 19 | devops agent | pipeline-validator skill |
| Modernization (.NET) | 26 | implementer agent, architect agent | .NET-specific skills (triage for non-internal content) |

### addyosmani/agent-skills (21 skills)

| Osmani Skill | Target Skill | Notes |
|---|---|---|
| idea-refine | NEW (via SkillForge) | No existing equivalent |
| source-driven-development | research-and-incorporate | Supplement with retrieval-led principles |
| context-engineering | context-optimizer | Merge into existing resources/ |
| code-simplification | analyze | Merge into existing resources/ |
| debugging-and-error-recovery | analyze | Merge into existing resources/ |
| api-and-interface-design | implementer agent | Resource for interface design guidance |
| performance-optimization | implementer agent | Resource for performance patterns |
| deprecation-and-migration | architect agent | Resource for migration planning |
| frontend-ui-engineering | implementer agent | Resource for UI patterns |
| spec-driven-development | planner | Supplement planning resources/ |
| planning-and-task-breakdown | planner | Supplement planning resources/ |
| incremental-implementation | planner | Resource for vertical slice patterns |
| test-driven-development | analyze | TDD patterns resource |
| code-review-and-quality | analyze | Review checklist resource |
| git-workflow-and-versioning | git-advanced-workflows | Merge into existing resources/ |
| security-and-hardening | security-scan | Security checklist resource |
| ci-cd-and-automation | pipeline-validator | CI/CD patterns resource |
| shipping-and-launch | session-end | Launch checklist resource |
| documentation-and-adrs | adr-review | ADR writing guidance resource |
| browser-testing-with-devtools | analyze | Browser testing patterns resource |
| using-agent-skills | context-optimizer | Meta-skill patterns resource |

### gstack skills (37 skills)

| gstack Skill | Target Skill | Notes |
|---|---|---|
| qa, qa-only | analyze | QA methodology resource |
| investigate | analyze | Root cause investigation patterns |
| benchmark | NEW (via SkillForge) or analyze | Performance benchmarking patterns |
| canary | NEW (via SkillForge) or pipeline-validator | Post-deploy monitoring patterns |
| design-shotgun, design-consultation | NEW (via SkillForge) | Design exploration methodology |
| design-html, design-review | NEW (via SkillForge) | Design QA and finalization patterns |
| plan-design-review | planner | Design review checklist resource |
| devex-review, plan-devex-review | NEW (via SkillForge) | Developer experience audit patterns |
| review | analyze | Pre-landing review patterns |
| plan-eng-review | planner | Engineering review checklist resource |
| plan-ceo-review | planner | Strategic review checklist resource |
| codex | analyze | Adversarial review patterns |
| ship, land-and-deploy | session-end | Ship and deploy checklist resource |
| setup-deploy | pipeline-validator | Deployment config resource |
| browse, connect-chrome | analyze | Browser automation patterns |
| pair-agent, setup-browser-cookies | analyze | Agent pairing patterns |
| cso | security-scan | Security audit methodology resource |
| careful, guard, freeze, unfreeze | NEW (via SkillForge) | Safety guardrails methodology |
| checkpoint | session-end | Checkpoint patterns resource |
| learn, retro | reflect | Learning capture patterns resource |
| office-hours | NEW (via SkillForge) | Structured questioning methodology |
| autoplan | planner | Auto-review pipeline patterns resource |
| health | quality-grades | Code health dashboard patterns |
| document-release | doc-sync | Post-ship documentation patterns |
| open-gstack-browser, gstack-upgrade | SKIP | Meta/utility, not transferable |

## Acceptance Criteria

### AC-1: Manifest exists with disposition for every source file
- A CSV manifest at `.agents/planning/wiki-manifest.csv` lists all 227 wiki files
- Each row has: domain, file path, size_bytes, disposition (include/merge/skip), target, rationale
- Zero blank disposition cells
- Row count equals 228 (header + 227 data rows)
- Pass/fail: `wc -l wiki-manifest.csv` returns 228 AND `csvtool col 4 wiki-manifest.csv | grep -c '^$'` returns 0

### AC-2: Resource files are under 8KB each
- Every file in skill `resources/` directories created by this effort is under 8,192 bytes
- Pass/fail: `find .claude/skills/*/resources -name "*.md" -size +8k | wc -l` returns 0

### AC-3: Total context per agent stays under 40KB
- Sum of all resource files referenced by any single skill or agent is under 40KB
- Pass/fail: script sums sizes of all referenced resources per target, none exceeds 40,960 bytes

### AC-4: Resource tables in SKILL.md list all new resources
- Each skill that receives resources has a `## Resources` table in SKILL.md
- Every file in that skill's `resources/` directory appears in the table
- Pass/fail: script compares `ls resources/` against table entries, zero mismatches

### AC-5: No broken resource references
- Every path listed in a SKILL.md Resources table resolves to an existing file
- Pass/fail: path resolution script returns exit code 0

### AC-6: Modernization content is non-internal
- Modernization resources contain only general .NET patterns (e.g., SDK-style projects, ARM64, memory pooling)
- No references to internal team names, internal tool names, org-specific infrastructure, or internal URLs
- Pass/fail: grep for internal markers (team names, internal domains, internal tool names) returns 0 matches in resources/ files

### AC-7: Summarized resources preserve semantic fidelity
- 5 representative resources (one per source type: wiki, Osmani, gstack, .NET, mental model) pass a smoke test
- Smoke test: agent answers a specific domain question. Expected answer documented before test. Agent response matches expected answer.
- Pass/fail: 5/5 smoke tests pass with documented prompts, expected answers, and actual responses

### AC-8: Skill size limits respected
- No SKILL.md exceeds 500 lines after resource table additions (unless `size-exception: true` in frontmatter)
- Pass/fail: `wc -l` on all modified SKILL.md files, none exceeds 500

### AC-9: External skill content integrated
- All 21 Osmani skills have corresponding resource files in target skill `resources/` directories
- All 35 gstack skills (minus 2 skipped) have corresponding resource files in target skill `resources/` directories
- Pass/fail: resource files exist for each mapped skill AND are listed in target SKILL.md `## Resources` tables

### AC-10: New skills created via SkillForge where needed
- Skills identified as NEW in the mapping tables are created using the SkillForge skill
- Each new skill has valid SKILL.md frontmatter and a `resources/` directory
- Pass/fail: new skill directories exist with valid SKILL.md files passing frontmatter validation

## Out of Scope

- **Skill logic changes**: No existing triggers, scripts, or process steps modified. Knowledge resources only.
- **Agent behavior changes**: No agent prompt modifications beyond resource references.
- **Wiki source edits**: The wiki is read-only for this effort.
- **Sync mechanism**: No automated wiki-to-repo sync. This is a one-time import.
- **Browser automation**: gstack browser skills require gstack infrastructure. Import patterns/methodology only, not runtime code.

## In Scope (Updated)

- **New skill creation**: Use SkillForge when no existing skill fits the knowledge domain.
- **Modernization domain**: Triage for non-internal .NET content. Include valuable .NET patterns.
- **All Osmani skills**: Import all 21 as resources into existing or new skills.
- **All gstack skills**: Import all 37 (minus 2 meta/utility) as resources into existing or new skills.

## Resolved Questions

| # | Question | Decision |
|---|----------|----------|
| 1 | How are `resources/` files consumed? | Per-skill `resources/` directory, referenced in SKILL.md `## Resources` table. Skills read them on invocation. |
| 2 | Shared vs per-skill directory? | Per-skill `resources/` only. No shared `.agents/knowledge/`. Each skill owns its resources. |
| 3 | Modernization domain handling? | Triage for non-internal .NET content. Include valuable patterns. Skip org-specific infrastructure references. |
| 4 | Compression format? | Summarized and optimized for LLM efficiency. Distilled reference documents, not raw copies or pipe-delimited. |
| 5 | New skills needed? | Yes. Use SkillForge skill to create new skills when no existing skill fits. |

## CVA Summary

### Commonalities (what is the same across all resource injections)
- Source format: markdown files with YAML frontmatter
- Target format: compressed markdown under 8KB
- Integration point: `resources/` directory + SKILL.md table entry
- Validation: size check, reference resolution, smoke test

### Variabilities (what differs)
- Source domain and content structure (narrative vs. tabular vs. framework)
- Target count per source file (1:1 vs. many:1 consolidation)
- Compression ratio achievable (prose compresses well, tables do not)
- Consumer type (skill vs. agent)

### Relationships
- Each source file maps to exactly one target (no fan-out to prevent duplication)
- Multiple source files may consolidate into one resource file (fan-in via merge disposition)
- Shared knowledge files may be referenced by multiple skills/agents (read-only, no ownership conflict)

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Token budget explosion from too many resources per skill | High | High | AC-3: 40KB cap per skill |
| Summarization strips semantic meaning | Medium | Medium | AC-7: smoke test validation with expected answers |
| Internal content in .NET resources | Medium | High | AC-6: grep gate for internal markers |
| Resources ignored by agents (loaded but not used) | Medium | Medium | AC-7: behavioral smoke tests |
| SKILL.md exceeds 500-line limit | Low | Medium | AC-8: line count check |
| Too many new skills via SkillForge | Medium | Medium | AC-10: only create when no existing skill fits |
| gstack browser patterns not useful without gstack runtime | Low | Low | Import methodology patterns only, not runtime code |
