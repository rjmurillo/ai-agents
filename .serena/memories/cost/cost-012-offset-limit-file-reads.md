# Skill-Cost-012: Limit File Reads with Offset/Limit

**Statement**: Use offset and limit parameters to avoid reading large files entirely

**Context**: When reading large files where only portion is needed

**Action Pattern**:
- SHOULD use `limit` parameter to read first N lines
- SHOULD use `offset` + `limit` to read specific sections
- MUST NOT read 10K+ line files without pagination
- SHOULD read symbols overview before deciding to read full file

**Trigger Condition**:
- File is >1000 lines
- Only need to inspect specific section
- Scanning for pattern in large file

**Evidence**:
- COST-GOVERNANCE.md line 155
- SESSION-PROTOCOL.md line 244

**Quantified Savings**:
- Example: 10K line file (500K tokens)
  - Full read: 500K × $15/M = $7.50
  - Limited read (100 lines): 5K × $15/M = $0.08
  - Savings: $7.42 per file

**RFC 2119 Level**: SHOULD (SESSION-PROTOCOL line 244)

**Atomicity**: 96%

**Tag**: helpful

**Impact**: 7/10

**Created**: 2025-12-20

**Validated**: 2 (COST-GOVERNANCE, SESSION-PROTOCOL)

**Category**: Claude API Token Efficiency

**Anti-Pattern**:
```python
# WRONG: Reading 10K line file when only need to check imports
Read(file_path="src/large_module.ts")
```

**Correct Pattern**:
```python
# CORRECT: Read first 50 lines to check imports
Read(file_path="src/large_module.ts", limit=50)

# OR: Read specific section
Read(file_path="src/large_module.ts", offset=100, limit=50)
```

**Best Practice**: Use Serena symbolic tools first
```python
# BEST: Use symbolic overview instead
mcp__serena__get_symbols_overview(relative_path="src/large_module.ts")
```
