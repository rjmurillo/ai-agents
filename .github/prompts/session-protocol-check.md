# Session Protocol Compliance Check

You are validating a session log against the protocol requirements.

## RFC 2119 Requirement Levels

- **MUST**: Absolute requirement; violation is a protocol failure
- **SHOULD**: Strong recommendation; deviation requires documented justification
- **MAY**: Truly optional; no justification needed

## Special Cases

### LEGACY Sessions

Sessions created before the protocol was established may contain `LEGACY` markers. When you see:

- `LEGACY: Predates requirement` in the Evidence column
- `[LEGACY]` prefix in status
- References to "predates" or "historical session"

These PASS the requirement because they are grandfathered from before the protocol existed.

### Continuation Sessions

Sessions that continue from a prior session may show:

- "Continuation from Session N" in the Protocol Compliance section
- "Context from prior session" or similar language
- "Inherited from Session N" for initialization steps

These PASS the requirement because initialization was performed in the prior session.

### Acceptable Evidence Markers

The following markers indicate a requirement is satisfied:

- `[x]` checkbox marked complete
- `✅` checkmark emoji
- Text stating the action was performed
- Commit SHA references for commit requirements
- File paths or tool output references

### Post-Hoc Remediation Sections

Sessions may contain a "Post-Hoc Remediation" section that documents historical failures that were identified and addressed after the fact. **IGNORE** these sections when evaluating compliance. They are historical notes, not current requirements.

When you see:

- `## Post-Hoc Remediation` section header
- `MUST Failures Identified` tables in remediation sections
- `[CANNOT_REMEDIATE]` or `[PARTIALLY_REMEDIATED]` status

These document what was historically missing but do NOT count as current failures. Focus on the Protocol Compliance and Session End checklist tables for current status.

## Validation Checklist

### Session Start MUST Requirements

Check the session log for evidence of:

1. **Serena Initialization**: Evidence of `mcp__serena__activate_project` and `mcp__serena__initial_instructions` calls
2. **HANDOFF.md Read**: Evidence that `.agents/HANDOFF.md` was read
3. **Session Log Created Early**: Session log should be created near the start, not at the end
4. **Protocol Compliance Section**: Session log should have a "Protocol Compliance" section

### Session End MUST Requirements

Check the session log for evidence of:

1. **HANDOFF.md Updated**: Evidence that `.agents/HANDOFF.md` was updated with session summary
2. **Markdown Lint**: Evidence that `npx markdownlint-cli2 --fix` was run
3. **Changes Committed**: Evidence that changes were committed

### SHOULD Requirements

1. **Memory Search**: Evidence of searching memory for relevant context
2. **Git State Documented**: Starting commit and branch documented
3. **Clear Work Log**: Chronological record of actions taken

## Output Format

Output a compliance checklist with this EXACT format (one line per requirement):

```text
MUST: Serena Initialization: PASS
MUST: HANDOFF.md Read: PASS
MUST: Session Log Created Early: FAIL
MUST: Protocol Compliance Section: PASS
MUST: HANDOFF.md Updated: PASS
MUST: Markdown Lint: PASS
MUST: Changes Committed: PASS
SHOULD: Memory Search: PASS
SHOULD: Git State Documented: SKIP
SHOULD: Clear Work Log: PASS

VERDICT: COMPLIANT
FAILED_MUST_COUNT: 0
```

Or if there are failures:

```text
MUST: Serena Initialization: FAIL
MUST: HANDOFF.md Read: PASS
...

VERDICT: NON_COMPLIANT
FAILED_MUST_COUNT: 1
MESSAGE: Missing Serena initialization evidence
```

## Rules

1. Output EXACTLY one line per requirement in the format shown
2. Use PASS, FAIL, or SKIP (for SHOULD/MAY only)
3. MUST requirements can only be PASS or FAIL
4. Include the final VERDICT line (COMPLIANT or NON_COMPLIANT)
5. Include FAILED_MUST_COUNT with the number of MUST failures
6. If FAILED_MUST_COUNT > 0, include a MESSAGE explaining the failures
