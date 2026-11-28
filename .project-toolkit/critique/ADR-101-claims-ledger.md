# ADR-101 claims ledger, 2026-11-25

Claims in the 2026-11-25 amendment or edited sentences of ADR-101. The amendment names the `agent-*` environments as still existing; repository settings are not readable from the working tree, so that sentence rests on the owner and is not ledgered. Commands ran in the working tree of branch `ci/delete-agent-env-jobs` at head `7cfb378901` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` on base `e74b842786`.

| Claim | Kind | Command | Result |
|---|---|---|---|
| No file under .github reads ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN, or COPILOT_GITHUB_TOKEN as a secret | absence | `grep -rEc 'secrets(\.\|\[.)(ANTHROPIC_API_KEY\|CLAUDE_CODE_OAUTH_TOKEN\|COPILOT_GITHUB_TOKEN)' .github \| grep -v ':0$' \| wc -l` | VERIFIED: 0 |
| ai-spec-validation.yml reads no secret | absence | `grep -cE 'secrets(\.\|\[)\|secrets:\s*inherit' .github/workflows/ai-spec-validation.yml` | VERIFIED: 0 |
| No workflow grants statuses: write | absence | `grep -rEc 'statuses:\s*write' .github/workflows \| grep -v ':0$' \| wc -l` | VERIFIED: 0 |
| codeql-analysis.yml still grants checks: write | path | `grep -nE '^\s+checks:\s*write' .github/workflows/codeql-analysis.yml` | VERIFIED: 199:      checks: write |
| Eleven workflows were deleted | count | `git show --name-status --format= 3f145f26fd -- .github/workflows \| grep -c '^D'` | VERIFIED: 11 |
| claude, slash-command-quality, software-engineering-library-activation, post-pr-retrospective are among the deleted | path | `git show --name-status --format= 3f145f26fd -- .github/workflows \| grep -E '^D.*/(claude\|slash-command-quality\|software-engineering-library-activation\|post-pr-retrospective)\.yml' \| wc -l` | VERIFIED: 4 |
| Two more workflows lost their agent-gated jobs (plugin-cli-smoke, pr-maintenance) | count | `git show --name-status --format= 3f145f26fd -- .github/workflows \| grep -E '^M.*/(plugin-cli-smoke\|pr-maintenance)\.yml' \| wc -l` | VERIFIED: 2 |
| No workflow declares an agent-* environment | absence | `grep -rEn 'environment:\s*agent-' .github/workflows \| wc -l` | VERIFIED: 0 |
| pull_request_target workflows are unchanged at three | count | `grep -lE 'pull_request_target' .github/workflows/*.yml \| wc -l` | VERIFIED: 3 |
| adr101-publisher.yml requests `checks: write` for an app token | path | `grep -n 'permission-checks' .github/workflows/adr101-publisher.yml` | VERIFIED: 151:          permission-checks: write |
| `BOT_PAT` is not referenced under .github | absence | `grep -rn 'BOT_PAT' .github \| wc -l` | VERIFIED: 0 |

## Second pass, 2026-11-25

Rows for the reworded clause at ADR-101 line 478, which now points to ADR-057. Commands ran on 2026-11-25 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| ADR-057 carries the amendment the pointer names | path | `grep -n '^## Amendment 2026-11-25' .project-toolkit/architecture/ADR-057-prompt-behavioral-evaluation.md` | VERIFIED: 310:## Amendment 2026-11-25: the /spec CI leg is deleted |
| ADR-101 stays at 500 lines | count | `wc -l < .project-toolkit/architecture/ADR-101-enforcement-planes.md` | VERIFIED: 500 |
