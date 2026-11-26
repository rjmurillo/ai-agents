---
name: memory-documentary
version: 1.0.0
description: "Evidence-based documentary reports across project memory, repository artifacts, and GitHub issues, with citation chains. Use when you ask for an \"evidence-based report\", \"investigate across all memory systems\", or \"what happened with X over time\". Do NOT use for a single recall (use memory-search) or citation hygiene (use memory-enhancement)."
license: Apache-2.0
metadata:
  timelessness: 8/10
  category: analysis
  routing:
    role: nested-helper
    invoker: memory
    trigger: memory routes narrative cross-system report requests to memory-documentary
    user-facing: false
---
# Memory Documentary Skill

Generate comprehensive documentary-style reports from your memory systems with full evidence chains.

<!-- vendor-portability: .project-toolkit/retrospective, .project-toolkit/sessions, .project-toolkit/analysis, and .project-toolkit/architecture are optional sources inside the consumer repository. The report uses available sources. -->

---

## Quick Start

```text
/memory-documentary [topic]
```

Example topics:

- "recurring frustrations"
- "coding patterns not codified"
- "evolution of thinking on testing"
- "decisions I second-guessed"
- "what I complain about most"

---

## Triggers

Use this skill when:

- `Search my memories for patterns about...`
- `What does my history say about...`
- `Generate a documentary on my topic`
- `Cross-reference all systems for...`
- `Evidence-based analysis across memory systems`

---

## When to Use

Use this skill when:

- You need cross-system evidence for a pattern or recurring theme
- Investigating historical decisions and their evolution over time
- Building a cited, verifiable narrative from memory data

Use `memory` skill instead when:

- You need a simple search for a known fact or pattern
- The query targets a single memory tier, not cross-system synthesis

## Quick Reference

| Phase | Action | Output |
|-------|--------|--------|
| 1 | Topic Comprehension | Search variants, scope boundaries |
| 2 | Investigation Planning | Explicit queries per system |
| 3 | Data Collection | Evidence with retrieval keys and dates |
| 4 | Report Generation | Documentary with citations |
| 5 | Memory Updates | Store meta-pattern discovered |

---

## Process

Find project records through `memory-search` or the `memory` skill's recall
procedure. Use timeline and
documentation tools when their project scope is clear. Choose sources that
answer the question and record coverage gaps.

**Project Artifacts**:

- `.project-toolkit/retrospective/` - Learning extractions
- `.project-toolkit/sessions/` - Session logs
- `.project-toolkit/analysis/` - Research reports
- `.project-toolkit/architecture/` - ADRs
- `.project-toolkit/planning/` - Plans and PRDs

**GitHub Issues**:

- Open and closed issues
- Comments and related PRs

---

## Commands

```bash
# Standard invocation
/memory-documentary "recurring frustrations"

# With explicit time range
/memory-documentary "testing patterns" --since 2025-12-01
```

---

## Report Structure

### Executive Summary

- Key finding in one sentence
- Timeline span (earliest to most recent)
- Evidence count (memories + observations + issues + files)
- Major pattern categories

### Evidence Trail

Full citation for each finding:

- Source system or repository path
- Record ID or file path used for retrieval
- Date from the record or version history
- Direct quote from source
- Links to related evidence

### Pattern Evolution

Timeline showing how thinking changed:

```text
YYYY-MM-DD: [Observation #ID] - Initial state
YYYY-MM-DD: [Serena memory-name] - First iteration
YYYY-MM-DD: [Issue #NNN] - Technical response
```

### Unexpected Patterns

Cross-system synthesis revealing:

- Frequency patterns (time clustering)
- Correlation patterns (X happens before Y)
- Avoidance patterns (conspicuous absence)
- Contradiction patterns (saying vs doing)
- Evolution patterns (recursive loops)
- Emotional patterns (frustration markers)

### Synthesis

- What all systems agree on
- Which observations are recent and which patterns persist
- Actionable recommendations

---

## Evidence Standards

| Standard | Requirement |
|----------|-------------|
| Citation | Every claim has a retrieval key, a date, and a quote |
| Quotes | Direct quotes, not paraphrases |
| Verification | Retrieval commands for all evidence |
| Cross-links | Related evidence connected |

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Partial searches | Miss critical evidence | Search ALL systems |
| Paraphrasing | Loses verifiability | Direct quotes only |
| Single query | Miss variations | 3+ query variants per system |
| Missing source coverage | Incomplete picture | Name the sources the report could access |

---

## Verification

After execution:

- [ ] Report saved to `.project-toolkit/analysis/[topic]-documentary-[date].md`
- [ ] Every claim has a citation with source system, retrieval key, and direct quote
- [ ] Evidence and source coverage are recorded
- [ ] Verified durable patterns use the `memory` write procedure when retained

## Output Location

Reports saved to: `.project-toolkit/analysis/[topic]-documentary-[date].md`

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| memory | Operations (search, update) |
| retrospective | Learning extraction |
| skillbook | Pattern → skill conversion |

---

## On Invocation

**Read**: `references/execution-protocol.md`

This contains the full 5-phase execution protocol with detailed instructions for each data source.
