# Composite Action Encapsulation Pattern

**Statement**: Centralize Copilot CLI invocation in a reusable composite action

**Context**: AI-powered CI/CD workflows

**Evidence**: Session 13 - Eliminated duplication across 4 workflows

**Atomicity**: 95%

**Impact**: 9/10

## Why

Eliminates duplication of:

- Node.js/npm setup
- Authentication
- Agent loading
- Prompt building
- Verdict parsing

## Implementation

`.github/actions/ai-review/action.yml`

**Inputs**:

- `agent`: Agent name (analyst, critic, qa, roadmap, etc.)
- `context-type`: pr-diff, issue, session-log, spec-file
- `additional-context`: Extra context to append
- `prompt-file`: Path to prompt template
- `bot-pat`: GitHub PAT for API access
- `copilot-token`: Copilot authentication token

**Outputs**:

- `verdict`: PASS | WARN | CRITICAL_FAIL
- `findings`: Full AI response text
- `labels`, `milestone`: Parsed structured data
