# ADR-044: ADR Exception Criteria (Chesterton's Fence)

## Status

Accepted

## Date

2026-03-07

## Context

ADR-005 received a Python exception in PR #908 (Claude Code Hooks) without documented justification. The exception was technically valid but the rationale — why the PowerShell-only rule exists, what alternatives were tried, and what precedent risks the exception introduces — was not captured at the time.

This creates two problems:

1. **Future maintainers** cannot assess whether the exception was well-reasoned or expedient.
2. **Future exception requests** have a precedent (PR #908) showing that exceptions can be granted informally.

The broader issue is that ADR exceptions are structurally easier to create than to challenge. An exception adds a few lines to an ADR; challenging an exception requires understanding the original decision's full context. Chesterton's Fence analysis corrects this asymmetry by requiring that context to be documented before approval.

## Decision

**ADR exceptions MUST include a Chesterton's Fence analysis before approval.**

The analysis MUST answer three questions:

1. **Why does the rule exist?** — Quote the original ADR rationale. Paraphrase is not acceptable.
2. **Impact if removed?** — Document what breaks, degrades, or sets problematic precedent.
3. **Alternatives tried?** — List at least two compliance attempts and their outcomes.

Exceptions that do not include this analysis are rejected by the architect agent.

The analysis template and rejection criteria are documented in `.agents/governance/ADR-EXCEPTION-CRITERIA.md`.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Status quo** (no analysis required) | No friction | PR #908 shows exceptions become informal; rationale lost | Rejected: PR #908 is concrete evidence of the failure mode |
| **Blanket prohibition** (no exceptions ever) | Eliminates exception abuse | Inflexible; some exceptions are legitimate (e.g., PR #760 SkillForge, PR #908 Anthropic SDK) | Rejected: legitimate cases exist |
| **Architect approval without documentation** | Faster approval | Loses rationale for future reference; approval authority leaves organization | Rejected: documentation is the point |
| **Chesterton's Fence analysis (chosen)** | Forces understanding before exception; documents rationale for future maintainers; intentional friction discourages unnecessary exceptions | Slows exception process; requires effort | Accepted: friction is intentional and proportionate |

### Trade-offs

**Intentional friction is a feature.** The extra documentation effort is designed to raise the cost of creating an unnecessary exception above the cost of complying with the original ADR. If compliance is genuinely impossible, the analysis should take 30 minutes. If compliance was never seriously attempted, the analysis will expose that.

**Rubber stamp risk is mitigated by requiring direct quotes.** Requiring the original ADR rationale to be quoted (not paraphrased) means the requestor must actually read the decision. This is a lightweight but effective quality gate.

## Consequences

### Positive

- Future exceptions include rationale that survives team turnover.
- Exception requests that skip alternatives analysis are surfaced and rejected early.
- ADR authority is preserved: exceptions document trade-offs rather than undermining rules silently.
- PR #908-style informal exceptions are no longer accepted.

### Negative

- Exception process takes longer (intentional).
- Documentation burden increases for legitimate exceptions.
- Some teams may perceive this as bureaucratic overhead.

### Neutral

- Existing exceptions (PR #760 SkillForge, PR #908 Claude Code Hooks) are retroactively documented in `.agents/governance/ADR-EXCEPTION-CRITERIA.md` as examples — they remain valid.

## Implementation Notes

1. `.agents/governance/ADR-EXCEPTION-CRITERIA.md` — criteria document and exception template (this PR).
2. `src/claude/architect.md` — exception validation checklist added to ADR Review section (this PR).
3. Existing ADR-005 exceptions remain valid; no retroactive revocation.

## Related Decisions

- [ADR-005](./ADR-005-powershell-only-scripting.md) — Motivating case (PR #908 exception)
- [ADR-022](./ADR-022-architecture-governance-split-criteria.md) — Governance split criteria

## References

- GitHub Issue #947
- GitHub Issue #938 (criteria document)
- PR #908 (Claude Code Hooks exception — motivating incident)
- PR #760 (SkillForge exception — positive example)
- `.agents/governance/ADR-EXCEPTION-CRITERIA.md`
