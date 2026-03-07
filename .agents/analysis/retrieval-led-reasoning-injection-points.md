# Retrieval-Led Reasoning: Strategic Injection Points Analysis

**Date**: 2026-02-08
**Analyst**: Claude Sonnet 4.5
**Context**: Improving agent adherence to documented patterns by embedding passive context directives

---

## Executive Summary

**Problem**: Agents rely on pre-training data instead of retrieving from project documentation, leading to:
- Outdated framework knowledge (Next.js, React, etc.)
- Bypassing tested skills in favor of inline code
- Ignoring established patterns documented in memories
- Violating project constraints despite documentation

**Solution**: Inject "prefer retrieval-led reasoning over pre-training-led reasoning" directives at strategic points in auto-loaded context, with inline indexes pointing to authoritative sources.

**Evidence**: Vercel research shows passive context (100% pass rate) dramatically outperforms active skill invocation (53-79% pass rate).

---

## Research Foundation

### Vercel Study: Passive Context vs Active Invocation

| Configuration | Pass Rate | Why |
|---------------|-----------|-----|
| Baseline (no docs) | 53% | Pure pre-training |
| Skill (default) | 53% | Requires decision point |
| Skill + explicit instructions | 79% | Better but still requires decision |
| **AGENTS.md passive context** | **100%** | No decision point, always present |

**Key Insight**: When information is present every turn without requiring invocation, agents use it reliably. Decision points (should I call this skill?) create failure modes.

---

## Current State Assessment

### Existing Injection Points

| Location | Directive Present? | Effectiveness | Issue |
|----------|-------------------|---------------|-------|
| SKILL-QUICK-REF.md | ✓ (line 6) | Medium | Buried in memory hierarchy section |
| CRITICAL-CONTEXT.md | ✗ | N/A | No retrieval-first directive |
| AGENTS.md | Partial | Medium | Lists sources but no directive |
| SESSION-PROTOCOL.md | Partial | Medium | Memory loading protocol but no directive |
| PROJECT-CONSTRAINTS.md | ✗ | N/A | No retrieval-first directive |
| ADR-007 hook | ✗ | N/A | No memory index injection |

### Current Directive Location

**SKILL-QUICK-REF.md** (line 6):
```text
> **Principle**: Prefer retrieval-led reasoning over pre-training-led reasoning for session protocol,
> memory operations, and repository conventions.
```

**Problem**: This is passive context (good) but:
1. Too narrow in scope (only mentions session protocol, memory, conventions)
2. Not prominent enough (buried after header)
3. No inline index showing WHERE to retrieve from
4. Not repeated at other strategic points

---

## Strategic Injection Points

### Priority 1: High-Traffic Auto-Loaded Files

These files are loaded every session and read by agents early.

#### 1.1 CRITICAL-CONTEXT.md (Top of File)

**Current**: Opens with "Critical Context (Auto-loaded)"
**Inject After**: Line 3 (before "Blocking Constraints")

**Recommended Directive**:

