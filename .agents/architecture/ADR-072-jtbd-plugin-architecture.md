# ADR-072: JTBD-Based Plugin Architecture with Per-Harness Emission

## Status

Proposed. Architect design review completed (verdict: APPROVE WITH CHANGES); this
ADR may exist as `proposed` but MUST clear the five approval conditions in
"Conditions to reach Accepted" before its status moves to `accepted` and any
milestone is implemented. Requested by issue #1774 (parent epic #1072, v0.4.0
Framework Extraction). Refines the plugin taxonomy of ADR-045 (see Decision
Drivers). No code moves on this ADR alone.

## Date

2026-06-09

## Distribution context

This repository is a distribution installed by roughly 400 engineers across an
organization through multiple harnesses (Claude Code, GitHub Copilot CLI, VS Code,
Codex CLI, Cursor). The plugin boundaries are an install-time contract for that
population; the marketplace currently ships two live plugins (`claude-agents`,
`project-toolkit`). Getting boundaries wrong forces a migration on every consumer,
which is why this is an ADR, not a refactor.

## Context

Plugins are sliced today by where files live, not by the job the user hires them
to do. ADR-045 already began framework extraction into concern-based plugins
(`core-agents`, `framework-skills`, `session-protocol`, `quality-gates`); this ADR
re-expresses those boundaries in job-to-be-done terms and adds per-harness emission
for the non-agent artifact classes.

Users think in jobs ("ship code safely", "enforce standards", "understand this
codebase"), and they run different harnesses that each consume a different file
format for the same capability. "Write and ship code" is `/build`/`/test`/`/review`
/`/ship` commands plus quality skills and hooks on Claude Code; `.github/prompts/`
plus agents on Copilot CLI; `AGENTS.md` directives on Codex CLI; `.cursor/rules/*.mdc`
on Cursor.

### Current generation model (corrected; the seam is asymmetric)

The architect review corrected a premise in #1774 that this ADR carried in draft.
The repository does NOT use one uniform `templates/*.shared.md` source for every
artifact class. It uses two seams:

- **Agents:** canonical source is `templates/agents/*.shared.md` (dual frontmatter);
  `build/generate_agents.py` emits `src/{claude,copilot-cli,vs-code-agents}/`.
  Neither output tree is itself the source.
- **Commands, rules, hooks:** generation ALREADY exists
  (`build/scripts/generate_commands.py`, `generate_rules.py`, `generate_hooks.py`,
  wired into `build/scripts/build_all.py`). Their canonical source is `.claude/`
  (`.claude/rules/*.md`, `.claude/commands/*.md`, `.claude/hooks/*.py`), which
  Claude Code consumes directly; the generators transform that source into
  `.github/instructions/`, `.github/prompts/`, and `src/copilot-cli/`. See the
  artifacts stanza in `templates/platforms/copilot-cli.yaml` (`sourceDir: .claude/...`).

So commands/rules/hooks already have per-harness emission from a single source. The
job is not to build that seam; it is to make the per-harness coverage complete
(Codex, Cursor) and to map capabilities onto plugins.

## Decision

Adopt two coupled changes. Capability slicing without complete per-harness emission
still leaves harness gaps; per-harness emission without capability slicing still
presents a storage-shaped install menu.

### 1. Slice plugins by job-to-be-done (capability)

Reconcile against the five-plugin set named in #1774 (the four below plus
`agent-team`), not the four-plugin draft summary. Authoritative list:

| Plugin | Job to be done | Contents (capability) |
|--------|----------------|-----------------------|
| `dev-lifecycle` | Write and ship code safely | spec -> plan -> build -> test -> review -> ship workflows, supporting quality skills, shipping hooks |
| `quality-gates` | Enforce standards | PR review skills, golden principles, taste lints, security scan, pipeline validator, enforcement hooks |
| `session-protocol` | Learn and improve | session init/end, handoff protocol, retrospective, memory documentary |
| `agent-team` | Delegate to specialists | the specialist agents, routing, and the memory the agents share |
| `project-toolkit` | All of the above | meta-plugin that DEPENDS ON the above, retained for one-install convenience |

### 2. Reuse the existing source seam; do NOT relocate canonical sources

Default to the lower-risk mechanism the architect recommended: reuse the existing
`.claude/ -> generated` seam for commands/rules/hooks rather than relocating every
rule/command/hook source into `templates/`. The agent seam (`templates/agents`)
stays as is. New work is limited to:

- Completing per-harness emitters where coverage is missing (Codex `AGENTS.md`
  fragments, Cursor `.cursor/rules/*.mdc`), each behind a drift check matching the
  existing generators.
- Mapping capabilities to plugins (manifests), not moving files.

Relocating sources into `templates/*.shared.md` for all classes is recorded as a
considered alternative (see Alternatives), not the decision, because it is a real
migration with no demonstrated benefit over the working `.claude/` seam.

