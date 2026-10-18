# ADR Debate Log: ADR-119 Decision 14, Link the .claude/lib Entries into src/claude/lib

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-119-debate-log-5.md` (added by PR #6732)
- **Outcome**: Consensus (1 Accept, 5 Disagree-and-Commit; no P0)
- **Final Status**: proposed
- **Records covered**: ADR-119 decision 14, with its Consequences, Impact, and Reversibility step 7 edits.
- **Panel**: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the delta changes binplace rows, the build's owned paths, and the CODEOWNERS pins on code the completion gate and hooks load.
- **Trigger**: the owner reported that the PR completion gate had several bypasses where verifiers import `.claude/lib` through `abspath(__file__)` beside a link, because `.claude/lib` was a separate byte copy.

## Round 1 Summary

### Key Issues Addressed

- architect (P1): the ADR cited this log before it existed. This file closes it.
- architect (P1): Reversibility step 7 said "two surface-parity install rows"; the diff removes five install surfaces and two guide surfaces. Step 7 now names all seven.
- critic (P1): the "real file blocks the link (exit 2)" claim was wrong for files. Write mode replaces a real file; only a real directory with differing bytes is refused. The ADR now says so, and `test_real_file_at_a_lib_file_link_path_is_replaced_in_write_mode` pins it.
- critic (P1): the rollback for the two file links had no test. `test_dropping_link_true_turns_lib_file_links_back_into_copies` covers it.
- critic, independent-thinker (P1/P2): the ratchet skipped every tracked symlink. `_is_tracked_file_link` now skips a link only when its target is tracked, so a dangling or out-of-tree link still fails loud. A test covers four cases.
- security (P1): `binplace_links.py` checks only top-level plugin entries, so a nested link under `src/claude/lib` would redirect loaded code. `test_plugin_lib_tree_holds_no_symlinks` pins none exist. CODEOWNERS on `/src/claude/lib/` carries the review.
- critic (P2): link targets were compared as text only. The live test now also asserts each link resolves inside `src/claude/lib`, and the `paths.py` root test asserts the resolved path of `.claude/lib/paths.py`.
- independent-thinker, high-level-advisor (P1): `paths.py` now reports `src/claude` as its plugin root, and a Windows checkout without `core.symlinks` fails at import. Both are in the ADR Consequences.
- security, high-level-advisor (P2): the gate transition window had no owner. The ADR names the PR author and ends the override at merge.
- analyst (P2), found at pre-push after the panel: `check_unreachable_code.py` and the pre-push semgrep scan (`git_hook_policy._commit_link_paths`) refused a tracked file link as a non-regular file. Both now skip a link and scan its target; tests cover a tracked target, an untracked target, and the git listing.
- analyst (P2): stale `type_ignore_count_ratchet.py` comment fixed; the ADR Impact lists both ratchets.

### Agent Positions

| Agent | Round 1 |
|-------|---------|
| architect | D&C |
| critic | D&C |
| independent-thinker | D&C |
| security | D&C |
| analyst | Accept |
| high-level-advisor | D&C |

### Dissent

- independent-thinker, high-level-advisor (D&C): a stricter freshness gate on the copies is the cheaper alternative and keeps Windows safe. The ADR already treats the stale second copy as the defect: `build_all.py --check` catches drift after the fact, but a gate that imports the copy beside the diff it verifies has already run the wrong code. Links remove the second copy. The owner set this direction, and the panel reviewed consequences and implementation, not the direction.
- architect (P2), declined: the eight real modules in `.claude/lib` are not in CODEOWNERS. This change does not widen that gap. Flagged for the owner.
- analyst (P2), not changed: `effective_context_ceilings.py` keys and the `git_hook_policy.py` mirror rows still name `.claude/lib`. Both stay harmless under links; the full test suite and `pre_pr.py` pass with them. A later cleanup can drop the dead keys.
- security (P2), existing behavior: write mode replaces a real file at a link path with no byte compare, as it did before this change. The NO-REGEN sentinel is the guard.

### Next Steps

None blocking. After merge, fetch `origin` so the completion gate sees the new links on the trusted ref. Status stays `proposed` until the owner accepts.
