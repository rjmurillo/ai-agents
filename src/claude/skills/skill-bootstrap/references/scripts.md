# skill-bootstrap Scripts

The detail behind the Scripts section of `SKILL.md`.

Each CLI uses only the Python standard library, prints JSON (with an `examined` count, except `bootstrap_adr.py draft`), writes nothing inside the repository (`bootstrap_eval.py freeze` writes there only with `--allow-in-repo`; `bootstrap_adr.py draft` only creates a new file in a located ADR folder; `bootstrap_mine.py --out` refuses an in-repo path with no override), and runs on Linux, macOS, and Windows.

`bootstrap_friction.py`, `bootstrap_review.py`, and `review_clusters.py` are modules the miner imports, not CLIs. `boundary_grants.py` is a module `bootstrap_boundary.py` imports to parse and check its grants. `adr_shape.py`, `adr_commits.py`, and `adr_reason.py` are pure-function modules for ADR detection, ported from align-cli under MIT (`LICENSE-align`); they have no CLI and do no I/O. `adr_shape.py` also holds the trailer and importer-text cleaning, and `adr_commits.py` also holds the text helpers and the pull request selection. `adr_docs.py`, `adr_locate.py`, `adr_scan.py`, and `bootstrap_adr.py` are the I/O side: `adr_docs.py` reads README, changelog, and decision-log files, `adr_locate.py` finds the ADR folders, and `adr_scan.py` runs git and lists the candidates. `adr_scan.py` reads commits with `git rev-list` and `git cat-file --batch`, so a commit message cannot forge a record. `bootstrap_adr.py` is the only CLI of the group and also holds the ADR drafting code.

Exit code 0 means success and exit code 1 means findings that need action, for every script. Exit codes 2 and 3 differ by script:

| Script | Exit 2: configuration | Exit 3: external |
|---|---|---|
| `bootstrap_mine.py` | Bad arguments; not a repository; bad rev; unreadable `TARGET` or `--prs-json`; refused `--out`; an authored file over the 5 MiB read cap | Git missing, failed, or timed out; a working-tree read failed; `--out` write failed, including a write race |
| `bootstrap_forms.py` | Bad arguments; unreadable or malformed plan | None |
| `bootstrap_eval.py` | Bad arguments; unreadable or malformed cases, results, or frozen file; edited frozen file; refused `--out`, including a write race | Git missing, failed, or timed out; the regex grader child failed; `--out` write failed; any other I/O error |
| `bootstrap_sweep.py` | Bad arguments; malformed or mismatched input; run directory in the repository or not empty; changed judge rubric; git missing or failed; any read or write failure (payload `error` is `io`) | None |
| `bootstrap_drift.py` | Bad arguments; repo or skills root not a directory; unknown `--name` | None; an unreadable `reverify.json` is `malformed` (exit 1) |
| `bootstrap_boundary.py` | See the detail below | Git missing, failed, or timed out; an unreadable working-tree file |
| `bootstrap_adr.py` | Bad arguments, including `--max-commits` above 10,000; not a repository; bad rev, `--since`, or `--prs-json`; a `--scan` or `--prs-json` path that is not a regular file or is over 16 MiB; unreadable or malformed scan file; refused `--out` (inside any work tree of the repository, a directory, or already there); `draft` into a work tree folder that is not a located ADR folder or is ignored by git, or into a place git reports no work tree for; a `--status` other than Proposed, Rejected, Deprecated, or Superseded (a draft is never Accepted, per the ADR lifecycle rule that acceptance needs review); JSON nested past the recursion limit or text that cannot be written as UTF-8; any read or write failure (payload `error` is `io`); an unexpected exception (payload `error` is `internal`) | Git missing, failed, timed out, could not be started, or refused a repository for dubious ownership |

The payload `error` names the cause: `config` for exit 2 and `git` for exit 3. `bootstrap_sweep.py` and `bootstrap_adr.py` report `io` with exit 2 for read and write failures. `bootstrap_sweep.py` also reports git failures as `config` with exit 2. `bootstrap_adr.py` also exits 2 with `internal` for an unexpected exception, because its exit 1 is reserved for `exists` and exits 3 and 4 mean external and auth.

