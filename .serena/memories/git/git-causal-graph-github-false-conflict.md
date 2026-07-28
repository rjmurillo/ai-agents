# A Custom Merge Driver Makes Local and GitHub Merge Results Disagree

**Category**: Git Operations
**Source**: 2026-07-28, PR #3636, PR #3497

## Statement

`.agents/memory/causality/causal-graph.json` is merged by a custom merge driver.
Git runs that driver in a local clone. GitHub does not run custom merge drivers on
its servers. So a merge of that file can be clean in every local clone and
conflicted on GitHub, and the two answers are both correct for the code that
produced them.

This is the case the stale-cache runbook does not cover. Read
`docs/autonomous-pr-monitor.md` "Stale merge-state cache" first: it owns the
ancestry check and the safe base-ref refresh, and its guidance is correct as far
as it goes. Its outcome table says a failing trial merge means the conflict is
"real and authoritative". For a driver-managed path that inference does not hold,
because the local trial merge runs a driver that GitHub will not run. The reverse
also applies: a clean local trial merge does not prove GitHub will agree.

## Which case am I in

Check in this order. The two causes are independent and need different fixes.

```bash
PR=3636
eval "$(gh pr view "$PR" --json baseRefOid,headRefOid \
  -q '"BASE=\(.baseRefOid)\nHEAD=\(.headRefOid)"')"
git fetch -q origin main

# 1. Stale cache: nothing to merge at all.
if git merge-base --is-ancestor "$BASE" "$HEAD"; then
  echo "base is already an ancestor: stale cache, see autonomous-pr-monitor.md"
fi

# 2. Driver-managed path in the merge?
git check-attr merge -- .agents/memory/causality/causal-graph.json
```

Fetch first and use the SHAs GitHub reports. Testing against a local `origin/main`
that has drifted answers a question nobody asked.

## Proving the driver is the cause

Do not infer the driver from a clean local merge. Run the negative control: force
the driver to fail and confirm the merge starts conflicting.

```bash
HEAD=cadd47a5b18e5a331c9616836237ba489bd1b15d
MAIN=$(git rev-parse origin/main)

git merge-tree --write-tree "$HEAD" "$MAIN" >/dev/null; echo "driver on:   $?"
git -c merge.causal-graph.driver=false \
    merge-tree --write-tree "$HEAD" "$MAIN" >/dev/null; echo "driver off:  $?"
```

Measured on 2026-07-28 for that SHA pair: driver on exits 0 with no conflict;
driver forced to `false` exits 1 with `CONFLICT (content)` in the graph. Replacing
the driver with a plain text merge also exits 1. A raw `git merge-file` of the
three blobs produces 239 conflict hunks. The driver is doing the work.

`git merge-tree` honors `.gitattributes` merge drivers, so it is a valid probe.
That also means `merge-tree` exiting 0 does **not** predict GitHub, which runs no
driver. Use it to learn what the driver does, not to predict the server.

`git config --get merge.causal-graph.driver` exits 1 when the driver is absent.
Guard it under `if` rather than letting it kill a `set -e` script. Absent means
the clone never ran `scripts/maintenance/install_merge_drivers.py`, wired in at
`lefthook.yml:20`.

## Resolution

Merge `origin/main` into the branch locally and push the merge commit. The driver
resolves the file on the way in, and GitHub then sees an already-merged result it
does not have to compute.

```bash
git fetch origin main && git merge origin/main --no-edit && git push
```

**This expires.** It fixes one base SHA. The next commit on `main` that touches the
graph puts the same PR back to `CONFLICTING`, and the merge has to be repeated.
Confirmed on PR #3636: it returned to `CONFLICTING` within the hour. The graph
changed in 49 of the last 200 first-parent commits on `main`, so expect this
roughly one time in four, not on every commit.

## Verifying the merge kept the data

Node counts prove nothing. The driver is not a pure union: `_survives` in
`scripts/validation/merge_causal_graph.py` treats a record present in the merge
base and absent from one side as a deliberate deletion and keeps it deleted
(issue #3375). A correct merge can therefore land below either parent, and a
count above both parents can still be missing records.

Compare identity keys instead, per collection, against each parent. Use the
driver's own keys from `_COLLECTIONS` in `merge_causal_graph.py`: `nodes` by
`id`, `patterns` by `name`, `edges` by `(source, target)`.

```python
import json, subprocess, sys
G = ".agents/memory/causality/causal-graph.json"
KEYS = {"nodes": ("id",), "patterns": ("name",), "edges": ("source", "target")}

def ids(rev):
    d = json.loads(subprocess.run(["git", "show", f"{rev}:{G}"],
                                  capture_output=True, text=True).stdout)
    return {c: {tuple(str(r.get(f, "")) for f in fs) for r in d.get(c, [])}
            for c, fs in KEYS.items()}

merged = ids(sys.argv[1])
for parent in sys.argv[2:]:
    p = ids(parent)
    for c in KEYS:
        lost = p[c] - merged[c]
        print(f"{parent} {c}: {len(lost)} keys dropped")
```

Run it as `python3 verify_merge.py HEAD HEAD^1 HEAD^2`. Anything dropped is
either a deletion the driver honored or data loss. Resolve which before pushing.

Compare keys, not whole records. Comparing serialized records reports a false
drop for every record the driver legitimately rewrote: `_COUNTERS`,
`_SET_VALUED`, `_EARLIEST`, and `_LATEST` in the same file give
`evidence_count`, `occurrences`, `frequency`, `episodes`, `created`, `last_used`,
and `updated` merge policies that change the value on purpose, and every field
not named there still goes through `_prefer_diverged`. Checking PR #3636 this way
reported one pattern lost; by key it lost nothing, and the record differed only in
`occurrences`, `episodes`, and `contributions`.

## Two wrong turns

`git rebase origin/main` needs a force push to publish, which is prohibited here.
Merge instead.

`git checkout origin/main -- <graph>` discards every node the branch contributed.
The lefthook wrapper will not bring them back: it only processes episodes staged
in the current commit, and a merge stages none (`lefthook.yml:284-289`). The
standalone generator is not so limited. It defaults to the whole episode directory
and takes `--reset-graph` to rebuild from scratch
(`.claude/skills/memory/scripts/update_causal_graph.py`), so recovery is possible;
it is just not automatic. `merge_causal_graph.py` records that 41 of 242 episodes
on disk had no node in the committed graph, most arriving through this path.

## Related

- `docs/autonomous-pr-monitor.md`, "Stale merge-state cache". Owns the other cause.
- Issue #3644. Durable fix for the driver-versus-GitHub disagreement.
- `.gitattributes`. Assigns the `causal-graph` driver.
