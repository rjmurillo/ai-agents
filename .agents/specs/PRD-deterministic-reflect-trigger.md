# PRD: Deterministic Reflect Trigger (Stop-hook session-signal scanner)

**Status**: Draft
**Owner**: unassigned
**Milestone**: v0.7.0
**Tracking issue**: [#5817](https://github.com/rjmurillo/ai-agents/issues/5817)
**Created**: 2026-09-16

---

## Prior Art / Constraints

This capability has been attempted once and deleted once. Read this section before proposing a design; two of the three failure modes below are re-reachable.

### The first attempt shipped dead and stayed dead

`.claude/hooks/Stop/invoke_skill_learning.py` (1,234 LOC) and its helper `skill_pattern_loader.py` (412 LOC) landed in PR #908 alongside the `reflect` skill. Issue #3184 measured what they did at runtime:

> `.claude/hooks/Stop/invoke_skill_learning.py` (1,234 LOC) plus its helper `.claude/hooks/Stop/skill_pattern_loader.py` (412 LOC) read `hook_input["messages"]`, but the Claude Code Stop payload carries `session_id`, `transcript_path`, and `cwd`, not `messages`. The hook early-returns on every Stop and has since it shipped.

Every invocation from ship to deletion was an early return. It cost roughly 100 ms per Stop to do nothing. PR #3237 deleted it along with five other provably-dead hooks.

The lesson binds this PRD: **a hook that reads a payload field the event does not send is a silent no-op forever, and nothing in the test suite notices.** The old hook had three dedicated test suites totalling 2,453 LOC. All of them passed. None of them drove the real payload.

### The owner already chose local over CI

Issue #1757 proposed automating `reflect`. PR #1761 implemented it as a GitHub Action. The owner closed it unmerged:

> Rejected: this CI workflow approach is wrong. Reflection needs the local context of the work to extract real signal. A GitHub Action run after-the-fact, divorced from the session, has no signal advantage over the existing local Stop hook (.claude/hooks/Stop/invoke_skill_learning.py).
>
> If we want post-session reflection at scale, extend the local Stop hook to be smarter about HIGH/MED/LOW confidence extraction and Serena persistence. Don't duplicate it as a CI workflow.

That ruling stands and this PRD follows it: local hook, not CI. Note the secondary fact, that #1757 was closed `completed` while its only linked PR was closed unmerged, and today no Stop hook exists on any surface. A closed issue is not evidence that a capability shipped.

### The old design was the token-hungry one

`.claude/hooks/requirements.txt` existed solely for that hook, pinning `anthropic>=0.39.0` with the comment `# Used by: Stop/invoke_skill_learning.py`. The deleted module exported `classify_learning_by_llm`. So the first attempt was an LLM classification call on every Stop, which is the design this PRD exists to avoid rather than repeat.

### Current state, measured 2026-09-16 on `origin/main` at `5e4b302c9`

| Fact | Value | How checked |
|---|---|---|
| Hook events registered in `.claude/settings.json` | `SessionStart` 4, `UserPromptSubmit` 1, `SessionEnd` 1, `PreCompact` 1 | `json.load` of the file |
| `Stop` hooks registered | none | same |
| Hooks reading `transcript_path` | none | grep of `.claude/lib/`, `.claude/hooks/`, `scripts/`, `templates/hooks/` |
| `claude-agent-sdk` as a dependency | absent | grep of `pyproject.toml`, `scripts/`, `.claude/lib/` |
| Copilot CLI event mapping | `Stop: Stop`, `eventDrop: []` | `templates/platforms/copilot-cli.yaml:66,74` |

The Copilot mapping matters: in July 2026 `Stop` was remapped onto `SessionEnd`, and it is now direct. A Stop hook added today reaches both harnesses through the normal generator path.

### Binding constraints

- ADR-064: skills are the single user-invocable surface.
- ADR-042: Python only; no new shell scripts.
- `.claude/rules/tool-use-hook-bar.md` is scoped to `PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure`, so it does not govern `Stop`.
- `.claude/rules/universal.md`: no scratch written into the repository tree. The deleted `skill_pattern_loader.py` wrote `.claude/hooks/Stop/.skill_pattern_cache.json` into the source tree and needed a `.gitignore` line to hide it. Do not repeat that.
- `.claude/rules/ci-scripts.md` MUST-12: a run that did nothing must not report like a run that succeeded. Print examined counts.
- **`templates/hooks/` is the editable source; `.claude/settings.json`, `.claude/hooks/` and `src/claude/hooks/` are generated.** ADR-109 B4. `build/scripts/hook_templates.py` says so in its own docstring: it compiles `templates/hooks/` into `src/claude/hooks/` and `.claude/settings.json`, and `templates/hooks/settings.tmpl` renders straight to `.claude/settings.json` with no plugin-tree hop. A Stop hook is authored as `templates/hooks/Stop/<name>.py` plus its registration in `templates/hooks/settings.tmpl` and `templates/hooks/hooks.json`, then regenerated. Editing the generated trees directly is lost on the next `build_all.py` run, and `--check` fails the drift gate. `templates/hooks/` currently holds `PreCompact`, `PreToolUse`, `SessionEnd`, `SessionStart`, `UserPromptSubmit`; a `Stop` directory does not exist yet and this work creates it.

---

## Buy-vs-build decision

**Classification**: core. The signal being detected (a correction the user issued to this agent, in this session, in this repository) exists only inside the session transcript. No vendor sells it.

**Alternatives evaluated**:

| Option | Verdict | Why |
|---|---|---|
| Invoke `reflect` (LLM skill) on every `Stop` | Reject | `Stop` is per-turn (`agent-harness-reference` SKILL.md: "Per-turn stop"). An LLM pass per turn is the cost profile the first attempt carried and the reason this PRD was requested. |
| CI workflow reading the merged PR | Reject | Already ruled on in PR #1761. No local context, so no signal advantage. |
| Deterministic scanner over the transcript, nudge only | **Build** | Zero marginal token cost per turn. The expensive LLM pass runs only when a human accepts the nudge. |
| Reuse an existing log-analysis library | Reject | The input is a private JSONL schema owned by the harness. A general library would need the same per-record classifier written anyway. |

**Recommendation**: build, at the smallest size that can be measured. The scanner is one Python module with no third-party dependency.

---

## 1. Problem Statement

`reflect` captures corrections, praise, and edge cases so a later session does not repeat a mistake. Its value is proportional to how often it runs, and today nothing invokes it: no `Stop` hook is registered on any surface, and the routing line in `CLAUDE.md` fires only when a human names the trigger. Every session that ends without it loses whatever it learned.

The obvious fix, invoking `reflect` from a `Stop` hook, is wrong at the cost axis. `Stop` is a per-turn event, so a long session fires it dozens of times, and each fire would pay for an LLM pass over the conversation whether or not anything happened worth recording. That is the shape of the deleted `invoke_skill_learning.py`, which carried an `anthropic` SDK dependency for exactly this purpose.

The separable part is **detection**. Deciding whether a session contains a correction is a deterministic scan over text the harness has already written to disk. Only **extraction**, turning a detected correction into a durable learning, needs a model. Splitting the two puts the per-turn cost at roughly one file read and leaves the expensive half opt-in.

---

## 2. User Stories

- **US-1**: As a maintainer ending a session in which I corrected the agent twice, I want the agent to tell me those corrections are unrecorded, so that the next session does not repeat them.
- **US-2**: As a maintainer ending a session where nothing notable happened, I want no prompt at all, so that the nudge keeps meaning something when it does appear.
- **US-3**: As a maintainer running a long session, I want at most one nudge per session per signal set, so that a per-turn event does not become a per-turn interruption.
- **US-4**: As a contributor, I want the hook to be provably wired, so that it cannot repeat the 1,234-LOC silent no-op that shipped last time.
- **US-5**: As an operator, I want the hook to fail open on any error, so that a bad transcript read never wedges the end of a turn.

---

## 2a. Requirements (EARS)

The normative statements, extracted from the prose sections that follow so downstream traceability has one place to read them. `PRD-agent-skill-classification-audit.md` carries 12 such statements and is the precedent.

- REQ-1: WHEN the harness emits a `Stop` event, THE SYSTEM SHALL read the transcript named by the payload's `transcript_path`, SO THAT detection uses the file the harness already wrote instead of a payload field that may not exist.
- REQ-2: WHEN the `Stop` payload omits `transcript_path`, or the path is unreadable, THE SYSTEM SHALL exit 0 without a decision payload, SO THAT a hook error never wedges the end of a turn.
- REQ-3: WHEN scanning transcript records, THE SYSTEM SHALL count a record as a human turn only on positive evidence of one, and SHALL NOT count a record carrying `toolUseResult`, SO THAT tool output and file contents are never read as operator speech.
- REQ-4: WHEN a malformed line appears in the transcript, THE SYSTEM SHALL skip that line, continue scanning, and report the skipped count, SO THAT a partial write during a live session does not abort detection.
- REQ-5: WHEN the scan finds at least one qualifying signal and no marker records that signal set for this `session_id`, THE SYSTEM SHALL emit a `Stop` decision naming the counts and the `reflect` skill, SO THAT the operator learns the corrections are unrecorded.
- REQ-6: WHEN a marker already records the current signal set for this `session_id`, THE SYSTEM SHALL exit 0 without a decision payload, SO THAT a per-turn event does not become a per-turn interruption.
- REQ-7: WHEN the scan finds no qualifying signal, THE SYSTEM SHALL exit 0 without a decision payload, SO THAT the nudge keeps meaning something when it does appear.
- REQ-8: WHERE the scanner runs, THE SYSTEM SHALL make no network call and SHALL NOT include transcript content in the decision reason or the marker, SO THAT the session's contents never leave the machine or reach a durable artifact.
- REQ-9: WHEN the scanner writes its marker, THE SYSTEM SHALL write outside the repository tree, with owner-only permissions, symlink-safe path resolution, and an atomic create-or-replace, SO THAT the deduplication state cannot be read, corrupted, or forged by another process.
- REQ-10: WHEN any run completes, THE SYSTEM SHALL print the examined counts alongside the finding counts, SO THAT a run that found nothing is distinguishable from a run that examined nothing (`ci-scripts.md` MUST-12).
- REQ-11: WHEN the hook is registered, THE SYSTEM SHALL be authored in `templates/hooks/` and reach both harnesses by regeneration, SO THAT no edit lands in a generated tree that `build_all.py` will overwrite.

---

## 3. Data Model

### Input: the Stop payload

Documented shape (`.agents/analysis/claude-code-hooks-opportunity-analysis.md:419-430`), confirmed by #3184's empirical probe:

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/path/to/project"
}
```

`transcript_path` is the enabler. The first attempt failed because it invented `messages` instead of following this pointer.

### Input: the transcript

Newline-delimited JSON, not a database. Measured on a real 5.8 MB session on 2026-09-16 at `~/.claude/projects/-home-user-ai-agents/<sessionId>.jsonl`; no SQLite file exists anywhere under `~/.claude`. Record-type census from that session:

| `type` | Count |
|---|---|
| `attachment` | 439 |
| `assistant` | 427 |
| `user` | 272 |
| `queue-operation` | 95 |
| `ai-title` | 93 |
| `atis-latch` | 93 |
| `last-prompt` | 92 |
| `agent-setting` | 25 |
| `system` | 15 |
| `mode` | 13 |

### The trap in the `user` type

`type == "user"` covers two different things, and only one is a human speaking. Two key shapes observed in the same session:

```text
('cwd','entrypoint','gitBranch','isSidechain','message','origin','parentUuid',
 'permissionMode','promptId','promptSource','sessionId','timestamp','type',
 'userType','uuid','version')

