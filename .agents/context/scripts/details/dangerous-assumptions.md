## Dangerous assumptions

- `scripts/README.md` opens "PowerShell scripts for the AI Agents system": stale, zero tracked `.ps1`/`.psm1` remain.
- `stale_script_refs.py` matches only `.ps1`/`.psm1` (none tracked, so it reports nothing); a doc naming a deleted `.py` trips no lefthook or CI gate, only `orphan-ref-validator` (`/build` exit gate 4).
- `scripts/security/run_semgrep.py` runs only from `git_hook_policy.py semgrep`, which lefthook never calls; pre-push `security-scan` uses `semgrep-push` and its inline `_run_semgrep_tree`.
- `scripts/ci/` and `.github/scripts/` are separate trees, both feeding workflow steps; `ci-scripts.md` binds both.
