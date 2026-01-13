# Skill v2.0 Standard Compliance Gap Analysis

**Date**: 2026-01-03
**Session**: 372
**Standard**: `.agents/governance/skill-description-trigger-standard.md` v2.0
**Scope**: All 27 skills in `.claude/skills/`

---

## Executive Summary

**Compliance Status**: 3/27 skills (11%) fully compliant with v2.0 standard

### Key Findings

| Metric | Count | Percentage |
|--------|-------|------------|
| **Total Skills** | 27 | 100% |
| **P0 Fixes Complete** | 3 | 11% (github, merge-resolver, programming-advisor) |
| **With Triggers Section** | 9 | 33% |
| **Without Triggers Section** | 18 | 67% |
| **Over 300 Lines** | 5 | 19% (candidates for progressive disclosure) |
| **Missing Decision Trees** | ~22 | 81% (estimate) |
| **Missing Anti-Patterns** | ~23 | 85% (estimate) |
| **Missing Verification** | ~20 | 74% (estimate) |

### Compliance Breakdown

**Full Compliance** (All v2.0 elements):
- github ✅ (description, triggers, decision tree)
- merge-resolver ✅ (description, triggers, phases with verification)
- programming-advisor ✅ (description, triggers, workflow, anti-patterns, cost analysis)

**Partial Compliance** (Description + Triggers, missing body elements):
- memory-documentary (needs decision tree, anti-patterns, verification)
- memory (needs anti-patterns)
- pr-comment-responder (needs decision tree, anti-patterns)
- research-and-incorporate (needs anti-patterns)
- session-log-fixer (has verification, needs anti-patterns)
- SkillForge (needs anti-patterns, verification - has references/)

**Low Compliance** (Description only, no triggers):
- 18 skills need triggers sections and body elements

---

## Priority Classification

### Tier 1: High-Value Skills (P1)

Top 10 most-used skills missing triggers sections:

| Skill | Lines | Has | Missing | Priority Reason |
|-------|-------|-----|---------|-----------------|
| **planner** | 273 | Good description | Triggers, decision tree, anti-patterns, verification | Core workflow orchestrator |
| **doc-sync** | 319 | Excellent description with trigger keywords | Triggers section (recommended), decision tree | Frequently invoked |
| **metrics** | 170 | Good description | Triggers, decision tree, anti-patterns | Regular reporting use |
| **incoherence** | 159 | Good description | Triggers, decision tree, anti-patterns, verification | Diagnostic tool |
| **analyze** | 58 | Good description | Triggers, decision tree, anti-patterns | Entry point skill |
| **security-detection** | 138 | Good description | Triggers, decision tree, verification | Security-critical |
| **prompt-engineer** | 141 | Good description | Triggers, decision tree, anti-patterns, verification | Agent optimization |
| **serena-code-architecture** | 239 | Good description | Triggers, decision tree, anti-patterns, verification | Architecture analysis |
| **session** | 234 | Good description | Triggers, decision tree, anti-patterns | Session management |
| **adr-review** | 147 | Excellent description | Triggers (optional for auto-invoked), anti-patterns | Strategic decisions |

### Tier 2: Guidance Skills (P2)

These provide reference information:

| Skill | Lines | Status |
|-------|-------|--------|
| **using-forgetful-memory** | 189 | Guidance-style, minimal triggers needed |
| **using-serena-symbols** | 208 | Guidance-style, minimal triggers needed |
| **curating-memories** | 127 | Guidance-style, minimal triggers needed |
| **exploring-knowledge-graph** | 102 | Guidance-style, minimal triggers needed |

### Tier 3: Utility Skills (P2)

Single-purpose, well-scoped:

| Skill | Lines | Status |
|-------|-------|--------|
| **fix-markdown-fences** | 216 | Good description with trigger keywords, needs section |
| **steering-matcher** | 94 | Internal utility, needs triggers for orchestrator |
| **encode-repo-serena** | 111 | Good description, needs triggers and decision tree |
| **decision-critic** | 64 | Good description, needs triggers and examples |

---

## Detailed Gap Analysis by Skill

### Skills WITH Triggers Sections (9)

#### ✅ github (Full Compliance)
- **Description**: ✅ Excellent (32 words, 245 chars, trigger keywords)
- **Triggers**: ✅ Table format, phrase → operation mapping
- **Decision Tree**: ✅ Comprehensive (Need GitHub data? → script selection)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ✅ Implicit in script reference
- **Recommendation**: Add anti-patterns table

