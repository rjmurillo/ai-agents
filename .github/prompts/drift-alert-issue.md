# Agent Drift Detected

**Detection Date**: $DETECTION_DATE
**Workflow Run**: $SERVER_URL/$REPOSITORY/actions/runs/$RUN_ID

## Agents with Drift

$DRIFT_DETAILS

## Recommended Actions

Follow the runbook:
$SERVER_URL/$REPOSITORY/blob/main/docs/runbooks/agent-drift-alert.md

1. Review the differences listed above
2. Determine if drift is intentional or accidental
3. Either:
   - Fix the agent template for the side that drifted
   - Record intended drift in `build/scripts/detect_agent_drift.py`

## Related Files

- Claude agents: `src/claude/`
- Shared templates: `templates/agents/`
- VS Code agents: `src/vs-code-agents/`

## Commands

```bash
# Run drift detection locally, with the flags the workflow uses
uv run --frozen python build/scripts/detect_agent_drift.py --output-format text --fail-on-install-drift

# See detailed JSON output
uv run --frozen python build/scripts/detect_agent_drift.py --output-format json --fail-on-install-drift
```
