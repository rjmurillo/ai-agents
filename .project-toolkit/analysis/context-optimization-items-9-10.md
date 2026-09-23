# Context Optimization: Items 9 and 10

**Date**: 2026-02-09
**Branch**: feat/context-optimization-items-4-8
**Status**: Analysis complete, recommendations only

---

## Item 9: Reduce Serena initial_instructions overhead

### Problem

The `mcp__serena__initial_instructions` MCP call is the single largest context consumer at session start. SESSION-PROTOCOL.md Phase 1 (line 69) makes it a BLOCKING requirement.

### Findings

#### Finding 1: initial_instructions is for clients without system prompts

The Serena `project.yml` tool description (line 58-60) explicitly states:

> "Should only be used in settings where the system prompt cannot be set, e.g. in clients you have no control over, like Claude Desktop."

Claude Code **can** set the system prompt. The Serena MCP server already injects its configuration via the system prompt (visible as `## serena` in the system-reminder). This means calling `initial_instructions` duplicates content that Serena already provides.

#### Finding 2: The payload has two components

The `initial_instructions` response contains:

1. **Static instructions** (~700 tokens): General guidance on using symbolic tools, editing mode, interactive mode. These instructions repeat what Serena's system prompt already provides.
2. **Memory name list** (~7,500+ tokens): A JSON array listing all 995 memory filenames. This is the dominant cost.

The memory name list is also returned by `check_onboarding_performed` (which provides the same list with slightly different framing).

#### Finding 3: Memory list grows linearly

With 995 memories, the name list alone is approximately 31,543 characters (995 names averaging 31.7 chars each, plus JSON formatting). At roughly 4 chars/token, that is approximately 7,900 tokens. Every new memory adds to this cost. At the current growth rate, this will exceed 10k tokens from the name list alone within months.

#### Finding 4: Dual redundancy exists

Both `initial_instructions` and `check_onboarding_performed` return the full memory list. The session protocol requires calling both (Phase 1 requires initial_instructions; Phase 2 references memory-index from Serena). If both are called, the memory list appears twice in context.

### Recommendations

| ID | Recommendation | Savings Estimate | Complexity | Risk |
|----|----------------|-----------------|------------|------|
| 9A | **Skip initial_instructions call entirely** | ~10.7k tokens/session | Low (AGENTS.md + SESSION-PROTOCOL.md edit) | Low. Serena system prompt already provides tool guidance. Memory list from check_onboarding is sufficient. |
| 9B | **Skip both initial_instructions and check_onboarding** | ~10.7k + ~8k = ~18.7k tokens | Low | Medium. Agents lose awareness of available memories at session start. Mitigated by memory-index pattern (agents already use memory-index, not raw filename scanning). |
| 9C | **Configure Serena initial_prompt instead** | Variable | Low (project.yml edit) | Low. The `initial_prompt` field in project.yml (line 85) is currently empty. It could hold a compact, curated set of instructions (~200 tokens) without the memory list bloat. |
| 9D | **Curate memory count** (Item 10 synergy) | Proportional to memory reduction | Medium | Medium. Reducing 995 memories to 500 saves ~3,950 tokens from the name list alone. |

**Recommended approach**: 9A (primary) + 9C (optional enhancement).

**Rationale**: The static instructions in initial_instructions duplicate Serena's system prompt. The memory list is available through check_onboarding (which SESSION-PROTOCOL already calls implicitly through Serena activation). Claude Code agents do not need initial_instructions because Claude Code controls the system prompt.

**Protocol changes required**:

1. SESSION-PROTOCOL.md Phase 1, line 69: Change from MUST call initial_instructions to SHOULD NOT call initial_instructions (with rationale referencing this analysis).
2. AGENTS.md Serena Initialization section: Remove `mcp__serena__initial_instructions` from the required two-call sequence. Replace with `mcp__serena__check_onboarding_performed` if memory name awareness is still desired.
3. SessionStart hooks: Check if `Invoke-SessionInitializationEnforcer.ps1` enforces the initial_instructions call and update accordingly.

---

## Item 10: Memory curation gaps

### Problem

995 Serena memories (2.47 MB, 72,542 lines) exist with no automated curation. Memory skills exist (curating-memories, using-forgetful-memory, exploring-knowledge-graph, memory-enhancement) but have no automatic triggers.

### Findings

#### Finding 1: What automated memory operations exist today

| Hook/Automation | Location | What It Does | Scope |
|-----------------|----------|--------------|-------|
| Stop: invoke_skill_learning.py | `.claude/hooks/Stop/` | Extracts skill learnings from conversation, writes to `-observations.md` files | Skill observations only, not general memory curation |
| Stop: Invoke-SessionValidator.ps1 | `.claude/hooks/Stop/` | Validates session completeness (checks if Serena memory was updated) | Enforcement only, does not create memories |
| SessionStart: Invoke-MemoryFirstEnforcer.ps1 | `.claude/hooks/SessionStart/` | Enforces ADR-007 memory-first evidence | Read enforcement only |
| SessionStart: Invoke-SessionStartMemoryFirst.ps1 | `.claude/hooks/SessionStart/` | Enforces memory-first requirements | Read enforcement only |
| CI: memory-health.yml | `.github/workflows/` | Runs citation health checks on PRs | Citation staleness detection only |
| Session-End skill | `.claude/skills/session-end/` | Checks serenaMemoryUpdated flag | Enforcement only, does not curate |

