---
name: Prompt Eval Requirements
applyTo: "{.claude/agents/*.md,src/claude/*.md,src/copilot-cli/*.md,src/vs-code-agents/*.md,.claude/skills/*/SKILL.md,.claude/commands/*.md,.github/prompts/*.md}"
priority: 9
version: 1.0.0
status: active
---

# Prompt Behavioral Eval Requirements (ADR-057)

## Scope

**Applies to**: Agent definitions, skill definitions, command prompts, and quality gate prompts.

When editing any file matched by `applyTo`, you MUST also create or update the corresponding scenario file.

## Rules

### MUST: Include or update scenario file

When editing a file that requires behavioral evaluation (per ADR-057), the commit MUST include:

1. A scenario file at `tests/evals/<name>-scenarios.json` (or update existing)
2. At least one scenario per decision branch the change introduces or modifies
3. At least one regression scenario for existing behavior the change could affect

### Scenario file naming convention

| Source File Pattern | Scenario File |
|---|---|
| `.claude/agents/<name>.md` | `tests/evals/agent-<name>-scenarios.json` |
| `src/claude/<name>.md` | `tests/evals/agent-<name>-scenarios.json` |
| `.claude/skills/<name>/SKILL.md` | `tests/evals/skill-<name>-scenarios.json` |
| `.claude/commands/<name>.md` | `tests/evals/command-<name>-scenarios.json` |
| `.github/prompts/<name>.md` | `tests/evals/prompt-<name>-scenarios.json` |

### Scenario file format

```json
{
  "scenarios": [
    {
      "id": "S1",
      "desc": "What this scenario tests",
      "input": "Simulated context the LLM receives",
      "expected_verdict": "EXPECTED_OUTPUT_CATEGORY",
      "expected_reason_contains": "keyword",
      "rationale": "Why this is expected"
    }
  ]
}
```

### When to skip

- Structural-only changes (sections added, renamed, moved) with no behavioral impact
- Documentation changes within the file (comments, examples) that don't alter instructions
- Must explicitly state "structural-only, no eval needed" in commit message

### Running evals

```bash
# Full suite (auto-detects changes):
python3 scripts/eval/eval-suite.py

# Specific agent:
python3 scripts/eval/eval-agents.py --agent <name> --dry-run

# Before/after comparison:
python3 scripts/eval/eval-prompt-change.py \
  --prompt .claude/agents/<name>.md \
  --scenarios tests/evals/agent-<name>-scenarios.json \
  --base-ref main
```

## References

- [ADR-057](../../.agents/architecture/ADR-057-prompt-behavioral-evaluation.md)
- [Methodology](../../.agents/testing/prompt-eval-methodology.md)
- [Eval README](../../scripts/eval/README.md)