('cwd','entrypoint','gitBranch','isSidechain','message','parentUuid','promptId',
 'sessionId','sourceToolAssistantUUID','timestamp','toolUseResult','type',
 'userType','uuid','version')
```

The second carries `toolUseResult` and `sourceToolAssistantUUID`: it is a tool result the harness records as a user-role turn. A scanner that treats every `user` record as human speech will read tool output, file contents, and command stderr as if the operator had said it. Given that the corpus includes this repository's own rule files, which contain the literal words "no", "wrong", and "incorrect" in abundance, that mistake produces a scanner that fires on every session and means nothing.

Human turns must be selected positively (presence of `promptSource`, absence of `toolUseResult`), never by filtering the negative case, and the selection rule needs a test using a real record of each shape.

### Output: the nudge

A `Stop` decision, top-level per `agent-harness-reference` SKILL.md line 66: `{"decision": "block", "reason": "<text>"}`. The reason names counts and the skill to invoke, and never quotes transcript content (see Security).

### State: the dedupe marker

One marker per session, keyed on `session_id`, recording which signal set has already been nudged. It records counts and a signal hash, never matched text.

Storage contract, because the marker holds session metadata and also decides whether a nudge fires:

- **Per-user application data, outside the repository tree.** A shared or world-readable location leaks `session_id` and per-session counts; a world-writable one lets anything on the machine suppress or replay a nudge by editing the state the hook trusts.
- **Owner-only permissions** on creation (`0o700` directory, `0o600` file), or the platform ACL equivalent. Set the mode at creation rather than after, so no window exists where the file is readable.
- **Symlink-safe path handling.** Resolve the parent and refuse to follow a symlink into it. An attacker-planted symlink otherwise redirects the write.
- **Atomic create-or-replace.** `Stop` is per-turn and turns can overlap, so two invocations can race one marker. Write to a temporary file in the same directory and `os.replace`, or create exclusively with `O_EXCL` where the semantics need it. A torn marker must not read as "already nudged" or as "never nudged"; it must fail open to no nudge and say so.

---

## 4. Integrations

| System | Interaction |
|---|---|
| `templates/hooks/` | The editable source. New `Stop/` directory, plus registration in `settings.tmpl` and `hooks.json` |
| Claude Code `Stop` event | Reached through the generated `.claude/settings.json`. Never hand-edited |
| Copilot CLI | Generated from the same registration; `Stop: Stop` direct, `eventDrop: []` |
| `reflect` skill | The nudge names it. The hook never invokes it and never writes memory itself |
| Serena memory | Untouched by the hook. Persistence stays inside `reflect`, which already requires explicit user approval before writing |
| `build_all.py` | Renders `templates/hooks/` into every generated tree, Claude and Copilot; `--check` must be clean |

The hook proposes and stops. It does not write learnings, because `reflect` already requires the user to approve each proposed learning before persistence, and a hook that wrote memory directly would route around that consent.

---

## 5. Failure modes

| Mode | Trigger | Required behavior |
|---|---|---|
| Payload field absent or renamed | Harness changes the `Stop` contract | Exit 0, no block, and a runtime-contract test with a negative control that fails when the field is missing. This is the #3184 failure verbatim |
| `transcript_path` unreadable or absent | Deleted file, permissions, sandbox | Exit 0, fail open. A hook error must never wedge the turn |
| Malformed JSONL line | Partial write while the session is live | Skip the line, keep scanning, count skipped lines in the report |
| Nudge storm | `Stop` is per-turn | Dedupe on `session_id` plus signal hash. At most one nudge per session per signal set |
| Blocking loop | Hook blocks, harness re-enters Stop | Probe for a re-entry field on the payload (`stop_hook_active` is used in #3184's probes but is not documented in this repository) and honor it. Until probed, treat as an open question, not an assumption |
| Scanner too eager | Substring matching on "no" hits "now", "note", "nothing" | Precision must be calibrated against real transcripts before the hook is registered, not after |
| Scanner too quiet | Markers miss how this operator actually corrects | Same calibration run reports recall |
| Silent success | The run that found nothing looks like the run that worked | Print examined counts per ci-scripts MUST-12 |
| In-tree scratch | Marker file written under `.claude/` | Forbidden. The deleted loader did this and needed a `.gitignore` entry to hide it |

---

## 6. Security

The transcript is the highest-sensitivity file this repository's tooling touches. It holds the full session: pasted credentials, tool output, file contents, and environment values.

- **No egress.** The scanner makes no network call. This is the property that makes the deterministic design safer than the LLM one it replaces, which shipped an `anthropic` client reading conversation content.
- **No transcript content leaves the process.** The nudge reason carries counts and categories. It does not quote matched text, because the matched text is the user's own words and may carry anything they pasted.
- **No content in the marker.** Counts and a hash only.
- **No in-tree writes.** Marker goes outside the repository. A transcript excerpt committed by accident is a disclosure, and `git add -A` is routine here.
- **Path handling.** `transcript_path` arrives from the harness and is read, never executed and never interpolated into a shell command. Resolve it and confirm it is a file before opening.

---

## 7. Observability

Per ci-scripts MUST-12, the hook reports scope alongside findings, so a zero can be distinguished from a no-op:

```text
reflect-trigger: 272 user records, 118 human turns, 2 HIGH, 0 MED (nudged)
reflect-trigger: 272 user records, 118 human turns, 0 HIGH, 0 MED (silent)
reflect-trigger: transcript unreadable at <path> (fail-open, no block)
```

Line one of that output is also the calibration instrument: running the scanner across a corpus of existing transcripts yields the precision and recall numbers Acceptance criteria require.

---

## 8. Acceptance criteria

Written so each is executable. #1757 was closed as completed with nothing merged; criteria that cannot be run invite that outcome again.

- [ ] AC-1: Given a Stop payload whose `transcript_path` points at a transcript containing two human corrections, the hook exits with a `decision: "block"` payload naming a count of 2.
- [ ] AC-2: Given a transcript with no correction and no praise, the hook exits 0 with no decision payload.
- [ ] AC-3: Given a payload with no `transcript_path` key, the hook exits 0 and prints the fail-open line. **Negative control**: the same test with the key present and valid must produce a block, proving the case discriminates.
- [ ] AC-4: Given a transcript whose only "correction-like" text sits inside a record carrying `toolUseResult`, the hook exits 0. Tool output is not human speech.
- [ ] AC-5: Given two consecutive Stop events on one `session_id` with an unchanged signal set, the second exits 0. One nudge per session per signal set.
- [ ] AC-6: Given a transcript with one malformed line among valid ones, the hook completes and reports the skipped count.
- [ ] AC-7: The hook writes nothing under the repository root. Asserted by `check_test_tree_writes.py` conventions and a test that snapshots `git status --porcelain` across a run.
- [ ] AC-8: A runtime-contract test drives the hook through its real registered path, not by importing a helper. Per `.claude/rules/testing.md` MUST-8, assert the process exit code.
- [ ] AC-9: Calibration report committed: precision and recall of the marker set measured against at least 10 real transcripts, with the count of transcripts and human turns examined stated next to the rates.
- [ ] AC-10: `uv run python build/scripts/build_all.py --check` is clean and the Copilot shim exists after regeneration.
- [ ] AC-10b: The **installed Copilot `Stop` registration** is driven end to end, not just asserted present. One case sends a payload whose transcript holds a correction and asserts a blocking decision; one sends an unreadable or absent `transcript_path` and asserts fail-open. Both assert the hook process exit status, not a helper return value. AC-8 proves the Claude path and AC-10 proves the wiring exists; neither proves a Copilot `Stop` payload reaches the scanner.
- [ ] AC-11: `uv run python scripts/validation/pre_pr.py` reports no FAIL.
- [ ] AC-12: Measured wall-clock cost of one Stop invocation on a 5 MB transcript is stated in the PR. The deleted hook cost about 100 ms to do nothing; a replacement that costs more than that to do something real needs its number on the record.

---

## 9. Out of scope

- Changing what `reflect` does once invoked, including its HIGH/MED/LOW tiers and its approval-before-persistence rule.
- Writing to Serena memory from the hook.
- Retrospective triggers. Those are settled in `.claude/rules/retros.md` and are a different cadence.
- Reviving any part of `invoke_skill_learning.py` or `skill_pattern_loader.py`. Both were deleted as dead in PR #3237 and this is a new module.
- Adding `claude-agent-sdk` as a dependency. The scanner needs no SDK to read a JSONL file. If a later phase wants the SDK, that is its own decision with its own supply-chain review.
- Any CI-side reflection. Ruled out in PR #1761.

---

## 10. Deferred

- **Cross-harness parity beyond registration.** Ship Claude-first; confirm the Copilot dispatcher path with a runtime test before claiming both.
- **Signal types past corrections and praise.** Edge cases and repeated patterns are in `reflect`'s tiers but are harder to detect deterministically. Add only with calibration numbers.
- **Auto-invoking `reflect` on a HIGH signal.** The nudge is the bounded first step. Auto-invocation reintroduces per-session LLM cost and needs its own measurement.

---

## 11. Open questions

1. **Re-entry field.** Does the Claude Code `Stop` payload carry `stop_hook_active` or an equivalent? #3184's probe scripts include it for SubagentStop, but no repository document defines it. Probe before relying on it. A blocking hook without re-entry protection can loop.
2. **Nudge or notice.** `decision: "block"` keeps the turn open and is what makes the nudge visible; it also interrupts. Is a non-blocking stdout notice enough? This changes the user-visible behavior more than any other choice here.
3. **Marker lifetime.** The storage contract is now settled in the Data Model (per-user app data, owner-only, symlink-safe, atomic). What remains open is retention: how long markers live on a machine that runs many sessions, and what prunes them.
4. **Calibration corpus.** Ten transcripts is a number chosen for tractability, not derived. How many sessions does a stable precision estimate actually need?
5. **Subagent sessions.** Sidechain records carry `isSidechain`. Do subagent turns count toward the signal, or only the main thread?

---

## 12. CVA summary

| Varies | Constant |
|---|---|
| Harness (Claude Code, Copilot CLI) | The `Stop` payload names a transcript path |
| Transcript size and session length | Records are newline-delimited JSON with a `type` field |
| Which markers indicate a correction | Human turns must be told apart from tool results before any matching |
| Whether the nudge blocks or notifies | The hook proposes and never persists |

The stable abstraction is **detect, then propose**. Detection is deterministic and cheap; extraction stays inside `reflect` behind human approval. Every option above keeps that seam.

---

## 13. Complexity tier

**Tier 3 (Senior)**. Rationale:

- One new hook module plus registration in two manifests and one generated tree. Bounded.
- Reversible: deleting the registration disables it, which is how the last one was retired.
- No ADR required. ADR-008 already covers lifecycle-hook automation and this adds an event under it rather than changing the architecture. If open question 2 resolves toward blocking-by-default for every session, that is an ADR.
- Raised above Tier 2 by the calibration requirement and by the prior-art trap: the naive version of this module has already shipped once and did nothing for months.

---

## 14. Traceability

| Artifact | Reference |
|---|---|
| Tracking issue | #5817 |
| Requested by | Owner, 2026-09-16, following PR #5803 |
| Replacement path owed by | #5709 step 1 (Stop hook that nudges `reflect`) |
| Prior attempt, rejected | #1757, PR #1761 (closed unmerged) |
| Prior implementation, deleted | PR #908 shipped it, #3184 and PR #3237 removed it |
| Payload contract | `.agents/analysis/claude-code-hooks-opportunity-analysis.md:419-430` |
| Hook contract reference | `.claude/skills/agent-harness-reference/SKILL.md` |
| Skill this serves | `.claude/skills/reflect/SKILL.md` |
| Lifecycle-hook ADR | `.agents/architecture/ADR-008-protocol-automation-lifecycle-hooks.md` |
| Memory tier ADRs | ADR-017, ADR-106 |
