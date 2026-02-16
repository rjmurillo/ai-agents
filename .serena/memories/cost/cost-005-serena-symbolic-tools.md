# Skill-Cost-005: Serena Symbolic Tools Over File Reads

**Statement**: Use Serena symbolic tools instead of reading entire files

**Context**: When analyzing code structure or searching for symbols

**Action Pattern**:
- MUST use `find_symbol` to locate code entities
- MUST use `get_symbols_overview` for file structure
- MUST use `search_for_pattern` for targeted searches
- MUST NOT read entire files when symbolic queries suffice

**Trigger Condition**:
- Need to find a class, method, or function
- Need to understand file structure
- Need to locate specific code patterns

**Evidence**:
- COST-GOVERNANCE.md line 152
- SESSION-PROTOCOL.md Phase 5 line 241

**Quantified Savings**:
- 80%+ token reduction vs full file reads
- Example: 50K token file read → 10K symbol overview
- At $15/M Opus input: $0.75 → $0.15 per file
- For 100 files/session: $75 → $15 = $60 saved

**RFC 2119 Level**: MUST (SESSION-PROTOCOL line 241)

**Atomicity**: 99%

**Tag**: helpful

**Impact**: 10/10

**Created**: 2025-12-20

**Validated**: 2 (COST-GOVERNANCE, SESSION-PROTOCOL)

**Category**: Claude API Token Efficiency

**Anti-Pattern**:
```python
# WRONG: Reading entire file to find one method
Read(file_path="src/large_file.ts")
```

**Correct Pattern**:
```python
# CORRECT: Use symbolic tools
mcp__serena__find_symbol(
    name_path_pattern="ClassName/methodName",
    relative_path="src/large_file.ts",
    include_body=True
)
```

**Impact Multiplier**: Compounds across sessions due to prompt caching
