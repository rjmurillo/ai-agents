# Agent mirror: two generated trees, three hand-maintained ones

Agent definitions have five destination trees. The generator writes exactly two
of them. The other three are hand-maintained copies that a human or agent must
edit deliberately. Regeneration will not carry a change into them, and no PR
gate compares their text. The only text comparison is a weekly, allowlist-scoped
audit that covers two pairs; see "The two verifications" below for what it does
and does not prove.

## The pipeline

- Shared body: `templates/agents/<name>.shared.md` (30 files as of 2026-08-01).
- Generator: `build/generate_agents.py` (+ `build/generate_agents_common.py`),
  invoked by `build/scripts/build_all.py::_build_agents` which calls
  `generate_agents.main([...])` across all platform configs.

| Tree | Written by the generator? |
|---|---|
| `src/copilot-cli/agents/<name>.agent.md` | yes |
| `src/vs-code-agents/<name>.agent.md` | yes |
| `src/claude/<name>.md` | no, hand-maintained |
| `.claude/agents/<name>.md` | no, hand-maintained |
| `.github/agents/<name>.agent.md` | no, hand-maintained |

The generated pair is exactly the `outputDir` set for agents in
`templates/platforms/*.yaml`: `src/copilot-cli/agents` and `src/vs-code-agents`.
Nothing else.

Verify this rather than trusting an empty diff. Running the generator and
seeing no change is consistent with "wrote the identical bytes back". Append a
unique marker to one file in each tree, prove the marker is absent from the
rest of the tree first, then run `python3 build/generate_agents.py`: the marker
is erased in a generated tree and survives in a hand-maintained one. Measured
2026-08-01 at `7e8d3ac2f4`, the marker survived in `src/claude/`,
`.claude/agents/`, and `.github/agents/`.

So a behavioral change (for example a severity rubric on
silent-failure-hunter) made ONCE in the `.shared.md` body reaches two trees.
The remaining three need the same edit applied by hand, in the same change.

## The two verifications, and what each does not prove

1. Similarity scoring: `build/scripts/detect_agent_drift.py`. Scores
   `src/claude` against `src/vs-code-agents`, and `.claude/agents` against
   `.github/agents`, over an 18-section allowlist. It never reads a template
   body. It is a weekly and manual audit
   (`.github/workflows/drift-detection.yml` has only `schedule` and
   `workflow_dispatch` triggers), not a PR merge gate. The #2707 fix cited
   "detect_agent_drift 100% on all silent-failure-hunter pairs" as evidence,
   but that 100.0 is vacuous: `silent-failure-hunter` matches zero allowlisted
   sections, so the score is hardcoded and cannot fall (verified 2026-08-01 at
   `7e8d3ac2f4`). Treat a 100.0 as evidence only after confirming the pair
   compares a nonzero number of sections.
2. Installed-copy parity: `scripts/validation/run_install_parity_ci.py` (backed
   by `build/scripts/validate_install_parity.py`). It checks **co-change in a
   diff, not content**: "reports the sibling files that should have changed
   together and did not" (`validate_install_parity.py:24`). It never compares
   two files' text. Measured 2026-08-01 at `7e8d3ac2f4`:

   ```bash
   uv run python build/scripts/validate_install_parity.py --files \
     templates/agents/merge-resolver.shared.md .claude/agents/merge-resolver.md \
     .github/agents/merge-resolver.agent.md src/claude/merge-resolver.md \
     src/copilot-cli/agents/merge-resolver.agent.md \
     src/vs-code-agents/merge-resolver.agent.md
   ```

   returns `install-parity: OK`, rc 0, on six files the detector scores at
   20.9% similar. The #2707 claim that parity "confirmed all six
   silent-failure-hunter install-parity members carry the identical rubric
   body" is not something parity can establish. Diff the files to make that
   claim.

## Why this matters

Neither check proves the five trees agree on content. The detector compares
text but only inside an 18-section allowlist, only between two specific pairs,
and only on a weekly schedule. Parity runs at PR time but only asks whether
sibling files moved together. A contradiction that lives outside the allowlist,
or in one of the four agents whose allowlist match is empty, is invisible to
both. Read both files before you edit either.

## Workflow when changing an agent

1. Edit `templates/agents/<name>.shared.md`.
2. Run `build/scripts/build_all.py --check` (must be clean after commit).
3. Confirm `detect_agent_drift.py` reports 100% on the changed pairs, AND that
   those pairs compare a nonzero number of sections (otherwise the 100.0 is
   hardcoded and proves nothing).
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