| Script and subcommand | Phase | Computes |
|---|---|---|
| `bootstrap_mine.py candidates` | 2 | Reverts; ranked churn, TODO hotspots, review rounds |
| `bootstrap_mine.py claims` | 4, 6, drift | Repository paths and line references in skill text that are missing, untracked, or out of range, each labeled `current` or `historical` |
| `bootstrap_forms.py check` | 3, 4 | Plan violations: computable item without an instrument, script missing, scaffold without a reason |
| `bootstrap_eval.py freeze`, `score` | 5 | Hash-frozen cases; pass rate per condition, capability delta, `gain`, `no_gap`, `flat`, `regression`, `incomplete` |
| `bootstrap_sweep.py plan`, `index`, `import`, `tally` | 2 | Source classes and read tools; evidence checks and batches; judge rows; ranked incidents, knowledge gaps, friction map |
| `bootstrap_drift.py check` | 6, drift | Each skill's `reverify.json` checks; `update_candidates`; `timed_out`; `--require` also fails a skill with no `reverify.json` or only skipped checks |
| `bootstrap_boundary.py plan`, `snapshot`, `verify` | 1, 3, 6 | Names and conflicts; the write boundary |
| `bootstrap_adr.py locate` | 2 | ADR folders with prefix, width, highest number, H1 form, and headings; the single `primary` folder; `next_number`; `walk_truncated` when the directory walk hit its folder or depth limit |
| `bootstrap_adr.py scan` | 2 | Decisions with no ADR, from commits, an offline pull request export, and decision-log entries; `truncated`; `shallow` for a shallow clone; `walk_truncated`; `examined.log_files` and `examined.log_files_skipped` for decision logs that are unreadable, oversized, or past the first 20 in path order; `adr_corpus_truncated` when reading existing ADRs stopped at 2,000 files or 32 MiB of text; drop counts per filter, with `pr_other_repo` for export rows whose URL is not under the origin (a GitLab origin matches none, because its URLs are not `/pull/`; with no origin nothing is dropped), `commit_too_large` for a commit object over 1 MiB, and `log_over_limit` for decision-log entries past 1,000 per file |
| `bootstrap_adr.py draft` | 6 | One new ADR, status `Proposed`, created with mode `x` so a file is never replaced |

`bootstrap_boundary.py` detail: `plan` exits 1 on a conflict or an invalid name. `verify` exits 1 on a path outside the boundary, an existing skill changed without `--update`, an ignored file written in a skill (it would not ship), a path under an `--also-create` grant that changed in any way other than a new untracked file (`create-only-changed`; a path the snapshot HEAD tracks, a new symlink or nested repository, and a new `.gitignore` or `.gitattributes` in any letter case never count as new; an ignored `.gitignore` or `.gitattributes` under the grant also fails, even one that predates the run; a path an `--also-allow` grant also covers follows `--also-allow`), HEAD or branch moved, or index flags or `info/exclude` changed. Exit code 2 covers bad arguments; an output root outside the allowed set; an output root, skill directory, `--also-allow` path, or `--also-create` path that git ignores; an `--also-allow` or `--also-create` path outside the repository, under `.git`, or overlapping a skills root; a symlink in any of those paths; or a snapshot that already exists, is inside the repository, is unreadable, or is from another repository or output root. `verify` does not see gitignored files outside the output root, including other ignored files inside an `--also-create` grant, empty directories, other writes inside `.git/`, or tag, config, and push operations. It catches accidental writes by a cooperating run; it is not a sandbox. Only the Phase 1 snapshot counts, so `snapshot` refuses to overwrite an existing file. An unreadable file in the working tree stops `snapshot` with exit code 3 before any write.

`bootstrap_drift.py` runs a `command` check only with `--allow-commands`; review the argv first, because it executes repository code. The command gets no stdin, discarded output, and only `PATH`, `HOME`, `LANG`, `LC_ALL`, `SYSTEMROOT`, `TEMP`, and `TMP` from the environment, each only when set. Never pass `--allow-commands` in a job that holds secrets or runs on untrusted pull request content.

`bootstrap_adr.py` exits 1 only when `draft` finds its target file already there, or finds another ADR with the same number after it wrote (payload `error` is `exists`, with `written: false` in the first case and `written: true` in the second). In the second case it leaves the draft on disk: `path` names it, `others` names the other ADRs, and the caller must renumber or remove one of the two. It never retries with another number.

`bootstrap_adr.py scan` reads git and the working tree and makes no network call. `--out` must be outside the repository. `--prs-json` is a JSON list of merged pull requests. Each item needs `number`, `title`, `body`, `url` (or `html_url`), `merged_at` (or `mergedAt`), and `author` (or `user`) with `login`. `merge_commit_sha` (or `mergeCommit.oid`) is optional.

`bootstrap_adr.py` finds ADR folders in three steps. It reads an `.adr-dir` file and checks the known folder names together. Only when those find nothing does it look for any folder with three or more ADR-named files. Inside the repository, `draft` writes only into a folder found this way, and a folder with no ADR-named file is not one. It refuses a path that git ignores. An `rfc` or `rfcs` folder is read, so its links still hide decisions, but it has `draft_target: false`. It is never `primary`, and `draft` refuses it. A draft title drops the commit's `type(scope)!:` prefix and its trailing `(#N)`.

## Windows PowerShell

On Windows PowerShell 7, set the plugin root once, then run the same subcommands with `python`. This form takes the first non-empty value of `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, and `.claude`, and does not use the locator check the bash form uses (ADR-121 decision 1 leaves PowerShell to a follow-up):

```powershell
$root = @($env:COPILOT_PLUGIN_ROOT, $env:CLAUDE_PLUGIN_ROOT, '.claude') | Where-Object { $_ } | Select-Object -First 1
python "$root/skills/skill-bootstrap/scripts/bootstrap_boundary.py" snapshot --repo . --output-root <output-root> --out "<snapshot path>"
```
