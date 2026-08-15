# Merging Main Into a Docs-Only Branch Forfeits the Retrospective Bypass

**Category**: Git Operations
**Source**: 2026-08-06, branch `docs/memory-squash-severs-stack`, PR #4726. Measured on `git_hook_policy.py` at `8244012bd`, lefthook v2.1.10.

Symptom this explains: a branch that pushed cleanly ten minutes ago is refused
with `ERROR: git push requires retrospective evidence for this session`, and the
only thing that changed since the good push was `git merge origin/main`.

## Statement

The pre-push retrospective gate has a documentation-only bypass. It tests
**every path in the push**, not the paths you authored:

```python
def _documentation_only(paths):
    return bool(paths) and all(
        any(p.search(path) for p in DOCUMENTATION_PATTERNS) for path in paths
    )
```

`DOCUMENTATION_PATTERNS` is seven entries: `\.md$`, `\.txt$`, `(^|/)README$`,
`(^|/)LICENSE$`, `(^|/)CHANGELOG$`, `\.gitignore$`, `\.editorconfig$`. Nothing
else qualifies. The anchors are load bearing: `src/MY_README` and `README.old`
both fail the bypass, so a repository that keeps prose in unsuffixed files does
not get it.

`all()` over the push set means one non-documentation path forfeits the bypass
for the whole push. Merging `origin/main` into a docs branch drags every path
main touched since the fork into that set: `.py`, `.yml`, `.json`, fixtures.
The bypass that held on the previous push cannot hold on this one, and the
merge is what removed it.

## The cost is paid before you are told

The pre-push jobs sit in a `parallel: true` group (`lefthook.yml`, the group
containing `retrospective-policy`). `retrospective-policy` is declared *before*
`python-tests` and decides in **0.29 seconds**. Lefthook still runs the group to
completion, so the doomed push cost the full slowest job:

| job | seconds |
|---|---|
| `retrospective-policy` (the refusal) | 0.29 |
| `pre-pr-validation` | 77.49 |
| `python-tests` | 743.77 |

About 12 minutes spent on a push decided by a merge you made beforehand. Reading
the declaration order and concluding the cheap gate runs last is the wrong
lesson; it is declared first. Parallel-group completion is the mechanism.

## What to do instead

GitHub reports `mergeable_state: behind` when main has moved. That is the state
that tempts the local merge. Take it server side:

```bash
gh pr update-branch
```

This merges main into the head branch on GitHub. No local push, so no pre-push
hook run, so no forfeited bypass and no 12 minute bill. It is not a hook bypass:
nothing local is being skipped, because nothing local is being pushed.

If you have already merged and not yet committed anything on top, drop the merge
commit and let the remote stay where it is:

```bash
# Refuse on a dirty tree: --hard discards uncommitted work.
BRANCH="$(git branch --show-current)"
test -n "$BRANCH" \
  && test -z "$(git status --porcelain)" \
  && git rev-parse --verify -q HEAD^2 >/dev/null \
  && git reset --hard HEAD^1 \
  && git push origin "$BRANCH"
```

Reset to the merge's first parent, not to `origin/$BRANCH`. The remote ref also
discards any authored commits you had not pushed *before* the merge, which the
"nothing committed on top" precondition does not exclude. `HEAD^1` drops the
merge commit and nothing else.

Confirm before resetting that the merge commit is the tip and that it authored
nothing by comparing its tree to Git's automatic merge tree:

```bash
git rev-parse --verify -q HEAD^2 >/dev/null
automatic_tree="$(git merge-tree --write-tree HEAD^1 HEAD^2)"
actual_tree="$(git rev-parse HEAD^{tree})"
test "$actual_tree" = "$automatic_tree" \
  || { echo "merge commit differs from automatic merge tree"; exit 1; }
```

Do not use `git diff --name-only HEAD^1 HEAD` for this proof. A manual conflict
resolution or extra staged edit can replace a blob while leaving the same path
in the name list. Name-set equality proves which paths changed, not what their
contents became.

## The other three bypasses, and why they do not save you

`check_retrospective_evidence` returns 0 early for four reasons. Know which one
you are relying on:

1. **Documentation-only push.** The one this memory is about.
2. **Trivial session.** Requires `len(paths) == 1` and a session log created
   inside `TRIVIAL_SESSION_SECONDS`. A merge push is never one path.
3. **`_today_retrospective_exists`.** Globs the **working tree**
   `.agents/retrospective/` for today's and yesterday's prefixes. It reads the
   checked-out tree, so a retrospective that exists on a *different branch* is
   invisible. The prefixes come from `_recent_date_prefixes`, which is **UTC**:
   at 2026-08-06 evening PDT, UTC is already 2026-08-07, so a file dated
   `2026-08-06` counts as yesterday and still passes.
4. **Retrospective evidence in the session log for the current branch.**
   `_session_log_for_current_branch` matches on branch, so a log naming another
   branch does not count.

## Do not

Do not set `SKIP_RETROSPECTIVE_GATE=true`. No rule file names this variable:
`.claude/rules/universal.md` MUST NOT item 2 enumerates six mechanisms
(`--no-verify`, `LEFTHOOK=0`, `LEFTHOOK_BIN`, a lefthook config override, a
direct hook edit, `LEFTHOOK_EXCLUDE`) and `SKIP_RETROSPECTIVE_GATE` is not among
them. What binds is that item's stated principle, that "no repository document
describes any of them as a supported skip", plus the gate's own behavior: it
prints the variable name in its refusal path, which reads as an invitation. It
is not one. The same gap applies to `SKIP_SCOPE_CHECK`, also named in no rule.
Treat a `SKIP_*` variable you found by reading a validator as undocumented, not
as sanctioned.

Do not re-run the push hoping the refusal was transient. The path set is a
deterministic property of the push range.

Do not merge main into a docs branch just because GitHub says `behind`. Here
it does not block: `main` carries a **ruleset** with
`strict_required_status_checks_policy: false` (measured 2026-08-14; reverted 2026-08-10), so an out-of-date head can still
merge. Use `gh pr update-branch` only if a status check itself requires fresh
content (e.g. count ratchets comparing against the current baseline).
Do not read a 404 from `gh api repos/{owner}/{repo}/branches/main/protection` as
"main is unprotected". This repository governs `main` with rulesets, not classic
branch protection, and the classic endpoint 404s regardless. Ask
`gh api repos/{owner}/{repo}/rules/branches/main` instead, which returns
`code_quality`, `copilot_code_review`, `deletion`, `non_fast_forward`,
`pull_request`, `required_linear_history`, and `required_status_checks`.

## Related

- `git-rebase-after-push-costs-two-cycles.md`. The same 12 minute bill from the
  other direction: a doomed push that git had already classified as rejected.
- `git-a-squash-merge-severs-a-stacked-pr.md`. Why a stacked branch ends up
  wanting a main merge in the first place.
