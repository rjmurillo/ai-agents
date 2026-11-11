# new_issue.py with --source agent refuses to run without Step 0 evidence

## What happens

`new_issue.py` requires `--source`. With `--source agent` it also requires two evidence flags, or a Step 0 block already in the body:

- `--blocked-by`: Step 0 Q3, who is blocked and on what.
- `--signal`: Step 0 Q5, the metric, log, run, or ticket that proves the gap.

A hedged or empty value is refused and no issue is created. `--source human` skips both flags and appends a `source:human` marker to the body. The `source:<value>` label is created when missing.

## Practice

Gather the two facts before the call. Probe with `--dry-run`, which validates the flags and prints the plan without creating anything.

```bash
python3 .claude/skills/github/scripts/issue/new_issue.py --title "<title>" \
  --source agent --blocked-by "<who is blocked on what>" \
  --signal "<run URL, log line, or ticket>" --body-file <private file> --dry-run
```

Body-file rules are in `github-skill/body-file-readers-refuse-open-directories-and-world-writable-files`.

## Evidence

- OBSERVED 2026-11-11: `new_issue.py` lines 177 to 192 define both flags and the "unless the body already carries a Step 0 block" exception. The module docstring at lines 12 to 16 names Q3 and Q5.
- OBSERVED 2026-11-11: a `--dry-run` with both flags and a mode 600 body file returned `would_create`.
- The sweep children hit this error first on 2026-11-10 and reported it as a learning.

## Relations

- **related_to**: [github-skill/body-file-readers-refuse-open-directories-and-world-writable-files](body-file-readers-refuse-open-directories-and-world-writable-files.md)
