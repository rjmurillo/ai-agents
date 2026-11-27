# Copilot CLI ran the tool after its hook timed out

**Atomicity**: 90%
**Category**: Hook contract, Copilot CLI
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E096, E097. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a Copilot CLI host hook timeout fail closed, and can its large registered timeouts be trusted?

## Conventional answer

ADR-068 Decision item 4 asserted an in-process 1500 ms budget that fails closed on exhaustion. The design also said the host enforces the requested hook timeout, so summed per-shim timeouts were safe.

## First-principles position

Copilot CLI 1.0.72-1 let the tool run after the hook timed out. The dispatcher did not implement the documented 1500 ms budget. The design cited the 2-second probe to justify much longer timeout settings. That probe shows failure behavior at its tested value, not how the host handles longer settings.

## Evidence with limits

- E096 (2026-07-20): a PreToolUse hook set to `timeoutSec` 2, and also 5, slept longer than the limit. The host log read "timed out; allowing the tool call to proceed" and the guarded tool ran.
- E096: ADR-068 had assumed an in-process 1500 ms budget that fails closed. That code never existed.
- E096: the consolidated host entry requested 95s PreToolUse and 35s PostToolUse, with 465s summed at the time (2026-07-22). That is a 232:1 extrapolation from the one 2s probe.
- E096: a hung early guard can let up to 15 later guards be skipped (2026-07-20).
- E097 (2026-07-22): The PreToolUse manifest had 13 shims with timeouts totaling 465 seconds. The design claim cited a 2-second probe.
- Limits: The probes used Copilot CLI 1.0.72-1 and tested 2 and 5 seconds. E097 reused E096 evidence. Neither record tested a timeout at 35 seconds or more.
- State on main at 1be533c496 (2026-11-26): still wrong for E096. `.serena/memories/root-cause-pretooluse-bash-hook-wedge.md:32` says a timeout becomes a hard denial. ADR-068:422 records the fail-open probe, and ADR-068:525 says no 1500 ms budget or SIGALRM exists.
- State on main at 1be533c496 (2026-11-26): fixed for E097. ADR-068:521-523 says the cited 2-second probe cannot establish how the host handles the requested 35 seconds.

## Decision

Treat a Copilot host hook timeout as fail-open. Never let a security guard depend on it. Do not claim the host grants or caps large timeouts until a probe at that value exists. State the extrapolation gap whenever a timeout design cites a probe at a smaller value.

The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/root-cause-pretooluse-bash-hook-wedge.md`
- `.serena/memories/copilot-hooks-observations.md`
- `.serena/memories/decision-hook-contract-surface-seam.md`
