# QA Patterns: Session Protocol Validation

**Context**: Verification of CI workflow logic for session protocol validation

**Last Updated**: 2025-12-29 (Session 96)

## Date Filtering Patterns

### ISO 8601 String Comparison

**Pattern**: Use bash string comparison `<` for ISO 8601 dates (YYYY-MM-DD)

**Rationale**: Lexicographic ordering matches chronological ordering for ISO 8601 format

**Example**:
```bash
CUTOFF_DATE="2025-12-21"
file_date="${filename:0:10}"  # Extract YYYY-MM-DD

if [[ "$file_date" < "$CUTOFF_DATE" ]]; then
  # File is before cutoff
fi
```

**Verified Correctness**:
- "2025-12-20" < "2025-12-21" → TRUE
- "2025-12-21" < "2025-12-21" → FALSE (correctly excludes equality)
- "2024-12-31" < "2025-01-01" → TRUE

**When to Use**: Filtering files by date prefix in filenames

**When NOT to Use**: Dates not in ISO 8601 format (e.g., MM/DD/YYYY)

## Safe Default Pattern

**Pattern**: Include unknown/malformed items for validation when filtering

**Rationale**: False negatives (skipping validation) are worse than false positives (extra validation)

**Example**:
```bash
if [[ "$file_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  # Valid format, apply date logic
  if [[ "$file_date" < "$CUTOFF_DATE" ]]; then
    SKIP_LIST="${SKIP_LIST}${file}"
  else
    VALIDATE_LIST="${VALIDATE_LIST}${file}"
  fi
else
  # Invalid/unknown format, safe default: validate
  VALIDATE_LIST="${VALIDATE_LIST}${file}"
fi
```

**When to Use**: Quality gates, validation workflows, filtering operations

**Anti-Pattern**: Silently skipping unknown items (creates blind spots)

## Edge Case Verification

**Critical Edge Cases for Date Filtering**:

1. **Exact boundary date**:
   - Date ON cutoff should be validated (not skipped)
   - Verify operator: `<` not `<=`

2. **Malformed filename**:
   - Non-standard formats should default to validation
   - Regex validation before date comparison

3. **Empty result set**:
   - All files skipped → set flag `has_sessions=false`
   - Downstream jobs check flag before running

4. **Mixed old/new files**:
   - Correctly partition into skip/validate lists
   - JSON array contains only validate list

## JSON Array Construction

**Pattern**: Use jq for safe JSON array construction from bash variables

**Example**:
```bash
FILES="file1.md
file2.md
file3.md"

JSON_ARRAY=$(echo "$FILES" | jq -R -s -c 'split("\n") | map(select(length > 0))')
# Result: ["file1.md","file2.md","file3.md"]
```

**Flags**:
- `-R`: Raw string input (not JSON)
- `-s`: Slurp entire input
- `-c`: Compact output
- `select(length > 0)`: Filter empty strings

**When to Use**: Building GitHub Actions matrix from bash script

**Why jq**: Handles escaping, special characters, produces valid JSON

## QA Testing Approach

### Static Analysis for Workflow Logic

**When**: Validating bash/YAML workflow changes without runtime testing

**Approach**:
1. Extract critical code paths (date comparison, filtering, JSON construction)
2. Create test scenario matrix (happy path, edge cases)
3. Manually trace execution for each scenario
4. Verify correct output for each path

**Advantages**:
- Fast feedback (no CI runtime required)
- Comprehensive edge case coverage
- Documents expected behavior

**Limitations**:
- Cannot catch runtime-specific issues (environment variables, GitHub Actions context)
- Requires deep understanding of bash semantics

**Recommendation**: Follow up with integration test for high-risk changes

## Session 96 Findings

**Feature**: Issue #215 - Skip validation for historical session files before 2025-12-21

**Implementation**: `.github/workflows/ai-session-protocol.yml` lines 63-82

**Test Coverage**: 6/6 scenarios (100%)
- Before cutoff (2025-12-20)
- On cutoff (2025-12-21)
- After cutoff (2025-12-29)
- Non-standard filename
- All files historical
- Mix old/new files

**Edge Cases**: 4/4 verified
- Exact boundary (2025-12-21 validated, not skipped)
- Malformed date (safe default: validate)
- Empty list (has_sessions=false)
- Filename with description suffix (correct extraction)

**Verdict**: PASS (all scenarios verified via static analysis)

**Recommendations**:
- Add integration test with sample files (P2)
- Document cutoff date inline (P2)

## Related Memories

- `ci-infrastructure-workflow-required-checks`: Workflow execution patterns
- `workflow-patterns-matrix-artifacts`: Matrix strategy patterns
- `validation-baseline-triage`: Validation workflow design
