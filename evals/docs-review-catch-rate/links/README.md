# Documentation link and style replay

This corpus replays Richard's past documentation review findings.
The runner uses current checks against isolated historical checkouts.
Each checkout lives under `~/worktrees/ai-agents/` and is removed afterward.

## Result

caught 12 of 12 in-scope positives, 0 FP on 12 negatives, 2 manual with reasons

The saved result records revisions, merge bases, findings, and checker hashes.
The score counts individual defects, including the historical heading rename.

## Cases

- C5-01 contains three broken relative paths before PR #7235.
- C5-02 contains two broken cross-file anchors before PR #7235.
- C5-03 contains six known broken targets at `ae5acffcb3`.
- PR #5640 removed the `lifecycle-commands` heading from `CLAUDE.md`.
- PR #5640 also passes in staged mode. Only the changed files are passed, and the unchanged inbound link is still reported.
- C5-04 needs manual review because valid destinations can have misleading labels.
- C5-05 needs portability review because repository existence cannot prove plugin distribution.
- Twelve negative cases come from clean documentation reviews.

The corpus records exact paths, defect classes, and source lines.
Matches allow three lines of movement and require matching targets when recorded.
Every finding on a negative counts, including style advisories.
Style findings count only on changed lines under `docs/`.
Link regressions include unchanged sources pointing into renamed targets.

## Run

```console
uv run python scripts/eval/docs_review_links_replay.py
```

The runner fetches each PR head and reads its base through the GitHub skill.
It computes the merge base before invoking the authoring checks.
Tree cases use `check_md_links.py --tree`, which includes baseline debt.
Other cases use pre-PR comparison and `prose_lint.py --docs-style --json`.
The PR #5640 case also runs once with the changed paths as file arguments.

Partial runs require `--case` and an explicit `--output` path.
Full results belong in `results/<date>.json`.
Temporary refs are removed even when replay fails.
Historical CRLF checkout differences are checked before disposable worktree removal.

## Limits

External URLs and renderer-specific anchors remain outside this check.
Generated mirrors and files outside the documented source scope remain excluded.
The two manual cases remain visible in the denominator accounting.
This fixed corpus measures these historical cases, without estimating future recall.
