---
type: metrics
id: workflow-local-run-latency-2026-11-10
title: Standalone latency of the workflow-local-run job body, full act path
epic: EPIC-5456
created: 2026-11-10
status: draft
---

# workflow-local-run latency, full act path

Release gate 3 of epic #5456. The `workflow-local-run` pre-push job was unmeasured
in `gate-latency-v0.7.0.md` because `act` and a container runtime were missing.
This file closes that exclusion for one workflow and states the limits.

## Why this is not a `gate_latency.py` hook capture

`gate_latency.py --change-class workflows` passes `.github/workflows/pytest.yml`
as the only push file. The job body (`git_hook_policy.py workflow-local`) keeps only
files changed against `origin/main`, and for `pytest.yml` alone it adds `--no-full`.
Measured on a throwaway branch, that path ended after actionlint in 0.28s, and an
unchanged `pytest.yml` skips in about 0.2s. Neither reaches `gh act`. The full act
path is reachable only by changing another workflow, which no change class does. So
the job body was timed directly, 30 attempts, on one representative workflow.

## What was timed

- Command: `uv run --frozen python scripts/validation/git_hook_policy.py workflow-local .github/workflows/yaml-lint.yml`
- Tree: `3abb246c3c`, a throwaway local commit that appends one comment line to
  `yaml-lint.yml` on top of main `21f93c46a9`. It was never pushed. The job body is
  identical to main's.
- Stages that ran in every counted attempt: actionlint, `gh act -n`, `gh act` (full).
- Runner: the `gh act` extension v0.2.89 (`nektos/gh-act`), Docker 29.9.3, image
  `catthehacker/ubuntu:full-latest` already present (warm image cache).
- Host: 48 CPUs, Linux 7.0.0-43-generic, Python 3.14.8, shared with other agent
  sessions. Load average before each attempt is in the table below.
- Standalone `act` v0.2.97 was also installed to `~/.local/bin/act` for this work.
  The hook does not call it: it calls `gh act`. Release archive
  `act_Linux_x86_64.tar.gz` sha256 `67b4976a56f33ea7870b798912e738ec44eef38e7578ae7b532f2def1c73a5ad`
  matches the `checksums.txt` line from the same release. That file came over the same
  channel, so it is not an independent signature. Installed binary sha256
  `c4d4728b7375fad11980456249edeb3a4ca48ba4e785cb8100ad14bd53e77056`.

## Result, n=20 counted attempts

| stat | seconds |
|---|---|
| min | 75.04 |
| p50 | 78.71 |
| p95 (nearest rank) | 84.86 |
| max | 90.70 |

p95 here is the 19th of 20 sorted values. n=20 is the sampler's own threshold for
calling p95 a tail estimate.

## Excluded attempts

8 of 30 attempts did not run the full act path and are not counted. Another act
process on this shared host held act's local reusable-workflow server port. The job
printed `port is already bound by another local act process` and still exited 0.
Six attempts returned in 1.4 to 2.0 seconds. Two ran partly, at 49.5 and 52.9
seconds. The gate reports success on those runs without running the whole
workflow. Excluded attempts: 10, 11, 12, 13, 21, 22, 23, 24.

## Counted attempts

| attempt | wall seconds | load 1m before |
|---|---|---|
| 1 | 80.15 | 20.95 |
| 2 | 76.28 | 29.24 |
| 3 | 78.41 | 16.39 |
| 4 | 75.92 | 19.23 |
| 5 | 75.46 | 16.51 |
| 6 | 81.33 | 9.46 |
| 7 | 82.67 | 18.42 |
| 8 | 77.28 | 20.96 |
| 9 | 82.50 | 19.73 |
| 14 | 90.70 | 22.47 |
| 15 | 80.13 | 27.92 |
| 16 | 79.01 | 18.86 |
| 17 | 79.26 | 19.16 |
| 18 | 76.70 | 16.99 |
| 19 | 82.50 | 11.87 |
| 20 | 84.86 | 23.38 |
| 25 | 76.08 | 25.47 |
| 26 | 77.98 | 17.59 |
| 27 | 75.18 | 21.04 |
| 28 | 75.04 | 16.41 |

## Limits

One workflow. `yaml-lint.yml` is a small, single-job file. A push that changes a
larger workflow runs a longer act stage, up to the job's 30 minute cap, and this file
says nothing about those. The job runs in a parallel group in the pre-push hook, so
this figure is not added to a hook total here. The sampler did not capture a hook run
with the full act path.
