# ADR Debate Log: ADR-104 amendment for testmon-selected pre-push tests

Panel: full six seats, because the change moves executable enforcement: pre-push now runs tests instead of collecting them.

## Summary

- **Rounds**: 2
- **Outcome**: Consensus (round 2: critic Disagree-and-Commit with its last gap since fixed; security Pass; devops Pass)
- **Final Status**: ADR-104 stays proposed (amended).

## Decisions under review

The owner decided on 2026-10-09:

- Pre-push runs pytest-testmon-selected tests, best effort, so failures surface before CI. Collection only, chosen the day before, never ran an assertion.
- The xdist distribution mode switches from loadfile to worksteal.
- A main-push-only CI job seeds the testmon database. The hook downloads it when no local database exists, and every partition runs with the worst exit code returned.

## Round 1 Summary

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Disagree-and-Commit | Cold run breaches rules 2 and 5 without saying so; container clamp consequence unstated |
| critic | Disagree-and-Commit | Self-contradiction on the first run; live docs still described collection only and loadfile |
| independent-thinker | Disagree-and-Commit | Subprocess blind spot understated; branch divergence and seed cost unstated |
| security | Disagree-and-Commit | Seed trust rested on event and branch only; temp-file and download hardening |
| analyst | Disagree-and-Commit | Several figures had no recorded source; 7-day artifact expiry unstated |
| high-level-advisor | Accept (conditional) | Chesterton sentence and a real revert path |

### Key Issues Addressed

- The seed job inherited the hook's 780 s budget and would have uploaded a partial database.
- A signal-killed pytest returned a negative code, and `max(0, -9)` let the push pass.
- The seed trust check did not require a successful run, the right workflow, or a commit on main.
- The ADR contradicted itself on the first run and did not state the measured 575 s cold breach.

### Major Changes Made

- The seed job has its own 3300 s budget and uploads only when every partition passed.
- Any negative child exit code is a failure.
- A seed is trusted only from a successful `pytest.yml` push run on main whose head is an ancestor of `origin/main`. The download streams under a 256 MB cap into a fresh temp directory, and the database is staged with `O_CREAT|O_EXCL|O_NOFOLLOW`.
- ADR-104 leads with the seed fetch, states the 575 s cold run as an accepted breach of rules 2 and 5, names `--testmon-forceselect`, lists every consequence, adds re-evaluation triggers, and gives the revert path.
- Measurements live in `.project-toolkit/analysis/testmon-prepush-measurements.md`, including the replay-trial figures.
- Live docs no longer describe collection-only pre-push or loadfile.

## Round 2 Summary

### Agent Positions

| Agent | Position | Note |
|-------|----------|------|
| critic (verifier for all seats) | Disagree-and-Commit | Nine of ten items resolved; replay-trial figures needed a source, now recorded |
| security | Pass | Two Low findings that need local write access to the clone |
| devops | Pass | Seed budget, upload gate, and signal handling verified with tests |

### Dissent

The container clamp of 150 s cannot finish a cold run when no seed exists, for example on a branch that changes `uv.lock`. The owner accepted this when choosing the seed option. The ADR states it.

The seed job costs about 30 runner-minutes per main push. That figure is inferred until the first main run measures it.

## Strategic Review

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | PASS: the ADR says collection only never ran an assertion, so failures cost CI turns |
| Path Dependence | PASS: the revert path is listed, about 20 files in one pull request |
| Core vs Context | PASS: testmon is bought; the seed fetcher selects nothing |
| Second-System Effect | PASS with a flag: most added lines are tests; the deleted collection-contract tests follow from the decision |
