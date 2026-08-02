# Agent Drift Detected

**Detection Date**: $DETECTION_DATE
**Workflow Run**: $SERVER_URL/$REPOSITORY/actions/runs/$RUN_ID

## Agents with Drift

$DRIFT_DETAILS

## Recommended Actions

1. Review the differences listed above
2. Determine if drift is intentional or accidental
3. Either:
   - Update Claude agents to match shared content
   - Update shared templates to include Claude improvements
   - Document the intentional difference

## Related Files

- Claude agents: `src/claude/`
- Shared templates: `templates/agents/`
- VS Code agents: `src/vs-code-agents/`

## Commands

```bash
# Run drift detection locally
python3 build/scripts/detect_agent_drift.py

# See detailed JSON output
python3 build/scripts/detect_agent_drift.py --output-format json
```
