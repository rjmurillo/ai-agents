---
type: requirement
id: REQ-050
title: Receipts, a Stop check of claims in the final reply against tool results
status: draft
priority: P2
category: functional
created: 2026-11-25
related:
  - REQ-048
  - ADR-084
  - ADR-128
  - "#5817"
  - "#7631"
  - "#7633"
---

# REQ-050: Receipts, a Stop check of claims in the final reply against tool results

This file is durable. It lands in git history. It holds counts and paths only, no transcript text.

## Step 0 First Principles

Answers come from the owner's decisions D1 to D12 on 2026-11-25, plus the spike measurements in draft PR #7631.

Gate result on 2026-11-25: `tests/commands/step0_parser.py` returns H3 on Q1. Q3 passes the specificity test and Q5 passes the speculative test.
H3 fires because the parser counts a requester only in the form `<Name> on the <Team> team`. The gate policy accepts one named requester on the evidence path (issue #6990).
REQ-048 and REQ-049 return H3 for the same single-owner answer. Q1 is left as written. The owner decides whether it passes.

### Q1

Richard Murillo (repository owner) requested it. On 2026-11-23 he asked for a spike on whether a receipt checker earns a Phase 1 port. On 2026-11-25 he accepted the verdict and asked for our own design: "take the idea, customize it. They built a chair. I want a better chair." Single requester, so the evidence path applies: specific Q3 plus evidenced Q5. The owner decides whether Q1 passes.

### Q2

Today the owner reads each final reply and checks its claims by hand. Step by step:

1. The agent ends a turn with claims such as "36 passed", "pushed", or a commit SHA.
2. The owner scrolls back through tool output to find the call that proves each claim.
3. When no call proves it, the owner asks the agent, or reruns the command.

The `evidence-provenance` skill and the voice rule's "Clear the gate or drop the claim" section tell the agent not to overclaim. Nothing checks the reply after it is written.

Reframing: capability invention, check: on a fresh blind sample, at least 180 of 200 proven stamps are correct and at most 21 of 100 sampled replies are misses (AC-24, AC-25).

### Q3

Richard Murillo, reading final replies in Claude Code and Copilot CLI sessions on `rjmurillo/ai-agents`. He is blocked on trusting completion claims without rereading tool output. The hand check in `.project-toolkit/prototypes/nocap-spike/REPORT.md` (PR #7631) found a reply that said "19 pass" when the cited `gh pr checks` output showed 18.

### Q4

The smallest deliverable is the Claude Code Stop hook with the tests, ci, and sha kinds. It prints proven and contradicted stamps as one advisory message. Estimate: 40 hours for a human team, about 4 hours AI-assisted. The owner chose the full kind set, the Copilot path, and the `receipts` skill in one release. That totals 120 hours for a human team, about 3 days AI-assisted.

### Q5

Spike round 4 on 2026-11-25 (`REPORT.md` in draft PR #7631): of 60 unstamped completion replies, 12 carried an unsupported claim, a miss rate of 0.20. In round 1, 56 of 146 stamps were NO RECEIPT, a rate of 0.384. Each is a claim the owner checks by hand today. Round 1 also found 12 of 40 proven stamps citing a call that did not prove the claim.

### Q6

At 10x more sessions, the per-reply cost is fixed: the spike measured p95 0.40 s per transcript, with no network or model call. Longer transcripts are the risk. The three largest in the spike pool, up to 36 MB, took up to 3.5 s. A byte and time budget keeps the hook inside the shared 15 s Stop timeout. A 10x larger claim vocabulary makes regex backtracking the liability, so every pattern is bounded and a ReDoS test covers each one.

## Prior Art / Constraints

### Direct prior art from memory

- Draft PR #7631, the spike: an upstream Apache-2.0 checker measured on this repo's sessions. Relevance: it sets the claim kinds, the verdict model, and the eval method. Decision: adapt the idea only. No upstream code is copied (owner decision D3).
- REQ-048 and issue #5817 (`src/claude/hooks/Stop/invoke_reflect_nudge.py`): an advisory, fail-open Stop hook. It reads `transcript_path`, prints a `systemMessage`, and exits 0 on every path. Relevance: the same event, output channel, and failure policy on Claude Code. Decision: honor. Receipts copies its registration shape, `--advisory` flag, and off switch.
- `dispatch_groups.json` group `plugin-stop-1-reflect_nudge`: Copilot-excluded under ADR-084 rule 2a, because Copilot had no documented advisory Stop output or `transcript_path`. Relevance: receipts ships to Copilot, so it does not take that exclusion. ADR-084 rule 2b (proposed 2026-11-25) covers both receipts registrations. Decision: adapt. The probe below covers `transcript_path`, and the Copilot output is a block decision (owner decision D6).
- `.serena/memories/decision-claude-hook-group-dispatch.md`: Copilot Stop hooks cannot share a plain observe dispatcher, because two decision objects concatenate into invalid JSON. Decision: honor. The Copilot receipts hook is its own direct registration.
- `src/claude/lib/failure_classifier/transcript.py`: a shipped mapper from Claude Code records to tool events. Decision: adapt. Receipts reuses its record-shape knowledge and the reflect nudge's bounded read.
- chestertons-fence: not run as a separate skill. The change only adds files and one registration per harness. Recommendation: PRESERVE every existing Stop hook unchanged.

### Copilot CLI probe (2026-11-25)

- Tool: GitHub Copilot CLI 1.0.116 installed. A live probe in a scratch repo fired `sessionEnd` only, because the account returned "exceeded your monthly quota" before any model turn.
- The `sessionEnd` payload keys were `cwd`, `reason`, `sessionId`, and `timestamp`.
- Logged `hook.start` inputs in all 11,160 `~/.copilot/session-state/*/events.jsonl` files held 19,518 `agentStop` runs, from Copilot 1.0.37 to 1.0.105 (full count, 2026-11-25). Keys in every run: `cwd`, `sessionId`, `stopReason`, `timestamp`, and `transcriptPath`. `stop_hook_active` was present in 17,632 runs.
- `transcriptPath` pointed at that session's own `events.jsonl` in 10,977 runs and was empty in 8,541. Builds before 1.0.79 had 5,711 set and 5,424 empty. The 1.0.79 builds had 4,830 set and 3,117 empty. On 1.0.87 and later, all 436 runs carried it.
- `events.jsonl` records the receipts inputs: `assistant.message` (content, `toolRequests`), `tool.execution_start` (`toolName`, `arguments`), and `tool.execution_complete` (`success`, `shellExecution.exitCode`, `result.content`).
- Logged `agentStop` outputs were empty (13,922), `decision` plus `reason` (3,897, every `decision` value `block`), or `reason` alone (1,699). No logged output used any other field. No block was logged on 1.0.87 or later. The official sidecar documents only `decision` and `reason`. An advisory display field is DOCS SILENT and untested. An earlier draft cited 2,115 runs and 49 blocks; that scan was capped at the 3,000 most recently modified files.

### Connected context from prior-art search

- Connected entity: `reflect-nudge`, Stop hook. Adjudication: in-scope. Note: it shares the 15 s Stop budget, and receipts must leave it headroom.
- Connected entity: `evidence-provenance`, skill. Adjudication: out-of-scope. Note: it guides how the agent writes claims. Receipts checks them afterwards.
- Connected entity: `failure-classifier`, lib. Adjudication: blast-radius. Note: sharing its transcript mapper couples the two hooks.
- Connected entity: `agent-harness-reference`, skill. Adjudication: in-scope. Note: its sidecar gains the probed `agentStop` payload row.
- Search depth: medium, matched to Tier 3.

### Coverage notes

- Topic `receipts`: 3 variants (`receipt`, `claim check|verif|overclaim`, `stop hook|systemMessage|advisory stop`) over `.serena/memories`. Results: 0, 1, and 5 files. The one claim hit is about a CI gate, not this feature. Confidence: high.
- Topic `copilot-agentstop-payload`: the official sidecar, the probe sidecar, and a live probe. Result: payload keys measured from logged runs, display field untested. Confidence: medium.
- Hindsight MCP was unavailable (connection closed), so only repository memory files were searched.
- Blast-radius count: 1, under the human-mode threshold of 2. No halt.

## Problem statement

Final replies carry claims that a tool result should prove. The owner checks them by hand. The spike measured 12 of 60 completion replies carrying an unsupported claim, and 12 of 40 proven stamps citing the wrong call.

## User stories

1. As the owner in Claude Code, when a turn ends, I see one short line per checked claim. It says whether a tool result proves it or contradicts it, and which call is the receipt.
2. As the owner in Copilot CLI, when a reply states a claim a tool result contradicts, the agent takes one more turn and corrects the reply.
3. As the owner, when a reply has no checkable claim, I see nothing and the turn ends normally.
4. As the owner, I can run `/receipts` to see every stamp for the last reply, including claims with no receipt.
5. As the owner, I can turn the hook off with one environment variable.

## Design goals: the better chair

The spike found where the upstream design fails on this repo's sessions. Each goal below is a requirement, not a tuning knob.

1. **Receipts come from output, never from the agent's words.** A SHA, count, or URL counts as evidence only when it appears in tool output. The agent's own command text, PR body, or arguments never prove a claim. The spike traced 9 of 12 wrong citations to this.
2. **A stamp cites the call that proves the claim kind.** A merge claim cites merge output, not a `git fetch`. A count cites the run that printed the count.
3. **CI checks are their own kind.** "115 checks passed" is checked against check-run output, not test output. This caused 14 spike stamps and the one missed contradiction.
4. **Freshness counts only real edits to the tested tree.** Reads, `git merge-tree`, quoted `>` in strings, temp-file redirects, and writes outside the repo are not edits.
5. **Repo scripts are first-class evidence.** JSON envelopes from the `github` skill scripts (`get_pr_checks.py`, `merge_pr.py`, `get_pull_requests.py`) parse like `gh` output.
6. **One verdict engine, two transcript readers.** Claude Code JSONL and Copilot `events.jsonl` map to the same evidence model.
7. **Bounded by construction.** Every pattern is linear-time on long input, and the hook stops at a deadline.

## Ontology

- **Reply**: the main-thread assistant text after the last tool call of a turn. A turn opens at each main-thread user message.
- **Claim**: a checkable statement in a reply. Kinds: `tests`, `ci`, `build`, `sha`, `committed`, `pushed`, `merged`, `pr_opened`, `deployed`, `url`, `file`, `number`.
- **Evidence**: one record per completed tool call: tool name, arguments, output text, exit status, success flag, and call index.
- **Ledger**: the session's evidence, carried across turns.
- **Tamper**: a change that makes a failing suite pass without fixing it: a skip marker added, a failing test deleted, or a deselect of the failing test.
- **Stamp**: the verdict on one claim. Values: `proven`, `contradicted`, and `no receipt`. These labels are this repository's own.
- **Receipt**: the call a stamp cites, by index, tool name, and a short reason.
- Decision rule: freshness is by call order, not timestamp.
- Bounded contexts: claim finding, evidence building, judging, and the harness readers and outputs.

## Data model

- `Turn(index, calls, reply)`: identity is the turn index in one transcript. Invariant: `reply` is non-empty for a judged turn.
- `ToolCall(call_id, name, args, output, exit_code, success)`: identity is the harness tool-call id. Invariant: a call with no completion record is not evidence.
- `Claim(kind, text, span, values)`: identity is `(turn, span)`. `values` holds the parsed counts, SHAs, URLs, paths, or refs.
- `Stamp(claim, verdict, receipt, why)`: `verdict` is one of the three labels. Invariant: `proven` and `contradicted` always carry a receipt.
- Lifecycle: built in memory per Stop event, emitted, and discarded. On Claude Code nothing persists.
- `BlockMarker(session_id, claim_digest)`: Copilot only. `claim_digest` is the SHA-256 of the session id, claim kind, and normalized claim values. The marker file holds digests only, one per line, and lives outside the repository.

## Integrations

- **Claude Code Stop event**: payload `session_id`, `transcript_path`, and `cwd`. Output: one `systemMessage`. Failure: a missing or unreadable path prints nothing and exits 0.
- **Copilot CLI agentStop event**: payload `sessionId`, `transcriptPath`, `stop_hook_active`, and `cwd`. Output: `{"decision": "block", "reason": ...}` only when a claim is contradicted and its digest is not in the session's block marker. `stop_hook_active` true also passes, but it is not the loop guard: logs show it false on 378 of 3,889 next stops after a block, and on 279 of 1,586 blocks on 1.0.79 builds (full count, 2026-11-25). Failure: an empty path, a missing file, or a parse error prints nothing and exits 0.
- **Transcript files**: read once, bounded by bytes and lines. Malformed lines are skipped.
- **Hook dispatcher** (`invoke_dispatch_claude.py`): runs the Claude shim in an advisory Stop group. The Copilot hook is a direct registration.
- Idempotent: the same transcript gives the same stamps. The Copilot block is not idempotent by design: a claim blocks once per session.

## Failure modes

- Budget overrun on a large transcript: stop at the byte or time cap, emit nothing, and log one stderr line.
- Regex backtracking on adversarial input: every pattern has a ReDoS test at 100 KB input.
- A false contradicted stamp on Copilot costs one wasted turn. The block marker caps it at one per claim per session. The release gate requires at least 30 judged contradicted stamps with none false.
- A false proven stamp misleads the owner. The release gate requires a lower 95% Wilson bound of at least 0.85 on 200 stamps.
- Transcript schema change: unknown record types are ignored. A changed result shape yields no stamps, which fails safe.
- Copilot block loop: `stop_hook_active` is unreliable, so the hook records each blocked claim's digest. A second stop with the same claim finds the digest and passes.
- Marker file unwritable: the hook does not block, because it cannot guarantee one block per claim. It logs one stderr line.
- Unmeasured kinds: `build`, `deployed`, and `url` did not appear in the spike tally. A kind with fewer than 10 judged stamps in the release sample ships as `no receipt` only on Copilot and is listed as unmeasured in the skill page.
- Overlapping Stop events: on Claude Code the hook keeps no state, so both emit the same stamps. On Copilot CLI both stops read one block marker, and Open questions lists that case.

## Security

- No authentication, secrets, or network. Input is the local transcript the harness wrote.
- Trust boundary: transcript text is untrusted data. It is parsed with bounded patterns and never executed.
- Prompt injection: on Copilot, the block reason is model-visible. The reason holds only fixed template text, the claim kind, the call index, and the tool name. It never echoes reply or tool-output text.
- PII: the Claude message repeats at most 80 characters of claim text per stamp, to the session only. The only disk write is the Copilot block marker, which holds SHA-256 digests and no text.
- Abuse case: a crafted reply causes catastrophic backtracking. Mitigation: bounded patterns, ReDoS tests, and the hook deadline.

## Observability

- What proves it works: the labeled eval fixtures reproduce their expected stamps exactly, and the timing test stays under budget.
- Runtime signal: one stderr line on each skip path (no transcript, budget, error, marker failure), as the reflect nudge does. The off switch prints nothing and exits before any read (AC-9).
- No metrics or alerts, because the hook is local.

## Acceptance criteria

- [ ] AC-1: WHEN a Claude Code Stop event fires with a readable `transcript_path` and the final reply holds a `proven` or `contradicted` stamp, the receipts hook SHALL print one `systemMessage` that lists each such stamp with its receipt.
- [ ] AC-2: On Claude Code, the receipts hook SHALL NOT emit `decision: "block"` and SHALL exit 0 on every path.
- [ ] AC-3: WHEN a Copilot CLI `agentStop` event fires with `stop_hook_active` false and the final reply holds a `contradicted` stamp whose digest is not in the session's block marker, the hook SHALL print one `{"decision": "block", "reason": ...}` object naming each contradicted claim's kind, call index, and tool name.
- [ ] AC-4: WHILE `stop_hook_active` is true, or WHEN no `contradicted` stamp is new to the block marker, the Copilot hook SHALL print nothing to stdout.
- [ ] AC-5: The Copilot block reason SHALL contain no text copied from the reply or from tool output.
- [ ] AC-6: IF the transcript path is empty, missing, unreadable, or over the byte cap, THEN the hook SHALL print nothing to stdout, write one stderr line naming the reason, and exit 0.
- [ ] AC-7: The hook SHALL stop work at an internal deadline of 5 s, so the shared 15 s Stop group keeps at least 10 s for the reflect nudge.
- [ ] AC-8: WHEN the final reply has no stamp other than `no receipt`, the Claude hook SHALL print nothing to stdout.
- [ ] AC-9: WHILE `AI_AGENTS_RECEIPTS` is `0` or `off`, the hook SHALL exit 0 before reading any file.
- [ ] AC-10: The claim finder SHALL recognize the 12 kinds in the Ontology, each covered by positive, negative, and edge tests.
- [ ] AC-11: Evidence for `sha`, `number`, and `url` claims SHALL come only from tool output. A test SHALL show that a value present only in a call's arguments gives `no receipt`.
- [ ] AC-12: A `proven` or `contradicted` stamp SHALL cite a call whose tool and output match the claim kind. A test SHALL show that a `git fetch` never proves a `merged` claim.
- [ ] AC-13: A check-count claim SHALL be judged as `ci` against check-run output from `gh pr checks` or `get_pr_checks.py`.
- [ ] AC-14: Freshness SHALL count only edits inside the repository at `cwd`. Tests SHALL show that `git merge-tree`, a quoted `>` inside a string, a temp-file redirect, and a write outside the repo are not edits.
- [ ] AC-15: Tamper detection SHALL stamp a passing-tests claim `contradicted` after a failing run followed by an added skip marker, a deleted failing test, or a deselect of it.
- [ ] AC-16: WHEN the user invokes the `receipts` skill, its script SHALL print every stamp for the last reply, including `no receipt`, with kind, verdict, receipt, and reason. It SHALL read both transcript formats.
- [ ] AC-17: WHERE the skill script gets `--turn N`, it SHALL print stamps for turn N, and SHALL exit 2 when N is out of range.
- [ ] AC-18: No shipped file name, skill name, output label, or doc page SHALL use the upstream product name or its verdict marks. No upstream source code SHALL be copied.
- [ ] AC-19: Every module the hooks and the skill script import SHALL be the standard library or this plugin's own modules.
- [ ] AC-20: A ReDoS test SHALL run every claim and evidence pattern against 100 KB adversarial input and finish each in under 1 s.
- [ ] AC-21: A timing test SHALL show the hook finishing a 4 MB transcript in under 2 s.
- [ ] AC-22: The hook SHALL NOT write transcript text, claim text, or stamps to any file. The Copilot block marker SHALL hold SHA-256 digests only.
- [ ] AC-23: A committed eval set of synthetic transcripts SHALL run in tests and reproduce its expected stamps exactly. No committed fixture SHALL hold text from a real session. Labeled real-session sets SHALL stay outside the repository, and only their aggregate counts are published.
- [ ] AC-24: Before release, a fresh blind sample of 200 `proven` stamps SHALL show a lower 95% Wilson bound of proven precision of at least 0.85. That needs at least 180 of 200 judged correct.
- [ ] AC-25: Before release, a fresh blind sample of 100 replies SHALL show an upper 95% Wilson bound of the miss rate of at most 0.30. That allows at most 21 misses of 100. The sample is one reply per run that has a completion word, a turn with at least one tool call, and no `proven` or `contradicted` stamp. A miss is such a reply with an unsupported or contradicted claim of one of the 12 kinds.
- [ ] AC-26: The sample sizes, the sampling rules, and the pass rules in AC-24, AC-25, and AC-27 SHALL be fixed in a committed file before any draw. A threshold or pattern change after a draw SHALL require a new draw.
- [ ] AC-27: Before the Copilot hook ships, at least 30 `contradicted` stamps mined from the real-session pool SHALL be judged by hand, and none SHALL be false. The stamps SHALL come from an offline replay of the owner's Copilot `events.jsonl` logs, so no hook registers first. Until then the Copilot hook SHALL NOT be registered. If the gate is unmet on 2027-02-25, the hook stays unregistered and ADR-128 is reviewed again.
- [ ] AC-28: After the Copilot hook blocks on a claim, it SHALL NOT block on the same claim digest again in that session, whatever `stop_hook_active` says. A test SHALL replay a second stop with `stop_hook_active` false and show no block.
- [ ] AC-29: IF the block marker cannot be read or written, THEN the Copilot hook SHALL print nothing to stdout and write one stderr line.
- [ ] AC-30: The release report SHALL list the judged stamp count per kind. A kind with fewer than 10 judged stamps SHALL be named unmeasured in `docs/skills/receipts.md` and SHALL NOT cause a Copilot block.
- [ ] AC-31: `docs/skills/receipts.md` SHALL exist with the sibling section order, and `docs/skills/README.md` SHALL list it.
- [ ] AC-32: The `agent-harness-reference` sidecar SHALL record the probed `agentStop` payload keys with tool versions and the DOCS SILENT display field.

## Out of scope

- Blocking on Claude Code, or any change to how a Claude turn ends.
- Codex and other harnesses.
- Non-English claims. The spike corpus is English. Upstream's Chinese, Thai, and Spanish support waits for a corpus to measure it.
- Any change to the reflect nudge, the dispatcher, or `evidence-provenance`.

## Deferred

- Eval expansion to standard suites such as SWE-rebench. Owner: Richard Murillo. Trigger: after this ships.
- A second independent labeler for the release sample. Owner: Richard Murillo.
- A live Copilot probe of advisory display fields, once quota returns. Owner: receipts maintainer.

## Open questions

The owner settled these on 2026-11-25:

- D3: adapt the idea only; copy no upstream code.
- D4: ship to Copilot CLI as well as Claude Code.
- D5: file the tracking issue (#7633).
- D6: block on a contradicted claim on Copilot CLI.
- D7: ship the full kind set.
- D8: the release gate uses the lower bound 0.85.
- D9: keep the Copilot block, gate it, and write an ADR first.
- D10: amend ADR-084 with rule 2b in the same change as ADR-128.
- D11: draw the Copilot gate stamps by offline replay of the owner's logs; review again if unmet on 2027-02-25.
- D12: replace the capped-scan log figures with the full count in every artifact.

These stay open. The ADR-128 review raised them and the owner has not decided them.
`.project-toolkit/critique/ADR-128-debate-log.md` lists each one under "Deferred P1 and P2 items".

Owner decisions:

- A hard cap on blocks per session. It changes D9.
- The replay pool, the stamp draw, and a live Copilot probe. Each changes D11.
- A separate sunset date for each registration.
- A per-kind floor of 10 or 30 stamps.
- Removal of the hook after one confirmed false block.
- Two alternatives the ADR does not weigh: a stateless transcript guard and a prompt notice.

Spec work that must land here before the build slice starts:

- A definition of normalized claim values, with a digest rule for kinds that carry no value.
- Acceptance criteria for ADR-128 Decisions 4 and 6.
- The block reason text, and a count of blocks that change the reply.
- The Copilot behavior when two stops overlap and both read the block marker before either writes it. AC-28 covers sequential stops only.
- A stated firing bound for the Claude Code registration. AC-1 allows one `systemMessage` per Stop event. The owner judges whether that meets ADR-084 condition g.
- A signal after release that shows the hook still earns its place, with a review date.

## CVA summary

- Common: every claim kind follows the same flow: find the claim, select evidence of the matching kind, judge it, and cite the receipt. Both harnesses share that engine.
- Varies: the claim pattern and evidence parser per kind, the transcript reader per harness, and the output per harness (advisory message or block decision).
- Relationship: the reader feeds the ledger, and the ledger feeds the judge. The output layer is the only harness-specific step after reading.

## Buy-vs-build decision

- Classification: core. Checking claims against tool output is a capability the owner wants to shape beyond upstream.
- Alternatives: (a) depend on the upstream package; (b) vendor the pinned upstream core; (c) build our own from the idea and the spike's findings.
- Recommendation: build (c). The owner ruled out (b): "I don't want to effectively fork" it. Option (a) breaks the stdlib-only plugin contract and keeps every defect the spike found.
- Rationale: the spike showed the idea works on this repo's sessions, at 0.93 proven precision after fixes (round 4, 2026-11-25). It also named five design defects that a fresh design fixes from the start. Credit for the idea goes to the upstream project in the skill page.

## Complexity classification

- Engineering tier: 4. A new claim engine with 12 kinds, two harness readers, two outputs, a skill, and an eval set.
- Problem domain: Complicated. The behavior is measured, and the remaining risk is analyzable.
- Methodology: build in slices. Engine and eval first, then the Claude hook, the Copilot hook, and the skill and docs.

## ADR cross-reference

ADR-128 (proposed) is required before the Copilot slice is built. The owner decided this on 2026-11-25 (D9). The ADR covers a Stop hook that blocks a Copilot turn, the block marker, and the 30-contradiction gate. It is drafted with `adr-generator` and reviewed with `adr-review`. Slices 1 and 2 (engine, kinds) do not wait for it. Slice 3 (the Claude hook) waits for the owner to accept ADR-084 rule 2b, because rule 2a says any other advisory hook needs its own amendment.
