# Git packed-refs blank-line repair

Issue #2903 tracks a session-init failure where external C# language tooling
can insert a blank line into `.git/packed-refs`. Git rejects that file with:

```text
fatal: unexpected line in .git/packed-refs
```

The observed corruption is a lone `0x0a` blank line between the
`# pack-refs with: ...` header and the first ref record. Git's parser also
rejects blank lines elsewhere in `packed-refs`.

## Automatic repair

The repository hooks run `scripts/maintenance/repair_packed_refs.py` before
their first git ref operation:

- `.githooks/pre-commit`
- `.githooks/pre-push`

The helper resolves normal repositories and linked worktrees, locates the
common git directory, and reads `packed-refs` directly. If it finds blank
lines, it backs up the original file beside it, removes only blank records,
rewrites the file, and runs `git for-each-ref` to verify that git can parse the
result.

Clean repositories and repositories without `packed-refs` stay silent. The
hook prints only when it repairs the file or when an unexpected failure occurs.

## Manual run

```bash
uv run python scripts/maintenance/repair_packed_refs.py
```

The command exits `0` when the file is clean, missing, or repaired. It exits
nonzero only when an unexpected failure prevents verification.
