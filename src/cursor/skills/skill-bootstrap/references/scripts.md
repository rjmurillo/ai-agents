# skill-bootstrap Scripts

The detail behind the Scripts section of `SKILL.md`.

Each CLI uses only the Python standard library, prints JSON with an `examined` count, writes nothing inside the repository (`bootstrap_eval.py freeze` writes there only with `--allow-in-repo`; `bootstrap_mine.py --out` refuses an in-repo path with no override), and runs on Linux, macOS, and Windows.

`bootstrap_friction.py`, `bootstrap_review.py`, and `review_clusters.py` are modules the miner imports, not CLIs.

Exit code 0 means success and exit code 1 means findings that need action, for every script. Exit codes 2 and 3 differ by script:

| Script | Exit 2: configuration | Exit 3: external |
|---|---|---|
| `bootstrap_mine.py` | Bad arguments; not a repository; bad rev; unreadable `TARGET` or `--prs-json`; refused `--out`; an authored file over the 5 MiB read cap | Git missing, failed, or timed out; a working-tree read failed; `--out` write failed, including a write race |
| `bootstrap_forms.py` | Bad arguments; unreadable or malformed plan | None |
| `bootstrap_eval.py` | Bad arguments; unreadable or malformed cases, results, or frozen file; edited frozen file; refused `--out`, including a write race | Git missing, failed, or timed out; the regex grader child failed; `--out` write failed; any other I/O error |
| `bootstrap_sweep.py` | Bad arguments; malformed or mismatched input; run directory in the repository or not empty; changed judge rubric; git missing or failed; any read or write failure (payload `error` is `io`) | None |
| `bootstrap_drift.py` | Bad arguments; repo or skills root not a directory; unknown `--name` | None; an unreadable `reverify.json` is `malformed` (exit 1) |
| `bootstrap_boundary.py` | See the detail below | Git missing, failed, or timed out; an unreadable working-tree file |

The payload `error` names the cause: `config` for exit 2, `git` or `io` for exit 3. `bootstrap_sweep.py` exits 2 for both, with `config` for git failures and `io` for read or write failures.

| Script and subcommand | Phase | Computes |
|---|---|---|
| `bootstrap_mine.py candidates` | 2 | Reverts; ranked churn, TODO hotspots, review rounds |
| `bootstrap_mine.py claims` | 4, 6, drift | Repository paths and line references in skill text that are missing, untracked, or out of range, each labeled `current` or `historical` |
| `bootstrap_forms.py check` | 3, 4 | Plan violations: computable item without an instrument, script missing, scaffold without a reason |
| `bootstrap_eval.py freeze`, `score` | 5 | Hash-frozen cases; pass rate per condition, capability delta, `gain`, `no_gap`, `flat`, `regression`, `incomplete` |
| `bootstrap_sweep.py plan`, `index`, `import`, `tally` | 2 | Source classes and read tools; evidence checks and batches; judge rows; ranked incidents, knowledge gaps, friction map |
| `bootstrap_drift.py check` | 6, drift | Each skill's `reverify.json` checks; `update_candidates`; `timed_out`; `--require` also fails a skill with no `reverify.json` or only skipped checks |
| `bootstrap_boundary.py plan`, `snapshot`, `verify` | 1, 3, 6 | Names and conflicts; the write boundary |

`bootstrap_boundary.py` detail: `plan` exits 1 on a conflict or an invalid name. `verify` exits 1 on a path outside the boundary, an existing skill changed without `--update`, an ignored file written in a skill (it would not ship), a path under an `--also-create` grant that changed in any way other than a new untracked file (`create-only-changed`), an ignored file under an `--also-create` grant, HEAD or branch moved, or index flags or `info/exclude` changed. Exit code 2 covers bad arguments; an output root outside the allowed set; an output root, skill directory, `--also-allow` path, or `--also-create` path that git ignores; an `--also-allow` or `--also-create` path outside the repository, under `.git`, or overlapping a skills root; a symlink in any of those paths; or a snapshot that already exists, is inside the repository, is unreadable, or is from another repository or output root. `verify` does not see gitignored files outside the output root, empty directories, other writes inside `.git/`, or tag, config, and push operations. It catches accidental writes by a cooperating run; it is not a sandbox. Only the Phase 1 snapshot counts, so `snapshot` refuses to overwrite an existing file. An unreadable file in the working tree stops `snapshot` with exit code 3 before any write.

`bootstrap_drift.py` runs a `command` check only with `--allow-commands`; review the argv first, because it executes repository code. The command gets no stdin, discarded output, and only `PATH`, `HOME`, `LANG`, `LC_ALL`, `SYSTEMROOT`, `TEMP`, and `TMP` from the environment, each only when set. Never pass `--allow-commands` in a job that holds secrets or runs on untrusted pull request content.

## Windows PowerShell

On Windows PowerShell 7, set the plugin root once, then run the same subcommands with `python`. This form takes the first non-empty value of `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, and `.claude`, and does not use the locator check the bash form uses (ADR-121 decision 1 leaves PowerShell to a follow-up):

```powershell
$root = @($env:COPILOT_PLUGIN_ROOT, $env:CLAUDE_PLUGIN_ROOT, '.claude') | Where-Object { $_ } | Select-Object -First 1
python "$root/skills/skill-bootstrap/scripts/bootstrap_boundary.py" snapshot --repo . --output-root <output-root> --out "<snapshot path>"
```
