# The wave cap lives in the orchestrator template, so a hand-written fan-out brief drops it

## What happened

During the v0.7.0 P2 sweep on 2026-10-11, about 12 agents ran `pre_pr.py` and `git push` at the same time. Issue #6292 records the result: the `/tmp` inode table filled and every tool call failed with ENOSPC.

The orchestrator template sets a different bound. `templates/agents/orchestrator.shared.md` line 347 says "Max concurrent delegations per wave: 4 by default". Line 348 bars repository-wide git operations, stash included, inside a concurrent wave.

## Why the brief missed it

The ship contract for the sweep was hand-written. It named no wave size and no stash ban at first. A search on 2026-10-12 of `templates/` for "concurrent delegations", "per wave", and "wave cap" matched only the orchestrator template and one orchestrator partial. No rule under `templates/rules/` or `.claude/rules/` repeats the bound, and no ship or push-pr skill file does either.

An agent reads the brief it is handed. The cap held for agents spawned through the orchestrator agent and did not reach agents spawned by a contract file.

## Evidence that parallelism itself was fine

Thirteen sweep PRs merged between 07:03Z and 09:40Z on 2026-10-12 under a throttled resume with the push lock. The loss came from an unbounded wave on one host, not from running agents in parallel.

## Sources

- `templates/agents/orchestrator.shared.md` lines 347 and 348.
- Issue #6292 (inode counts and the 12 concurrent runs).
- Retrospective `.project-toolkit/retrospective/2026-10-12-v070-p2-sweep-resource-and-contract.md` (PR #6334), Five Whys item 1.
- Related: `ci/ci-tmp-inode-cap-stops-every-tool-call-during-parallel-pushes`.
