# Agent drift alert

## Symptom

The weekly [Agent Drift Detection](../../.github/workflows/drift-detection.yml)
workflow (Monday, 09:00 UTC) opened or updated an issue titled
"Agent Drift Detected - `<date>`" with the `drift-detected` and `automated`
labels. `scripts/ci/drift_create_alert_issue.py` builds the issue body from
[.github/prompts/drift-alert-issue.md](../../.github/prompts/drift-alert-issue.md),
filling in the date, the run link, and the drift details. The commands in that
body omit `--fail-on-install-drift`; use the Confirm command below instead.

The audit makes two comparisons. It compares the Claude agents in
`src/claude/agents/` with the VS Code and Copilot agents in
`src/vs-code-agents/`. It also compares the install copies in `.claude/agents/`
with those in `.github/agents/` for agents built from shared templates.

## Confirm

Run the same audit the workflow runs, with the same flags as
`scripts/ci/drift_run_detection.py`:

```bash
uv run --frozen python build/scripts/detect_agent_drift.py --output-format text --fail-on-install-drift
```

Keep `--fail-on-install-drift`. Without it, drift between the install copies is
reported but does not change the exit code, so an alert can look like noise.
The audit ends with a `RESULT:` line and exits 0 when nothing drifts. For detail, add `--output-format markdown` or `--output-format json`.
The default similarity threshold is 80 percent; change it with
`--similarity-threshold`.

## Recover

1. Decide whether the drift is intended. Most drift comes from a hand edit to a
   generated agent file.
2. Fix the source, not the output. The audit names the comparison on each
   agent line: `[src-claude vs src-vscode]` for the vendored pair or
   `[.claude/agents vs .github/agents]` for the install pair. Match the
   template to the side that holds the defect:

   - Claude side (`src/claude/agents/` or `.claude/agents/`): edit
     `templates/agents/<name>.claude.md.tmpl` or a partial it includes.
   - VS Code or Copilot side (`src/vs-code-agents/`, `src/copilot-cli/`, or
     `.github/agents/`): edit `templates/agents/<name>.copilot.md.tmpl` or a
     partial it includes.

   Do not fix drift in `templates/agents/<name>.shared.md`. `build_all.py`
   renders every agent tree from the two templates above, so an edit to the
   shared file reaches no agent and the next full build erases a fix made
   with `generate_agents.py`. Rebuild, commit, then check:

   ```bash
   uv run python build/scripts/build_all.py
   uv run python build/scripts/build_all.py --check
   ```

   Run the check after you commit the template and its outputs. Before the
   commit, it reports the changed outputs as stale.

3. Rerun the audit until it exits 0.
4. Open the PR with the `push-pr` skill. Close the alert issue with a link to
   the merged PR.

If the difference is intended, record why in the issue and in the template,
then close the issue.

## Escalate

`templates/agents/` and `build/scripts/` belong to `@rjmurillo`
(`.github/CODEOWNERS`).

## Links

- [CONTRIBUTING.md: CI Drift Detection](../../CONTRIBUTING.md#ci-drift-detection)
- [CONTRIBUTING.md: Do Not Edit Generated Files](../../CONTRIBUTING.md#important-do-not-edit-generated-files)
