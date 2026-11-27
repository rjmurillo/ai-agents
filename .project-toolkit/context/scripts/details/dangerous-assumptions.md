## Dangerous assumptions

- `stale_script_refs.py` matches only `.ps1`/`.psm1` command references. Because no PowerShell scripts are tracked, any non-allowlisted live command reference is stale; a doc naming a deleted `.py` trips no lefthook or CI gate, only `orphan-ref-validator` (`/build` exit gate 4).
- `scripts/security/run_semgrep.py` runs only from `git_hook_policy.py semgrep`, which lefthook never calls; pre-push `security-scan` uses `semgrep-push` and its inline `_run_semgrep_tree`.
- The repo-local `ai-agents-validation-and-qa` skill's `references/rule-ci-scripts.md` binds both `scripts/ci/` and `.github/scripts/`.