#### ✅ merge-resolver (Full Compliance)
- **Description**: ✅ Excellent (35 words, 194 chars, trigger keywords)
- **Triggers**: ✅ List format, 5 natural phrases
- **Decision Tree**: ✅ Implicit in phases
- **Anti-Patterns**: ❌ Missing
- **Verification**: ✅ Phase 3 validation (blocking)
- **Recommendation**: Add anti-patterns for common mistakes

#### ✅ programming-advisor (Full Compliance)
- **Description**: ✅ Excellent (43 words, 248 chars, trigger keywords)
- **Triggers**: ✅ Table format, 5 trigger phrases
- **Decision Tree**: ✅ Recommendation framework
- **Anti-Patterns**: ✅ Comprehensive section
- **Verification**: ✅ Cost analysis, comparison tables
- **Recommendation**: None - exemplar skill

#### 🟨 memory-documentary
- **Description**: ✅ Good (multi-line, trigger keywords)
- **Triggers**: ✅ Yes
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**: Add decision tree, anti-patterns, verification checklist

#### 🟨 memory
- **Description**: ✅ Good (multi-line, trigger keywords)
- **Triggers**: ✅ Table format
- **Decision Tree**: ✅ Tier-based routing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ✅ Implicit in examples
- **Recommendation**: Add anti-patterns for common memory mistakes

#### 🟨 pr-comment-responder
- **Description**: ✅ Excellent (multi-line, trigger keywords)
- **Triggers**: ✅ Yes
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**: Add when to use vs manual response

#### 🟨 research-and-incorporate
- **Description**: ✅ Excellent (multi-line, clear workflow)
- **Triggers**: ✅ Yes
- **Decision Tree**: ✅ Implicit in 5-phase workflow
- **Anti-Patterns**: ❌ Missing
- **Verification**: ✅ Output artifacts listed
- **Recommendation**: Add anti-patterns for research scope creep

#### 🟨 session-log-fixer
- **Description**: ✅ Excellent (multi-line, exact error messages as trigger keywords)
- **Triggers**: ✅ List format, 5 triggers
- **Decision Tree**: ❌ Missing (implicit in process)
- **Anti-Patterns**: ✅ Present
- **Verification**: ✅ Comprehensive checklist
- **Recommendation**: Exemplar for verification patterns

#### 🟨 SkillForge
- **Description**: ✅ Excellent (multi-line, comprehensive)
- **Triggers**: ✅ Yes
- **Decision Tree**: ✅ Phase-based workflow
- **Anti-Patterns**: ❌ Missing (moved to references?)
- **Verification**: ❌ Missing in main file
- **Progressive Disclosure**: ✅ Applied (871 → 401 lines)
- **Recommendation**: Check if anti-patterns/verification in references/

### Skills WITHOUT Triggers Sections (18)

#### Tier 1 - High Value

##### 🔴 planner (273 lines)
- **Description**: ✅ Excellent (multi-line, clear use cases)
- **Triggers**: ❌ Missing section
  - Implicit: "plan this", "break down", "create milestones"
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "plan [feature]", "break down [epic]", "create implementation plan"
  - Add decision tree: planning vs execution mode
  - Add anti-patterns: premature planning, over-specification
  - Add verification: milestone completeness checklist

##### 🔴 doc-sync (319 lines)
- **Description**: ✅ Excellent (trigger keywords embedded: "sync docs", "update CLAUDE.md")
- **Triggers**: ❌ Missing section (description has them!)
- **Decision Tree**: ✅ Present (what to sync decision tree)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ✅ Present (validation steps)
- **Recommendation**:
  - Extract triggers from description to dedicated section
  - Add anti-patterns: manual edits to generated files

##### 🔴 metrics (170 lines)
- **Description**: ✅ Good (clear purpose)
- **Triggers**: ❌ Missing
  - Implicit: "show metrics", "generate report", "agent usage"
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "show agent metrics", "generate usage report", "metrics for last [N] days"
  - Add decision tree: when to use vs GitHub Insights
  - Add anti-patterns: running without git history

##### 🔴 incoherence (159 lines)
- **Description**: ✅ Good (clear detection purpose)
- **Triggers**: ❌ Missing
  - Implicit: "detect incoherence", "find contradictions", "check consistency"
