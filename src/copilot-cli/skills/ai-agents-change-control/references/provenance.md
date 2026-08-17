# Provenance and Re-Verification Table

A selected index of the drift-prone volatile facts for `ai-agents-change-control`. SKILL.md keeps the maintenance rule and the verified date; the per-fact re-verify commands live here because they are consulted only when editing the skill, not when using it to classify a change.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

Verified against the working tree on 2026-07-30. Volatile facts and their re-verification commands:

| Fact | Source | Re-verify |
|------|--------|-----------|
| Verification-based enforcement wording | `.agents/SESSION-PROTOCOL.md:36` | `sed -n 30,40p .agents/SESSION-PROTOCOL.md` |
| Investigation allowlist (8 patterns as of 2026-07-30; ADR-034 text reconciled to the same 8 in #2958) | `scripts/modules/investigation_allowlist.py`; `.agents/architecture/ADR-034-investigation-session-qa-exemption.md:78-87` | `uv run python -c "from scripts.modules.investigation_allowlist import get_investigation_allowlist_display as g; print(len(g()), g())"; sed -n '78,87p' .agents/architecture/ADR-034-investigation-session-qa-exemption.md` |
| build_all no-claude-writes invariant | `build/scripts/build_all.py:1108-1115,1171-1178` | `sed -n '1108,1115p;1171,1178p' build/scripts/build_all.py` |
| 20-commit block threshold and bypass label | `scripts/validation/pr_commit_count.py:54-65`; `scripts/ci/enforce_pr_validation.py:11,54-63` | `grep -n "THRESHOLD = " scripts/validation/pr_commit_count.py; grep -n "BYPASS_LABEL" scripts/ci/enforce_pr_validation.py` |
| Git hook jobs, filters, and validators | `lefthook.yml` | `uv run --frozen lefthook validate` |
| No `version` in any manifest or marketplace entry (ADR-092) | the three `.claude-plugin/plugin.json` files, both `marketplace.json` files | `python3 build/scripts/validate_plugin_version_bump.py` |
| Why the field must be absent | `build/scripts/validate_plugin_version_bump.py` docstring | `grep -n "WHY THE FIELD MUST BE ABSENT" build/scripts/validate_plugin_version_bump.py` |
| SHA-pin tension (Exceptions: None vs GP-006) | `.agents/governance/PROJECT-CONSTRAINTS.md:180`; `.agents/governance/golden-principles.md:63-69` | `grep -n "Exceptions" .agents/governance/PROJECT-CONSTRAINTS.md; sed -n 63,70p .agents/governance/golden-principles.md` |
| ADR-066 accepted, ADR-071 accepted, #2230 rejected | Status sections of both ADR files | `sed -n '1,15p' .agents/architecture/ADR-066-hook-fail-open-reconciliation.md; sed -n '1,15p' .agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` |
| FM-9 and FM-10 sections; "neutral default" quote | `.agents/governance/FAILURE-MODES.md:284,315,387` | `sed -n '280,325p;383,390p' .agents/governance/FAILURE-MODES.md` |
| Incident retro paths (908, 1187, 1887, 1965, 2205) | `.agents/retrospective/` | `find .agents/retrospective -maxdepth 1 \( -name "*908*" -o -name "*1187*" -o -name "*1887*" -o -name "*1965*" -o -name "*2205*" \)` |
| `[skip-drift-check]` bypass contract | `.github/workflows/agent-drift-detection.yml:17,65-69` | `grep -n "skip-drift-check" .github/workflows/agent-drift-detection.yml` |
| Pinned required contexts (no LLM blocker) | `scripts/ci/ruleset_required_contexts.py:REQUIRED_CONTEXTS`, `RETIRED_AI_REVIEW_CONTEXTS` | `grep -n "CONTEXTS" scripts/ci/ruleset_required_contexts.py` |
| ADR-006 amendment scope and conditions | `.agents/architecture/ADR-006-thin-workflows-testable-modules.md:255-309` | `grep -n "Amendment 2026-04-28" .agents/architecture/ADR-006-thin-workflows-testable-modules.md` |
| Hook-install check rationale | `scripts/validation/checks_plugin.py:174-180` | `grep -n "def validate_lefthook_installed" scripts/validation/checks_plugin.py` |

Maintenance rule: any edit to a cited source line number or ADR status invalidates the matching row. Re-run the re-verify command and update the row in the same commit. This file is plugin content, so regenerate the Copilot mirror (`uv run python build/scripts/build_all.py`) in the same commit. No manifest bump: the manifests carry no version (ADR-092).
