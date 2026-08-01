# Agent mirror pipelines: generated vs hand-maintained trees

Agent files live in several trees. Two are generated from templates; the rest
are hand-maintained. Never confuse them.

## Generated trees (template source -> generator -> output)

- Source of truth: `templates/agents/<name>.shared.md`.
- Generator: `build/generate_agents.py` (+ `build/generate_agents_common.py`),
  invoked by `build/scripts/build_all.py::_build_agents`.
- Destination 1 (Copilot CLI): `src/copilot-cli/agents/<name>.agent.md`.
- Destination 2 (VS Code): `src/vs-code-agents/<name>.agent.md`.

A behavioral change to a shared agent is made ONCE in the `.shared.md` body
and flows to both generated trees on regeneration. Do NOT hand-edit the
generated destinations.

## Hand-maintained trees (NOT generated from templates)

- `src/claude/*.md`: canonical hand-maintained Claude agent prompts. Edit
  directly, in lockstep with the shared template (ADR-036).
- `.claude/agents/`: hand-maintained self-host install copy for Claude Code.
- `.github/agents/`: hand-maintained self-host install copy for GitHub Copilot.

These three trees are never written by `build/generate_agents.py`. The generator
carries a hard guard against writing under `.claude/` (REQ-003-010).

## The two verifications

1. Template-to-generated staleness: `build/generate_agents.py --validate`.
   Runs on PRs via `.github/workflows/agent-drift-detection.yml`. Catches "I
   edited the generated file instead of the template" or "I edited the template
   but forgot to regenerate."

2. Claude-vs-VS-Code semantic drift: `build/scripts/detect_agent_drift.py`.
   Compares `src/claude/` against `src/vs-code-agents/` using section
   similarity. Runs weekly via `.github/workflows/drift-detection.yml`. Catches
   Claude-specific enrichment that has diverged significantly from the
   template-derived VS Code body. Note: this detector does NOT compare against
   the templates directly.

3. Install-copy parity: `scripts/validation/run_install_parity_ci.py` (backed
   by `build/scripts/validate_install_parity.py`). Asserts that every
   install-parity member of a shared-template agent carries the identical body.

## Workflow when changing a shared agent

1. Edit `templates/agents/<name>.shared.md`.
2. Also edit `src/claude/<name>.md` in the same change (it is NOT auto-synced).
3. Run `python3 build/generate_agents.py` to refresh `src/copilot-cli/agents/`
   and `src/vs-code-agents/`.
4. Run `build/scripts/build_all.py --check` (must be clean after commit).
5. Confirm `run_install_parity_ci.py` is OK.
6. Commit all generated and hand-edited files together.

## Evidence

- Source: `build/scripts/detect_agent_drift.py` module docstring (verified
  at HEAD); `templates/platforms/copilot-cli.yaml` and
  `templates/platforms/vscode.yaml` `outputDir` fields.
- Issue #4155 documents that the prior "two-pipeline" description incorrectly
  listed `.claude/agents/` as a generated destination and incorrectly stated
  that `detect_agent_drift.py` compares against templates.
- Checks: `build/scripts/detect_agent_drift.py`,
  `scripts/validation/run_install_parity_ci.py`,
  `build/scripts/validate_install_parity.py`.
