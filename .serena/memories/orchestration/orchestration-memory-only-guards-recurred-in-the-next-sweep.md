# Guards kept only in memory recurred in the next sweep; guards in prompt text held

## What happened

The 2026-10-13 issue sweep retro produced several guards. Commit `7862817b8c` (PR #6460, 2026-10-13) stored them in `orchestration/orchestration-observations.md`.

Six days later, the 42-issue sweep (2026-10-17 to 2026-10-19) repeated two of them:

- Launch args. Line 66 says to assert `Array.isArray(args)` at the top of a Workflow script. The final round launched with `args.pending = '__FROM_FILE__'` and ran 0 agents. The relaunch added the guard.
- Process matching. Line 67 says an unbracketed `pkill -f` matched its own monitor. In wave 2, two agents' `pgrep -f` waits matched their own monitor shells.

One guard did not recur. The disk check before heavy steps (line 63) went into the sweep prompts. Wave-1 fix summaries cite "disk check (63G)" before each push, and no ENOSPC halt happened.

## Why memory did not stop it

Serena memory activates only when someone searches it. Nothing searches memory before a Workflow launch. On 2026-10-19, a search of `templates/`, `src/claude/skills/`, `src/claude/agents/`, and `.agents/governance/` for `Array.isArray` and `__FILL__` found 0 files. The memory line was the only copy.

The Workflow script is written fresh each sweep, so the repository has no script source to carry the guard.

## Relation to other memories

[orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief](orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief.md) records the same family: a bound that exists in one surface does not reach an agent that reads a different surface. That memory compares a template with a hand-written brief. This one compares memory with prompt text, and adds two recurrences as evidence.

`.claude/rules/universal.md` MUST NOT 7 states the general rule: an optional memory service is not the binding for a convention others must obey.

## Sources

- Retro: `.project-toolkit/retrospective/2026-10-19-issue-sweep-round2.md` (Five Whys, Mistake 4; Force Field Analysis).
- Prior retro: `.project-toolkit/retrospective/2026-10-13-issue-sweep-fanout.md` (Learnings 1, 3, 4).
- Wave-2 agent quirks in the session scratchpad `wave2.json` (`pgrep -f` self-match, 2 agents).
