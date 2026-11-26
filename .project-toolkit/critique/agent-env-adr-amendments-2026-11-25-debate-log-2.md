# ADR Debate Log 2: records made false by deleting the agent-* environment jobs

## Summary

- **Rounds**: 4 of 10
- **Outcome**: Consensus in round 4. Critic vote: Accept. Architect vote: Accept.
- **Final Status**: unchanged for every ADR. ADR-057, ADR-071, ADR-083, ADR-088, ADR-101, and ADR-109 keep their status.
- **Prior debate log**: `agent-env-adr-amendments-2026-11-25-debate-log.md` in this directory. It closed by consensus after round 3. This log restarts at round 1.
- **Scope**: dated amendments to ADR-057, ADR-071, ADR-083, ADR-088, and ADR-109, one pointer line in ADR-101, and state notes in `bot-author-feedback-protocol.md` and `claude-workflow-authorization-pattern.md`.
- **Panel**: reduced panel, architect and critic.
- **Why reduced**: every edit records history or corrects a statement the deletion made false. No decision text changes. No executable enforcement and no rule that other gates read changes.
- **Owner decisions, 2026-11-26 (UTC)**: fix the review findings, then re-review. Amend ADR-109 and the authorization pattern doc. Amend four more records (ADR-071, ADR-083, the bot-author protocol, and the ADR-109 real-CLI text). Fix 14 other files outside this directory.
- **Standing owner decisions**: ADR-114 stays unamended. No ratchet baseline may rise, as the first log records.
- **Base**: branch base `f4557cc4f2`. Deletion commit `3f145f26fd` (2026-11-25). The panel read the working tree on head `879dff55b3` (2026-11-25), with the amendments uncommitted. The amendments, the ledgers, and this log are committed together.

Commit `3f145f26fd` deleted every GitHub Actions job gated by an `agent-*` environment. The first debate log covered the ADRs that cited deleted files by path. A later `/review` run found more records that the deletion made false without breaking a citation. This log covers those records.

## Gates before the panel

- **Claims ledgers**: eight files in this directory. `ADR-057-claims-ledger.md`, `ADR-071-claims-ledger.md`, `ADR-083-claims-ledger.md`, `ADR-088-claims-ledger.md`, `ADR-101-claims-ledger.md`, `ADR-109-claims-ledger.md`, `bot-author-feedback-protocol-claims-ledger.md`, and `claude-workflow-authorization-pattern-claims-ledger.md`. Every row with a command ran against the working tree. The owner statement about the latest 100 deployments is NOT RUN, and ADR-057 attributes it to the owner. Two derived sentences, one in the ADR-071 ledger and one in the ADR-083 ledger, have no command of their own. Each follows from rows above it.
- **Documentation accuracy, first run**: Phase 4 as one Sonnet agent over ADR-057, ADR-088, ADR-101, ADR-109, and the pattern doc. 24 claims: 21 MATCH, 2 MISMATCH, 1 UNVERIFIABLE. Both mismatches are the path of this log, which did not exist yet. The unverifiable claim is the owner statement.
- **Documentation accuracy, second run**: Phase 4 as one Sonnet agent over ADR-071, ADR-083, and the bot-author protocol. 26 claims: 21 MATCH, 4 MISMATCH, 1 UNVERIFIABLE. Two mismatches are the path of this log. Two are the word "ran" in ADR-083, changed in round 2 below. The unverifiable claim rests on whether a clone has the local hooks installed.
- **Self-consistency**: VERIFIED with one residual. Each pre-amendment line that names a deleted workflow, an `agent-*` environment, `RUN_CLI_E2E`, `process-prs`, or the nightly job is covered by an amendment. The residual is ADR-083:367, listed under round 3.
- **Refuting seat, first run**: one haiku analyst agent over 36 ledger rows. Result: 0 rows refuted. 17 rows were UNAVAILABLE to the seat because they read git history. The author ran those rows and they hold.
- **Refuting seat, second run**: one haiku analyst agent over 47 rows. Result: 35 consistent, 11 UNAVAILABLE to the seat, 1 refuted. The refuted row is in the bot-author ledger. Its grep for `run: python3` missed three script calls in `pr-maintenance.yml`. The row was rewritten to list all seven python calls. The author ran the 11 unavailable rows and they hold.
- **Rows added later**: rows written after round 2 did not go to a refuting seat. The architect re-ran them in round 3. Both seats re-ran, in round 4, the four rows added after the round 3 Block.

