# Skill: Enumerate argv forms before a subprocess guard goes to review (85%)

**Atomicity Score**: 85%
**Source**: Retrospective `.project-toolkit/retrospective/2026-10-11-goal-followup-loop.md`
**Date**: 2026-10-11
**Tag**: harmful (the failure this prevents)
**Impact**: 6/10 (two review rounds and 10 findings on one test helper)

## Statement

Enumerate launcher, shell, and option-value argv forms before review; #6272 drew six threads.

## Evidence

PR #6272 added `tests/e2e/local_smoke_guard.py`, which finds the program a subprocess call starts. The first version read only the first word. One independent review found four gaps, and the PR review then found six more:

- option values (`env -u FOO copilot`, `sudo -u root copilot`)
- shell wrappers (`sh -c`, `cmd /c`, `pwsh -Command`)
- npm version suffixes (`@github/copilot@1.0.91`)
- path objects with spaces
- `command -v` lookups
- launches during collection

Listing these forms first, each with a test, would have cleared them in one round.
