# Agent drift alert

## Symptom

The weekly [Agent Drift Detection](../../.github/workflows/drift-detection.yml)
workflow (Monday, 09:00 UTC) opened or updated an issue titled
"Agent Drift Detected - `<date>`" with the `drift-detected` and `automated`
labels. The issue follows
[the drift alert template](../../.github/ISSUE_TEMPLATE/drift-alert.md).

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
2. Fix the source, not the output. Edit the shared template under
   `templates/agents/`, then regenerate and verify the generated files:

   ```bash
   uv run python build/generate_agents.py
   uv run python build/generate_agents.py --validate
   ```

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
