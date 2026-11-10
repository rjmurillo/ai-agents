# ADR Debate Log: ADR-109 hook-discovery guard follow-up (D32)

## Summary

- **Rounds**: 1 of 10
- **Prior debate logs**: `.project-toolkit/critique/ADR-109-debate-log.md` (original consensus) and `.project-toolkit/critique/ADR-068-071-084-085-109-req048-task006-debate-log.md` (the D28 amendment, closed)
- **Outcome**: Consensus in round 1. The architect voted Accept and the critic voted Disagree-and-Commit.
- **Final Status**: accepted (unchanged; this edit appends a dated follow-up)
- **Subject**: a 2026-11-09 follow-up paragraph after the 2026-11-04 D28 amendment in ADR-109 section 2.
- **Trigger**: owner decision D32 (2026-11-09) added the no-environment CI leg `smoke-claude-hooks`. That made a D28 sentence false: "The only guard is the opt-in `tests/e2e/test_cli_stop_nudge_e2e.py`".
- **Panel**: reduced (architect, critic), per AGENTS.md. The ADR text is prose that records a CI change. No gate reads it.

## Round 1

| Agent | Vote | Findings |
|-------|------|----------|
| architect | Accept | Append-only holds. The ADR-114 decision 1 citation, the path filter, the gate wiring, and the test claims are verified. P2: name the superseded sentence; say "trusted" pull requests, since the job also needs `authorize.outputs.trusted`; say where 2.1.319 ran; fix the stale `claude` marker text in `pyproject.toml`; the result message and the workflow's "What the smokes prove" list omit the leg. |
| critic | Disagree-and-Commit | P0: none. A skip or a missing Hooks row fails the job. P1: `--expected-count` is a minimum and the substring matches the module, so a deleted or renamed negative control would still pass the gate. Fix: name both tests with `--require-pass`, as the Codex leg does. P2: the two ADR wording points above; the leg has not run on a real runner; the positive test reads `src/claude`, not an installed copy. |

## Changes made after round 1

- The assert step names both CLI tests with `--require-pass`. Verified 2026-11-09: the gate passes on a live junit report from Claude Code 2.1.316. It fails with "no smoke test matched required-pass" when the shipped-hooks test is missing.
- The ADR-109 follow-up quotes the superseded D28 sentence. It now says "trusted pull request", says 2.1.316 is the pinned CI version and 2.1.319 ran locally, and names the `--require-pass` pins.
- The `pyproject.toml` `claude` marker text now says most claude tests need a credential, and names the no-credential hook discovery tests.

## Dissent and residuals

- The critic notes that the leg has not run on a real runner. Empty-HOME behavior there is unproven until this pull request's own CI runs the job.
- The positive test reads `src/claude`, not an installed copy. The ADR states the leg proves registration, not execution, on Ubuntu only.
- The result message and the "What the smokes prove" header list were left unchanged. They are cosmetic.

## Post-consensus edit (frontmatter only, not panel-reviewed)

- The ADR-109 frontmatter `date` moves from 2026-11-04 to 2026-11-09, matching the D32 follow-up. A PR #7166 review thread raised it, and the architecture README index was regenerated. The body text is unchanged.
