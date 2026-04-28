# Execution Plan: REQ-003 Multi-Tool Artifact Build System

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-04-27 |
| **Owner** | Claude (planning) / Richard (execution sponsor) |
| **Complexity** | High |
| **Spec** | `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md` |
| **Branch** | `feat/req-003-multi-tool-build` |
| **Total tasks** | 30 (M0:1 + M1:4 + M2:3 + M3:7 + M4:3 + M5:7 + M6:5; sizing 17S / 10M / 3L) |
| **Estimated effort** | ~23 person-days (post-amendment realism; analyst flagged 19-day budget as optimistic) |
| **Critical path** | M0 → M1 → M2 → M3 → M4 → M5 → M6 (no parallelism between milestones) |

## Objectives

- [ ] M1: Schema foundation — `templates/platforms/copilot-cli.yaml` + `validate_templates_schema.py`
- [ ] M2: Counter generalization — config-driven `validate_marketplace_counts.py`
- [ ] M3: Low-transform generators — `generate_agents.py` v2 + `generate_skills.py` + `build_all.py`
- [ ] M4: Medium-transform generators — `generate_commands.py` + `generate_rules.py` (severity-gated)
- [ ] M5: Hook generator with matcher shim — `generate_hooks.py` (HIGHEST RISK)
- [ ] M6: Marketplace two-plugin model — additive `claude-toolkit` + `copilot-cli-toolkit`

## Milestones

### M0 — Pre-flight Gate (S, ~0.5 day, BLOCKING)

| ID | Task | Size | REQ |
|----|------|------|-----|
| M0-T1 | Submit written ADR-006 (no-logic-in-YAML) justification: `copilot-cli.yaml` carries configuration data not control flow. Obtain maintainer sign-off. | S | R4 |

**Exit**: ADR-006 reviewer approval recorded; M1 unblocked. If rejected, escalate to architectural decision before any further work.

### M1 — Schema Foundation (S+M+S+S, ~2.5 days)

| ID | Task | Size | REQ |
|----|------|------|-----|
| M1-T1 | Create full `copilot-cli.yaml` (5 artifact stanzas, auditPolicy, schemaVersion) | S | REQ-003-002 |
| M1-T2 | Write `validate_templates_schema.py` (allowed-key, traversal, version) | M | REQ-003-002, -009 |
| M1-T3 | Unit tests: good fixture, bad-key, traversal | S | REQ-003-002 |
| M1-T4 | Create `templates/README.md` documenting provider×artifact mapping | S | REQ-003-002 |

### M2 — Counter Generalization (S+M+S, ~2 days)

| ID | Task | Size | REQ |
|----|------|------|-----|
| M2-T1 | Extract `build/scripts/yaml_loader.py` shared module | S | REQ-003-002, -009 |
| M2-T2 | Refactor `validate_marketplace_counts.py` config-driven | M | REQ-003-004 |
| M2-T3 | Verify zero-Python-edit extensibility | S | REQ-003-004 |

### M3 — Low-Transform Generators (M+S+M+S+S+S+M, ~5 days)

| ID | Task | Size | REQ |
|----|------|------|-----|
| M3-T1 | `generate_agents.py` v2 (suffix transform) — MUST preserve all v1 transforms by reusing `generate_agents_common.py`: `convert_frontmatter_for_platform`, `convert_handoff_syntax`, `convert_memory_prefix`, `expand_toolset_references`, `toolsFrom` aliasing, LF normalization. Snapshot test must include `visual-studio` agent with `toolsFrom` to prove no silent loss. | M | REQ-003-001, -010 |
| M3-T2 | `generate_skills.py` (directory copy) | S | REQ-003-001, -010 |
| M3-T3 | `build_all.py` orchestrator (`--check`/`--clean`/`--audit-format json`); audit log policy: **OVERWRITE not append**, NOT git-tracked (add `build/audit/` to `.gitignore`); test fixture asserts `git diff --name-only` post-run contains no `.claude/` paths (REQ-003-010 enforcement) | M | REQ-003-005, -008, -010, -011 |
| M3-T4 | NO-REGEN sentinel detection in generator base | S | REQ-003-008 |
| M3-T5 | Audit blocklist enforcement | S | REQ-003-011 |
| M3-T6 | Snapshot tests for agents + skills (include `visual-studio` toolsFrom case + multi-platform output diff) | S | REQ-003-001 |
| M3-T7 | Wire `build_all.py --check` into `.github/workflows/validate-plugin-manifests.yml` | M | REQ-003-005 |

