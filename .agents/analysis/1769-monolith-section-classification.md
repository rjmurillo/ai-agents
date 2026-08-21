# Monolith Section Classification: .agents/*.md Extraction

> **Issue**: #1769 (Phase 1 audit)
> **Date**: 2026-06-01
> **Scope**: Every top-level `##` section in the three always-loaded monoliths
> **Method**: Static section inventory (fence-aware) + steering overlap check

## Summary

Phase 1 of #1769 is an audit only. It maps every top-level `##` section in the
three monolith instruction files to one of three destinations and does NOT move
any content. Content moves happen in later phases.

Destinations:

- **KEEP-IN-STEERING**: content already lives in an `.agents/steering/*.md` file.
  Per decision D6, the steering file stays authoritative and the section is not
  re-extracted into a rule.
- **ALWAYS-LOAD-RULE**: universal safety invariant. Lands in the one always-load
  rule (`agent-boundaries.md`, `applyTo: "**"`, `priority: critical`).
- **PATH-SCOPED-RULE**: loads only when a matching path is touched. Lands in one
  of the six path-scoped rule files with an `applyTo:` glob.

Frontmatter follows the repo convention (`applyTo:` + `priority:`), NOT the
issue's stale `paths:`/`alwaysApply:` keys. See the binding decision comment on
#1769 (2026-05-31): when the issue was filed, `.claude/rules/` held 1 file and
no generator. Main now has ~29 rule files and `build/scripts/generate_rules.py`,
which generates BOTH `.github/instructions/` and `src/copilot-cli/instructions/`
from `.claude/rules/`. Phase 2 authors rules and runs the generator; it does not
hand-author the Copilot mirror.

Section counts measured fence-aware (headings inside fenced code blocks, which
are template/example content, are excluded):

| Monolith | Top-level `##` sections | Lines |
|----------|-------------------------|-------|
| `AGENT-SYSTEM.md` | 13 | 1908 |
| `AGENT-INSTRUCTIONS.md` | 17 | 749 |
| **Total** | **30** | **2657** |

