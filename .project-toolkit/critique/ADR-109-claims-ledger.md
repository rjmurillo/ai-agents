# ADR-109 claims ledger

Verified 2026-11-22 for issue #7493.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| Parser-free recall uses a dated heading on the first body line. | Behavior | Run the copied plugin's registered hook with a dated heading in a fixture memory. | The hook displays the title from the heading. |
| The fallback uses the filename stem. | Behavior | Move the fixture into a nested memory folder and run the registered hook. | The hook displays the stem without the folder. |
| Loaded confidence defaults to zero. Search computes the displayed value. | Behavior | Read the fallback in `serena_integration.py` and the scoring in `search.py`. | The fallback loads zero. The installed hook displays a computed nonzero score. |
| Dispatcher failures report on stderr and preserve the prompt. | Behavior | Move the copied plugin's recall shim aside and run the registered hook. | Exit zero, empty stdout, and two stderr lines. |
| The host has a 15-second registration timeout. | Count | Read the recall registration in `src/claude/hooks/hooks.json`. | The registration sets 15 seconds. Host timeout behavior remains unverified. |
| The dispatcher does not enforce the shim timeout. | Behavior | Read the dispatcher contract and manifest for the recall group. | The manifest sets 10 seconds for the shim. The dispatcher delegates timeout enforcement to the host. |
| The launcher filters PATH and checks Python symlink targets. | Behavior | Run `tests/hooks/test_plugin_memory_recall_runtime.py`. | Checkout candidates were rejected. The external test interpreter ran. |
| Ripgrep ignores inherited configuration. | Behavior | Run `test_rg_returns_paths` in `tests/test_memory_search.py`. | The invoked command includes `--no-config`. |
| The 256 KiB cap applies to the Python loader. | Behavior | Search a fixture with a match beyond 256 KiB, then call `load_memory` with the cap. | Ripgrep and grep found the match. The loader skipped the file. |

## Second pass, 2026-11-25

Rows for the amendment section, first titled "`metrics-analysis.prompt.md` has no workflow reader" and retitled "effects of deleting the agent-environment jobs" on 2026-11-26. Commands ran on 2026-11-25 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| ai-metrics-analysis.yml no longer exists | absence | `test ! -e .github/workflows/ai-metrics-analysis.yml && echo absent` | VERIFIED: absent |
| Commit 3f145f26fd (2026-11-25) deleted it | behavior | `git show --format=%cs --name-status 3f145f26fd -- .github/workflows/ai-metrics-analysis.yml \| tr '\n' ' '` | VERIFIED: 2026-11-25 D .github/workflows/ai-metrics-analysis.yml |
| 2026-11-19 amendment text about metrics-analysis.prompt.md | quote | `grep -n 'stays as an input the `ai-metrics-analysis.yml` workflow reads' .project-toolkit/architecture/ADR-109-template-first-plugin-distribution.md \| head -n 1` | VERIFIED: 271:The tenth, `metrics-analysis.prompt.md`, stays as an input the `ai-metrics-analysis.yml` workflow reads. |
| metrics-analysis.prompt.md is still in the tree | path | `test -f .github/prompts/metrics-analysis.prompt.md && echo present` | VERIFIED: present |
| No workflow names metrics-analysis.prompt.md | absence | `git grep -l -F 'metrics-analysis.prompt.md' -- .github/workflows \| wc -l` | VERIFIED: 0 |
| Before the deletion one workflow named each of the five other files | behavior | `for f in artifact-insight-scan.md merge-conflict-analysis.md pr-comment-triage.md spec-check-completeness.md spec-trace-requirements.md; do printf '%s=%s ' "$f" "$(git grep -l -F "$f" 3f145f26fd^ -- .github/workflows \| sed 's#.*/##' \| tr '\n' ',')"; done` | VERIFIED: artifact-insight-scan.md=artifact-insight-scanner.yml, merge-conflict-analysis.md=pr-maintenance.yml, pr-comment-triage.md=pr-maintenance.yml, spec-check-completeness.md=ai-spec-review.yml, spec-trace-requirements.md=ai-spec-review.yml, |
| No workflow names any of the six files now | absence | `for f in metrics-analysis.prompt.md artifact-insight-scan.md merge-conflict-analysis.md pr-comment-triage.md spec-check-completeness.md spec-trace-requirements.md; do git grep -l -F "$f" -- .github/workflows; done \| wc -l` | VERIFIED: 0 |
| All six files are still in the tree | path | `cd .github/prompts && ls metrics-analysis.prompt.md artifact-insight-scan.md merge-conflict-analysis.md pr-comment-triage.md spec-check-completeness.md spec-trace-requirements.md \| wc -l` | VERIFIED: 6 |
| Commit 3f145f26fd deleted two of those reader workflows and modified pr-maintenance.yml, which remains | behavior | `git show --format= --name-status 3f145f26fd -- .github/workflows/artifact-insight-scanner.yml .github/workflows/pr-maintenance.yml .github/workflows/ai-spec-review.yml \| tr '\n' ' '` | VERIFIED: D .github/workflows/ai-spec-review.yml D .github/workflows/artifact-insight-scanner.yml M .github/workflows/pr-maintenance.yml |
| No job under .github declares an agent-* environment now (the "every other job" clause) | absence | `git grep -n -E '^\s*environment:\s*agent-' -- .github \| wc -l` | VERIFIED: 0 |

