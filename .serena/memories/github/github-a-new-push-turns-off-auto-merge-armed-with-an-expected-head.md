# A new push turns off auto-merge that was armed with an expected head SHA

## Statement

Auto-merge armed through `merge_pr.py --auto --expected-head-sha <sha>` pins one head. A new commit on the PR branch moves the head, and GitHub turns auto-merge off. After every push to an armed PR, read `auto_merge` from the PR state. If it is false, re-arm with `merge_pr.py --strategy squash --auto --expected-head-sha <new head>`.

## Evidence

- OBSERVED 2026-10-24: PR #6899 had auto-merge armed with `--expected-head-sha 7b25903d3f`. After a push to `260042f462`, `get_pr_context.py` reported `auto_merge` false. Re-arming was needed.
- OBSERVED: PR #6899 later merged as `08cdb54477`.
- Related: `github-dismissed-reviews-block-automerge.md` covers a different cause of a stalled auto-merge.