`SESSION-PROTOCOL.md` (10 sections, 324 lines) was one of the three
always-loaded monoliths this audit covered; it was deleted 2026-08-20
(Issue #5138), so its row and section table below are struck from the
live count. Its classification table is kept for the historical record.

`AGENT-INSTRUCTIONS.md`'s "Notes for Next Session" row below was a real
top-level section in the pre-edit file, not a scanner defect: the retired
session-log template nested a ` ```bash ` example inside its outer
` ```markdown ` fence, and CommonMark does not support fence nesting. The
first bare ` ``` ` line (closing the inner example) closed the OUTER fence
too, so everything after it, including "## Notes for Next Session", parsed
as ordinary document content rather than fenced example content. Verified
against `markdown-it` (`4.2.0`): parsing the original nested structure
produces a genuine `heading_open`/`heading_close` pair for "Notes for Next
Session". `tests/test_monolith_section_classification.py`'s fence-aware
scanner parsed this correctly per CommonMark; the template's fence
structure was the defect, not the scanner. Discontinuing session log
creation deleted that whole malformed template
(`.claude/rules/session-logs.md` MUST 1), so the phantom heading is gone
and the true count drops from 31 to 30. Its classification row is kept
for the historical record, same as the SESSION-PROTOCOL.md convention
above.

## Target Rule Files (Phase 2)

| Rule file | `applyTo:` | `priority:` |
|-----------|------------|-------------|
| `agent-boundaries.md` | `**` | `critical` |
| `session-protocol.md` | `.agents/sessions/**` | `high` |
| `agent-catalog.md` | `templates/agents/**,src/claude/**,.claude/agents/**` | `high` |
| `memory-handoff.md` | `.agents/**,.serena/**` | `normal` |
| `workflow-routing.md` | `templates/**,.agents/planning/**` | `normal` |
| `phase-execution.md` | `.agents/planning/**,.agents/sessions/**` | `normal` |
| `governance-agents.md` | `.agents/governance/**` | `high` |

Phase 2 must treat internal-only globs as Claude rule scopes, not portable mirror
scopes. `build/scripts/generate_rules.py` strips `.agents/`, `.claude/`, and
`.serena/` when it emits Copilot instruction mirrors, and all-internal scopes can
collapse to `applyTo: "**"` in generated outputs.

`governance-agents.md` avoids colliding with the existing `.claude/rules/governance.md`,
which already scopes `.agents/governance/**` for governance-file edit rules. The
new rule carries the agent quality-gate and conflict-resolution directives.

## Steering Overlap Reference (D6)

A section maps to KEEP-IN-STEERING only when its content already has a steering
owner. The steering files and their scopes:

| Steering file | `applyTo:` |
|---------------|------------|
| `agent-prompts.md` | `src/claude/**/*.md,.github/copilot-instructions.md` |
| `claude-skills.md` | `.claude/skills/**` |
| `documentation.md` | `**/*.md` (excl. `src/claude/**`, steering) |
| `powershell-patterns.md` | `**/*.ps1,**/*.psm1` |
| `security-practices.md` | `**/Auth/**,*.env*,**/*.secrets.*,.github/workflows/**,.githooks/**` |
| `testing-approach.md` | `**/*.Tests.ps1` |

## AGENT-SYSTEM.md (13 sections, 1989 lines)

| `##` Section | Lines | Classification | Target / glob |
|--------------|-------|----------------|---------------|
| 1. Executive Summary | 33 | PATH-SCOPED-RULE | `agent-catalog.md` (`templates/agents/**,src/claude/**,.claude/agents/**`); compress to system-purpose preamble |
| 2. Agent Catalog | 744 | PATH-SCOPED-RULE | `agent-catalog.md`; compress 20-agent prose to a table + per-agent key constraints (D7) |
| 2.5 Agent Coordination | 58 | PATH-SCOPED-RULE | `agent-catalog.md`; role table + ADR-009 escalation rule. Was "2.5 Agent Tier Hierarchy" (149 lines); the tier hierarchy was removed in issue #5130 and the section now quotes ADR-009 verbatim |
| 3. Workflow Patterns | 282 | PATH-SCOPED-RULE | `workflow-routing.md` (`templates/**,.agents/planning/**`); canonical workflow source is `src/claude/orchestrator.md`, keep pointer |
| 4. Routing Heuristics | 37 | PATH-SCOPED-RULE | `workflow-routing.md` |
| 5. Memory and Handoff System | 100 | PATH-SCOPED-RULE | `memory-handoff.md` (`.agents/**,.serena/**`) |
| 6. Parallel Execution | 296 | PATH-SCOPED-RULE | `workflow-routing.md`; compress voting/parallel-readiness detail |
| 7. Steering System | 71 | KEEP-IN-STEERING | `.agents/steering/README.md` is authoritative for steering mechanics; leave a pointer only |
| 8. Quality Gates | 42 | PATH-SCOPED-RULE | `governance-agents.md` (`.agents/governance/**`); critic/QA gate rules |
| 9. Conflict Resolution | 43 | PATH-SCOPED-RULE | `governance-agents.md`; agent-disagreement + blocker-report rules |
| 10. Quick Reference Tables | 40 | PATH-SCOPED-RULE | `agent-catalog.md`; workflow-selection + model-assignment tables |
| 11. Extension Points | 91 | KEEP-IN-STEERING | Adding-agents / adding-steering / adding-workflows mechanics overlap `agent-prompts.md` + `steering/README.md`; keep a pointer, do not duplicate |
| 12. Appendix | 53 | PATH-SCOPED-RULE | `memory-handoff.md`; entity-naming + relation-type tables drive memory writes |

## AGENT-INSTRUCTIONS.md (18 sections, 824 lines)

| `##` Section | Classification | Target / glob |
|--------------|----------------|---------------|
| Agent System Overview | PATH-SCOPED-RULE | `agent-catalog.md`; pointer + one-paragraph overview |
| Quick Start Checklist | ALWAYS-LOAD-RULE | `agent-boundaries.md` (`**`, `critical`); pre-work safety steps |
| Document Hierarchy | PATH-SCOPED-RULE | `agent-catalog.md`; which doc owns what |
| Phase Execution Protocol | PATH-SCOPED-RULE | `phase-execution.md` (`.agents/planning/**,.agents/sessions/**`) |
| Impact Analysis (Agent Prompt Changes) | KEEP-IN-STEERING | Agent-prompt-change impact overlaps `agent-prompts.md` (`src/claude/**`); pointer only |
| Commit Message Format | KEEP-IN-STEERING | Conventional-commit + Co-Authored-By rule already in `.claude/rules/universal.md` (`**`, `critical`); do not duplicate |
| Markdown Formatting Standards | KEEP-IN-STEERING | `documentation.md` (`**/*.md`) is authoritative for markdown linting |
| Notes for Next Session | PATH-SCOPED-RULE | `memory-handoff.md`; session carry-forward guidance |
| Session History | PATH-SCOPED-RULE | `session-protocol.md`; session log history belongs with session rules |
| Files to Review | PATH-SCOPED-RULE | `memory-handoff.md`; context retrieval order and handoff dependencies |
| Agent Invocation Reference | PATH-SCOPED-RULE | `agent-catalog.md`; delegation syntax |
| Skill System | KEEP-IN-STEERING | `claude-skills.md` (`.claude/skills/**`) is authoritative for skill standards |
| Traceability Rules | PATH-SCOPED-RULE | `memory-handoff.md`; cross-reference + entity-link requirements |
| Steering System | KEEP-IN-STEERING | `steering/README.md` authoritative; pointer only |
| Critical Reminders | ALWAYS-LOAD-RULE | `agent-boundaries.md`; DO / DO-NOT safety invariants |
| Emergency Recovery | ALWAYS-LOAD-RULE | `agent-boundaries.md`; recovery steps must be reachable from any path |
| Related Documents | KEEP-IN-STEERING | Pointer list; stays as a pointer block in the slimmed monolith |
| Lessons Learned | PATH-SCOPED-RULE | `memory-handoff.md`; feeds memory/retro, scope to `.agents/**` |

## SESSION-PROTOCOL.md (10 sections, 324 lines): historical, file deleted 2026-08-20

| `##` Section | Classification | Target / glob |
|--------------|----------------|---------------|
| RFC 2119 Key Words | ALWAYS-LOAD-RULE | `agent-boundaries.md`; requirement-keyword definitions bind every session |
| Protocol Enforcement Model | PATH-SCOPED-RULE | `session-protocol.md` (`.agents/sessions/**`); trust vs verification model |
| Session Start Protocol | PATH-SCOPED-RULE | `session-protocol.md` |
| Session Mid Protocol | PATH-SCOPED-RULE | `session-protocol.md`; commit-count monitoring |
| Session End Protocol | PATH-SCOPED-RULE | `session-protocol.md` |
| Unattended Execution Protocol | PATH-SCOPED-RULE | `session-protocol.md`; autonomous-operation rules |
| Validation Tooling | PATH-SCOPED-RULE | `session-protocol.md`; `scripts/validation/` + validator commands |
| Optional Appendix: JSON Session Log Template | PATH-SCOPED-RULE | `session-protocol.md`; optional JSON schema and validator usage |
| ADR Cross-Reference | KEEP-IN-STEERING | Pointer to governing ADRs; stays in slimmed monolith |
| Related Documents | KEEP-IN-STEERING | Pointer block; stays in slimmed monolith |

## Tallies

Live count, `AGENT-SYSTEM.md` and `AGENT-INSTRUCTIONS.md` only
(`SESSION-PROTOCOL.md` deleted 2026-08-20, Issue #5138); its 1
ALWAYS-LOAD-RULE, 7 PATH-SCOPED-RULE, and 2 KEEP-IN-STEERING sections are
struck from these counts. `AGENT-INSTRUCTIONS.md`'s "Notes for
Next Session" heading (see note above the per-monolith table) is also
struck: its 1 PATH-SCOPED-RULE section was a genuine heading in the
pre-edit document, removed along with the malformed template that exposed
it, so it is no longer present in the current document.

| Classification | Count |
|----------------|-------|
| ALWAYS-LOAD-RULE | 3 |
| PATH-SCOPED-RULE | 19 |
| KEEP-IN-STEERING | 8 |
| **Total sections** | **30** |

ALWAYS-LOAD sections (the only content entering `agent-boundaries.md`):

- AGENT-INSTRUCTIONS `Quick Start Checklist`
- AGENT-INSTRUCTIONS `Critical Reminders`
- AGENT-INSTRUCTIONS `Emergency Recovery`

## Notes and Caveats for Phase 2

- This is a static section map. Phase 2 MUST re-read each section before moving
  it, because line counts shift as content compresses.
- KEEP-IN-STEERING does not mean "delete." The slimmed monolith keeps a one-line
  pointer to the steering owner so existing `read()` references stay valid (D1).
- Two KEEP-IN-STEERING calls route to existing `.claude/rules/` files, not
  steering: `Commit Message Format` is already in `universal.md`, and markdown
  standards are owned by `documentation.md` steering. Phase 2 MUST NOT duplicate
  either into a new rule.
- `agent-boundaries.md` must stay under 100 lines. The four always-load sections
  above total well over that in raw form; Phase 2 compresses them to invariant
  bullets, dropping prose and examples.
- No content was moved in this PR. This document is the only file added.
