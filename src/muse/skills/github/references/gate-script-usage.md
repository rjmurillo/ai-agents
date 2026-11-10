# Gate-dispatched script usage

Fourteen scripts under `scripts/pr` and `scripts/utils` have no examples or
exit codes in their `--help`. The completion gate dispatches them, and the
`Verify dispatch closure against base` check compares each one byte for byte
with the base ref. Any edit to their source, including a help epilog, fails
that check. Their usage lives here instead.

Run each as `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/<path>"`.
Exit codes follow ADR-035 unless a row says otherwise. They come from each
script's header docstring and its exit statements.

| Script | Examples (arguments) | Exit codes |
|---|---|---|
| `utils/check_github_transport.py` | `--output-format json` | 0 check completed, read `transport` for the verdict; 2 plugin lib missing; 3 quota refusal or transport wobble; 4 credential fault |
| `pr/get_pr_context.py` | `--pull-request 123`; `--pull-request 123 --include-diff --include-changed-files`; `--pull-request 123 --field author_is_bot` | 0 ok; 1 invalid parameters; 2 not found; 3 API failure; 4 auth |
| `pr/get_pr_checks.py` | `--pull-request 123`; `--pull-request 123 --wait --timeout-seconds 600`; `--pull-request 123 --required-only` | 0 all passing, skipped, or pending (read `RequiredState`, not the code alone); 1 a check failed; 2 PR not found; 3 API error; 4 auth; 7 timeout with `--wait` |
| `pr/get_pr_review_threads.py` | `--pull-request 123`; `--pull-request 123 --unresolved-only --include-comments` | 0 ok; 1 invalid parameters; 2 not found; 3 API failure; 4 auth |
| `pr/get_unresolved_review_threads.py` | `--pull-request 123`; `--pull-request 123 --include-comments --output-format json` | 0 snapshot returned, possibly incomplete (check `fetched_pages_complete`); 2 usage; 4 auth. API and pagination failures return 0 with `success: false`, not 3 |
| `pr/get_unaddressed_comments.py` | `--pull-request 123`; `--pull-request 123 --bot-only --only-unaddressed` | 0 ok; 3 API failure; 4 auth |
| `pr/add_pr_review_thread_reply.py` | `--thread-id PRRT_kwDOExample --body "Fixed in abc1234"`; `--thread-id PRRT_kwDOExample --body-file reply.md --resolve --pull-request 123 --expected-head-sha abc1234` | 0 ok; 2 usage or file not found; 3 API failure; 4 auth. `--resolve` needs an `--expected-*` flag |
| `pr/resolve_pr_review_thread.py` | `--thread-id PRRT_kwDOExample`; `--pull-request 123 --all --expected-pull-request 123` | 0 ok; 1 operation failed or invalid parameters; 3 API failure; 4 auth |
| `pr/test_pr_merged.py` | `--pull-request 123`; `--pull-request 123 --exit-100-on-merged` | 0 query succeeded, read `merged`; 2 config error or no such PR; 3 API failure; 4 auth; 100 merged, only with `--exit-100-on-merged` |
| `pr/test_pr_merge_ready.py` | `--pull-request 123`; `--pull-request 123 --expected-head-sha abc1234` | 0 ready to merge; 1 not ready; 2 PR not found; 3 API error; 4 auth |
| `pr/wait_for_unresolved_zero.py` | `--pull-request 123`; `--pull-request 123 --interval-seconds 180 --max-wait-seconds 900` | 0 three consecutive zero readings; 1 max wait elapsed; 2 invalid argument; 4 auth |
| `pr/check_suppressed_review_findings.py` | `--pull-request 123`; `--pull-request 123 --dispositions-file dispositions.json` | 0 report printed; 2 pull request number not positive, bad owner or repo, or plugin lib missing; 3 review fetch failed; 4 auth |
| `pr/check_review_thread_resolution_shas.py` | `--pull-request 123`; `--pull-request 123 --repo-path .` | 0 ok; 2 pull request number not positive, bad owner or repo, or plugin lib missing; 3 markdown parser missing or thread fetch failed; 4 auth |
| `pr/run_completion_gate.py` | `--pull-request 123`; `--pull-request 123 --json`; `--pull-request 123 --verify-config-only` | 0 all criteria passed; 1 a criterion failed or errored; 2 config or usage error, including an untrusted config; 3 external error or `verdict: unknown`; 4 auth |
