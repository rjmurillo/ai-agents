# rev-list --not --all cannot see another worktree's local refs

`refs/worktree/`, `refs/bisect/`, and `refs/rewritten/` are per-worktree ref
namespaces. Git stores them under the worktree's own admin directory
(`.git/worktrees/<name>/refs/`), not in the shared ref store. Every ref query
run from the main checkout is therefore blind to them.

Reproduced against real git 2.43.0:

```bash
git worktree add wt -b feature
cd wt
OID=$(git commit-tree HEAD^{tree} -p HEAD -m mywork)
git update-ref refs/worktree/mywork "$OID"
cat ../.git/worktrees/wt/refs/worktree/mywork   # the oid lives here
cd ..
git rev-list --no-walk "$OID" --not --all       # prints the oid: unreachable
git for-each-ref --contains "$OID"              # empty
grep -c "$OID" .git/worktrees/wt/logs/HEAD      # 0
```

`update-ref` on a worktree-local ref writes no reflog entry for HEAD, so a
reflog probe finds nothing either. Every ordinary safety check reads clean, and
`git worktree remove` deletes the admin directory with the ref inside it. The
commit survives until the next `git gc --prune=now`, then `cat-file` is fatal.
Verified end to end, with a negative control that loses the commit.

To see them, read the files. Walk `<admin>/refs/**`, skip `ref: ` symrefs (they
anchor nothing on their own) and the null oid, and feed the oids into the same
`git rev-list --no-walk --stdin --not --all` query the reflog oids already use.
An unreadable or unparsable ref file must answer "unknown", never "no risk".
See `_worktree_ref_oids` and `unreachable_admin_commits` in
`scripts/maintenance/_gc_stale.py`.

The rescue is `git update-ref refs/heads/<name> <oid>` from the main checkout,
which promotes the anchor into the shared store before the worktree goes away.

Seven adversarial review rounds. This was the seventh distinct loss channel,
and the fourth one that a mock-based test suite reported as safe.
