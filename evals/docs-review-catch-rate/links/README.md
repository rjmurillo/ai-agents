# Documentation link and style replay

Richard supplied these historical review findings and clean reviews on 2026-11-19.
The corpus pins each reviewed snapshot to its full commit SHA.

## Score

2026-11-19: caught 12 of 12 in-scope positives, 0 FP on 12 negatives, 2 manual with reasons.

The score counts individual defects, matching file, class, and lines within three.
Cases with multiple destinations also require the matching target.
Every finding on a negative counts, including style advisories.

## Cases

| Case | Evidence | Mode | Expected defects |
| --- | --- | --- | --- |
| C5-01 | PR #7235 base, routing diagram links | Tree | Three missing targets. |
| C5-02 | PR #7235 base, workflow command anchors | Tree | Two missing anchors. |
| C5-03 | Snapshot ae5acffcb3, skill reference links | Tree | Six missing targets. |
| Rename | PR #5640, CLAUDE lifecycle heading rename | Pre-PR | One broken inbound anchor. |
| Negatives | Twelve clean reviews listed in the corpus | Pre-PR | Zero findings. |

`git log -S '## Lifecycle commands' -- CLAUDE.md` identifies the rename commit.
That commit belongs to PR #5640.
The replay checks that PR's pinned head, including its unchanged inbound source.
Unit tests also cover synthetic heading renames and target moves.

## Manual cases

- C5-04: A valid destination cannot prove its label describes the target section.
- C5-05: Plugin distribution boundaries require portability review beyond repository link existence.

Each manual case carries its reason in `corpus.json`.
Both snapshots still run through the checks.

## Reproduce

Run from the repository root with authenticated GitHub access:

```console
uv run python scripts/eval/docs_review_links_replay.py
```

Use `--case C5-01` for one case, with `--output` for exploratory results.
The default output is `results/<UTC-date>.json` beside the corpus.
The runner fetches each PR head into an isolated ref.
It reads `baseRefOid` through the repository's GitHub context helper.
Each temporary worktree lives under `~/worktrees/ai-agents/`.
The comparison base is the snapshot's merge base with `baseRefOid`.
The runner removes its worktree and ref after each case, including failures.

The result records SHAs, commands, findings, matches, and checker input hashes.
Tree mode reports baseline debt so known broken links remain measurable.
Pre-PR mode excludes existing defects and checks new breakages across the tree.
This includes unchanged sources whose targets moved or lost headings.
Style scoring includes only added lines under `docs/`.
The remaining prose rules remain outside this eval's scope.
Three negative PRs exercise style checks on changed documentation files (2026-11-19).
The other negatives still exercise link detection across the scoped tree.
