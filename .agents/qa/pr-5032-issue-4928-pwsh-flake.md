---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15001-fix-4928-pwsh-flake.json
qaCommit: e94ffd1c20d5ca080df9b04d3d0a062c0fe48903
---

# QA Report: PowerShell runtime contract flake fix (#4928)

## Scope

Verified the batched pwsh invocation eliminates subprocess timeout flakes.

## Evidence

| Check | Result |
|---|---|
| Single run | 1 passed in 1.66s |
| 5x xdist runs | All pass consistently (~2s each) |
| Full test file | 35 passed in 1.96s |
| No regressions | All assertions preserved |

## Root Cause

N separate pwsh subprocess spawns (one per hook entry x 2 scenarios)
contended for process slots under xdist parallelism. With 66+ existing pwsh
processes, individual spawns exceeded the 30-second timeout.

## Fix Verification

Batching all Test-Path checks into a single pwsh -Command per scenario
reduces spawns from Nx2 to 2 total. Runtime dropped from 30s+ to ~2s.

## VERDICT: PASS
