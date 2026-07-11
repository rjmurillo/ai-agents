<!-- RETRO-STATE: skeleton-pending-fill -->
# Retrospective: 2026-07-10

> UNFILLED SKELETON written by invoke_auto_retrospective.py (Stop hook).
> The sections below are empty placeholders, not a completed retrospective.
> Run /retro fill 2026-07-10 (or the retrospective skill) to populate them, then
> delete this banner and the RETRO-STATE marker above.

## Session Context

### Work Items
- {'time': '2026-07-09T09:00:00Z', 'entry': 'Confirmed the content-controlled fixture body strips to the same SHA as the security agent body (be36604d...), matching report.json agent_prompt_sha; the parity test reads the fixture on disk, so the fixture is load-bearing and must stay tracked.'}
- {'time': '2026-07-09T09:10:00Z', 'entry': 'Diagnosed the commit blocker: the pre-commit SkillForge validator scans every staged /SKILL.md and had no exemption for eval fixtures, which are agent bodies reused verbatim and lack Triggers/Process sections by construction.'}
- {'time': '2026-07-09T09:20:00Z', 'entry': 'Added an evals/ exemption to the pre-commit STAGED_SKILL_FILES filter with rationale, matching the existing command-mirror exemption pattern.'}
- {'time': '2026-07-09T09:30:00Z', 'entry': 'Wrote tests/hooks/test_pre_commit_skill_validation_filter.py that extracts the exact filter block from the hook and runs it under bash, proving real skills are selected while evals/ fixtures and command-mirror skills are excluded. 6 tests pass.'}
- {'time': '2026-07-09T09:40:00Z', 'entry': 'Documented the exemption and the fixture reconstructability in ADR-075; verified 0 em/en dashes; ran the 49-test suite green and ruff on all changed files.'}


## What Went Well

- _UNFILLED. Run the retrospective agent to populate this section._

## What Could Improve

- _UNFILLED. Run the retrospective agent to populate this section._

## Key Learnings

- _UNFILLED. Run the retrospective agent to populate this section._

## Failure Patterns

- _UNFILLED. Run the retrospective agent to populate this section.
  Check .agents/governance/FAILURE-MODES.md._