## Round 1

Reviewed ADR-057, ADR-088, ADR-101, ADR-109, and the pattern doc. Critic verdict: REVISE. Architect verdict: ACCEPT-WITH-CHANGES. No P0. All P1 items were applied.

### Accepted

- ADR-088 now ties the loss to its own criterion. That criterion asks for an owner, a cadence, persisted run state, and a CI or scheduled invocation. The owner and the manual cadence remain. The scheduled invocation and the shared state are gone.
- ADR-088 no longer softens the loss. A model or CLI change with no repository change prompts no run. The rollback streak now lives in a local state file.
- ADR-088 absence claims now match the search scope. They say no GitHub Actions job runs the eval, because the ledger searched `.github`.
- ADR-109 counted six prompt files with no reader. The panel found a seventh, `post-pr-retrospective.md`. Only `scripts/ci/build_retrospective_prompt.py` reads it, and only a deleted workflow ran that script.
- ADR-109:73 said execution stays with the environment-gated hook smoke. That job is deleted. The amendment says so, and its heading now reads "effects of deleting the agent-environment jobs".
- An ADR-057 amendment sentence said "went with them" with no antecedent. It was reworded.
- ADR-057 now names the decision-maker and cites both debate logs.
- The ADR-057 ledger gained rows that link the ungated `publish-stats` job to the gated `update-stats` job.

### Not changed

- ADR-101 gets no pointer line to this log. The file sits at the 500-line cap. Line 478 points to "ADR-057, amendment of 2026-11-25", and that amendment cites this log. This is a deferred P1 with that justification.
- The critic listed more records the deletion made false: ADR-071, ADR-083, and the bot-author protocol. The owner approved amending them. They entered the panel in round 2.

## Round 2

Reviewed eight records after the owner widened the scope. Critic verdict: ACCEPT-WITH-CHANGES. Architect verdict: ACCEPT-WITH-CHANGES. No P0. All P1 items were applied.

### Accepted

- "Ran" became "was defined to run" in ADR-071:639 and ADR-083 Decision item 4 and its Impact row. No ledger row shows a completed Copilot leg. The `smoke` job carried an `agent-*` environment from commit `9b40ac9572` (2026-10-08).
- ADR-071:641 lists more superseded passages: the Negative consequences about the nightly smoke, the Delivered follow-ups paragraph, the exit-trigger detection, and one References entry.
- ADR-071:642 narrows "no executed-hook check" to the real-CLI cases.
- ADR-071:643 records that Renovate automerges a Copilot pin bump, and that no job installs the new version first.
- ADR-109 names an eighth prompt file with no reader, `default-ai-review.md`. `scripts/ci/load_ai_review_prompt.py` reads it. Only the `ai-review` composite action runs that script, and no workflow uses the action now.
- ADR-109:342 states what the pre-push `hook-anchoring-e2e` job selects and when it fails the push.
- The bot-author state note now covers the `pull_requests:write` prerequisite, the acknowledgment baseline, and the zero-actions alert.

## Round 3

Convergence vote on the round 2 changes. Architect vote: Accept. Critic vote: Block.

### The Block

ADR-071:642 said `installed-plugin-hook-guard.yml` "still executes the shipped hook scripts on pull requests". That was false. The guard installs only `src/copilot-cli`. That tree's `hooks/hooks.json` registers no hook event. The guard passes with nothing to execute.

The author wrote the sentence in round 2. Its ledger row was marked VERIFIED, but the command printed workflow lines. It showed a definition, not a behavior. The architect had suggested the claim in round 2 and withdrew it in round 4.

### Accepted

- ADR-071:642 now says the guard runs on pull requests, installs only `src/copilot-cli`, and has no registered hook to execute.
- ADR-071:639 said the Claude plugin-load cases "run only there". Both seats flagged it. It now adds "only when `claude` is on PATH", and notes the job also runs with `codex` alone.
- The false ledger row was replaced by four rows. They show the workflow trigger and install source, the empty hook registry, the binary check in `git_hook_policy.py`, and the skip condition in `test_plugin_load_smoke.py`.

### Not changed

