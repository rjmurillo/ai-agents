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
- The critic noted that this section did not record a clean re-run. The gate ran again on 2026-11-26 with both edits committed. It returned PASS with no same-PR finding.

## Merge resolution, 2026-11-26

Pull request #7629 (`4d459a2206`, 2026-11-26) added a second ADR-057 amendment with the heading date 2026-11-25: "ADR-127 decision 9". Its debate log is `ADR-057-debate-log-2.md`. Pull request #7691 (`67899d52d4`, 2026-11-25) flipped ADR-088 to `implemented: true`. Both reached `main` before this branch did. Merging that content conflicted in ADR-057, ADR-088, and the ADR-057 claims ledger. The author resolved the conflicts by hand against `6c0a0fc5db` (2026-11-26), a local merge of `main` (`4d104e9a8f`, 2026-11-26) into the pull request #7630 head `f4557cc4f2` (2026-11-25). That merge commit was never pushed. Squash commit `dff887317c` (2026-11-26) on `main` holds the same tree.

- **ADR-088**: exact union. It keeps the frontmatter from `main` and this branch's amendment section. One pointer changed: line 270 now names "the `/spec` CI leg amendment" of ADR-057, because two ADR-057 amendments share that date. The file stays at 311 lines.
- **ADR-057, order**: the ADR-127 amendment comes first, at lines 310 to 404. Lines 1 to 405 keep the numbering on `main`, so the line cites in that amendment's ledger still hold. This branch's amendment follows at lines 406 to 412.
- **ADR-057, merged lines**: lines 92, 135, 137, 218, 239, 257, and 267 carry both sides' edits, merged word by word. Lines 269, 281, 282, 300, and 308 carry this branch's edits only.
- **ADR-057 line 432**: the CI workflows row states both facts. The `/spec` leg ran until 2026-11-25 and no CI leg runs evals now. `Validate PR` runs the deterministic ADR-127 evidence check.
- **ADR-057 lines 239 and 410, narrowed**: this branch said no CI job invokes the gates in `eval-prompt-change.py`. The ADR-127 amendment says its check calls the runner's `acceptance_gate` and calls no model. The two statements contradicted each other. Both lines now say that no CI job runs the eval, and that the evidence check calls `acceptance_gate` on committed results.
- **Ledger**: the ledger from `main` comes first, byte for byte. This branch's ledger follows. Its H1 became the H2 "Amendment 2026-11-25: the /spec CI leg is deleted". A "Fourth pass" table holds the rows for the narrowed lines.
- **Size**: ADR-057 is 448 lines. `check_adr_lifecycle.py` reports no violation outside the baseline. No baseline changed.

Both seats read the staged resolution and both diffs. Architect vote: Accept. Critic vote: Block, then Disagree-and-Commit after one ledger fix. Neither seat raised a P0.

### The Block

The critic's P1: the Fourth pass intro said `main` (`dff887317c`) was merged, while the merge resolved against `6c0a0fc5db`. The intro now names `6c0a0fc5db` and states the tree identity. A new ledger row runs `git diff --quiet 6c0a0fc5db dff887317c`. The critic's dissent on the re-vote: a draft of that intro named the merge commit's second parent before the commit existed, and credited the ADR-127 amendment to pull request #7630. The intro now names #7629 and makes no claim about the parent.

### Not changed

- "Amendment 2026-11-25" now matches two headings in ADR-057. Both seats judged lines 89, 239, 257, 277, 418, and 440 clear. Lines 135, 137, 218, 267, 281, and 433 resolve by context only. Lines 1 to 405 stay as merged, so the line numbers that the other ledger cites do not move.
- ADR-057:282 lists the `/spec` leg and contributors as users of the acceptance gate. The ADR-127 check also calls it. Lines 239 and 410 say so.
- ADR-088:218 describes the weekly gate in the present tense. Both sides carried it. The amendment in the same record covers it.
- Three line cites in the ledger from `main` are stale on `main` itself. They are outside this merge.

## Pointer clarification, 2026-11-27

After the merge, ADR-057 holds two amendments with the heading date 2026-11-25. Line 310 is the ADR-127 decision 9 amendment from `main`. Line 406 is this branch's `/spec` CI leg amendment, which holds the owner's reason for the deletion. A pointer that said "ADR-057, amendment of 2026-11-25" or "amendment of that date" matched both headings.

Each pointer now names the `/spec` CI leg amendment. The sites:

- ADR-071:637, ADR-083:131, ADR-083:477 to 478, ADR-101:478, and ADR-109:328.
- `claude-workflow-authorization-pattern.md`:7.
- `.agents/governance/FAIL-OPEN-INVENTORY.md`:370, `CONTRIBUTING.md`:468, and `gate-ladder.md`:16 in the `ai-agents-change-control` skill references.
- ADR-088:269 to 273, changed in the merge resolution above.

No decision text changed. No line count changed: ADR-071 stays at 850 lines, ADR-083 and ADR-101 at 500, ADR-109 at 390, and ADR-088 at 311. The quotes of the old wording earlier in this log are dated history and stay.

Both seats read the wording diff and the ADR-088 change. Architect vote: Accept. Critic vote: Accept. Neither seat raised a P0 or a P1.

### P2, not changed

- ADR-127:248 and `scripts/validation/checks_ci_parity.py`:348 cite "ADR-057 Amendment 2026-11-25" by date only. Both came from `main`, and the text around each names the deterministic check.
- ADR-114:132 and REQ-047:64 still describe the earlier approval and smoke contracts. Both records are outside this change by owner decision.

## Evidence correction, 2026-11-27

The ledger's Fourth pass called `6c0a0fc5db` the last tip of the pull request #7630 branch. That was wrong. `git ls-remote origin refs/pull/7630/head` prints `f4557cc4f2`. `6c0a0fc5db` is a local merge of `main` into that head, and it was never pushed. The merge commit `715828e46f` (2026-11-26) repeats the wrong phrase in its message. The message stays, because the branch history is not rewritten.

The ledger intro and the Merge resolution section above now say what `6c0a0fc5db` is. A new ledger row checks the tree identity from pushed commits only: `git merge-tree --write-tree f4557cc4f2 4d104e9a8f` and `git rev-parse dff887317c^{tree}` both print `984f58ed058c`. No ADR text changed. The seats did not re-vote on this correction, because it changes no record they reviewed.