### M4 — Medium-Transform Generators (M+L+M, ~4 days)

| ID | Task | Size | REQ | Deps |
|----|------|------|-----|------|
| M4-T1 | `generate_commands.py` (commands → user-invocable skills); register with orchestrator | M | REQ-003-001, D7 | M3-T3 |
| M4-T2 | `generate_rules.py` with severity-gate logic (high=fail, medium=warn, low=silent) + governance-keyword scan; verify severity field convention with author before implementation | L | REQ-003-006 | M3-T3 |
| M4-T3 | Snapshot fixtures covering all severity branches | M | REQ-003-006 | M4-T1, M4-T2 |

### M5 — Hook Generator with Matcher Shim (S+M+L+S+S+M+S, ~6 days, HIGHEST RISK)

| ID | Task | Size | REQ |
|----|------|------|-----|
| M5-T0 | **Pre-flight dry-run**: parse every live `matcher` value in `.claude/settings.json` against the planned shim disambiguation logic (regex/tool-glob/bare). Verify multi-pipe glob (`Bash(pwsh*Invoke-Pester*\|npm test*\|...)`), MCP namespaced (`mcp__serena__write_memory`), regex alternation (`^(Edit\|Write)$`), case sensitivity. Dry-run output documents expected classification per pattern; any ambiguity blocks M5-T2 design. | S | REQ-003-007 |
| M5-T1 | `generate_hooks.py` core (event remap, eventDrop WARN, version:1 wrapper) | M | REQ-003-007 |
| M5-T2 | Matcher shim injector (stdin buffer, pattern disambiguation, BytesIO replay) — **GO/NO-GO checkpoint at end of M5-T2**: if effort exceeds 2L, trigger kill criteria below | L | REQ-003-007 |
| M5-T3 | Idempotency: re-run replaces shim, does not stack | S | REQ-003-007 |
| M5-T4 | Whitespace normalization + crash policy (parallel with M5-T3) | S | REQ-003-007 |
| M5-T5 | Property-based tests via Hypothesis (fuzz pattern strings) + snapshot regression against all 29 real `.claude/hooks/*.py` scripts (live regression corpus, not synthetic fixtures) | M | REQ-003-007 |
| M5-T6 | Wire hooks into `build_all.py` orchestrator | S | REQ-003-005 |

**M5 kill criteria** (escalate if any triggers): (a) M5-T2 effort exceeds 2L; (b) M5-T5 coverage falls below 90% of live patterns; (c) M5-T0 dry-run flags >2 ambiguous patterns. **Fallback**: ship hooks WITHOUT matcher translation, emit WARN per dropped matcher in audit log, re-scope shim to follow-on PR. M6 unblocks regardless.

### M6 — Marketplace Two-Plugin Model (S+S+S+S+M, ~3 days)

| ID | Task | Size | REQ |
|----|------|------|-----|
| M6-T1 | `src/copilot-cli/.claude-plugin/plugin.json` (Copilot-side manifest) — explicit unique `name` field, disjoint from existing 3 entries; D9 isolation enforced | S | REQ-003-003, D9 |
| M6-T2 | Add additive entries to `marketplace.json` (legacy preserved); explicit naming decision recorded in plan decision log | S | REQ-003-003, -012 |
| M6-T3 | Update count tokens to actual file counts | S | REQ-003-003 |
| M6-T4 | Integration test: `jq '[.plugins[].name] \| unique \| length == (.plugins \| length)'` (uniqueness assertion) + counter green + no legacy deletions | S | REQ-003-003, -012 |
| M6-T5 | End-to-end integration test: source change in `.claude/agents/` → `build_all.py` → install Copilot CLI plugin into clean dir → verify agent appears via `copilot plugin list` | M | REQ-003-007 verification |

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-04-27 | Sequence milestones by transform complexity (low → high) | Front-load wins; defer hook matcher shim risk to M5 | Hooks-first to validate riskiest path early — rejected because shim breakage with no orchestrator yet would need stub everything |
| 2026-04-27 | Extract shared `yaml_loader.py` in M2 not M1 | M1 ships standalone; M2 introduces the consumer | Inline loader in each generator — rejected; duplicates path-traversal check |
| 2026-04-27 | NO-REGEN sentinel implemented in M3 base class | All generators inherit; no per-artifact reimplementation | Per-generator implementation — rejected; drift risk |
| 2026-04-27 | M6 ships additive (legacy plugins preserved) | REQ-003-012 backward-compat window; rollback safety | Hard cutover — rejected; same failure class as PR #1773 |
| 2026-04-27 | Audit log lives at `build/audit/`, not `src/copilot-cli/` | Per-spec amendment; keeps internal build metadata out of customer install | Inside plugin install — rejected by critic pre-mortem |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-04-27 | Created plan from spec REQ-003 + milestone-planner + task-decomposer outputs | Claude |
| 2026-04-27 | Amended after analyst pre-mortem (3 plan-level risks) + critic review (NEEDS_REVISION, 6 findings). Added M0 (ADR pre-flight), M1-T4 (README), M3-T7 (CI wiring), M5-T0 (dry-run), M6-T5 (e2e), M5 kill criteria, audit log policy, M3-T1 transform-preservation. Task count 23→30; effort 19d→23d. | Claude |

