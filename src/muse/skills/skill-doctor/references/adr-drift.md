# ADR drift

Read this from Step 1a of `SKILL.md`. It covers what `adr_drift.py` checks, the
finding kinds, how drafts work, and the align states. The script is read-only
except for `draft`, which writes one new file.

## Commands

```bash
python3 "$SKILL_ROOT/scripts/adr_drift.py" locate --repo "$REPO"
python3 "$SKILL_ROOT/scripts/adr_drift.py" scan --repo "$REPO" \
  --out "$REPORT_DIR/adr_drift/<repo-slug>.json"
python3 "$SKILL_ROOT/scripts/adr_drift.py" draft \
  --scan "$REPORT_DIR/adr_drift/<repo-slug>.json" --id <finding-id> \
  --out "$REPORT_DIR/proposed/adr"
```

Exit codes: 0 ok, 1 logic error or the `draft` target exists, 2 bad arguments,
unreadable input, `--out` not allowed, or not a git repository, 3 a git command
failed. Every subcommand accepts `--help`.

`scan` reads the last 300 commits from `HEAD` (`--max-commits`, `--since`) and
the ADR files in the working tree. It uses no network. `--out` must be outside
the repository. The result carries `head`, `examined`, and `truncated`. When
`truncated` is true, say so: older history was not read.

`--prs-json FILE` takes a list of objects with an integer `number` and optional
`title`, `body`, and `url`. It is the shape `bootstrap_mine.py --prs-json`
reads. The caller exports it. The script never calls an API. A PR joins a
commit through `(#123)` in a squash subject or `Merge pull request #123`.

## Folder detection

`locate` checks, in order:

1. A `.adr-dir` file (adr-tools). When valid, it names the only folder.
2. The project-toolkit architecture folder, `docs/adr`, `docs/architecture`,
   `docs/decisions`, `architecture/decisions`, `doc/adr`. A folder counts when it
   holds a numbered ADR or a template.
3. Filename convention per folder: `ADR-NNN-slug.md` or `NNNN-slug.md`.

`primary` is the folder to write to. It is `null` when zero or two or more
folders are found. `next_number` is the highest number plus one, for display.
`draft` recomputes the number at write time.

## Finding kinds

Every finding has `id`, `kind`, `group`, `severity`, `confidence`, `evidence`,
a non-empty `suggested_fix`, and `fix` (a `draft` argv, or null).

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
| History | `undocumented-decision` | heuristic | Draft an ADR with `draft`. |
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
contradiction. A commit that touches a file in an ADR folder is skipped.

`undocumented-decision` signals:

- `BREAKING CHANGE` footer, or `!` after the commit type.
- Subject or body verbs: switch to, replace X with Y, migrate, adopt, drop
  support, deprecate, instead of, decide, standardize on. With `--prs-json`, the
  PR title and body run through the same verbs.
- A dependency added or removed in `pyproject.toml`, `package.json`, `go.mod`,
  `Cargo.toml`, or `*.csproj`. A version bump is not a signal.

A PR number in a squash or merge subject is evidence and a suppression key, not
a signal by itself.

A signal is suppressed when any ADR in the working tree names the commit's full
SHA, a short SHA of 7 or more characters, `#<PR>`, the PR URL, or (for a
dependency signal) the dependency name. A rerun after `draft` writes into a
repository ADR folder does not propose the same decision again.

## Drafts

`draft` writes one Markdown file from one `undocumented-decision` finding. No
model runs. The text is the commit subject and body (or the PR title and body),
plus the commit SHA and PR URL as source links.

- The number is the highest number in `--out` and in every repository ADR
  folder, plus one, assigned at write time.
- Filename prefix, zero padding, H1 form (`# ADR-123: Title` or `# 123. Title`),
  section headings, and frontmatter keys follow the newest record in the folder.
- `--status` defaults to `Proposed`. A heading the source does not cover reads
  "Not recorded in the source."
- Inside the repository, `--out` must be an ADR folder from `locate`, or the exit
  code is 2. A path outside the repository is allowed.
- The file opens with exclusive create. An existing target exits 1 and keeps its
  bytes.

Skill-doctor writes drafts only under `$REPORT_DIR/proposed/adr/`, never into
the repository.

## align

`align` (github.com/aligndottech/align-cli) is an optional cross-check. The
deterministic result is complete without it. `scan` records one of these states
in `align.status`:

| State | Report line |
| --- | --- |
| `absent` | align not installed. Deterministic check complete. Optional cross-check: github.com/aligndottech/align-cli. |
| `detected` | align found. Not run. To cross-check: `DO_NOT_TRACK=1 align adr`. |
| `no_graph` | align found, no graph. Not built, because building reads api.github.com and downloads a model. |
| `ran` | Advisory text under its own heading. |
| `failed` | Exit code and stderr tail. |

Without `--with-align`, align never runs. With the flag, the script runs
`align adr` only, with `DO_NOT_TRACK=1`, stdin from `/dev/null`, a 60 second
timeout, and the repository as the working directory. It needs `align` on PATH
and an existing `~/.align/local.db`. Before passing the flag, tell the user that
in cloud mode `align adr` calls the Align gateway, and the script cannot check
which mode is set. The script never runs bare `align`, `up`, `connect`, `use`,
`mcp`, or any hook setup. Its output is advisory. It never changes finding
counts or exit codes. `align.version` stays null because the script makes no
second call.