```markdown
## RETRIEVAL-LED REASONING (MANDATORY)

**IMPORTANT**: Prefer retrieval-led reasoning over pre-training-led reasoning for ALL project-specific decisions.

**What this means**:
- Framework versions (Next.js, React) → Read project docs, NOT pre-training
- Project constraints (languages, patterns) → Read PROJECT-CONSTRAINTS.md, NOT pre-training
- Learned patterns (skills, conventions) → Read Serena memories, NOT pre-training
- Architecture decisions → Read ADRs, NOT pre-training
- Session protocol → Read SESSION-PROTOCOL.md, NOT pre-training

**Retrieval Sources Index**:
- Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
- Session protocol: `.agents/SESSION-PROTOCOL.md`
- Memory index: Serena `memory-index` (read via `mcp__serena__read_memory`)
- Architecture: `.agents/architecture/ADR-*.md`
- Planning: `.agents/planning/*.md`
- Skills: `.claude/skills/{skill-name}/SKILL.md`

When in doubt: **Read first, reason second.**
```

**Why This Works**:
- CRITICAL-CONTEXT.md is auto-loaded via @import in CLAUDE.md
- Read early (blocking constraints section)
- Explicit index shows WHERE to retrieve from
- Covers ALL decision types, not just session protocol

#### 1.2 SKILL-QUICK-REF.md (Move Directive Higher + Expand)

**Current**: Line 6 (after memory hierarchy)
**Move To**: Line 3 (immediately after purpose statement)

**Recommended Directive**:

```markdown
---

## RETRIEVAL-LED REASONING PRINCIPLE

**CRITICAL**: Before making ANY decision based on framework knowledge, language syntax, or project patterns:

1. **PAUSE**: "Do I need current/accurate information for this?"
2. **CHECK**: Scan retrieval sources below
3. **READ**: Load authoritative source
4. **REASON**: Apply retrieved information, not pre-training

**Common Failure Modes**:
- ✗ "Next.js routing works like this..." (pre-training → outdated)
- ✓ "Let me check the Next.js docs..." (retrieval → current)
- ✗ "I'll create a PR with gh pr create" (pre-training → bypasses skill)
- ✓ "Let me check skill-quick-ref for PR skill" (retrieval → uses tested skill)

**Retrieval Priority Order**:
1. **Project-specific**: Serena memories, ADRs, planning docs
2. **Framework/Library**: Official docs (Context7, DeepWiki, WebSearch)
3. **Never**: Pre-training for project-specific or version-specific information

---
```

**Why This Works**:
- Earlier placement (line 3 vs line 6)
- Concrete examples showing failure modes
- Clear 3-step process (pause, check, read, reason)
- Priority order explicit

#### 1.3 AGENTS.md (Add Section Before "Session Protocol")

**Current**: Opens with Serena initialization
**Inject After**: Line 29 (after Serena initialization section)

**Recommended Section**:

```markdown
---

## RETRIEVAL-LED REASONING: AGENTS ARE LIBRARIANS, NOT ORACLES

**You are an agent WITH access to perfect information, NOT an oracle WITH perfect knowledge.**

### The Problem

Agents have two sources of information:
1. **Pre-training**: Knowledge cutoff 2025-01. Framework versions, APIs, patterns may be outdated.
2. **Retrieval**: Current project docs, memories, ADRs, framework documentation.

**Default behavior**: Agents use pre-training because it's instant and confident.
**Correct behavior**: Agents retrieve because it's accurate and current.

### The Solution

Before reasoning about:
- Framework APIs (Next.js, React, FastAPI) → Retrieve from docs
- Project constraints (languages, patterns) → Retrieve from PROJECT-CONSTRAINTS.md
- Learned patterns (skills, conventions) → Retrieve from Serena memories
- Architecture decisions → Retrieve from ADRs
- Session protocol → Retrieve from SESSION-PROTOCOL.md

**Memory Index**: The `memory-index` Serena memory maps task keywords to relevant memories.

**Example workflow**:
```text
Task: "Create a PR for this fix"
❌ Wrong: gh pr create --title "..." (pre-training)
✓ Right: Read memory-index → skills-github-cli-index → use github skill
```

**Verify your retrieval**:
- Framework docs: Use Context7, DeepWiki, or official docs
- Project memory: Use Serena (mcp__serena__read_memory)
- Architecture: Read ADRs in .agents/architecture/

---
```

**Why This Works**:
- Frames agents as librarians (retrieve) vs oracles (know)
- Explains WHY retrieval matters (accuracy, currency)
- Shows concrete workflow with right/wrong examples
- Points to memory-index as starting point

### Priority 2: Session Start Hooks (System Reminders)

These are injected by startup hooks and appear before user input.

#### 2.1 ADR-007 Memory-First Hook (Enhance)

**Current**: Lists steps, no memory index
**Location**: `.agents/hooks/session-start.sh` (if exists) or Claude Code settings

**Recommended Enhancement**:

```markdown
## ADR-007 Memory-First Enforcement (Session Start)

**BLOCKING GATE**: Complete these steps BEFORE any reasoning or implementation:

### Retrieval-Led Reasoning Principle

**IMPORTANT**: Prefer retrieval-led reasoning over pre-training for ALL decisions.
- Framework/library APIs → Retrieve from docs (Context7, DeepWiki)
- Project patterns → Retrieve from Serena memories (see index below)
- Constraints → Retrieve from PROJECT-CONSTRAINTS.md
- Architecture → Retrieve from ADRs

### Memory Index Quick Reference

The `memory-index` Serena memory maps keywords to memories. Common lookups:

| Task | Keywords | Memories |
|------|----------|----------|
| GitHub PR operations | github, pr, cli, gh | skills-github-cli-index, skills-pr-review-index |
| Session protocol | session, init, protocol, validation | skills-session-init-index, session-protocol |
| PowerShell scripts | powershell, ps1, pester, test | skills-powershell-index, skills-pester-testing-index |
| Security patterns | security, vulnerability, CWE | skills-security-index, security-scan |
| Architecture decisions | adr, architecture, decision | adr-reference-index |

**Process**:
1. Identify task keywords (e.g., "create PR")
2. Check table above OR read full memory-index
3. Load listed memories BEFORE reasoning

[... rest of current ADR-007 hook content ...]
```

**Why This Works**:
- Injects memory index directly into session start
- Provides quick reference table for common tasks
- No tool call required (passive context)
- Emphasizes retrieval BEFORE reasoning

#### 2.2 Branch Warning Hook (Add Skill Reminder)

**Current**: Warns about protected branch
**Location**: Startup hook output

**Recommended Addition**:

```markdown
## WARNING: On Protected Branch

[... existing warning ...]

**REMINDER**: Before using raw git/gh commands, check if a skill exists:
- Git operations: Check `.claude/skills/git-*/`
- GitHub operations: Check `.claude/skills/github/` (mandatory per usage-mandatory memory)
- Prefer retrieval-led reasoning: Read skill documentation, don't rely on pre-training
```

