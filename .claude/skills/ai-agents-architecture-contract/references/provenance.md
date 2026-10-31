# Provenance and Re-Verification Table

<!-- vendor-portability-exec: repo-local contributor skill; invokes upstream validation scripts of rjmurillo/ai-agents on purpose -->

The drift-prone volatile facts behind `ai-agents-architecture-contract`. SKILL.md keeps the maintenance rule, the verified date, and the sibling map; the per-fact sources and re-verify commands live here because they are consulted only when editing or auditing the skill, not when using it to answer "which tree is canonical".

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

Re-verified 2026-10-31 against 42e409325 for the rows marked below; the `reverify.json` checks and the `claims` and `hook-counts` instruments are the live gate. Rows without a 2026-10-31 stamp were not re-audited. Sources and re-verification commands:

| Claim | Source | Re-verify |
|---|---|---|
| Asymmetric seam (re-verified 2026-10-31) | `.project-toolkit/architecture/ADR-072-jtbd-plugin-architecture.md` ("the seam is asymmetric" section; status accepted, `implemented: false`) | `grep -n "asymmetric" .project-toolkit/architecture/ADR-072-*.md` |
| Generator inventory | `build/scripts/build_all.py` `GENERATORS` list (re-verified 2026-10-31); `.agents/governance/GENERATOR-FILES.md` | `grep -n -A8 "^GENERATORS" build/scripts/build_all.py` |
| REQ-003-010 no-write invariant (re-verified 2026-10-31) | `assert_no_claude_writes` defined in `build/scripts/build_all.py`; the call site follows the comment `# REQ-003-010: enforce .claude/ no-write invariant.`; a violation raises `REQ-003-010 VIOLATION` with exit code 2; ADR-108 allowlists the template-owned skill files | `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-architecture-contract/scripts/contract_probe.py" --repo . guard` |
| Agent template generation (ADR-109 B1) | `build/scripts/build_all.py` agents generator; `templates/platforms/binplace.yaml` `agents` row; ADR-052 superseded by ADR-109 | `grep -n 'class: agents' -A3 templates/platforms/binplace.yaml && sed -n '2,9p' .project-toolkit/architecture/ADR-052-template-strategy.md` |
| lib sync pairs | `build/scripts/lib_mirror.py` SYNC_PAIRS | `grep -n -A4 "SYNC_PAIRS" build/scripts/lib_mirror.py` |
| Hook events and registrations per file (ADR-097 retired every tool-call hook; re-verified 2026-10-31) | `.claude/settings.json`, `.claude/hooks/hooks.json`, `src/copilot-cli/hooks/hooks.json` | `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-portability-campaign/scripts/hook_inventory.py" --repo . counts` |
| Per-event hook failure policy | `agent-harness-reference`; ADR-071 | Read the reference's exit and failure matrices |
| Fail-closed reversal, #2205 rationale | `.project-toolkit/architecture/ADR-066-*.md`, ADR-071 (Accepted) | `grep -n -A2 "## Status" .project-toolkit/architecture/ADR-066*.md .project-toolkit/architecture/ADR-071*.md` |
| Dispatcher modes and current inventory | generated manifests; ADR-068 | `find src/copilot-cli/hooks -name _manifest.json -print -exec cat {} \;` |
| Skill-first over subagent dispatch | `.agents/governance/SKILL-CREATION-CRITERIA.md`, "Skill-first rule" | `grep -n -A8 "### Skill-first rule" .agents/governance/SKILL-CREATION-CRITERIA.md` |
| Serena is the only memory backend | `.claude/skills/memory/memory_core/memory_router.py` module docstring | `head -12 .claude/skills/memory/memory_core/memory_router.py` |
| Explicit correction and topical-memory retrieval | `memory` and `memory-search` skills; the retired hooks have no test that guards their absence | `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-portability-campaign/scripts/hook_inventory.py" --repo . counts` shows no tool-call registration |
| Plugin names and versions, marketplaces, npm CLI (re-verified 2026-10-31) | the two plugin.json files `src/claude/.claude-plugin/plugin.json` and `src/copilot-cli/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json`, `packages/ai-agents-cli/package.json`. The root `.claude-plugin/plugin.json` does not exist; `.claude/.claude-plugin/plugin.json` was deleted at ADR-109 B6 | `grep -n -e '"name"' -e '"version"' src/claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json .claude-plugin/marketplace.json .github/plugin/marketplace.json packages/ai-agents-cli/package.json` (only package.json prints a version) |
| No pwsh commands in CONTRIBUTING and no repo `.ps1` files (ADR-042) | `CONTRIBUTING.md`; repo tree | `grep -c pwsh CONTRIBUTING.md` prints 0; `git ls-files "*.ps1"` prints nothing |
| Ruff changed-file and whole-tree count ratchets block regressions while legacy debt remains | `.github/workflows/pytest.yml:135-186`; `scripts/ci/ruff_ratchet.py`; `scripts/ci/ruff_count_ratchet.py` | `sed -n '135,186p' .github/workflows/pytest.yml; head -40 scripts/ci/ruff_ratchet.py scripts/ci/ruff_count_ratchet.py` |
| testpaths exclude skill tests | `pyproject.toml [tool.pytest.ini_options].testpaths` | `grep -n "testpaths" pyproject.toml` |
| Observable-evidence enforcement doctrine (PR #5135, 2026-08-18, retired the earlier wording; renamed from "verification-based enforcement" by PR #5135, 2026-08-18, which retired mandatory session-log gates; SESSION-PROTOCOL.md itself was deleted along with the session skill cluster) | `.claude/skills/ai-agents-architecture-contract/SKILL.md`, "Verification-based governance" | `grep -in "verification-based governance" .claude/skills/ai-agents-architecture-contract/SKILL.md` |
| Retro-cited SHAs may exist in a clone but remain unreachable from `main` | local clone state | `for sha in ddb76e0 01e76615a; do git cat-file -t "$sha"; git merge-base --is-ancestor "$sha" origin/main; printf "%s %s\n" "$sha" "$?"; done` (expect type `commit` and ancestry status `1` when the objects exist) |

Maintenance rule: when any row above fails its re-verify command, fix the skill (SKILL.md and this reference) in the same PR as the change that broke it, and label anything newly proposed as proposed.
