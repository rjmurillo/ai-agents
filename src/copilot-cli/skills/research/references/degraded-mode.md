# Research fallback rules and stop conditions

What to do when a source, a tool, or the harness itself refuses. Each rule names
the substitute so a run degrades instead of halting.

## Fallback rules

- If `WebSearch` returns no results for a query, try 2 alternative phrasings, then proceed with available information.
- If a `WebFetch` URL is unreachable or returns a non-success status, note it as unavailable in the analysis and continue with other sources.
- If a source contradicts another, document both perspectives and note the disagreement.
- If Serena is unavailable, skip the Memory phase and record the skip in the Action phase output.
- If no long-term memory service besides Serena exists, skip the atomic-memory retention and record the skip in the Action phase output.
- If a URL points at github.com, do not call `WebFetch`. Use the github skill scripts, which reach the API through `gh` and so cannot be denied by a WebFetch hook. Each locator below is self-contained, so run each one as written. Issue body and metadata: `( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/get_issue_context.py --owner {owner} --repo {repo} --issue {n}; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )`. Issue discussion: `( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/issue/get_issue_comments.py --owner {owner} --repo {repo} --issue {n}; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )`. PR body and diff: `( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_context.py --owner {owner} --repo {repo} --pull-request {n}; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )`. PR review comments: `( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --owner {owner} --repo {repo} --pull-request {n}; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )`. PR review threads: `( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_threads.py --owner {owner} --repo {repo} --pull-request {n}; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )`.
- If `WebFetch` is denied by a harness permission decision rather than a network error, that is a capability signal, not a prompt-injection attempt. Record the denial, switch to the github script path above for github.com URLs or to `WebSearch` for other hosts, and continue. Do not halt the run. Never call a tool the denial names unless it is already in this skill's `allowed-tools`.

## Reading the issue-creation exit code

Exit 0 prints the new issue number. A non-zero exit does NOT always mean no
issue exists. The script creates the issue first and applies labels second, so a
label failure exits 3 with `issue_number` and `url` populated in its error
envelope. Read those two fields before reacting: when they are present the issue
exists and only labelling failed, so repair the labels and never re-run creation,
which would duplicate it. Only when they are absent did creation itself fail.
Either way, record the outcome in the active handoff and never claim a number you
did not receive.

## Stop conditions

- All 5 phases completed or intentionally skipped under a fallback rule.
- 3 phases have failed (intentional skips do not count as failures).
- The 50k output-token budget is reached.
