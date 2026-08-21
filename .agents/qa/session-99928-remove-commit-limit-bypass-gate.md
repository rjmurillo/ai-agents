---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99928-b3f7a91c2-remove-commit-limit-bypass-gate.json
qaCommit: 5e0b0d26bdfeb848d76cb147138c8986f4be1963
---
# QA Report: session 99928, remove commit-limit-bypass gate

## Scope

Content changes through commit `7729226c19ca`, across 14 commits on
`claude/commit-limit-bypass-8f2rur`. Commits 11-14 correct a citation error
found after the first push attempt: ADR-099 and several implementation files
cited "#5230" as the tracking issue, which turned out to be an unrelated
draft PR opened by a different session the same day (hitting the identical
gh-403 wall this ADR describes). Filed the real tracking issue (#5233) and
the root-cause issue for the org-level gh/API gap (#5232), then corrected
every "#5230" reference to "#5233".

1. `scripts/validation/pr_commit_count.py`: dropped `BLOCK_THRESHOLD`,
   `MAIN_MERGE_BLOCK_THRESHOLD`, and all main-merge-relief plumbing
   (`main_first_parent_shas`, `contains_main_merge`, `ReliefEvidence`,
   `main_merge_evidence`); `classify_count` returns only OK/WARNING/ALERT.
2. `scripts/validation/git_hook_policy.py`: `_check_commit_limit` is now
   advisory-only; deleted `_check_needs_split_bypass`,
   `_contains_main_merge`, `_merge_has_main_parent`,
   `_unpushed_commit_count`, `_new_commits_for_branch`, and the human-only
   bypass-label message.
3. `scripts/validation/check_pr_bypass_label.py`: deleted (only caller was
   the removed commit-limit-bypass check).
4. `scripts/ci/enforce_pr_validation.py`: dropped `BYPASS_LABEL`,
   `_fetch_labels`, and the `COMMIT_STATUS == "BLOCKED"` branch.
5. `.github/workflows/pr-validation.yml`: `Enforce Blocking Issues` no
   longer receives `COMMIT_STATUS`/`COMMIT_COUNT`/`COMMIT_LIMIT`; the
   needs-split label steps drop the `BLOCKED` condition.
6. Tests: rewrote `tests/validation/test_pr_commit_count.py` (74 tests),
   removed 31 dead functions/helpers from `tests/test_lefthook_integration.py`,
   narrowed `tests/validation/test_human_only_label_guidance.py` to the
   surviving `description-validation-bypass` label, deleted
   `tests/test_check_pr_bypass_label.py` and
   `tests/validation/test_commit_limit_parity.py`, updated
   `tests/ci/test_pr_validation_workflow.py` and
   `tests/workflows/test_pr_validation_needs_split.py`.
7. Docs: `CONTRIBUTING.md`, `AGENTS.md`, `.agents/governance/GOTCHAS.md`,
   `gate-ladder.md` (both copies), the critic agent prompt (template plus
   5 hand-maintained/generated copies), the `ai-agents-change-control`
   `SKILL.md` (both copies).
8. `.agents/architecture/ADR-099-remove-commit-limit-bypass-gate.md` and
   its debate log at `.agents/critique/ADR-099-debate-log.md`.

Not implemented here (recorded as a separate, complementary action in
ADR-099's Alternatives table, owner decision, not a code change): connecting
the Claude GitHub App for this organization so `gh`/API calls stop being
denied in Claude Code cloud sessions. That is unrelated infrastructure, not
part of this gate removal.

## Validation

| Check | Result |
|-------|--------|
| Root cause reproduced live, in this session | `gh auth status` failed (invalid `GH_TOKEN`); `gh api rate_limit` succeeded; `gh api repos/rjmurillo/ai-agents/pulls/5209` returned `403 GitHub access is not enabled for this session`; the GitHub MCP tool `pull_request_read` succeeded for the same PR in the same session. Confirms the block's local verification step is structurally, not transiently, unsatisfiable in this harness class. |
| `tests/validation/test_pr_commit_count.py` | `uv run --frozen pytest tests/validation/test_pr_commit_count.py -q`: 74 passed, including a negative control (`test_classify_count_has_no_block_status_at_any_size`) and an import-absence control (`test_the_block_and_relief_machinery_is_not_importable`) for the removed names. |
| `tests/test_lefthook_integration.py` | `uv run --frozen pytest tests/test_lefthook_integration.py -q`: 839 passed, 1 skipped, after an AST-based prune of 31 dead functions/helpers plus a manual fix (`POLICY_SUPPORT_FILES` still listed the deleted `check_pr_bypass_label.py`, which would have made the real-lefthook end-to-end fixture copy fail with a missing source file). |
| `tests/ci/test_pr_validation_workflow.py`, `tests/workflows/test_pr_validation_needs_split.py` | 46 + 16 passed after deleting/rewriting the classes that pinned the removed `BLOCKED`/bypass-label behavior. |
| `tests/validation/test_human_only_label_guidance.py` | 4 passed after narrowing to the surviving `description-validation-bypass` label. |
| Full affected-area suite | `uv run --frozen pytest tests/validation/ tests/ci/ tests/workflows/ tests/test_lefthook_integration.py -q`: 6848 passed, 20 skipped, 8 failed. All 8 failures are `tests/ci/test_mutation_harness_ciperms.py` refusing to run against an uncommitted working tree ("mutation target has uncommitted changes... Commit or stash it before running the harness"), a generic pre-existing guard unrelated to this change's content; confirmed by reading the error text and `git status` at the time. |
| Self-caught regression | First pass removed `fetch-depth: 0` from the `Checkout repository` step, reasoning only the commit-count gate needed it. `tests/ci/test_pr_validation_workflow.py::test_merge_tree_host_checkouts_fetch_full_history` and the `TestTheCommitCountGateCanReadMainsTrunk` class (further down the same file, not yet run at that point) would have caught this once executed; caught it first by reading further in the same test file and finding the merge-tree ratchet and count ratchets, later in the same job, also depend on unshallow history. Reverted with a corrected comment naming the real dependency. |
| `uv run --frozen ruff check` | Clean on every edited source and test file (`scripts/ci/enforce_pr_validation.py`, `scripts/validation/pr_commit_count.py`, `scripts/validation/git_hook_policy.py`, `scripts/ci/update_needs_split_label.py`, `scripts/validation/pr_description.py`, plus the 5 edited test files). |
| Mirrors regenerated, not hand-edited | `build/scripts/build_all.py --platform copilot-cli` for the `gate-ladder.md` and `SKILL.md` copies; `build/generate_agents.py` for the critic agent copies; `diff` confirmed byte-identical afterward in both cases. |
| First push attempt | Failed: the pre-push hook's `python-tests` job ran the full suite while I was still committing follow-up fixes, and `tests/ci/test_mutation_harness_ciperms.py` correctly refused to run against a working tree that changed mid-run. Not a defect in this change; resolved by not committing again until the tree was static, then retrying. |
| Second push attempt | Failed: `Session End Validation` correctly flagged the QA report as stale (ADR-096 `post_qa_code_changes`) after 4 more real-code commits landed (the citation fix) past the report's original binding. Resolved by rebinding this report and the session log to the new HEAD, which is what this revision of the report records. |
| `uv run --frozen python scripts/validation/pre_pr.py` | First run: 55 of 57 passed. `Session End Validation` failed on `qaValidation` having no bound report, resolved by adding this report and rebinding the session log. `Skill Markdown Portability` failed because removing the `pr_commit_count.py:58`/`:64` line citations from `gate-ladder.md` (both copies) genuinely lowered the vendor-portability marker's suppressed-ref count from 8 to 7, which the ratchet reports as drift until the baseline is tightened to match; ran `check_skill_md_portability.py --update-baseline --allow-baseline-shrink`, then reran the checker clean (`No Markdown vendor-portability drift. 238 grandfathered refs across 93 files (baseline 238)`). |
| Agent-Skill Discriminator Check (PR CI, post-push) | Failed: `critic` (touched only to drop stale gate references) scores 2/3 as a pre-existing skill-shape candidate whenever any of its files change, orthogonal to this PR's scope. Not a regression this change introduced. Resolved by adding the tool's own `[skill-discriminator: ...]` PR-description override token rather than scope-creeping into an unrelated agent-to-skill refactor. |
| Spec-to-Implementation Validation (PR CI, post-push, 3 rounds) | Round 1: FAILed on two real, confirmed gaps missed in the original sweep: (1) `tests/workflows/test_pr_validation_needs_split.py:3-5` docstring still described a 20-commit BLOCK tier as "enforced separately"; (2) both `ai-agents-change-control/SKILL.md` copies still listed "Commit count under 20" as a pre-push checklist item. Both fixed in commit `60b37660816e8bf9a0ebaf8ead08d4d96e8e7b59`; the `SKILL.md` mirror was regenerated via `build_all.py --platform copilot-cli`, confirmed byte-identical to the `.claude/` source, not hand-edited. Round 2 (re-ran against the still-old head_sha before the push landed, so it repeated round 1's finding) additionally caught a third real gap: ADR-099 lines 155-157 and 180 still claimed the CI checkout's `fetch-depth: 0` was removed/should be dropped, but it was restored during implementation (the merge-tree ratchet and count ratchets in the same job depend on it independently of the commit-count gate). Fixed in commit `7115df3d1c6b72c2ed50a181240b507206cef9d8` with a debate-log addendum. The bot's remaining point across all rounds (the 8 dirty-tree-guard failures in `test_mutation_harness_ciperms.py`) is addressed below, unchanged from the original verdict: the guard checks only the specific files each mutation targets against `git status`, not the whole tree, and none of those targets were among this session's uncommitted files at measurement time. |
| GitHub Copilot automated review (PR CI, post-push) | Three findings, all real. (1) `_check_commit_limit`'s two failure branches returned `2` despite the docstring claiming "never blocks", which `_check_push_updates` aggregates into a blocking exit; fixed by returning `0` with a `WARNING` print on both branches, new parametrized tests added (`73d601bb2`). (2) A dependency sweep found 6 skill/doc files (`provenance.md`, `ai-agents-debugging-playbook/SKILL.md`, `ai-agents-diagnostics-toolkit/SKILL.md` + `instrument-guides.md`, `ai-agents-failure-archaeology/references/incidents.md`, `software-engineering-library/references/refactoring.md`) still describing the removed 20/40-commit cap as live; corrected all 6, mirrors regenerated and byte-verified (`071e9b313`, `1d5fe69fc`, `daef97f0c`). Also corrected two script docstrings (`enforce_pr_validation.py`, `pr_commit_count.py`) that misattributed the CI-side gate's own removal to the same session-sandboxing failure that motivated the local pre-push gate's removal; the CI step runs under a working `GH_TOKEN` and never had that failure (`a77048f92`). (3) The mandatory six-role `adr-review` panel was not run on ADR-099 despite `AGENTS.md`'s unconditional trigger; run for real (`0cbe80154`), see below. |
| Real `adr-review` six-role panel (architect, critic, independent-thinker, security, analyst, high-level-advisor) | Ran per `.claude/skills/adr-review/`'s Phase 0-4 protocol against ADR-099. Converged on: (a) ADR-100 and ADR-101 already exist on `origin/main` (`status: proposed`) and decide the identical retirement over a 292-PR measured population, uncited; cross-referenced, and ADR-100's telemetry/re-measure conditions adopted via a new "Confirmation and Reversal Triggers" section since this ADR's own implementation shipped without either; (b) Context asserted a false premise ("an agent could not apply it to its own PR"), contradicted by `git_hook_policy.py`'s own comment recording an agent self-applying the label to PR #4735 (issue #4782); corrected. No panel role returned Block. Debate log at `.agents/critique/ADR-099-debate-log.md` relabels the original single-author pass as "simulated pre-panel perspectives" (kept, not deleted) and appends the real panel's findings (`0cbe80154`, `578bc3b24`). Two follow-up issues filed per the panel's gap finding: #5238 (90-day re-measure) and #5239 (push-ceiling telemetry, ADR-100 Decision item 6). |
| 3 stale Serena memories | `diagnosing-a-blocked-pr.md` and `git-a-squash-merge-severs-a-stacked-pr.md` presented the removed block/label as still-live; `pr-review-observations.md` listed the label workflow as a standing preference. All three annotated as superseded (not deleted), per `.claude/rules/curating-memories.md` (`1a24873de`). |
| `git merge origin/main` (13 commits behind by the time all corrections landed) | Real conflict in `AGENTS.md`: this branch's Mid-gate line (advisory-only wording) and main's Start/End-gate lines (session-log-creation discontinued, unrelated commit `746e2c36a`) sat in the same 3-line hunk without overlapping content. Verified via `git merge-tree` before merging, resolved by keeping both non-overlapping edits, verified no other files conflicted (`scripts/validation/git_hook_policy.py` and `tests/test_lefthook_integration.py` auto-merged cleanly) (`df86736a4`). |
| Full suite, clean tree, no `-x` (post-merge) | First attempt (`baz4rm41x`) failed 1 test: `tests/mutation/test_mutate_debate_log_path.py::test_m1_directory_name_reverted_is_detected` raised `MutationWorkspaceError: active mutation targets changed during isolated run: scripts/validation/git_hook_policy.py [MODIFIED]`, because the merge above ran concurrently with that background suite and auto-merged that exact file mid-run. Self-inflicted, not a real bug: confirmed by re-running the isolated test alone on the now-static, merged tree (`ben0zq34m`: 11 passed in 200.33s), then re-running the entire suite fresh with no concurrent git operations (`ba6rbw0im`): **27714 passed, 74 skipped, 0 failed, 1318.13s**. |
| `uv run --frozen python scripts/validation/pre_pr.py` (post-merge, `bvw2j6ybq`) | 55 of 57 passed. `Session End Validation` failed only because the QA report (this file) was bound to a pre-merge commit; resolved by this rebind. `Skill Markdown Portability` failed because `provenance.md`'s fix genuinely dropped its suppressed-ref count from 29 to 28 (an unrelated upstream merge also improved `ai-agents-docs-of-record` from 26 to 25); ran `check_skill_md_portability.py --update-baseline --allow-baseline-shrink`, reran clean (`5e0b0d26b`). |

## Findings

None outside the self-corrected items already listed above. Every review pass
available before merge (the discriminator check, three spec-validator rounds,
the Copilot automated review, the real `adr-review` panel it triggered, and
this report) surfaced real, actionable gaps, and all were resolved
same-session rather than deferred. Two items are explicitly deferred to
tracked follow-ups rather than resolved here, per the panel's own finding that
they are conditions ADR-100 states for its (broader, still-proposed)
retirement rather than requirements ADR-099 itself was authorized against:
push-ceiling telemetry (issue #5239) and a 90-day re-measure (issue #5238).

## Verdict

PASS. The gate is removed with no surviving reference to `commit-limit-bypass`
outside historical/explanatory prose (docstrings, retrospectives, superseded
memory entries, this report), the advisory `needs-split`/WARNING/ALERT signal
is unchanged, ADR-099 has been through a real six-role `adr-review` panel with
its findings corrected in the same change, and both the full test suite
(27714 passed, 0 failed) and `pre_pr.py` (57 of 57 after the baseline update
above) are green on the current, merged HEAD.
