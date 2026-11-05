# Agent drift alert

## Symptom

The scheduled [Agent Drift Detection](../../.github/workflows/drift-detection.yml)
workflow opened or updated an issue titled
"Agent Drift Detected - `<date>`" with the `drift-detected` and `automated`
labels. `scripts/ci/drift_create_alert_issue.py` builds the issue body from
[.github/prompts/drift-alert-issue.md](../../.github/prompts/drift-alert-issue.md),
filling in the date, the run link, and the drift details. The body links back
to this runbook.

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

1. Decide whether the drift is intended. A human owner (`@rjmurillo`) makes
   that call, not an agent. An agent must not add a baseline entry until the
   owner confirms the drift is intended. Most drift comes from a hand edit to a
   generated agent file. For intended drift, skip to the last part of this
   section.
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

If the difference is intended, accept it in code, not only in the issue.
Closing the issue alone does not stop the alert. The next scheduled run finds
the same drift and reports it again, as a new issue or as a comment on an open
`drift-detected` issue. In the same PR, add an entry to
`build/scripts/detect_agent_drift.py`:

- Low similarity: add `(agent, comparison)` to `KNOWN_BASELINE_DRIFT`, with
  the measured score as the floor. The audit then reports `OK (baselined)`
  while the score stays at or above that floor.
- Missing section: add `(agent, section, comparison)` to
  `KNOWN_MISSING_SECTIONS`. The audit then reports `MISSING (baselined)`.

Use the comparison label from the audit line, such as `src-claude vs src-vscode`
or `.claude/agents vs .github/agents`. Put the reason in a comment above the
entry. Neither table covers drift in a required section; fix that in the
template. Rerun the audit until it exits 0, then close the issue with a link to
the merged PR.

## Escalate

`templates/agents/` and `build/scripts/` belong to `@rjmurillo`
(`.github/CODEOWNERS`).

## Links

- [Template render map](../../templates/AGENTS.md): which template renders
  which agent tree.
- [Build pipeline notes](../../build/AGENTS.md): `build_all.py` and
  `detect_agent_drift.py`.

The CONTRIBUTING.md sections "CI Drift Detection" and "Do Not Edit Generated
Files" cover the PR-time `agent-drift-detection.yml` check, not the scheduled
alert. They name `generate_agents.py` as the regenerate command. The steps above
use `build_all.py`, which [build/AGENTS.md](../../build/AGENTS.md) describes as
the whole render sequence. If the two disagree for your change, ask the owner.
