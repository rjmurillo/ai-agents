---
type: requirement
id: REQ-050
title: Receipts, an annotate-only Stop check of claims in the final reply
status: draft
priority: P2
category: functional
created: 2026-11-25
related:
  - REQ-048
  - ADR-084
  - "#5817"
  - "#7631"
---

# REQ-050: Receipts, an annotate-only Stop check of claims in the final reply

This file is durable. It lands in git history. It holds counts and paths only, no transcript text.

## Step 0 First Principles

Answers come from the owner's choices on 2026-11-23 and 2026-11-25, plus the spike measurements in draft PR #7631.

Gate result on 2026-11-25: `tests/commands/step0_parser.py` returns H3 on Q1. Q3 passes the specificity test and Q5 passes the speculative test.
H3 fires because the parser counts a requester only in the form `<Name> on the <Team> team`. The gate policy accepts one named requester on the evidence path (issue #6990).
REQ-048 and REQ-049 return H3 for the same single-owner answer. Q1 is left as written. The owner decides whether it passes.

### Q1

Richard Murillo (repository owner) requested it. On 2026-11-23 he asked for a spike on whether a receipt checker core earns a Phase 1 port. On 2026-11-25 he accepted the round 4 verdict and asked for the port. Single requester, so Q1 passes on the evidence path: specific Q3 plus evidenced Q5.

### Q2

Today the owner reads each final reply and checks its claims by hand. Step by step:

1. The agent ends a turn with claims such as "36 passed", "pushed", or a commit SHA.
2. The owner scrolls back through tool output to find the call that proves each claim.
3. When no call proves it, the owner asks the agent, or reruns the command.

The `evidence-provenance` skill and the voice rule's "Clear the gate or drop the claim" section tell the agent not to overclaim. Nothing checks the reply after it is written.

Reframing: capability invention, check: on a fresh blind sample, the shipped hook's visible stamps keep proven precision at or above 0.90 and the miss rate at or below 0.25.

### Q3

Richard Murillo, reading final replies in Claude Code sessions on `rjmurillo/ai-agents`. He is blocked on trusting completion claims without rereading tool output. The hand check in `.project-toolkit/prototypes/nocap-spike/REPORT.md` (PR #7631) found a reply that said "19 pass" when the cited `gh pr checks` output showed 18.

### Q4

The smallest deliverable is the Stop hook alone. It runs the spike's round 4 core over the transcript and prints proven and contradicted stamps as one advisory message. Estimate: 16 hours for a human team, about 1 hour AI-assisted. The `receipts` skill, which shows every stamp on demand, adds 8 hours.

### Q5

Spike round 4 on 2026-11-25 (`REPORT.md` in draft PR #7631): of 60 unstamped completion replies, 12 carried an unsupported claim, a miss rate of 0.20. In round 1, 56 of 146 stamps were NO RECEIPT, a rate of 0.384. Each is a claim the owner checks by hand today.

### Q6

At 10x more sessions, the per-reply cost is fixed: p95 0.40 s per transcript, with no network or model call. Longer transcripts are the risk. The three largest in the pool, up to 36 MB, took up to 3.5 s. A byte and time budget keeps the hook inside the shared 15 s Stop timeout. A 10x larger claim vocabulary would make the vendored core's regex set the liability. The upstream ReDoS suite runs in tests to hold that.

## Prior Art / Constraints

### Direct prior art from memory

- REQ-048 and issue #5817 (`src/claude/hooks/Stop/invoke_reflect_nudge.py`): an advisory, fail-open Stop hook. It reads `transcript_path`, prints a `systemMessage`, never blocks, and exits 0 on every path. Relevance: the same event, output channel, and failure policy. Decision: honor. Receipts copies its registration shape, its `--advisory` launcher flag, and its off switch.
- `dispatch_groups.json` group `plugin-stop-1-reflect_nudge`: Copilot-excluded under ADR-084 rule 2a, because Copilot has no documented advisory Stop output field or `transcript_path`. Relevance: the same gap applies to receipts. Decision: honor, pending the owner's decision in Open questions.
- `.serena/memories/decision-claude-hook-group-dispatch.md`: Copilot Stop hooks cannot share a plain observe dispatcher, because decision objects concatenate into invalid JSON. Relevance: the Copilot exclusion avoids this. Decision: honor.
- `src/claude/lib/failure_classifier/transcript.py`: a shipped mapper from Claude Code records to tool events. Relevance: it covers the same record shapes as the spike adapter. Decision: adapt. The port reuses its record-shape knowledge and the reflect nudge's bounded read, not a second reader.
- `src/claude/lib/failure_classifier/classifier.py` cites an Apache-2.0 paper with "no code copied". `invoke_reflect_nudge.py` adapts fixed phrases from claude-mem. Relevance: no shipped file yet carries third-party code verbatim. Decision: propose-amend. Vendoring needs an owner decision and, likely, an ADR.
- chestertons-fence: not run as a separate skill. The change only adds files. It removes and rewrites nothing, so there is no fence to examine. Recommendation: PRESERVE every existing Stop hook unchanged.

### Connected context from prior-art search

- Connected entity: `reflect-nudge`, Stop hook. Adjudication: in-scope. Note: it shares the 15 s Stop budget, and receipts must leave it headroom.
- Connected entity: `evidence-provenance`, skill. Adjudication: out-of-scope. Note: it guides how the agent writes claims. Receipts checks them afterwards. It changes neither.
- Connected entity: `failure-classifier`, lib. Adjudication: blast-radius. Note: sharing its transcript mapper couples the two hooks. A record-shape change would then touch both.
- Search depth: medium, matched to Tier 3.

### Coverage notes

- Topic `receipts`: 3 variants (`receipt`, `claim check|verif|overclaim`, `stop hook|systemMessage|advisory stop`) over `.serena/memories`. Results: 0, 1, and 5 files. The one claim hit is about a CI gate, not this feature. Confidence: high.
- Topic `vendored-third-party-code`: 2 variants over memories and ADRs. Results: 0 memory files, and 6 ADRs that mention vendoring but not shipped third-party source. Confidence: low, because only 2 variants ran.
- Hindsight MCP was unavailable (connection closed), so only repository memory files were searched.
- Blast-radius count: 1, under the human-mode threshold of 2. No halt.

## Problem statement

Final replies carry claims that a tool result should prove. The owner checks them by hand, and the spike measured 12 of 60 completion replies carrying an unsupported claim.

## User stories

1. As the owner, when a turn ends, I see one short line per checked claim. It says whether a tool result proves it or contradicts it, and which call is the receipt.
2. As the owner, when a reply has no checkable claim, I see nothing.
3. As the owner, I can run `/receipts` to see every stamp for the last reply, including claims with no receipt.
4. As the owner, I can turn the hook off with one environment variable.

## Ontology

- **Reply**: the main-thread assistant text after the last tool call of a turn. A turn opens at each main-thread user text record.
- **Claim**: a checkable statement in a reply. Kinds: tests, ci, sha, number, merged, pushed, pr, file, and other kinds the core supports.
- **Evidence**: one record per tool call: name, arguments, output, exit status, and call index.
- **Ledger**: the session's evidence, carried across turns.
- **Stamp**: the verdict on one claim. Values: `proven` (a cited call proves it), `contradicted` (a call disproves it), `no receipt` (nothing proves or disproves it). These labels replace the upstream marks.
- **Receipt**: the call a stamp cites, by index, tool name, and a short reason.
- Decision rule: freshness is by call order, not timestamp.
- Bounded contexts: the core (claims, evidence, verdict, tamper), the adapter (transcript to core calls), and the hook (budget, output).

## Data model

- `Turn(index, calls, reply, delegated)`: identity is the turn index in one transcript. Invariant: `reply` is non-empty for a judged turn.
- `ToolCall(name, args, ts, result_text, is_error, has_result)`: identity is the tool-use id. Invariant: a call with no result is not evidence.
- `Stamp(kind, claim_text, verdict, cite, why)`: identity is `(turn, claim span)`. `verdict` is one of the three labels above.
- Lifecycle: built in memory per Stop event, printed, and discarded. Nothing persists.

## Integrations

- **Claude Code Stop event**: payload `session_id`, `transcript_path`, and `cwd`. Failure: a missing or unreadable path. Behavior: print nothing and exit 0.
- **Transcript JSONL**: read once, bounded by bytes and lines. Failure: a malformed line. Behavior: skip it.
- **Hook dispatcher** (`invoke_dispatch_claude.py`): runs the shim in an advisory Stop group. Idempotent: the same transcript gives the same stamps.
- **GitHub Copilot CLI**: excluded, as the reflect nudge is. See Open questions.

## Failure modes

- Budget overrun on a large transcript: stop reading at the byte or time cap, print nothing, and log one stderr line. Early warning: stderr shows a budget stop.
- A regex backtracks on adversarial input: the vendored ReDoS suite runs in CI. Prevention: patterns stay bounded.
- A false contradicted stamp erodes trust: the spike saw 0 in 678 runs. Early warning: a user report or eval regression. Prevention: hold the eval baseline in tests.
- A false proven stamp: 7 of 100 in round 4. Accepted limit, shown in the skill page.
- Transcript schema change: unknown record types are ignored. A changed tool_result shape yields no stamps, which fails safe.
- Overlapping Stop events: the hook is stateless, so both print the same stamps.

## Security

- No authentication, secrets, or network. Input is the local transcript the harness wrote.
- Trust boundary: transcript text is untrusted data. The hook parses it with bounded regexes and never executes it.
- PII: output repeats short claim text from the reply into the session only. Nothing is written to disk.
- Supply chain: the vendored core is pinned to upstream commit `a683c857` with every change listed. It is stdlib only.
- Abuse case: a crafted reply causes catastrophic backtracking. Mitigation: bounded patterns, the ReDoS suite, and the hook time budget.

## Observability

- What proves it works: the eval fixture reproduces the spike's stamp set exactly, and the timing test stays under budget.
- Runtime signal: one stderr line on every skip path (off, no transcript, budget, error), as the reflect nudge does.
- No metrics or alerts, because the hook is local and advisory.

## Acceptance criteria

- [ ] AC-1: WHEN a Claude Code Stop event fires with a readable `transcript_path` and the final reply holds a claim stamped `proven` or `contradicted`, the receipts hook SHALL print one `systemMessage` that lists each such stamp with its receipt.
- [ ] AC-2: The receipts hook SHALL NOT emit `decision: "block"` and SHALL exit 0 on every path.
- [ ] AC-3: IF the transcript is missing, unreadable, or over the byte cap, THEN the hook SHALL print nothing to stdout and one line to stderr naming the reason.
- [ ] AC-4: The hook SHALL stop work at an internal deadline of 5 s, so the shared 15 s Stop group keeps at least 10 s for the reflect nudge.
- [ ] AC-5: WHEN the final reply has no stamp other than `no receipt`, the hook SHALL print nothing to stdout.
- [ ] AC-6: WHILE `AI_AGENTS_RECEIPTS` is `0` or `off`, the hook SHALL exit 0 before reading any file.
- [ ] AC-7: WHEN the user invokes the `receipts` skill, its script SHALL print every stamp for the last reply, including `no receipt`, with kind, verdict, cited call index and tool name, and reason.
- [ ] AC-8: WHERE the skill script gets `--turn N`, it SHALL print stamps for turn N, and SHALL exit 2 when N is out of range.
- [ ] AC-9: The shipped core SHALL carry upstream's `LICENSE` and `NOTICE` text and a provenance file naming commit `a683c857`. Each modified file SHALL carry a one-line modification notice.
- [ ] AC-10: No shipped file name, skill name, output label, or doc page SHALL use the upstream product name or its verdict marks.
- [ ] AC-11: Every module the hook and skill script import SHALL be the standard library or this plugin's own modules.
- [ ] AC-12: A test SHALL replay the spike's labeled fixtures through the shipped core and match the spike's stamps exactly.
- [ ] AC-13: A test SHALL run the upstream synthetic battery through the shipped core and pass 125 of 125 cases.
- [ ] AC-14: A timing test SHALL show the hook finishing a 4 MB transcript in under 2 s.
- [ ] AC-15: The hook SHALL NOT write transcript text, claim text, or stamps to any file.
- [ ] AC-16: `docs/skills/receipts.md` SHALL exist with the sibling section order, and `docs/skills/README.md` SHALL list it.

## Out of scope

- Blocking mode, or any change to how a turn ends.
- GitHub Copilot CLI and Codex support.
- Fixing the three known round 4 defects: missing content verbs, test-description stamps, and SHAs under `"head":` keys.
- Any change to the reflect nudge, the dispatcher, or `evidence-provenance`.

## Deferred

- Eval expansion to standard suites such as SWE-rebench. Owner: Richard Murillo. Trigger: after this ships.
- A second independent labeler for the precision and miss samples. Owner: Richard Murillo.
- The three known defects above. Owner: next receipts change.

## Open questions

1. Vendoring upstream source into the shipped plugin is a first for `src/claude/`. Does it need an ADR before the build? Owner: Richard Murillo.
2. Does receipts take the reflect nudge's Copilot exclusion, with a new authorizing issue? Owner: Richard Murillo.
3. Which issue tracks this work? None exists yet. Owner: Richard Murillo.

## CVA summary

- Common: every Stop advisory reads the transcript under a budget, prints one `systemMessage`, and fails open.
- Varies: the signal. The reflect nudge scores human corrections. Receipts judges reply claims against tool output.
- Relationship: both hooks share the Stop group budget and the transcript record shapes. Neither depends on the other's output.

## Buy-vs-build decision

- Classification: context, not core. The repository's value is its agents and gates, not claim parsing.
- Alternatives: (a) depend on the upstream package at install time; (b) vendor the pinned core; (c) write a new checker.
- Recommendation: partner, by vendoring (b). Option (a) breaks the stdlib-only plugin contract and adds an install step. Option (c) discards a core that met upstream's published claims on this repo's sessions.
- Rationale: the spike measured the vendored core at 0.93 proven precision and a 0.20 miss rate. Upstream is Apache-2.0, the same license as this plugin.

## Complexity classification

- Engineering tier: 3. One new hook, one new skill, one vendored lib, and tests, inside the existing Stop dispatch.
- Problem domain: Complicated. The behavior is measured, and the remaining risk is analyzable.
- Methodology: build in slices. Core and parity tests first, then the hook, then the skill and docs.