## Third pass, 2026-11-26

Rows for the text the reduced panel added on 2026-11-26: the seventh prompt file and the 2026-11-09 follow-up sentence about hook execution. Commands ran on 2026-11-26 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| `build_retrospective_prompt.py` reads `post-pr-retrospective.md` | path | `sed -n '22p' scripts/ci/build_retrospective_prompt.py` | VERIFIED: TEMPLATE_PATH = Path(".github/prompts/post-pr-retrospective.md") |
| Before the deletion one workflow ran that script | behavior | `git grep -l 'build_retrospective_prompt' 3f145f26fd^ -- .github/workflows \| tr '\n' ' '` | VERIFIED: 3f145f26fd^:.github/workflows/post-pr-retrospective.yml |
| No workflow runs that script now | absence | `git grep -l 'build_retrospective_prompt' -- .github \| wc -l` | VERIFIED: 0 |
| Commit 3f145f26fd deleted the post-pr-retrospective workflow | behavior | `git show --format= --name-status 3f145f26fd -- .github/workflows/post-pr-retrospective.yml \| tr '\t' ' '` | VERIFIED: D .github/workflows/post-pr-retrospective.yml |
| No workflow named `post-pr-retrospective.md` directly before or after | absence | `echo base=$(git grep -l -F 'post-pr-retrospective.md' 3f145f26fd^ -- .github/workflows \| wc -l) head=$(git grep -l -F 'post-pr-retrospective.md' -- .github/workflows \| wc -l)` | VERIFIED: base=0 head=0 |
| The seventh file is still in the tree | path | `ls .github/prompts/post-pr-retrospective.md` | VERIFIED: .github/prompts/post-pr-retrospective.md |
| The 2026-11-09 follow-up carries the quoted phrase | quote | `sed -n '73p' .project-toolkit/architecture/ADR-109-template-first-plugin-distribution.md \| grep -c -F 'stays with the environment-gated hook smoke and the opt-in `test_cli_stop_nudge_e2e.py`'` | VERIFIED: 1 |
| Before the deletion `plugin-cli-smoke.yml` had an environment-gated `smoke` job that ran the hook e2e test | behavior | `git show 3f145f26fd^:.github/workflows/plugin-cli-smoke.yml \| grep -n -E '^  smoke:$\|environment: agent-\|test_cli_hook_e2e' \| tr '\n' ' '` | VERIFIED: 29:#   - Hook smoke (test_cli_hook_e2e.py): a plugin hook resolves and runs from the 82:#   RUN_CLI_E2E=1 uv run --frozen pytest tests/e2e/test_cli_hook_e2e.py -m "smoke and claude" -v 193:  smoke: 201:    environment: agent-${{ matrix.cli }} 288:          uv run --frozen pytest tests/e2e/test_cli_h |
| Commit 3f145f26fd removed that job | absence | `git show 3f145f26fd:.github/workflows/plugin-cli-smoke.yml \| grep -c -E '^  smoke:$\|environment: agent-\|test_cli_hook_e2e'` | VERIFIED: 0 |
| No file under .github names either e2e test now | absence | `git grep -l -E 'test_cli_hook_e2e\|test_cli_stop_nudge_e2e' -- .github \| wc -l` | VERIFIED: 0 |
| Both e2e test files are still in the tree | path | `ls tests/e2e/test_cli_hook_e2e.py tests/e2e/test_cli_stop_nudge_e2e.py \| wc -l` | VERIFIED: 2 |
| The pre-push `hook-anchoring-e2e` job calls the `cli-hook-e2e` handler | path | `grep -n -A2 'name: hook-anchoring-e2e' lefthook.yml \| tr -s ' \n' ' '` | VERIFIED: 896: - name: hook-anchoring-e2e 897- timeout: 20m 898- run: uv run --frozen python scripts/validation/git_hook_policy.py cli-hook-e2e |
| That handler runs `tests/e2e/test_cli_hook_e2e.py` | path | `grep -n 'run_cli_e2e("tests/e2e/test_cli_hook_e2e.py"' scripts/validation/git_hook_policy.py \| tr -s ' ' ' '` | VERIFIED: 9544: return run_cli_e2e("tests/e2e/test_cli_hook_e2e.py", repo_root, binaries=CLI_HOOK_E2E_BINARIES) |
| The `smoke-claude-hooks` job is still in the workflow | path | `grep -n -E '^  smoke-claude-hooks:$' .github/workflows/plugin-cli-smoke.yml` | VERIFIED: 246:  smoke-claude-hooks: |

