# Two-pipeline agent mirror: source, generate both trees, verify with drift + parity

Agent definitions have ONE source and TWO generated destinations. Edit the
source, regenerate, and let two independent checks prove the mirror is intact.
Never hand-edit a generated agent file.

## The pipeline

- Source of truth: `templates/agents/<name>.shared.md` (29 shared bodies as of
  #2707).
- Generator: `build/generate_agents.py` (+ `build/generate_agents_common.py`),
  invoked by `build/scripts/build_all.py::_build_agents` which calls
  `generate_agents.main([...])` across all platform configs.
- Destination 1 (Claude): `.claude/agents/<name>.md`.
- Destination 2 (Copilot CLI mirror): `src/copilot-cli/agents/<name>.agent.md`.

A single behavioral change (for example a severity rubric on
silent-failure-hunter) is made ONCE in the `.shared.md` body and flows to both
trees on regeneration.

## The two verifications

1. Source-to-generated drift: `build/scripts/detect_agent_drift.py`. Reports
   the percentage match on every (source, generated) pair. The #2707 fix
   required "detect_agent_drift 100% on all silent-failure-hunter pairs" before
   it was mergeable.
2. Installed-copy parity: `scripts/validation/run_install_parity_ci.py` (backed
   by `build/scripts/validate_install_parity.py`). An agent ships in several
   installed locations (the "install-parity members"); parity asserts every
   member carries the identical body. The #2707 fix confirmed "all six
   silent-failure-hunter install-parity members carry the identical rubric
   body."

## Why this matters

The drift check catches "I edited the generated file, not the source" and "I
edited the source but forgot to regenerate." The parity check catches "the two
platform trees diverged." Together they make the single-source invariant
enforceable in CI instead of a convention people forget.

## Workflow when changing an agent

1. Edit `templates/agents/<name>.shared.md`.
2. Run `build/scripts/build_all.py --check` (must be clean after commit).
3. Confirm `detect_agent_drift.py` reports 100% on the changed pairs.
4. Confirm `run_install_parity_ci.py` is OK.
5. The agent catalog line count regenerates (155 to 158 in #2707); commit the
   regenerated catalog with the change. Generated artifacts ship WITH the
   change, never in a follow-up PR.

## Evidence

- PR #2707 (merge a4af5d2f66aa): three SkillOpt fixes including
  silent-failure-hunter, verified via `build_all.py --check`,
  `detect_agent_drift` (100% on all pairs), and `run_install_parity_ci.py`.
- Source tree: `templates/agents/*.shared.md`.
- Generator: `build/generate_agents.py`, `build/scripts/build_all.py`.
- Checks: `build/scripts/detect_agent_drift.py`,
  `scripts/validation/run_install_parity_ci.py`,
  `build/scripts/validate_install_parity.py`.
