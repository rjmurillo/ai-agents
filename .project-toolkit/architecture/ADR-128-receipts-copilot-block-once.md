---
id: ADR-128
status: proposed
date: 2026-11-25
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-02-25
---

# ADR-128: The Receipts Stop Hook Blocks Once on Copilot CLI and Advises on Claude Code

## Status

Proposed. The Copilot hook stays unregistered until the Decision 7 gate passes and the owner accepts ADR-084 rule 2b. The debate record is `.project-toolkit/critique/ADR-128-debate-log.md`.

## Context

REQ-050 adds `receipts`. It checks claims in an agent's final reply against tool results. Each claim gets a stamp: `proven`, `contradicted`, or `no receipt`. The owner chose on 2026-11-25 to ship it to both Claude Code and Copilot CLI, and to block on Copilot. REQ-050 records those decisions.

The two harnesses give a Stop hook different output channels.

- Claude Code accepts a `systemMessage`. The user sees it, and the turn ends. The shipped reflect nudge (`src/claude/hooks/Stop/invoke_reflect_nudge.py`) uses that channel.
- Copilot CLI documents one `agentStop` output: `{"decision": "block", "reason": ...}`. The reason enters model context, and the agent takes another turn. An advisory display field is undocumented and untested.

Four forces make this an architecture decision.