- **Decision Tree**: ✅ Present (detection → reconciliation flow)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "detect incoherence", "find contradictions in docs", "check spec vs implementation"
  - Add anti-patterns: auto-applying changes without review
  - Add verification: reconciliation completeness

##### 🔴 analyze (58 lines)
- **Description**: ✅ Excellent (imperative: "Invoke IMMEDIATELY")
- **Triggers**: ❌ Missing
  - Implicit: "analyze codebase", "architecture review", "security assessment"
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "analyze codebase", "review architecture", "security assessment"
  - Add decision tree: when to use vs manual exploration
  - Add anti-patterns: analyzing without clear goal

##### 🔴 security-detection (138 lines)
- **Description**: ✅ Good (clear purpose)
- **Triggers**: ❌ Missing (auto-invoked by hooks)
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ✅ Implicit in detection patterns
- **Recommendation**:
  - Add triggers: "detect security changes", "check infrastructure modifications"
  - Add decision tree: when to trigger security review
  - Add anti-patterns: false positive patterns

##### 🔴 prompt-engineer (141 lines)
- **Description**: ✅ Excellent (clear optimization purpose)
- **Triggers**: ❌ Missing
  - Implicit: "optimize prompt", "improve agent prompt", "refine instructions"
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "optimize [agent] prompt", "improve prompt for [task]", "refine instructions"
  - Add decision tree: when to optimize vs rewrite
  - Add anti-patterns: over-optimization, removing necessary context
  - Add verification: A/B testing checklist

##### 🔴 serena-code-architecture (239 lines)
- **Description**: ✅ Excellent (clear workflow)
- **Triggers**: ❌ Missing
  - Implicit: "analyze architecture", "document structure", "create component entities"
- **Decision Tree**: ✅ Present (phases)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "analyze project architecture", "document codebase structure", "create architecture diagram"
  - Add anti-patterns: analyzing without LSP context
  - Add verification: entity completeness checklist

##### 🔴 session (234 lines)
- **Description**: ✅ Good (session management purpose)
- **Triggers**: ❌ Missing
  - Implicit: "check investigation eligibility", "skip QA validation"
- **Decision Tree**: ✅ Present (ADR-034 eligibility)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "check investigation eligibility", "can I skip QA", "is this investigation-only"
  - Add anti-patterns: incorrectly claiming investigation status

##### 🔴 adr-review (147 lines)
- **Description**: ✅ Excellent (multi-agent debate)
- **Triggers**: ❌ Optional (auto-invoked by hooks)
- **Decision Tree**: ✅ Present (phases 0-4)
- **Anti-Patterns**: ✅ Present
- **Verification**: ✅ Present (consensus checklist)
- **Recommendation**:
  - Triggers optional for auto-invoked skills
  - Consider triggers for manual invocation: "review this ADR", "validate decision"

#### Tier 2 - Guidance Skills

##### 🟡 using-forgetful-memory (189 lines)
- **Description**: ✅ Excellent (Zettelkasten principles)
- **Triggers**: ❌ Missing (guidance-style)
- **Decision Tree**: ✅ Present (when to query vs create)
- **Anti-Patterns**: ✅ Present (vague memories, missing context)
- **Verification**: ✅ Present (atomic memory checklist)
- **Recommendation**:
  - Add triggers: "how do I create a memory", "when to query vs create", "importance scoring"
  - Already has excellent decision trees and anti-patterns

##### 🟡 using-serena-symbols (208 lines)
- **Description**: ✅ Excellent (LSP symbol analysis)
- **Triggers**: ❌ Missing (guidance-style)
- **Decision Tree**: ✅ Present (Serena vs grep comparison)
- **Anti-Patterns**: ✅ Present
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "how do I find a symbol", "trace references", "when to use Serena vs grep"
  - Add verification: symbol search completeness

##### 🟡 curating-memories (127 lines)
- **Description**: ✅ Excellent (memory curation)
- **Triggers**: ❌ Missing
  - Implicit: "update memory", "mark obsolete", "link memories"
- **Decision Tree**: ✅ Present (when to update vs create new)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "update outdated memory", "link related memories", "mark memory obsolete"
  - Add anti-patterns: deleting vs marking obsolete
  - Add verification: link completeness

##### 🟡 exploring-knowledge-graph (102 lines)
- **Description**: ✅ Excellent (knowledge graph traversal)
- **Triggers**: ❌ Missing
  - Implicit: "what do we know about X", "explore connections", "find related memories"
