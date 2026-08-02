# Skill: Reading PR mergeability requires forcing its computation (98%)

## Statement

`gh pr list --json mergeStateStatus` returns `UNKNOWN` for most PRs. GitHub computes mergeability lazily and does **not** compute it because you asked for the status field. Request `mergeable` in the same query and the server computes both.

Querying `mergeStateStatus` alone does not under-report by a little. It under-reports by an order of magnitude.

## Evidence

2026-08-01, 46 open PRs, same repository, seconds apart:

```bash
$ gh pr list --json number,mergeStateStatus --jq '... group_by(.mergeStateStatus)'
BLOCKED=5 DIRTY=2 UNKNOWN=40

$ gh pr list --json number,mergeable,mergeStateStatus --jq '... group_by(.mergeable)'
CONFLICTING=35 MERGEABLE=11
```

The first reading says 2 PRs conflict. The truth is 35. I reported the wrong number from the first query and a verification pass caught it.

## EUREKA: the documented recipe is the broken one

`.serena/memories/jq/jq-pr-operation-patterns.md:18` recommends exactly the under-reporting form:

```bash
gh pr list --json number,mergeStateStatus | jq '.[] | select(.mergeStateStatus == "BLOCKED")'
```

That selects from a field that is mostly `UNKNOWN`, so it silently misses most BLOCKED PRs. The conventional pattern in this repo's own memory is the defect. Fix is one word: add `mergeable` to the `--json` list. The jq stays the same.

## Anti-Pattern

Reading conflict or block counts from `mergeStateStatus` alone, then reporting them as fact. `UNKNOWN` is not "no conflict"; it is "nobody asked".

## Correct Usage

```bash
# Forces computation. mergeable is the field that triggers it; keep it even if
# you only read mergeStateStatus.
gh pr list --state open --limit 100 --json number,mergeable,mergeStateStatus
```

Or skip the server entirely, which needs no lazily-computed state:

```bash
git merge-tree --write-tree --name-only origin/main <pr-head>
```

`merge-tree` also names the conflicting paths, which `mergeStateStatus` never does. It writes a tree object and reports conflicts without touching the index or working tree, so it is safe to run against a repository with other work in flight.

## Related

- `.serena/memories/jq/jq-pr-operation-patterns.md` (contains the under-reporting form)
- `.serena/memories/tasks/issue-2637-merge-pr-reject-unknown.md` (treats UNKNOWN as not-ready at merge time, which is the correct downstream behaviour)
