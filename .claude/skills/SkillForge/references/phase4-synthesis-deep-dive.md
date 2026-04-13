
**Panel:** 3-4 Opus agents with distinct evaluative lenses
**Requirement:** Unanimous approval (all agents)
**Fallback:** Return to Phase 1 with feedback (max 5 iterations)

### Panel Composition

| Agent | Focus | Key Criteria | When Active |
|-------|-------|--------------|-------------|
| **Design/Architecture** | Structure, patterns, correctness | Pattern appropriate, phases logical, no circular deps | Always |
| **Audience/Usability** | Clarity, discoverability, completeness | Triggers natural, steps unambiguous, no assumed knowledge | Always |
| **Evolution/Timelessness** | Future-proofing, extension, ecosystem | Score ≥7, extension points clear, ecosystem fit | Always |
| **Script/Automation** | Agentic capability, verification, quality | Scripts follow patterns, self-verify, documented | When scripts present |

### Script Agent (Conditional)

The Script Agent is activated when the skill includes a `scripts/` directory. Focus areas:

| Criterion | Checks |
|-----------|--------|
| **Pattern Compliance** | Result dataclass, argparse, exit codes |
| **Self-Verification** | Scripts can verify their own output |
| **Error Handling** | Graceful failures, actionable messages |
| **Documentation** | Usage examples in SKILL.md |
| **Agentic Capability** | Can run autonomously without human intervention |

**Script Agent Scoring:**

| Score | Meaning |
|-------|---------|
| 8-10 | Fully agentic, self-verifying, production-ready |
| 6-7 | Functional but missing some agentic capabilities |
| <6 | Requires revision - insufficient automation quality |

### Agent Evaluation

Each agent produces:

```markdown
## [Agent] Review

### Verdict: APPROVED / CHANGES_REQUIRED

### Scores
| Criterion | Score (1-10) | Notes |
|-----------|--------------|-------|

### Strengths
1. [Specific with evidence]

### Issues (if CHANGES_REQUIRED)
| Issue | Severity | Required Change |
|-------|----------|-----------------|

### Recommendations
1. [Even if approved]
```

### Consensus Protocol

```
IF all agents APPROVED (3/3 or 4/4):
    → Finalize skill
    → Run validate-skill.py
    → Update registry
    → Complete

ELSE:
    → Collect all issues (including script issues)
    → Return to Phase 1 with issues as input
    → Re-apply targeted questioning
    → Regenerate skill and scripts
    → Re-submit to panel

IF 5 iterations without consensus:
    → Flag for human review
    → Present all agent perspectives
    → User makes final decision
```

See: [references/synthesis-protocol.md](references/synthesis-protocol.md)