**Key gap**: All hooks enforce memory usage (read) or validate existence (write). None perform curation (deduplication, staleness marking, linking, pruning).

#### Finding 2: Session protocol requires writing but not curating

SESSION-PROTOCOL.md Session End Phase 1 (line 396) requires:

> "Serena memory for cross-session context (using mcp__serena__write_memory or equivalent)"

The protocol mandates memory creation at session end but never mandates curation. This is an append-only system with no garbage collection.

#### Finding 3: Memory growth trajectory

| Metric | Value |
|--------|-------|
| Total memories | 995 files |
| Total size | 2.47 MB (72,542 lines) |
| Average memory size | 2.48 KB (73 lines) |
| Session-specific memories (session-*) | ~40+ files |
| Issue-specific memories (issue-*, session-*-issue-*) | ~30+ files |
| Duplicate-likely patterns (e.g., two files for same ADR review) | Estimated 10-15% |

Many session-specific memories (e.g., `session-1145-issue-998-verification` through `session-1177-issue-998-verification`) are variations on the same theme, suggesting consolidation opportunities.

#### Finding 4: Memory skills have no invocation hooks

The four memory skills are passive reference documents:

| Skill | Purpose | Invoked By |
|-------|---------|------------|
| curating-memories | Update, obsolete, link, deduplicate | Manual only (trigger phrases) |
| using-forgetful-memory | Create, query Forgetful memories | Manual only |
| exploring-knowledge-graph | Traverse Forgetful graph | Manual only |
| memory-enhancement | Citation verification, health reports | CI workflow (memory-health.yml) for health; manual for citations |

No hook or automation invokes curation. The `/reflect` skill extracts learnings but does not curate existing memories.

#### Finding 5: The memory-enhancement health tool exists but is not connected to curation

The `memory-enhancement health` command generates staleness reports. The CI workflow (`memory-health.yml`) runs it on PRs. But the output is informational only. No automation acts on the results (marking stale memories obsolete, alerting about duplicates, etc.).

### Recommendations

| ID | Recommendation | Effort | Impact |
|----|----------------|--------|--------|
| 10A | **Add a Stop hook for memory health check** | Medium (Python script) | Runs `memory-enhancement health --summary` at session end. Outputs a warning if stale memory count exceeds threshold. Non-blocking, awareness only. |
| 10B | **Add periodic curation guidance to session protocol** | Low (protocol edit) | Add a SHOULD recommendation: "Every 10th session, agents SHOULD run `/curating-memories` to consolidate duplicate and obsolete memories." |
| 10C | **Consolidate session-verification memories** | Low-Medium (manual or scripted) | The ~30 `session-NNNN-issue-998-verification` files could be consolidated into a single `issue-998-verification-history.md`. Saves ~29 memory names from the initial_instructions list. |
| 10D | **Set a memory budget ceiling** | Low (protocol + monitoring) | Define a target: "Serena memories SHOULD stay below 500 files." Add a warning to the memory health workflow when count exceeds threshold. |
| 10E | **Add TTL metadata to session-specific memories** | Medium (tooling) | Add `expires: YYYY-MM-DD` frontmatter to transient memories. A curation script can auto-mark expired memories as obsolete. |
| 10F | **Create a curation automation script** | Medium-High (Python) | A script that: (1) identifies duplicate-name-pattern clusters, (2) flags memories older than N days with no citations, (3) identifies orphaned session memories. Runs manually or as a scheduled workflow. |

**Recommended approach**: 10B (immediate) + 10C (quick win) + 10D (guardrail).

**Rationale**: The append-only growth problem compounds with Item 9 (memory list bloat in initial_instructions). Reducing memory count directly reduces the token cost of every session start. A budget ceiling with monitoring creates backpressure against unbounded growth.

---

## Cross-cutting: Item 9 + Item 10 synergy

The two items reinforce each other:

1. Skipping initial_instructions (9A) removes the ~10.7k token payload.
2. Curating memories below 500 (10D) reduces the check_onboarding name list from ~7.9k tokens to ~4k tokens.
3. Combined: ~14.6k tokens saved per session at the initial_instructions + onboarding step alone.

If both 9B (skip both calls) and 10D are applied, the savings reach ~18.7k tokens/session, though at the cost of losing memory name awareness at session start. The memory-index pattern (agents read the index memory, not the full list) mitigates this.

---

## Summary

| Item | Finding | Top Recommendation | Estimated Savings |
|------|---------|-------------------|-------------------|
| 9 | initial_instructions duplicates Serena system prompt + bloats context with 995 memory names | Skip the call (9A) | ~10.7k tokens/session |
| 10 | 995 memories with no curation, append-only growth, no hooks | Budget ceiling + consolidation + protocol guidance (10B + 10C + 10D) | Proportional to memory reduction; enables ongoing savings |
