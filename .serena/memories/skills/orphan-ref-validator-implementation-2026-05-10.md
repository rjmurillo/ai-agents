# Orphan-Ref-Validator Implementation - 2026-05-10

Implemented `.claude/skills/orphan-ref-validator/` per REQ-008, DESIGN-008, TASK-008. Closes #1939, child of epic #1933.

## Wedge Decision

PR1 implements AC1, AC2, AC3, AC5, AC6, AC7, AC9. AC4 emission is delegated to canonical `build/scripts/validate_marketplace_counts.py` per `.claude/rules/canonical-source-mirror.md`; PR1 ships the regex (`COUNT_CLAIM_RE` / `COUNT_LABEL_MAP` mirror canonical) but does not emit `count_claim` Findings. AC8 (`/test` Gate 5 wiring) deferred to PR2. Skill scans for skill_name and script_path references; emits ADR-056 envelope with `VERDICT: PASS|WARN|CRITICAL_FAIL|ERROR`; exit codes per ADR-035.

## Default Scope (intentionally narrow)

- `.agents/specs/` (active specs)
- `tests/evals/`
- Plugin and marketplace manifests

Opt-in via flags:

- `--include-adrs` adds `.agents/architecture/` and `docs/`
- `--include-skill-descriptions` adds `.claude/skills/*/SKILL.md`

Rationale: ADRs and docs reference proposed-but-unimplemented or deleted-by-superseding entities; skill descriptions have widespread preexisting drift. Including them by default produces critical-fail dominated by historical artifacts, defeating the build-gate purpose.

## Ignore Directives

- `<!-- orphan-ref-ignore-file -->` in the first 50 lines skips the whole file. Used for M1 deletion specs (REQ-007, TASK-007, DESIGN-007), MCP technical specs (mcp-integration-overview, agent-orchestration-mcp-spec, session-state-mcp-spec, skill-catalog-mcp-spec).
- `<!-- orphan-ref-ignore -->` on a line skips that line. Used for spot ignores in REQ-002, REQ-008, TASK-008, INTERVIEW-1884, DESIGN-008.

## Filters

`scripts/filters.py` houses the kebab denylist (extracted to keep `scan.py` under 500-line taste-lint cap). Categories: prose phrases, model IDs (regex), Claude Code skill schema fields, third-party Action and CodeQL config names, bot identifiers, eval verdict literals, PowerShell/npm/pip module names, distributed-systems vocabulary, git hook lifecycle names, plugin namespace identifiers.

## /build Wiring

`.claude/commands/build.md` Mandatory Exit Gates extended from 3 to 4 gates. `orphan-ref-validator` runs after code-qualities-assessment, taste-lints, and doc-accuracy. CRITICAL_FAIL blocks the build phase.

## Real Orphan Surfaced

`.claude-plugin/marketplace.json` description originally claimed `23 agents, 23 slash commands, 35 lifecycle hooks, and 67 reusable skills`. The first PR1 attempt re-fixed the agent and command counts using a naive `iterdir` enumeration that diverged from the canonical `validate_marketplace_counts.py` (which excludes `AGENTS.md`/`CLAUDE.md` from agents and walks recursively for commands). Pre-push surfaced the divergence; canonical autofix (C8 `8e545bd3`) reverted to the canonical-correct counts: 23 agents, 23 slash commands, 35 lifecycle hooks, 68 reusable skills.

## Tests

`tests/test_scan.py` covers positive and negative detection per kind, ADR-056 envelope shape, vendored-install scenarios, ignore directives, glob target expansion, edge cases (empty file, secret denylist, oversized files, mixed living and dead refs).

## Deferred / Follow-Up

- PR2 milestones F1 (script-path detection broadly) and F2 (`/test` Gate 5 wiring).
- Track preexisting orphans surfaced in `--include-adrs` mode (deleted skills referenced in ADR-007, ADR-013, ADR-017, ADR-040; missing scripts in ADR-052) via separate cleanup issue.
- Track preexisting orphans surfaced in `--include-skill-descriptions` mode (cross-skill drift in SkillForge/TRANSFORMATION_NOTES, planner, reflect, security-scan, steering-matcher, work-operating-model, taste-lints, validation-authority, world-model-diagnostic, slashcommandcreator, pipeline-validator, pr-comment-responder, session-migration, memory-enhancement) via separate cleanup issue.

## Commits

- 62143d96: spec artifacts (REQ-008, DESIGN-008, TASK-008, INTERVIEW)
- 6957d8fe: skill core (SKILL.md, scan.py, filters.py removed-then-added in C3, tests)
- 8f34b6a4: M1 spec ignore directives + denylist refactor
- 0d08807c: MCP architecture spec ignore directives
- 8e545bd3: marketplace count fix + /build wiring + REQ-002/INTERVIEW-1884 ignores
