# Skill-Cost-006: Memory Reads Enable Prompt Caching

**Statement**: Read task-specific memories before work to enable prompt caching

**Context**: At session start and before multi-step tasks

**Action Pattern**:
- MUST read relevant memories before starting work
- MUST read task-specific memories per SESSION-PROTOCOL Phase 2 table
- SHOULD read memories in consistent order for cache hits

**Trigger Condition**:
- Starting any non-trivial task
- Beginning multi-step analysis or implementation

**Evidence**:
- COST-GOVERNANCE.md line 153
- SESSION-PROTOCOL.md lines 241-242, 257-263

**Quantified Savings**:
- Cache read: $1.50/M vs no-cache: $15/M (90% savings)
- Example: 100M token session
  - No cache: 100M × $15 = $1,500
  - With cache: 10M × $15 + 90M × $1.50 = $150 + $135 = $285
  - Savings: $1,215 (81% reduction)

**RFC 2119 Level**: MUST (SESSION-PROTOCOL line 242)

**Atomicity**: 98%

**Tag**: helpful

**Impact**: 10/10

**Created**: 2025-12-20

**Validated**: 2 (COST-GOVERNANCE, SESSION-PROTOCOL)

**Category**: Claude API Token Efficiency

**Pattern**:
```python
# Read memories BEFORE work to enable caching
mcp__serena__read_memory(memory_file_name="skill-usage-mandatory")
mcp__serena__read_memory(memory_file_name="pr-comment-responder-skills")
mcp__serena__read_memory(memory_file_name="skills-pr-review")

# Now start work - cache hits on subsequent reads
```

**Key Insight**: Prompt caching makes repeated context reads nearly free