1. **The Copilot plugin surface holds no hook today.** `src/copilot-cli/hooks/hooks.json` has an empty `hooks` object (2026-11-25). The receipts hook would be the first.
2. **ADR-084 kept the only vendored Stop hook out of Copilot.** Rule 2a says the reflect nudge "MUST stay out of the Copilot tree". Its stated reason is that Copilot documents neither an advisory field nor `transcript_path`. Rule 2a also says "Any other advisory hook needs its own amendment", and it calls a hook that fails any of its conditions enforcement.
3. **Copilot's loop guard is unreliable.** Local logs held 3,897 `agentStop` runs that returned a block (2026-11-25). The next stop in the same log file had `stop_hook_active` true 3,510 times, false 378 times, and absent once. Eight blocks had no next stop. The flag was false after 9.7% of blocks overall, and after 279 of 1,586 blocks on 1.0.79 builds. A hook that trusts the flag can block the same reply again.
4. **Contradicted precision is unmeasured.** The spike (draft PR #7631) produced zero contradicted stamps in 678 runs (2026-11-25). The spike report calls that stamp CAP. A false contradiction on Copilot costs the user one wasted model turn and puts a false statement in model context.

Measured facts that bound the design. All come from a full count of 11,160 `~/.copilot/session-state/*/events.jsonl` files on the owner's machine on 2026-11-25.

- The files held 19,518 logged `agentStop` runs on Copilot 1.0.37 to 1.0.105. The installed version was 1.0.116.
- `transcriptPath` was set in 10,977 runs and empty in 8,541. Builds before 1.0.79 had 5,711 set and 5,424 empty. The 1.0.79 builds had 4,830 set and 3,117 empty. All 436 runs on 1.0.87 and later carried it. No run was logged on 1.0.80 to 1.0.86.
- `stop_hook_active` was present in 17,632 of the 19,518 inputs.
- Logged outputs were empty (13,922), `decision` plus `reason` (3,897), or `reason` alone (1,699). Every `decision` value was `block`. No output used another field.
- No block was logged on 1.0.87 or later. Block behavior on those builds is unmeasured.

The "next stop" pairing in force 3 is an inference. The logs do not say that the next stop answers the same reply. An earlier draft of this record cited 25 false of 49 blocks. That figure came from a scan capped at the 3,000 most recently modified files, and the full count replaces it.

No live probe ran on 1.0.116. The account was out of quota, so only `sessionEnd` fired.

## Decision

1. **Claude Code stays advisory.** The Claude receipts hook prints one `systemMessage` and exits 0 on every path. It never emits a `decision` field. Each stamp repeats at most 80 characters of claim text from the reply. Each receipt names the tool under the Decision 6 pattern. Its dispatch group sets `copilotExclude: true`, so the generator never copies it into the Copilot tree.
2. **Copilot CLI blocks on a contradicted claim only.** The Copilot hook prints `{"decision": "block", "reason": ...}` when a tool result contradicts a claim in the final reply. `proven` and `no receipt` stamps print nothing.
3. **One block per claim per session, enforced by the hook's own marker.** Before blocking, the hook records a SHA-256 digest of the session id, the claim kind, and the normalized claim values. A claim whose digest is already recorded never blocks again. The bound is per claim: each distinct contradicted claim can block once, and no cap on blocks per session is set. `stop_hook_active` true also passes, but it is not the guard.
4. **The marker holds digests only.** It holds no reply text, tool output, path, or claim value. It lives in per-user storage outside every repository the hook can detect, under the same rule as ADR-084 rule 2a condition b. The directory mode is 0700 and the file mode is 0600. The hook opens the file with `O_NOFOLLOW`, appends atomically, and stops writing at a fixed size cap.
5. **If the marker cannot be read or written, the hook does not block.** It cannot promise one block per claim, so it prints nothing and logs one stderr line. A marker at its size cap counts as unwritable.
6. **The block reason is a fixed template.** It carries the claim kind, the call index, and the tool name. The tool name must match `^[A-Za-z0-9_.-]{1,48}$`; any other name prints as `tool`. The reason never copies text from the reply or from tool output, because it enters model context.
7. **Registration waits for a measured gate.** The Copilot hook is not registered until at least 30 `contradicted` stamps are judged by hand and none is false. The stamps come from an offline replay of the owner's own Copilot `events.jsonl` logs, so no hook registers before the gate passes. The pass rule and the sample size are fixed in a committed file before any draw. Zero false in 30 gives an upper 95% Wilson bound of 0.114 on the false rate. If the gate is unmet on 2027-02-25, the hook stays unregistered and this record is reviewed again.
8. **A kind with fewer than 10 judged stamps never blocks.** On Copilot that kind stamps `no receipt` only, and the skill page lists it as unmeasured.
9. **The hook needs `transcriptPath`.** An empty or unreadable path prints nothing and exits 0. That covers 8,541 of the 19,518 logged runs, all on builds 1.0.79 and earlier.
10. **The Copilot hook registers alone.** It does not share an observe dispatcher with another Stop hook, because two decision objects concatenate into invalid JSON.
11. **One environment variable turns both hooks off.** The hook reads `AI_AGENTS_RECEIPTS` before it opens any file. The off values are `0` and `off`.
12. **ADR-084 gains rule 2b in the same change.** Rule 2b covers both receipts registrations and names the rule 2a conditions each one departs from. The reflect nudge keeps its Copilot exclusion under rule 2a.

## Prior Art Investigation

### What Currently Exists

- Claude Code: one vendored Stop hook, the reflect nudge, in an advisory dispatch group. Its shim carries `copilotExclude: true` with decision `ADR-084`.
- Copilot CLI: no vendored hook. The hooks file is empty.
- The shared Stop timeout on Claude Code is 15 s (`src/claude/hooks/hooks.json`).
- Two tests pin the current state in `tests/hooks/test_plugin_stop_registration.py`. `test_copilot_plugin_has_no_entry_for_the_hook` asserts an empty Copilot Stop list. `test_the_advisory_set_is_exactly_the_reflect_nudge_group` asserts one advisory group.

### Historical Rationale

ADR-084 set six rules for a hook on the vendored surface. Rule 1 requires value in a consumer's own repository. Rule 2 keeps internal protocol enforcement out. Rule 2a lets one advisory nudge ship, and keeps it out of Copilot because Copilot documented no advisory output and no `transcript_path`. ADR-097 retired the tool-use hooks. PR #3372 deleted a hook that blocked a turn until a retro existed.

### Why Change Now

- The logs show `transcriptPath` on every run from 1.0.87 on (436 runs). The second reason for the Copilot exclusion no longer holds for those builds.
- The first reason still holds: Copilot has no documented advisory channel. Receipts does not need one, because a block decision is the documented channel and the owner chose it.
- Receipts is not protocol enforcement. It checks the agent's statements about the consumer's own work in the consumer's own session. That is consumer-repo value under ADR-084 rule 1.
- The deleted hook in PR #3372 blocked until the user produced an artifact. Receipts blocks once, on a statement a tool result contradicts, and demands no artifact.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| A. Claude Code only | No turn is ever blocked. No new Copilot contract to maintain. | Copilot sessions get no check. The owner chose to ship to Copilot. | It drops half the stated scope. |
| B. Advisory output on Copilot | Matches the Claude behavior. A false stamp costs nothing. | The docs are silent on an advisory field, and none was tested. | Nothing shows the user would ever see the output. |
| C. Block on Copilot, guarded by `stop_hook_active` | No state file. Fewer lines of code. | The flag was false on 378 of 3,889 next stops after a block. On 1.0.79 builds it was false on 279 of 1,586. | The guard misses about 1 block in 10, and about 1 in 6 on 1.0.79 builds. |
| D. Block on both harnesses | One behavior to explain. The agent corrects itself everywhere. | A false contradiction would cost a turn on Claude Code too. | On Claude Code the advisory message already reaches the user at no turn cost. The owner scoped the block to Copilot. |
| E. Block once per claim with a digest marker, gated on measurement (chosen) | The loop bound does not depend on the harness flag. The gate measures the one stamp that costs a turn. | One state file. The gate may never be met. | Chosen. |

### Trade-offs

- The marker trades a stateless hook for a loop bound the harness cannot give.
- The gate trades shipping speed for a measured false-block rate.
- The gate may be unreachable. Zero contradictions in 678 spike runs gives an upper 95% Wilson bound of 0.0056 per run. At that rate, 30 contradictions need at least 5,300 runs. The logs hold 19,518 `agentStop` runs (2026-11-25). Only 10,977 carry a `transcriptPath`, and Decision 9 means the live hook is silent on the other 8,541. The count of contradicted stamps in the pool is unmeasured, and it may be fewer than 30. Decision 7 sets the date that ends the wait.
- Blocking only on `contradicted` means an unsupported claim (`no receipt`) passes silently on Copilot. The `receipts` skill is the only way to see it there.

## Consequences

### Positive

- A Copilot agent that states a result its own tool output contradicts corrects the reply in the same session.
- A wrong contradiction costs at most one extra turn per claim per session, even when `stop_hook_active` misreports.
- Model context gains no untrusted text from the hook. The reason is a fixed template.
- The decision to block is tied to a measured count, not to a point estimate from the spike.

### Negative

- The Copilot hook writes a state file. Receipts on Claude Code writes nothing.
- A false contradiction still costs one turn and tells the model a true claim is false.
- Unsupported claims are invisible on Copilot unless the user runs the skill.
- The Copilot contract rests on logs from 1.0.37 to 1.0.105. Version 1.0.116 is unprobed, and no block was logged on 1.0.87 or later. A changed payload yields no stamps, which fails safe but silently.
- Builds 1.0.79 and earlier often send an empty `transcriptPath`. Those runs get no receipts check.
- The gate sample comes from one operator's sessions. Consumers' false-block rate is unmeasured.
- The repository gains a second harness-specific Stop behavior to test and explain.
- ADR-084 gains a second named exception, and its first blocking hook since PR #3372.

### Neutral

- The Copilot plugin surface stops being empty once the gate passes. ADR-084 rule 5 then applies: the hook carries a `Customer value:` line.
- The reflect nudge is unchanged on both harnesses.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|-----------------|-----------------|------|
| `src/copilot-cli/hooks/hooks.json` | Generated registration | Gains one `agentStop` entry after the gate passes | Medium |
| Hook generator and dispatch groups | Source of both registrations | A Claude advisory shim with `copilotExclude: true`, and a Copilot-only entry | Medium |
| `tests/hooks/test_plugin_stop_registration.py` | Pins one advisory group and an empty Copilot Stop list | The PR that adds each registration updates the test it trips, in the same change | Medium |
| ADR-084 rule 5 tests in `tests/hooks/test_dispatch_groups_parity.py` | Customer-value presence check | Must cover both receipts registrations | Low |
| `agent-harness-reference` sidecar | Contract record | Records the probed `agentStop` payload and tool versions | Low |
| ADR-071 runtime contracts | Verification record | A runtime-contract test with a negative control for the Copilot hook | Medium |
| Reflect nudge | Shares the 15 s Stop budget on Claude Code | None. Receipts stops at a 5 s internal deadline on both harnesses | Low |

## Implementation Notes

- Build order follows REQ-050: engine and eval, remaining kinds, the Claude hook, the Copilot hook, then the skill and docs. The Copilot hook slice waits on this ADR and its gate. The Claude hook slice waits on owner acceptance of ADR-084 rule 2b.
- Route the Copilot slice through the `ai-agents-portability-campaign` skill.
- A test replays a second stop with `stop_hook_active` false and the same claim, and shows no block.
- A live probe on the installed Copilot version runs before registration. It records one block and the next stop's payload.
- Judged real-session sets stay outside the repository. Only aggregate counts are published.
- Rollback: remove the Copilot registration. The marker file is inert without the hook.

## Related Decisions

- ADR-084: Vendored-Hook ROI Bar. This ADR applies rules 1 and 5. Rule 2b, proposed in the same change, covers both receipts registrations.
- ADR-071: Plugin Hook Runtime-Contract Verification.
- ADR-085: Cross-Harness Permission-Surface Asymmetry and Hook Survivor Disposition.
- ADR-097: Zero Tool-Use Hooks. It covers tool-use events. ADR-084 rule 6 sets the per-call bar and treats session-boundary events separately.

## References

- `.project-toolkit/specs/requirements/REQ-050-receipts-stop-annotation.md`
- `.project-toolkit/critique/ADR-128-claims-ledger.md`
- Issue #7633 (tracking) and draft PR #7631 (spike record).
- `src/claude/hooks/Stop/invoke_reflect_nudge.py`
