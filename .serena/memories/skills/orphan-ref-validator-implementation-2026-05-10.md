# Orphan-Ref-Validator Implementation - 2026-05-10

Implemented `.claude/skills/orphan-ref-validator/` per REQ-009, DESIGN-009, TASK-009. Closes #1939, child of epic #1933.

## Wedge Decision

PR1 implements AC1, AC2, AC3, AC5, AC6, AC7, AC8. AC4 emission is delegated to canonical `build/scripts/validate_marketplace_counts.py` per `.claude/rules/canonical-source-mirror.md`; PR1 ships the regex (`COUNT_CLAIM_RE` / `COUNT_LABEL_MAP` mirror canonical) but does not emit `count_claim` Findings. The `/test` Gate 5 wiring is a PR2 follow-up (tracked under TASK-009 F2, not an REQ-009 AC). Skill scans for skill_name and script_path references; emits ADR-056 envelope with `VERDICT: PASS|WARN|CRITICAL_FAIL|ERROR`; exit codes per ADR-035.

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
- `<!-- orphan-ref-ignore -->` on a line skips that line. Used for spot ignores in REQ-002, REQ-009, TASK-009, INTERVIEW-1884, DESIGN-009.

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

- 62143d96: spec artifacts (REQ-009, DESIGN-009, TASK-009, INTERVIEW)
- 6957d8fe: skill core (SKILL.md, scan.py, filters.py removed-then-added in C3, tests)
- 8f34b6a4: M1 spec ignore directives + denylist refactor
- 0d08807c: MCP architecture spec ignore directives
- 8e545bd3: marketplace count fix + /build wiring + REQ-002/INTERVIEW-1884 ignores

## Handling Orphans in Stale Specs (2026-07-27, issue #3450)

The gate returned `CRITICAL_FAIL` on clean `main` with 32 findings across 12 files
in `.agents/specs/`, so `/build` gate 4 and `/test` gate 5 were red for every
contributor regardless of what their PR touched. All 32 pointed at entities that
were deliberately deleted. Two had a successor; the rest had none:

| Entity | Refs | Removed by |
| --- | --- | --- |
| `build/scripts/validate_marketplace_counts.py` | 24 | #2187, `2043c39863`, no successor |
| `scripts/validation/bundle_registry.py` | 4 | #3432, `9b121ec6e8`, no successor |
| `scripts/Validate-Traceability.ps1` | 1 | #1141, `efa406e9ab`, migrated to Python |
| `scripts/Validate-SessionEnd.ps1` | 1 | #610, `a4c58192a5`, renamed to `Validate-Session.ps1`, then expunged in #830 `bdacb6b19d` with no Python port |
| skill `session-qa-eligibility` | 1 | folded into `session` |
| skill `session-migration` | 1 | sunset, #2359, `59e6587c46` |

**The trap.** The obvious fix is to append `<!-- orphan-ref-ignore -->` to each
line and call them historical. An adversarial review caught that this is wrong for
a large share of them. The specs carry `status: draft`, `todo`, and `in-progress`,
and many of the flagged lines are imperative rather than narrative: "Create
`scripts/validation/bundle_registry.py`", "MUST import from", "shall replace the
hard-coded `PLUGIN_COUNTERS` dict", "THE SYSTEM SHALL invoke the existing
validator". Those are live contracts against deleted code. Silencing them hides a
real defect permanently, and also blinds that line to any future orphan.

Verify a suspected-dead instruction before deciding, and check the history rather
than only the working tree. `tests/test_command_bundles.py` is gone, and
`git grep -E 'BUNDLE_REGISTRY|PLUGIN_COUNTERS' -- '*.py'` returns nothing, so those
are unimplementable. Both names still appear in spec and ADR prose; scope the
search to `*.py` or the claim is false. But
`COUNT_PATTERN` and `LABEL_MAP` were a different case: absent from `patterns.py`
today, yet `git log -S COUNT_CLAIM_RE` shows they did land, as `COUNT_PATTERN`,
`COUNT_CLAIM_RE`, `COUNT_LABEL_MAP`, and `extract_count_claims`, and were retired
in #2853 (`9c88990b77`) to mirror the validator deleted in #2187. A first pass
called them "never landed" on the strength of a `grep` over the working tree, and
a second review corrected it. Grep proves absence now; only `git log -S` proves an
entity never existed.

Nothing validates embedded count claims today. `counts.py` in the skill does
*catalog enumeration*, not count-claim scanning. The file is the original count
subsystem from #1979, gutted in #2853; #3434 later added sibling-namespace
enumeration to the same file. The filename is a fossil. The scanner emits
exactly three kinds: `skill_name`, `script_path`, `scan_truncated`.

**What was done instead.** Ten of the thirteen affected specs got a dated
`> [!IMPORTANT]` retirement note after the H1 naming the removed dependency, the
PR, and the commit, and stating the instructions below are no longer actionable.
The other three already declared themselves historical, consolidated, or done in
their own frontmatter, so a banner would have added nothing. The line
directives stay, but they now sit under a banner that tells the reader the truth.
That satisfies `.agents/critique/001-fix-validate-sessionend-references-critique.md`
(do not rewrite historical records into anachronism) without leaving a live
contract pointing at a deleted file. Adding an annotation is not anachronism;
rewriting the original prose would be.

**Line scope, not file scope.** SKILL.md lists file scope on an active spec as an
anti-pattern because it masks real orphans. Base-tree precedent at `d544eaa60a`,
measured with `git grep -oh -F` over `*.md`, was 25 line-scope and 22 file-scope
directives. Without the markdown filter the counts are 31 and 23; the extra six
are `patterns.py`, its Copilot mirror, a test, and a session log, which implement
the directive rather than use it. State the filter when quoting either number.

**Directive mechanics worth remembering.** Line scope skips every reference on its
line, so one directive covers a line carrying two findings. File scope must appear
in the first 50 lines or it silently fails. Appending the directive after a table
row works when the directive is placed inside the last cell's text (before the closing pipe). Appending after the closing pipe introduces an extra column.
