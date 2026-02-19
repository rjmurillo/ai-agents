# Skill-Cost-007: Haiku for Quick Tasks

**Statement**: Use Haiku model for quick, straightforward tasks

**Context**: When task does not require deep reasoning or large context

**Action Pattern**:
- SHOULD use `model: "haiku"` parameter for simple tasks
- SHOULD use Haiku for: linting, formatting, simple searches, status checks
- SHOULD NOT use Haiku for: complex reasoning, large refactors, architectural decisions

**Trigger Condition**:
- Task is mechanical (run command, format output)
- Task requires minimal context
- Task has clear success criteria

**Evidence**:
- COST-GOVERNANCE.md lines 154, 159-164
- SESSION-PROTOCOL.md line 243

**Quantified Savings**:
- Haiku input: $0.25/M vs Opus: $15/M (98% savings)
- Haiku output: $1.25/M vs Opus: $75/M (98% savings)
- Example: 10M token lint task
  - Opus: 10M × $15 = $150
  - Haiku: 10M × $0.25 = $2.50
  - Savings: $147.50 per task

**RFC 2119 Level**: SHOULD (SESSION-PROTOCOL line 243)

**Atomicity**: 96%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-20

**Validated**: 2 (COST-GOVERNANCE, SESSION-PROTOCOL)

**Category**: Claude API Token Efficiency

**Haiku-Appropriate Tasks**:
- Running markdown lint
- Formatting JSON/YAML
- Simple file searches
- Git status checks
- Directory listings

**Opus-Required Tasks**:
- Architectural design
- Complex refactoring
- Multi-file coordination
- Nuanced code review
- Strategic planning

**Pattern**:
```python
# For simple tasks
Task(
    subagent_type="implementer",
    prompt="Run markdownlint --fix on all .md files",
    model="haiku"
)
```
