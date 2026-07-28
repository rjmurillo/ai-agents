# Provenance and Re-Verification Table

The drift-prone volatile facts behind `ai-agents-architecture-contract`. SKILL.md keeps the maintenance rule, the verified date, and the sibling map; the per-fact sources and re-verify commands live here because they are consulted only when editing or auditing the skill, not when using it to answer "which tree is canonical".

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

Verified 2026-07-03 against the working tree. Volatile facts are date-stamped inline in SKILL.md. Sources and re-verification commands:

| Claim | Source | Re-verify |
|---|---|---|
| Asymmetric seam, "No code moves on this ADR alone" | `.agents/architecture/ADR-072-jtbd-plugin-architecture.md` (Status, "the seam is asymmetric" section) | `grep -n "asymmetric" .agents/architecture/ADR-072-*.md` |
| Generator inventory, 7 generators | `build/scripts/build_all.py:426` GENERATORS; `.agents/governance/GENERATOR-FILES.md` | `grep -n -A8 "^GENERATORS" build/scripts/build_all.py` |
| REQ-003-010 no-write invariant | `build/scripts/build_all.py:962` | `grep -n "REQ-003-010" build/scripts/build_all.py` |
| src/claude manual sync | `templates/README.md:131`; ADR-036 Accepted | `grep -n "MANUAL" templates/README.md` |
| lib sync pairs | `scripts/sync_plugin_lib.py:27` SYNC_PAIRS | `grep -n -A4 "SYNC_PAIRS" scripts/sync_plugin_lib.py` |
| Local 3 events / 4 groups; vendored 2 events / 2 groups; generated 2 events / 2 registrations | `.claude/settings.json`, `.claude/hooks/hooks.json`, `src/copilot-cli/hooks/hooks.json` | `python3 -c "import json; from pathlib import Path; [print(p, len((d:=json.loads(Path(p).read_text()))['hooks']), sum(map(len,d['hooks'].values()))) for p in ('.claude/settings.json','.claude/hooks/hooks.json','src/copilot-cli/hooks/hooks.json')]"` |
| Per-event hook failure policy | `agent-harness-reference`; ADR-071 | Read the reference's exit and failure matrices |
| Fail-closed reversal, #2205 rationale | `.agents/architecture/ADR-066-*.md`, ADR-071 (Accepted) | `grep -n -A2 "## Status" .agents/architecture/ADR-066*.md .agents/architecture/ADR-071*.md` |
| Dispatcher modes and current inventory | generated manifests; ADR-068 | `find src/copilot-cli/hooks -name _manifest.json -print -exec cat {} \;` |
| Skill vs subagent latency 5-20ms vs 100-200ms | `.agents/architecture/ADR-030-skills-pattern-superiority.md:31` | `grep -n "100-200ms" .agents/architecture/ADR-030*.md` |
| Memory sync direction | `scripts/memory_sync/sync_engine.py` module docstring | `head -8 scripts/memory_sync/sync_engine.py` |
| Explicit correction and topical-memory retrieval | `memory` and `memory-search` skills; retained hook files are unregistered | `uv run pytest -q tests/build_scripts/test_copilot_dispatcher_artifact.py::test_only_advisory_pretooluse_registrations_are_absent` |
| Plugin names/versions, marketplaces, npm CLI | the three `.claude-plugin/plugin.json` files, `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json`, `packages/ai-agents-cli/package.json` | `find . -name plugin.json -not -path "*/node_modules/*"` then read each |
| Stale CONTRIBUTING pwsh commands | `CONTRIBUTING.md:155`; no repo `.ps1` files | `grep -n "pwsh" CONTRIBUTING.md; find . -name "*.ps1" -not -path "./.venv/*"` |
| ruff advisory | `.github/workflows/pytest.yml` (comments near lines 107-119, issue #2194) | `grep -n -i "ruff" .github/workflows/pytest.yml` |
| testpaths exclude skill tests | `pyproject.toml:41` | `grep -n "testpaths" pyproject.toml` |
| Verification-based enforcement doctrine | `.agents/SESSION-PROTOCOL.md:30` | `grep -n "verification-based" .agents/SESSION-PROTOCOL.md` |
| Full history (~1471 commits) with unresolvable retro-cited SHAs | local clone state | `git rev-list --count HEAD; git cat-file -t ddb76e0` (expect "Not a valid object name") |

Maintenance rule: when any row above fails its re-verify command, fix the skill (SKILL.md and this reference) in the same PR as the change that broke it, and label anything newly Proposed as Proposed.
