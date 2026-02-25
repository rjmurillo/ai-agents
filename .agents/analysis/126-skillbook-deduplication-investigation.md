# Investigation: Skillbook Deduplication in Retrospective Workflow

**Issue**: #126
**Date**: 2026-02-24
**Status**: Complete

## Context

The 2025-12-16 Phase 4 retrospective (`2025-12-16-phase4-handoff-validation.md`)
noted: "Skillbook deduplication check referenced but unclear if functioning."
This investigation traces the retrospective-to-skillbook pipeline and documents
gaps in the deduplication mechanism.

## Findings

### 1. Skillbook Deduplication Logic

**Location**: `src/claude/skillbook.md`, lines 97-124

The skillbook agent defines a Pre-ADD Checklist with three steps:

1. Read `memory-index.md` for domain routing
2. Read the relevant domain index (`skills-*-index.md`)
3. Search activation vocabulary for similar keywords

**Similarity threshold**: 70%. Below 70% triggers ADD. Above 70% triggers UPDATE.
Exact match triggers REJECT.

**Implementation**: Prompt-based only. The agent prompt instructs the LLM to
perform deduplication, but no automated tool enforces it. The prompt references
`Search-Memory.ps1` for lexical search, but that script does not exist in the
repository.

**Memory router** (`memory_core/memory_router.py`): Provides SHA-256 hash-based
deduplication for merging search results across Serena and Forgetful backends.
This deduplicates identical content across sources. It does not compute semantic
similarity between skills.

### 2. Retrospective to Skillbook Handoff

**Location**: `src/claude/retrospective.md`, Phases 4-5

The retrospective agent defines a structured pipeline:

- **Phase 4** (line 645): Extract learnings with atomicity scoring
- **Phase 5** (line 889): Recursive learning extraction with skillbook delegation
- **Structured Handoff** (line 1270): Mandatory output format with skill
  candidates, memory updates, and git operations

The handoff format is well-specified. It includes skill ID, statement, atomicity
score, operation type, and target file. The retrospective agent recommends
routing to the skillbook agent, which the orchestrator handles.

**Enforcement**: None. The handoff relies on agent compliance with prompt
instructions. No validation script, CI check, or gate verifies that the
skillbook agent ran deduplication before persisting a skill.

### 3. Evidence from 2025-12-16 Retrospective

The retrospective that triggered this issue confirms the gap:

> "Deduplication Check: Placeholder for now (no existing skills to compare)"
> "Need actual skillbook integration to make this meaningful"
> "Compare Against Skillbook: Once skills are stored, test deduplication check
> with real data"

At the time, the skillbook contained no skills to deduplicate against. The
deduplication table in the retrospective template was empty.

### 4. Current State of Skill Storage

Skills are stored as atomic markdown files in `.serena/memories/` with domain
indexes (`skills-*-index.md`). The memory-index hierarchy (L1 -> L2 -> L3)
provides keyword-based routing. This supports manual deduplication via keyword
overlap checking, but does not automate similarity scoring.

## Gap Summary

| Component | Specified | Implemented | Gap |
|-----------|-----------|-------------|-----|
| Deduplication logic | Yes (prompt) | Prompt-only | No automated enforcement |
| Similarity threshold (70%) | Yes (prompt) | No tooling | LLM judgment only |
| `Search-Memory.ps1` | Referenced | Does not exist | Missing script |
| Memory router dedup | SHA-256 hash | Yes | Exact-match only, no semantic similarity |
| Handoff format | Yes (structured) | Prompt-only | No validation gate |
| Retrospective -> skillbook routing | Yes (orchestrator) | Manual | No automated trigger |

## Remediation Plan

### Short-term (P2, low effort)

1. **Remove `Search-Memory.ps1` references** from `skillbook.md`. Replace with
   the actual available tool: `memory_router.py` CLI or Serena `read_memory`
   tool for keyword search.

2. **Add deduplication verification to retrospective template**. The
   "Deduplication Check" table (retrospective.md line 782) should include a
   column for "Tool Used" to make it auditable.

### Medium-term (P1, moderate effort)

3. **Add keyword overlap scoring to memory router**. Extend `memory_router.py`
   with a function that computes Jaccard similarity between activation keywords
   of existing skills and a proposed skill. This replaces LLM-based similarity
   judgment with a deterministic metric.

4. **Create a `check_skill_duplicate.py` script**. Accept a proposed skill
   statement and keywords. Search existing skills. Return similarity score and
   most similar match. Exit code 0 if novel, 1 if duplicate.

### Long-term (P2, higher effort)

5. **Add CI validation for skill uniqueness**. Run the duplicate check script
   on any PR that adds files to `.serena/memories/`. Block merge if similarity
   exceeds threshold without explicit override.

6. **Automate retrospective -> skillbook routing**. When a retrospective
   artifact contains a Handoff Summary with skill candidates, trigger the
   skillbook agent automatically.

## Related Files

| File | Role |
|------|------|
| `src/claude/skillbook.md` | Skillbook agent prompt with dedup checklist |
| `src/claude/retrospective.md` | Retrospective agent prompt with handoff format |
| `.claude/skills/memory/memory_core/memory_router.py` | Memory router with hash-based dedup |
| `.agents/retrospective/2025-12-16-phase4-handoff-validation.md` | Original retrospective citing the gap |