### 3. Declare cross-plugin dependencies so a partial install cannot break

#1773 decision D3 keeps `project-toolkit` bundled because agents/commands/hooks/
skills are interdependent (per the #1148 analysis): installing one without the
others breaks. JTBD slicing increases the cross-plugin dependency surface, so each
capability plugin MUST declare its `dependencies` in `plugin.json`, and a partial
install must fail loud at install time rather than degrade to a silent no-op (the
#2205 customer-wedge failure class). Whether #1148's coupling claim still holds is
an evidence question routed to the analyst before M4.

### 4. Milestoned, with M5 as the contract-breaking step

- M1 to M3: complete the per-harness emitters for commands, rules, hooks
  (additive, revertible: add generated output plus drift check, delete nothing).
- M4: capability plugin manifests with declared `dependencies`.
- M5: cut `project-toolkit` to depend on the capability plugins and deprecate the
  directory-named plugins. This is the irreversible, install-contract-breaking
  milestone and MUST ship with an installed-user migration path and a marketplace
  alias so existing install commands do not 404.

Each milestone is a separate issue under epic #1072 with its own acceptance
criteria and tests.

## Conditions to reach Accepted (architect review, APPROVE WITH CHANGES)

1. Generation-architecture description corrected to the asymmetric model and the
   existing `.claude/ -> generated` seam reused as default (done in this draft; A1).
2. Cross-plugin coupling reconciled with #1773 D3 / #1148 via declared `plugin.json`
   dependencies and fail-loud partial install (Decision section 3; A2/A5). Analyst
   to re-verify #1148 currency before M4.
3. ADR-045 cited as binding precedent; relationship stated as refine-within-epic,
   and ADR-045 amended if its taxonomy is superseded (A3).
4. Reversibility assessment treats M5 as contract-breaking with a migration path and
   marketplace alias (Decision section 4 and Reversibility; A4).
5. Plugin count and contents fixed to one authoritative five-plugin list (Decision
   section 1; A6).

Open Definition-of-Ready questions to answer before Accepted: install-time vs
build-time emission; whether a `jobs` field is a plugin.json schema extension or
expressible via `keywords`; Cursor/Codex emission scope for v0.4.0 vs deferred.

## Consequences

### Positive

- Install menu matches user mental model (install by job, not directory).
- Per-harness correctness with no hand-maintained format drift, reusing the seam and
  drift checks that already exist.
- New harnesses are one emitter, not a re-authoring of every capability.

### Negative / Costs

- Cross-cutting change to the install contract for ~400 consumers.
- New emitters and drift checks for Codex and Cursor are net new code.
- Transition window where directory-named and capability plugins coexist.

### Tracked follow-ups (not silent deferrals)

- M1 to M5 issues opened under #1072 before implementation.
- Analyst re-verification of #1148 coupling currency before M4.
- ADR-045 amendment for the taxonomy relationship.
- Deprecation note plus marketplace alias for directory-named plugins (M5).

## Alternatives Considered

1. **Keep directory-based plugins, document the JTBD mapping in prose.** Does not
   fix harness coverage gaps or the storage-shaped menu. Rejected.
2. **Relocate all sources to `templates/*.shared.md` (the draft's original
   mechanism).** A real migration that moves the canonical source of every rule,
   command, and hook out of `.claude/` and regenerates `.claude/` as output. No
   demonstrated benefit over the working `.claude/ -> generated` seam. Rejected as
   default; may be revisited if a concrete benefit appears.
3. **One mega-plugin with runtime harness detection.** Harnesses consume static
   files at install time, not a runtime service. Rejected.

## Reversibility and Vendor Lock-in

M1 to M4 are reversible at the milestone boundary (additive generated output behind
drift checks; revert by dropping the emitter). M5 is the contract-breaking
milestone and is reversible only with a migration window: it MUST ship a marketplace
alias mapping the deprecated plugin names to the new capability plugins so installed
users' commands keep resolving, plus a documented migration. No
harness-proprietary format enters the canonical sources; per-harness specifics live
only in emitters, so dropping a harness is removing one emitter.

## References

- Issue #1774 (this decision), parent epic #1072.
- ADR-045 (framework extraction via plugin marketplace; the 4-plugin taxonomy this
  refines).
- ADR-002 (agent generation seam), ADR-042 (Python-first hooks), ADR-006 (thin
  workflows, testable modules: the generator and drift-check shape).
- Issue #1773 decision D3 and the #1148 component-interdependence analysis.
- `build/generate_agents.py`, `build/scripts/{build_all,generate_commands,generate_rules,generate_hooks}.py`, `templates/platforms/copilot-cli.yaml`, `.claude-plugin/marketplace.json`.