## Fourth pass, 2026-11-26, after the panel round

Rows added on 2026-11-26 after the panel round of that date, for sentences the round changed. Same working tree, head `879dff55b3` (2026-11-26), amendments uncommitted.

| Claim | Kind | Command | Result |
|---|---|---|---|
| load_ai_review_prompt.py reads default-ai-review.md | path | `grep -n 'default-ai-review' scripts/ci/load_ai_review_prompt.py` | VERIFIED: 16:DEFAULT_PROMPT_PATH = _REPO_ROOT / ".github" / "prompts" / "default-ai-review.md" |
| Only the ai-review action runs that script | absence | `git grep -n 'load_ai_review_prompt' -- .github` | VERIFIED: .github/actions/ai-review/action.yml:143:      run: python3 "$AI_REVIEW_ROOT/scripts/ci/load_ai_review_prompt.py" |
| No workflow uses the ai-review action now | absence | `git grep -c 'actions/ai-review' -- .github/workflows \| wc -l` | VERIFIED: 0 |
| Four workflows used the action before the deletion | count | `git grep -l 'actions/ai-review' 3f145f26fd^ -- .github/workflows \| sed 's/.*workflows.//' \| sort -u` | VERIFIED: ai-metrics-analysis.yml / ai-spec-review.yml / artifact-insight-scanner.yml / pr-maintenance.yml |
| The real-CLI cases of both e2e files skip without RUN_CLI_E2E=1, and no workflow names either file | behavior | `grep -n '_RUN = ' tests/e2e/test_cli_hook_e2e.py tests/e2e/test_cli_stop_nudge_e2e.py; git grep -c 'test_cli_hook_e2e\\|test_cli_stop_nudge_e2e' -- .github \| wc -l` | VERIFIED: tests/e2e/test_cli_hook_e2e.py:94:_RUN = os.environ.get("RUN_CLI_E2E") == "1" / tests/e2e/test_cli_stop_nudge_e2e.py:47:_RUN = os.environ.get("RUN_CLI_E2E") == "1" / 0 |
| hook-anchoring-e2e runs with -m "not copilot" and fails without claude on PATH | behavior | `sed -n '719p;721p;8982p;8989p;9544p' scripts/validation/git_hook_policy.py` | VERIFIED: CLI_HOOK_E2E_BINARIES = ("claude",) / CLI_E2E_LOCAL_MARKERS = "not copilot" / if not any(shutil.which(binary) for binary in binaries): / return 2 / return run_cli_e2e("tests/e2e/test_cli_hook_e2e.py", repo_root, binaries=CLI_HOOK_E2E_BINARIES) |