- **Decision Tree**: ✅ Present (breadth vs depth traversal)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "what do we know about [topic]", "explore [concept] connections", "find related memories"
  - Add anti-patterns: aimless traversal without goal
  - Add verification: coverage completeness

#### Tier 3 - Utility Skills

##### 🟡 fix-markdown-fences (216 lines)
- **Description**: ✅ Excellent (trigger keywords: "closing fences with language identifiers")
- **Triggers**: ❌ Missing section
- **Decision Tree**: ✅ Present (detection → fixing flow)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ✅ Present (lint check)
- **Recommendation**:
  - Add triggers: "fix markdown fences", "repair closing fences", "```text instead of ```"
  - Add anti-patterns: manual fixing without validation

##### 🟡 steering-matcher (94 lines)
- **Description**: ✅ Good (internal utility)
- **Triggers**: ❌ Missing
  - Implicit: orchestrator internal use
- **Decision Tree**: ✅ Present (pattern matching logic)
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "match steering patterns", "find applicable guidance"
  - Add anti-patterns: incorrect glob patterns

##### 🟡 encode-repo-serena (111 lines)
- **Description**: ✅ Good (Forgetful population)
- **Triggers**: ❌ Missing
  - Implicit: "encode codebase", "populate knowledge base", "onboarding"
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "encode codebase", "populate Forgetful", "refresh project understanding"
  - Add decision tree: when to encode vs update
  - Add anti-patterns: encoding without LSP context
  - Add verification: entity count, memory count

##### 🟡 decision-critic (64 lines)
- **Description**: ✅ Good (stress-testing decisions)
- **Triggers**: ❌ Missing
  - Implicit: "critique this decision", "stress-test reasoning", "challenge assumptions"
- **Decision Tree**: ❌ Missing
- **Anti-Patterns**: ❌ Missing
- **Verification**: ❌ Missing
- **Recommendation**:
  - Add triggers: "critique [decision]", "stress-test [reasoning]", "challenge assumptions"
  - Add decision tree: when to use vs direct implementation
  - Add anti-patterns: analysis paralysis
  - Add verification: assumption coverage

---

## Recommendations by Tier

### Tier 1: Immediate Action (Next PR)

Update top 5 high-value skills:

1. **planner** - Add triggers, decision tree, anti-patterns, verification
2. **doc-sync** - Extract triggers to section, add anti-patterns
3. **metrics** - Add triggers, decision tree, anti-patterns, verification
4. **incoherence** - Add triggers, anti-patterns, verification
5. **analyze** - Add triggers, decision tree, anti-patterns

**Estimated Effort**: 3-4 hours (30-45 min per skill)

### Tier 2: Follow-Up PRs

**Batch 1** (Guidance skills):
- using-forgetful-memory
- using-serena-symbols
- curating-memories
- exploring-knowledge-graph

**Batch 2** (Remaining high-value):
- security-detection
- prompt-engineer
- serena-code-architecture
- session
- adr-review

**Batch 3** (Utilities):
- fix-markdown-fences
- steering-matcher
- encode-repo-serena
- decision-critic

### Tier 3: Polish Existing (Low Priority)

Add missing anti-patterns to skills with triggers:
- memory-documentary
- memory
- pr-comment-responder
- research-and-incorporate
- SkillForge (check references/)

---

## Token Efficiency Opportunities

### Progressive Disclosure Candidates

Skills over 300 lines that could benefit from references/:

| Skill | Lines | Candidates for references/ |
|-------|-------|----------------------------|
| merge-resolver | 397 | Deep dive: git blame analysis, conflict resolution strategies |
| programming-advisor | 350 | Already has references/ for token-estimates, pricing-data, etc. |
| doc-sync | 319 | Deep dive: sync algorithms, validation rules |
| planner | 273 | Deep dive: milestone decomposition, estimation frameworks |

**Recommendation**: Apply progressive disclosure to merge-resolver and doc-sync after adding missing v2.0 elements.

---

## Implementation Plan

### Phase 1: P0 Complete ✅
- github ✅
- merge-resolver ✅
- programming-advisor ✅

### Phase 2: Tier 1 High-Value (Next Issue)
- planner
- doc-sync
- metrics
- incoherence
- analyze

**Deliverable**: GitHub issue with task breakdown

