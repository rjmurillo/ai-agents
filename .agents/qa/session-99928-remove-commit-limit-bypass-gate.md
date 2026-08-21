---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99928-b3f7a91c2-remove-commit-limit-bypass-gate.json
qaCommit: 7729226c19ca13a4beb199327430cf24ec227e51
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

## Findings

None outside the two self-corrected items already listed above (the checkout
`fetch-depth` revert, and the `POLICY_SUPPORT_FILES` stale-path fix). No
review round was available before this report (no PR opened yet); this
report documents the author's own verification before push.

## Verdict

PASS. The gate is removed with no surviving reference to `commit-limit-bypass`
outside historical/explanatory prose (docstrings, retrospectives, this
report), the advisory `needs-split`/WARNING/ALERT signal is unchanged, and the
full affected-area test suite is green apart from a pre-existing, unrelated
dirty-tree guard.