## Blockers

- None at planning stage. Residual open questions (RQ #1-4 in spec) are tagged for empirical post-merge testing per milestone (M4 has RQ #2; M5 has RQ #3 + RQ #4).

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|------------|--------|-----------|
| R1 | Hook matcher shim whitespace bypass enables security gate evasion | MED | HIGH | Exhaustive fixture per pattern type (M5-T5); whitespace normalization unit test (M5-T4); snapshot regression against all 29 real hook scripts |
| R2 | `applyTo:` not consumed by Copilot CLI for general use (RQ #2) | MED | MED | D8 WARN emit in M4-T2; no runtime dependency in exit criteria; revisit after empirical post-merge test |
| R3 | Two-plugin marketplace breaks Claude Code plugin load if discovery order changes | MED | HIGH | D9 per-source isolation; integration test (M6-T4); REQ-003-012 backward-compat window limits blast radius |
| R4 | ADR-006 (no logic in YAML) challenge blocks M1 | LOW | HIGH | Pre-merge ADR review request with written justification: config data, not control flow |
| R5 | `python3` not on Windows runner PATH (RQ #4) | MED | MED | M5 emits `py -3 -u` fallback in `powershell` block; document; empirical Windows test post-merge |
| R6 | CI staleness gate too slow at M3 onward (29 hook scripts × full regen) | LOW | MED | `--check` mode diffs without regenerating; fall back to artifact tree cache if CI exceeds 2 min |
| R7 | Phase 1 schema needs revision after M4 lands; cascade breakage | LOW | HIGH | `schemaVersion` SemVer enables additive changes without breaking older generators |
| R8 | M3 slip cascades; no float on critical path | MED | HIGH | Time-box M3 at day 5 post-M2-merge; if not green, drop M3-T6 (snapshot tests) to M4 milestone |
| R9 | Audit log noise in PR diffs (regen on every build) | LOW | MED | M3-T3 policy: overwrite not append; `build/audit/` in `.gitignore`; CI parses stdout not file |
| R10 | New plugin name collides with existing `claude-agents`/`copilot-cli-agents` | LOW | HIGH | M6-T4 uniqueness assertion via `jq`; M6-T2 names recorded in decision log pre-implementation |

## Deferred Items

- **Cursor (`.cursor/rules/*.mdc`) generation** — D3 out of scope
- **Codex CLI generation** — D6 out of scope
- **VSCode-specific separate plugin** — VSCode reads Copilot CLI artifacts; no separate plugin needed
- **Legacy plugin entry removal** — REQ-003-012 keeps additive for one release; removal is a separate PR next cycle
- **Authoring new artifact content** — build-pipeline-only; content unchanged
- **Migration of `.claude/<artifact>/`** — `.claude/` stays canonical and unchanged

## Related

- Issue: (no GH issue; tracked in spec REQ-003 + this plan)
- Spec: `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md`
- Branch: `feat/req-003-multi-tool-build`
- PRs: pending (one per milestone)
- ADRs: ADR-006 (no logic in YAML — pre-empt review), ADR-042 (Python migration), ADR-007 (memory-first)
- Aftermath of: PR #1773 (regression) + PR #1795 (P0 fix)
