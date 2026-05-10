# M1 Findings: Skill Invocation Contracts (REQ-008 Step 0.5)

Verified 2026-05-09 on branch `feat/req-008-step-0-5-memory-first-gate`.

## Verification

| Skill | Path | Status |
|---|---|---|
| chestertons-fence | `.claude/skills/chestertons-fence/SKILL.md` | Present |
| memory | `.claude/skills/memory/SKILL.md` | Present |
| exploring-knowledge-graph | `.claude/skills/exploring-knowledge-graph/SKILL.md` | Present |

Existing invocation pattern in `.claude/commands/spec.md` (lines 143, 150, 157): `Skill(skill="<name>")`. M2 prose follows this pattern.

---

## chestertons-fence

**Invocation (skill)**: `Skill(skill="chestertons-fence")` with `target` (file/path) and `change` (description) parameters.

**Invocation (script)**: `python3 .claude/skills/chestertons-fence/scripts/investigate.py --target <path> --change "<description>" [--format json]`

**Process**: 6 steps. Identify Structure → Git Archaeology → PR/ADR Search → Dependency Analysis → Generate Report → Decision (PRESERVE | MODIFY | REPLACE | REMOVE).

**Triggers**: `why does this exist`, `chestertons fence`, `before removing`, `investigate history`, `prior art investigation`.

**Output**: investigation report at `.agents/analysis/NNN-chestertons-fence-TOPIC.md` OR JSON to stdout.

**For Step 0.5**: `target = Q3 system path` (e.g., `.claude/commands/spec.md`), `change = Q4 wedge description`. Output feeds the "### Direct prior art from memory" subsection of PriorArtBlock.

**Failure mode**: skill unavailable → log skip in coverage notes; continue (per AC-07).

---

## memory

**Primary entry point (script)**: `python3 .claude/skills/memory/scripts/search_memory.py "<query>" [--max-results N] [--lexical-only]`

**Invocation (skill)**: `Skill(skill="memory")` for skill-mediated workflows; the `search_memory.py` script is the canonical Tier 1 search interface.

**Process**: 3 phases. Query → Validate → Report.

**Triggers**: `search memory`, `check memory health`, `extract episode from session`, `update causal graph`, `count memory tokens`.

**Output (JSON)**: `Count`, `Source`, `SearchStatus` (with `SerenaSucceeded`, `ForgetfulSucceeded`, `ForgetfulError`), `TokenBudget`, `Results[]` (each: `Name`, `Source`, `Score`, `Path`, `Content`, `TokenEstimate`).

**For Step 0.5**: invoked once per topic (3+ distinct query variants per topic). Topics derived from Q3+Q4 named entities (normalized: lowercase, trim, strip leading path separators). Output feeds "### Direct prior art from memory" subsection of PriorArtBlock.

**Failure mode**: Forgetful MCP unavailable → degrades automatically to Serena-only; `SearchStatus.ForgetfulSucceeded=false` is the detection signal. Coverage note recorded; gate continues without halting (per AC-07).

**Memory-First Gate declaration**: `.claude/skills/memory/SKILL.md` line 104 reads "Memory-First Gate (BLOCKING)". This is the canonical statement of the gate that REQ-008 wires into `/spec`.

---

## exploring-knowledge-graph

**Invocation**: `Skill(skill="exploring-knowledge-graph")`. No script files; SKILL tool invocation only. Backend: Forgetful MCP via `execute_forgetful_tool` calls inside the skill.

**Process**: 5 phases. Semantic Entry Point → Expand Memory Details → Entity Discovery → Entity Relationships → Entity-Linked Memories.

**Depth control (canonical from SKILL.md)**: Shallow = Phases 1-2 (~5-15 memories). Medium = Phases 1-4 (adds entity discovery + relationships). Deep = all 5 phases (adds entity-linked memories).

**Triggers**: `what do you know about X`, `how do I explore the knowledge graph`, `how are these concepts connected`, `give me comprehensive context on X`, `map out related knowledge for X`.

**Output**: grouped findings (Memories: Primary/Linked/Entity-linked; Entities: name, type, relationship count, linked memory count; Artifacts: documents and code via memory links; Graph Summary: total nodes, key themes, suggested follow-up queries).

**For Step 0.5**: depth = ProvisionalTier mapping. Tier 1-2 → Shallow (Phases 1-2). Tier 3 → Medium (Phases 1-4). Tier 4-5 → Deep (Phases 1-5). Output feeds "### Connected context from exploring-knowledge-graph" subsection of PriorArtBlock.

**Failure mode**: Forgetful MCP unavailable → skill cannot run (no fallback); skip and log in coverage notes; continue without halting (per AC-07).

---

## M1 Exit Criteria

- [x] `chestertons-fence/SKILL.md` exists; invocation contract documented (above)
- [x] `memory/SKILL.md` exists; `search_memory.py` invocation pattern documented
- [x] `exploring-knowledge-graph/SKILL.md` exists; depth parameter contract documented
- [x] Findings recorded in this file (referenced from PR description)

## Handoff to M2

M2 commit 2A prose can cite invocation patterns from this file verbatim. Three subsection headings (`### Direct prior art from memory`, `### Connected context from exploring-knowledge-graph`, `### Coverage notes`) are locked.