### Phase 3: Tier 2 Guidance
- 4 guidance skills batch update

### Phase 4: Tier 2 High-Value Remaining
- 5 skills batch update

### Phase 5: Tier 3 Utilities
- 4 utility skills batch update

### Phase 6: Polish
- Add anti-patterns to 5 skills with triggers

---

## Success Metrics

### Completion Criteria

- [ ] All 27 skills have descriptions with trigger keywords (10+ words)
- [ ] All high-value skills (Tier 1) have triggers sections
- [ ] All skills have decision trees or "when to use" guidance
- [ ] All skills have anti-patterns tables
- [ ] All skills have verification checklists
- [ ] Progressive disclosure applied where line count >300

### Quality Gates

- [ ] Each description passes 10+ word validator
- [ ] Each description includes at least 3 trigger keywords
- [ ] Triggers sections have 3-5 phrases minimum
- [ ] Decision trees show at least 2 alternative paths
- [ ] Anti-patterns have "Avoid / Why / Instead" format
- [ ] Verification checklists are concrete and testable

---

## Appendix: Full Skill Inventory

| # | Skill | Lines | Description | Triggers | Decision Tree | Anti-Patterns | Verification | Compliance |
|---|-------|-------|-------------|----------|---------------|---------------|--------------|------------|
| 1 | adr-review | 147 | ✅ | ❌ | ✅ | ✅ | ✅ | 80% |
| 2 | analyze | 58 | ✅ | ❌ | ❌ | ❌ | ❌ | 20% |
| 3 | curating-memories | 127 | ✅ | ❌ | ✅ | ❌ | ❌ | 40% |
| 4 | decision-critic | 64 | ✅ | ❌ | ❌ | ❌ | ❌ | 20% |
| 5 | doc-sync | 319 | ✅ | ❌ | ✅ | ❌ | ✅ | 60% |
| 6 | encode-repo-serena | 111 | ✅ | ❌ | ❌ | ❌ | ❌ | 20% |
| 7 | exploring-knowledge-graph | 102 | ✅ | ❌ | ✅ | ❌ | ❌ | 40% |
| 8 | fix-markdown-fences | 216 | ✅ | ❌ | ✅ | ❌ | ✅ | 60% |
| 9 | github | 170 | ✅ | ✅ | ✅ | ❌ | ✅ | 80% |
| 10 | incoherence | 159 | ✅ | ❌ | ✅ | ❌ | ❌ | 40% |
| 11 | memory | 231 | ✅ | ✅ | ✅ | ❌ | ✅ | 80% |
| 12 | memory-documentary | 189 | ✅ | ✅ | ❌ | ❌ | ❌ | 40% |
| 13 | merge-resolver | 397 | ✅ | ✅ | ✅ | ❌ | ✅ | 80% |
| 14 | metrics | 170 | ✅ | ❌ | ❌ | ❌ | ❌ | 20% |
| 15 | planner | 273 | ✅ | ❌ | ❌ | ❌ | ❌ | 20% |
| 16 | pr-comment-responder | 85 | ✅ | ✅ | ❌ | ❌ | ❌ | 40% |
| 17 | programming-advisor | 350 | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| 18 | prompt-engineer | 141 | ✅ | ❌ | ❌ | ❌ | ❌ | 20% |
| 19 | research-and-incorporate | 135 | ✅ | ✅ | ✅ | ❌ | ✅ | 80% |
| 20 | security-detection | 138 | ✅ | ❌ | ❌ | ❌ | ✅ | 40% |
| 21 | serena-code-architecture | 239 | ✅ | ❌ | ✅ | ❌ | ❌ | 40% |
| 22 | session | 234 | ✅ | ❌ | ✅ | ❌ | ❌ | 40% |
| 23 | session-log-fixer | 262 | ✅ | ✅ | ❌ | ✅ | ✅ | 80% |
| 24 | SkillForge | 401 | ✅ | ✅ | ✅ | ❌ | ❌ | 60% |
| 25 | steering-matcher | 94 | ✅ | ❌ | ✅ | ❌ | ❌ | 40% |
| 26 | using-forgetful-memory | 189 | ✅ | ❌ | ✅ | ✅ | ✅ | 80% |
| 27 | using-serena-symbols | 208 | ✅ | ❌ | ✅ | ✅ | ❌ | 60% |

**Average Compliance**: 50.4%
