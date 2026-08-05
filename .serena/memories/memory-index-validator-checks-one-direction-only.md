# The memory index validator only checks index to file, never file to index

## The trap

`scripts/validation/memory_index.py` walks entries and asserts each target
exists. It never walks the filesystem and asks whether a memory got indexed.
Add a memory file, forget the `memory-index.md` entry, and the validator prints
`Result: PASSED`. The memory is then invisible to keyword search, which is the
only way anything finds it.

Verified 2026-08-04 by probe. Two unindexed files were dropped in, one at
`.serena/memories/zz-probe-unindexed.md` and one at
`.serena/memories/git/zz-probe-subdir.md`, and the default run still reported:

```
Domains: 33 total, 33 passed, 0 failed
Files: 305 indexed, 0 missing
Keyword Issues: 0

Result: PASSED
```

## The orphan check does not close the gap

There is a `--fix-orphans` flag, and it is not the safety net it looks like:

- **Opt-in.** Nothing in the default run or the push gates passes it.
- **Warn only.** It prints `[P1 WARN]` and leaves the exit code alone.
- **Non-recursive.** `find_orphaned_files` uses `memory_path.glob("*.md")`, so
  anything under `git/`, `patterns/`, `session/`, or any other subdirectory is
  unreachable by it. Neither probe above was reported, including the top-level
  one.
- **Prefix-scoped.** It only considers files matching a domain prefix against
  the 33 `skills-*-index.md` domain indices, so a plain descriptive filename is
  out of scope even at the top level.

## Read the counts correctly

`Files: 305 indexed` counts entries parsed from the 33 `skills-*-index.md`
domain indices. It is not the filesystem count, which is 948, and it is not the
`memory-index.md` entry count, which is 121. Adding a row to `memory-index.md`
does not move it. A stable 305 across an edit is expected and says nothing about
whether your entry landed.

## The other direction is enforced, but not where you look

Verified 2026-08-05 by negative control: point one `memory-index.md` link at a
file that does not exist and the run flips to `Result: FAILED`. The check works.
The reporting does not. The failure surfaces as a single line roughly 800 lines
into the output:

```
- P1 VALIDITY: memory-index references non-existent file: <name>.md
```

while the summary block directly above the verdict still reads:

```
Files: 321 indexed, 0 missing
```

So `0 missing` and a missing file are simultaneously true, because that counter
belongs to the domain-index check described above and not to this one. Anything
that reads the counters, a `| tail -3`, a dashboard, a skim, sees all zeros on a
failing run.

Read the `Result:` line. It is the only field in the summary that reflects P1
VALIDITY errors.

## Do this instead

After adding any memory file, confirm your own entry by name rather than
trusting the summary line:

```bash
grep -n "your-memory-file-name" .serena/memories/memory-index.md
uv run --frozen python scripts/update_memory_index_tokens.py
```

The token-count script is the second half of the step. A new row written by hand
carries a placeholder count until it runs.

## What it cost

Commit `478d3a906` shipped a memory file with no index row. Every validator was
green. It was caught by reading the diff, not by any gate, and needed a
follow-up commit. (That file, `decision-shallow-fetch-kills-merge-base-in-ci.md`,
ships with PR #4572 and is not on `main` until that lands.)

## Related

`.serena/memories/find-coverage-by-mutation-not-by-name.md` is the same shape
one level up: a name-based check answers whether a spelling exists, not whether
the guarantee does. Here the validator checks that every named entry resolves to
a file, which says nothing about whether every file has an entry.