**Why This Works**:
- Appears at session start when agents are establishing context
- Reminds about skill-first pattern at critical decision point
- Ties to usage-mandatory constraint

### Priority 3: Protocol/Constraint Documents

These are read during session initialization.

#### 3.1 SESSION-PROTOCOL.md (Phase 2: Context Retrieval)

**Current**: Has memory loading protocol (line 94-100)
**Enhance**: Add retrieval-first directive before protocol

**Recommended Enhancement** (before line 94):

```markdown
### Retrieval-Led Reasoning (CRITICAL)

**Before proceeding with task, internalize this principle**:

You have two information sources:
1. **Pre-training**: Static, potentially outdated, no project context
2. **Retrieval**: Current, accurate, project-specific

**Always prefer retrieval.** Specifically:

- Session protocol → THIS DOCUMENT (SESSION-PROTOCOL.md)
- Project constraints → PROJECT-CONSTRAINTS.md
- Learned patterns → Serena memories via memory-index
- Architecture → ADRs in .agents/architecture/
- Framework/library APIs → Context7, DeepWiki, official docs

**Common failure**: Using outdated framework knowledge from pre-training when current docs are available.
**Correct approach**: Read memory-index, identify relevant memories, load them BEFORE reasoning.

**Memory Loading Protocol:**
```

**Why This Works**:
- Appears during Phase 2 (Context Retrieval) when agents are loading docs
- Explicit about two information sources
- Positioned right before memory loading protocol
- Emphasizes common failure mode

#### 3.2 PROJECT-CONSTRAINTS.md (Add Preamble)

**Current**: Opens with purpose statement
**Inject After**: Line 11 (after "How to use")

**Recommended Addition**:

```markdown
---

## RETRIEVAL-LED REASONING

**IMPORTANT**: This document is the SINGLE SOURCE OF TRUTH for constraints.

When making decisions about:
- Language choice (Python vs PowerShell) → Read "Language Constraints" section, NOT pre-training
- Skill usage → Read "Skill Usage Constraints" section, NOT pre-training
- Workflow patterns → Read "Workflow Constraints" section, NOT pre-training
- Commit structure → Read "Commit Constraints" section, NOT pre-training

**Do NOT rely on pre-training for these constraints.** Pre-training may reflect outdated patterns.

**Process**:
1. Identify decision type (language, workflow, etc.)
2. Read corresponding section in THIS document
3. Follow "Source" link for full rationale if needed
4. Apply constraint, not pre-training assumption

---
```

**Why This Works**:
- Establishes document as authoritative source
- Explicit about NOT using pre-training for constraints
- Shows process for using the document
- Appears before constraints table (early read)

---

## Implementation Priority

### Phase 1: High-Traffic Files (Immediate Impact)
1. ✅ CRITICAL-CONTEXT.md (top injection)
2. ✅ SKILL-QUICK-REF.md (move directive higher + expand)
3. ✅ AGENTS.md (add librarian section)

### Phase 2: Session Start Hooks (Passive Context)
4. ✅ ADR-007 hook (add memory index)
5. ✅ Branch warning hook (add skill reminder)

### Phase 3: Protocol Documents (Reinforcement)
6. ✅ SESSION-PROTOCOL.md (Phase 2 enhancement)
7. ✅ PROJECT-CONSTRAINTS.md (preamble addition)

---

## Success Metrics

### Leading Indicators (Process Compliance)
- % sessions with memory-index read before first code change
- % GitHub operations using skills vs raw gh commands
- % framework questions with doc retrieval before reasoning

### Lagging Indicators (Outcome Quality)
- Reduction in "outdated API" corrections from users
- Reduction in "there's a skill for that" corrections
- Reduction in constraint violations caught in PR review

### Measurement Approach
- Session log analysis: Count tool calls (mcp__serena__read_memory) before implementation
- Git history analysis: Search for raw `gh` commands in commits
- PR review analysis: Tag corrections as "retrieval failure"

---

## Related Work

- Vercel research: Passive context vs skill invocation
- usage-mandatory memory: Skill-first enforcement
- memory-index: Keyword → memory mapping
- ADR-007: Memory-first architecture
- SKILL-QUICK-REF.md: Passive context reference

---

## Next Steps

1. **Review this analysis** with project owner
2. **Implement Phase 1** (high-traffic files)
3. **Monitor for 5 sessions** (qualitative assessment)
4. **Measure leading indicators** (memory-index reads, skill usage)
5. **Implement Phase 2-3** if Phase 1 shows improvement
6. **Document in retrospective** after 20 sessions

---

## Appendix: Example Inline Indexes

### Framework Documentation Index Template

For framework-specific work (Next.js, React, FastAPI), inject:

```markdown
**Framework: {Name} v{Version}**

**Retrieval sources** (prefer over pre-training):
- Official docs: {URL}
- Context7: Use mcp__context7__get-library-docs
- DeepWiki: Use mcp__deepwiki__ask_question with repo {owner/repo}
- Project-specific patterns: Serena memory {memory-name}

**Common outdated pre-training patterns**:
- {Pattern 1 that changed in recent versions}
- {Pattern 2 that changed in recent versions}
```

### Decision Type → Retrieval Source Index

For complex decisions, inject:

```markdown
**Decision Type → Retrieval Source**

| Decision | Retrieval Source | NOT Pre-Training |
|----------|------------------|------------------|
| Language choice | PROJECT-CONSTRAINTS.md | ✗ ADR-005 is superseded |
| GitHub operation | skills-github-cli-index memory | ✗ May use outdated gh syntax |
| Architecture pattern | ADRs in .agents/architecture/ | ✗ May not reflect project decisions |
| Session protocol | SESSION-PROTOCOL.md | ✗ Protocol evolves |
```

---

**End of Analysis**
