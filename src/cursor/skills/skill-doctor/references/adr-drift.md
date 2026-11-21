# ADR drift

Read this from Step 1a of `SKILL.md`. It covers what `adr_drift.py` checks and
the finding kinds. The script writes only the `--out` file for `scan`.

## Commands

```bash
python3 "$SKILL_ROOT/scripts/adr_drift.py" locate --repo "$REPO"
python3 "$SKILL_ROOT/scripts/adr_drift.py" scan --repo "$REPO" \
  --out "$REPORT_DIR/adr_drift/<repo-slug>.json"
```

Exit codes: 0 ok, 2 bad arguments, unreadable input, `--out` not allowed, or not
a git repository, 3 a git command failed. Every subcommand accepts `--help`.

`scan` reads the last 300 commits from `HEAD` (`--max-commits`, `--since`) and
the ADR files in the working tree. It uses no network. `--out` must be outside
the repository. The result carries `head`, `examined`, and `truncated`. When
`truncated` is true, say so: older history was not read.

## Folder detection

`locate` checks, in order:

1. A `.adr-dir` file (adr-tools). When valid, it names the only folder.
2. The project-toolkit architecture folder, `docs/adr`, `docs/architecture`,
   `docs/decisions`, `architecture/decisions`, `doc/adr`. A folder counts when it
   holds a numbered ADR or a template.
3. Filename convention per folder: `ADR-NNN-slug.md` or `NNNN-slug.md`.

`primary` is the folder when exactly one is found, else `null`. `next_number` is
the highest number plus one.

## Finding kinds

Every finding has `id`, `kind`, `group`, `severity`, `confidence`, `evidence`,
and a non-empty `suggested_fix`.

| Group | Kind | Confidence | Suggested fix |
| --- | --- | --- | --- |
| Numbering | `no-adr-directory` | deterministic | Create an ADR folder. Severity info. |
| Numbering | `adr-duplicate-number` | deterministic | Rename the later file to the next free number. |
| Numbering | `adr-title-number-mismatch` | deterministic | Make the H1 match the filename. |
| Numbering | `adr-unparseable-name` | deterministic | Rename to the folder convention. |
| Numbering | `adr-number-gap` | deterministic | None needed. Report only. Severity low. |
| Links | `adr-broken-link` | deterministic | Point the link at the existing file. |
| Links | `adr-supersedes-missing-target` | deterministic | Fix the number or drop the edge. |
| Links | `adr-supersession-not-reciprocal` | deterministic | Add the matching edge to the other record. |
| Links | `adr-cited-path-missing` | deterministic | Update the ADR or mark it superseded. |
| History | `adr-superseded-by-commit` | heuristic | Update the status or write the successor. |
| History | `adr-contradiction-candidate` | heuristic | Review the ADR against the commit. |

Details that decide what fires:

- Links: only links that resolve into an ADR folder and name an ADR file. Code
  fences and inline code are skipped.
- Cited paths: backticked repo-relative paths whose first directory exists in
  the repository. Records with status superseded, deprecated, or rejected are
  skipped.
- Supersession edges come from frontmatter (`supersedes`, `superseded-by`) and
  from `Supersedes:`, `Superseded by:`, and `Status:` lines.

History findings say "candidate" and cite the commit. They never claim a
contradiction.
