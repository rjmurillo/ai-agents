# Provenance and Re-Verification Table

The full volatile-fact index for `ai-agents-change-control`. SKILL.md keeps the maintenance rule and the verified date; the per-fact re-verify commands live here because they are consulted only when editing the skill, not when using it to classify a change.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

Verified against the working tree on 2026-07-03. Volatile facts and their re-verification commands:

| Fact | Source | Re-verify |
|------|--------|-----------|
| Verification-based enforcement wording | `.agents/SESSION-PROTOCOL.md:36` | `sed -n 30,40p .agents/SESSION-PROTOCOL.md` |
| Investigation allowlist (9 patterns; ADR-034 text lags at 5) | `scripts/modules/investigation_allowlist.py`; `.agents/architecture/ADR-034-investigation-session-qa-exemption.md:79-83` | `uv run python -c "from scripts.modules.investigation_allowlist import get_investigation_allowlist_display as g; print(len(g()), g())"` |
| build_all no-claude-writes invariant | `build/scripts/build_all.py:962-967` | `grep -n "REQ-003-010" build/scripts/build_all.py` |
| 20-commit block threshold and bypass label | `.github/workflows/pr-validation.yml:369,483` | `grep -n "blockThreshold\|commit-limit-bypass" .github/workflows/pr-validation.yml` |
| Git hook jobs, filters, and validators | `lefthook.yml` | `uv run --frozen lefthook validate` |
| Plugin versions (volatile; never hard-code them in prose) | the three `.claude-plugin/plugin.json` files | `grep -o '"version": "[^"]*"' .claude/.claude-plugin/plugin.json src/claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json` |
| PR #1942 motivating failure | `build/scripts/validate_plugin_version_bump.py:10-12` | `sed -n 8,14p build/scripts/validate_plugin_version_bump.py` |
| SHA-pin tension (Exceptions: None vs GP-006) | `.agents/governance/PROJECT-CONSTRAINTS.md:180`; `.agents/governance/golden-principles.md:63-69` | `grep -n "Exceptions" .agents/governance/PROJECT-CONSTRAINTS.md; sed -n 63,70p .agents/governance/golden-principles.md` |
| ADR-066 proposed, ADR-071 accepted, #2230 rejected | Status sections of both ADR files | `sed -n 1,20p .agents/architecture/ADR-066-hook-fail-open-reconciliation.md; sed -n 1,10p .agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` |
| FM-9 and FM-10 sections; "neutral default" quote | `.agents/governance/FAILURE-MODES.md:284,315` | `grep -n "neutral default" .agents/governance/FAILURE-MODES.md` |
| Incident retro paths (908, 1187, 1887, 1965, 2205) | `.agents/retrospective/` | `ls .agents/retrospective/ \| grep -E "908\|1187\|1887\|1965\|2205"` |
| `[skip-drift-check]` bypass contract | `.github/workflows/agent-drift-detection.yml:17,65-69` | `grep -n "skip-drift-check" .github/workflows/agent-drift-detection.yml` |
| ai-pr-quality-gate authoritative blocker | `.github/workflows/ai-pr-quality-gate.yml:735` | `grep -n "check_critical_failures" .github/workflows/ai-pr-quality-gate.yml` |
| ADR-006 amendment scope and conditions | `.agents/architecture/ADR-006-thin-workflows-testable-modules.md:255-309` | `grep -n "Amendment 2026-04-28" .agents/architecture/ADR-006-thin-workflows-testable-modules.md` |
| Hook-install check rationale | `scripts/validation/checks_plugin.py:127-134` | `grep -n "def validate_git_hooks_installed" scripts/validation/checks_plugin.py` |

Maintenance rule: any edit to a cited source line number, plugin version, or ADR status invalidates the matching row. Re-run the re-verify command and update the row in the same commit. This file is plugin content; editing it requires a `.claude/.claude-plugin/plugin.json` bump.