- ADR-083:367 keeps a present-tense Positive consequence about the deleted job. The file sits at the 500-line cap. The 2026-11-25 amendment in the same record states that no workflow defines the job.
- ADR-088 says the deleted workflow "ran" its eval, "kept" the streak, and "opened or updated" the alert. Those words rest on the workflow definition. No run log was read. The workflow carried no environment from `cd4451f6b8` (2026-07-29) until `739e9e9bd9` (2026-09-15) set `bot-secrets`. `013eaaa809` (2026-10-07) set `agent-approval`, and `b8b984ea29` (2026-10-07) renamed it `agent-claude`. Whether `bot-secrets` required a reviewer is unknown.
- ADR-109:336 leaves one choice to the owner: delete the eight prompt files and the `ai-review` action, or wire them again.
- ADR-071 lines 822 to 824 cite paths that `9b40ac9572` deleted on 2026-10-08. That predates this change. The coverage list at ADR-071:641 names the References entry.
- ADR-025:109 lists a deleted workflow in a dated inventory. It is outside the owner-approved file set.
- Two inferences have no ledger row: "the first exit now means restoring one" in ADR-083, and "has no monitor" in ADR-088. Both follow from VERIFIED absence rows.
- One ADR-057 ledger row reports a count of 3 that includes a comment line. Lines 39 and 46 of the workflow carry the claim.

## Round 4

Re-vote on the two changed ADR-071 sentences and the four new ledger rows. Critic vote: Accept. Architect vote: Accept. No P0 or P1 remains open, apart from the ADR-101 pointer deferred in round 1.

Both seats re-ran the four rows and compared the diffs. Only the two ADR-071 lines moved since round 3.

### Not changed

- The architect asked which date this log uses for commits. It uses commit dates, as the ledgers do. `cd4451f6b8` has author date 2026-07-28 and commit date 2026-07-29.
- The architect inferred that the guard's e2e tests may skip in CI. They look for the install under the home directory, and the workflow writes it elsewhere. No run log was read. This is outside the change and is recorded for the owner.
- The critic noted that the generated index `README.md` was not a panel artifact. Its changed rows are the date cells of the five ADRs with a new frontmatter date.

## Method note

- **Dates**: frontmatter `date` is 2026-11-26 on ADR-057, ADR-071, ADR-083, ADR-088, and ADR-109, the day of their last edit. ADR-101 keeps 2026-11-25, the day of its edit. Amendment headings and body text use the event date, 2026-11-25.
- **One premise, one place**: the owner's reason for the deletion is stated once, in ADR-057. Other records point to "ADR-057, amendment of 2026-11-25".
- **Size caps**: ADR-071 stays at 850 lines, and ADR-083 and ADR-101 stay at 500. To add text at zero net lines, two historical bullets in ADR-071 were joined, and one 2026-10-08 paragraph in ADR-083 was joined. Their words did not change. ADR-109 is 390 lines.
- **Same-day ordering**: commit `be56d5276c` made the smoke job dispatch-only at 10:30 on 2026-11-25. `3f145f26fd` deleted it at 12:52 the same day. The records use "until 2026-11-25" for both.
- **Ratchets**: `check_adr_lifecycle.py` reports 153 violations across 127 records, none outside the baseline, with the amendments applied. No baseline changed.
- **ADR-114**: it sets the approval policy that created the `agent-*` environments. It is not edited, by owner decision.

## Post-review correction

After round 4, the `doc_accuracy.py` same-PR gate ran on the committed branch at `47196b8704` (2026-11-26). It returned FAIL with two findings on lines this change wrote. Both are wording, not fact.

- ADR-071:642 named a constant from `scripts/validation/cli_smoke_paths.py` in backticks beside one path that the constant holds. The gate read the sentence as a partial list of that constant. The sentence now says "the hook e2e globs" and keeps the file path. The claim did not change. The two ADR-071 ledger rows that show the constant still hold.
- Round 1 of this log gave a record count before its list. The gate counted the list differently, because one listed item is not an ADR id. The sentence now lists the records with no count.

No ADR line count changed. ADR-071 stays at 850 lines.

Both seats read the wording diff. Architect vote: Accept. Critic vote: Accept. Neither seat raised a P0 or a P1.

### Not changed

- The critic judged the first gate finding a false positive. The sentence cites `tests/e2e/test_cli_hook_e2e.py` as the test target, not as a list of the globs. The reword stays, because the gate has no way to suppress one finding.
- The critic noted that the ADR no longer gives a direct search hit for the constant name. The ADR-071 ledger keeps that anchor.
