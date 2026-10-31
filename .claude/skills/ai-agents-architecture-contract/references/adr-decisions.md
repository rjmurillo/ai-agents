# Load-Bearing Decisions and Their ADRs

The Phase 2 table of `ai-agents-architecture-contract`. SKILL.md keeps the supersession notes that change what is binding. This file keeps each decision, its record, and why it exists. Status is not typed here. Read it from the ADR frontmatter:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-architecture-contract/scripts/contract_probe.py" --repo . adrs
```

The command prints `status`, `superseded_by`, `implemented`, and `date` for every ADR this skill cites (state at 42e409325, 2026-10-31). It exits 1 when a cited ADR has no file. It does not tell you whether a mechanism is still enforced. Check the gate, not the status. ADR numbers have collided historically, so the command lists every file that matches a number.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers (issue #2050). Declared paths: templates/agents -->

| Decision | ADR | Note beyond status | Why it exists |
|---|---|---|---|
| Memory-first: retrieval precedes reasoning; Serena (`.serena/memories/`) canonical | ADR-007, then ADR-106 | ADR-007 is superseded. ADR-106 (Serena-Only Memory Architecture) is the binding record. The supplementary store was retired by issue #5574 | Agents re-derive knowledge badly; retrieval is cheaper and auditable |
| Distributed handoffs; HANDOFF.md deleted (was read-only) | ADR-014 | | Single-file write target caused merge-conflict storms |
| Two-source agent templates (shared templates plus hand-written `src/claude/`) | ADR-036 | Superseded by ADR-052, itself superseded by ADR-109. The manual dual-edit procedure ended when ADR-109 B1 made `src/claude/agents/` a generated tree | Claude prompts need harness-specific depth; 3 full sources would drift |
| Claude-first template strategy | ADR-052 | Superseded by ADR-109. Never built. ADR-109 inverted its direction: `templates/` stays canonical and `src/claude/agents/` is generated, so no direct Claude-to-platform generator exists and `docs/agent-catalog.md` still comes from `templates/agents/*.shared.md` | Superseded design, kept for history |
| Template-first plugin distribution | ADR-109 | B1 to B5 (agents, rules, skills, hooks, lib) are live; B6 retired the third manifest and the `claude-agents` marketplace entry | Agents, rules, skills, hooks, and lib render from `templates/` and `scripts/` into `src/claude/`, then binplace into `.claude/`; the drift gate catches a hand edit to a generated tree |
| Symlinked dogfood agents and skills | ADR-119 | `implemented` is true while the status is proposed. The symlinks exist, the decision is not accepted. Say so when you cite it | `.claude/agents/` and shipped `.claude/skills/<name>` link into `src/claude/` instead of copying |
| Python-only new scripts, bash prohibited | ADR-042 | | One toolchain, testable, cross-platform |
| Skill-first over subagent dispatch | `SKILL-CREATION-CRITERIA.md` "Skill-first rule" | Governance rule, enforced by `check_agent_skill_discriminator.py`; ADR-030 is rejected | A skill runs in the current context; a Task spawn loads a fresh one. Agents only for isolation |
| Memory skill decomposition into tiers | ADR-063, amended by ADR-089 | Tier 3 causal graph removed: nothing read it | Tier 1 semantic (Serena search), Tier 2 episodic |
| Hook failure policy: prevention-first, fail-closed-and-loud | ADR-066 | | Launcher fail-open hid a broken hook from every customer for 33 days |
| Plugin hook runtime-contract verification | ADR-071 | Six-agent adr-review | Vendor docs were wrong by omission twice; contracts are tested, not assumed |
| Consolidated per-event hook dispatcher for Copilot CLI | ADR-068 | Rationale narrowed after the 2026-07-22 hook purge; ADR-097 then retired every tool-call hook. Issue #3218 closed after confirming the generation machinery stays live | Historical matcher and timeout behavior made one process per shim unsafe |
| Zero tool-use hooks | ADR-097 | `.claude/settings.json` keeps only session-boundary events | Per-call hooks were retired; see Phase 3 counts from `hook_inventory.py` |
| JTBD plugin slicing, per-harness emission | ADR-072 | Accepted with `implemented: false`: accepting the direction moves no code. Plugins are still sliced by directory | Plugins are sliced by directory today, not by job-to-be-done |
| Context corpus is the product | ADR-069 | A thesis; do not cite as settled | Thesis only |
| LSP-first navigation (static steering) | ADR-062 | Runtime enforcement retired (#3216) | Symbol queries beat grep on token cost |
