# Test Scenarios: Issue #215 - Historical Session Validation

**Feature**: Skip validation for session files before 2025-12-21
**Implementation**: `.github/workflows/ai-session-protocol.yml` lines 63-82

## Test Plan

### Test 1: Session Before Cutoff (2025-12-20)

**Input**: `.agents/sessions/2025-12-20-session-01.md`
**Expected**: SKIPPED (added to `SKIPPED_FILES`, excluded from matrix)
**Verification Logic**:
```bash
file_date="2025-12-20"
CUTOFF_DATE="2025-12-21"
[[ "$file_date" < "$CUTOFF_DATE" ]]  # TRUE (2025-12-20 < 2025-12-21)
```
**Expected Output**:
- Line 90: "Skipped historical sessions (before 2025-12-21):"
- Line 91: ".agents/sessions/2025-12-20-session-01.md"
- File NOT included in JSON matrix

### Test 2: Session On Cutoff Date (2025-12-21)

**Input**: `.agents/sessions/2025-12-21-session-53.md`
**Expected**: VALIDATED (included in matrix)
**Verification Logic**:
```bash
file_date="2025-12-21"
CUTOFF_DATE="2025-12-21"
[[ "$file_date" < "$CUTOFF_DATE" ]]  # FALSE (2025-12-21 NOT < 2025-12-21)
```
**Expected Output**:
- Line 102: "Session files to validate:"
- Line 103: ".agents/sessions/2025-12-21-session-53.md"
- File included in JSON matrix
- Validate job runs for this file

### Test 3: Session After Cutoff (2025-12-29)

**Input**: `.agents/sessions/2025-12-29-session-98.md`
**Expected**: VALIDATED (included in matrix)
**Verification Logic**:
```bash
file_date="2025-12-29"
CUTOFF_DATE="2025-12-21"
[[ "$file_date" < "$CUTOFF_DATE" ]]  # FALSE (2025-12-29 NOT < 2025-12-21)
```
**Expected Output**:
- File included in JSON matrix
- Validate job runs for this file

### Test 4: Non-Standard Filename

**Input**: `.agents/sessions/special-session-notes.md`
**Expected**: VALIDATED (safe default)
**Verification Logic**:
```bash
filename="special-session-notes.md"
file_date="${filename:0:10}"  # "special-se"
[[ "$file_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]  # FALSE (does not match regex)
# Falls through to ELSE branch (line 79-80)
CHANGED_FILES="${CHANGED_FILES}${file}"  # Included for validation
```
**Expected Output**:
- File included in JSON matrix
- Validate job runs for this file

### Test 5: All Files Before Cutoff

**Input**:
- `.agents/sessions/2025-12-15-session-01.md`
- `.agents/sessions/2025-12-18-session-02.md`
- `.agents/sessions/2025-12-20-session-03.md`

**Expected**: `has_sessions=false`, empty matrix `[]`
**Verification Logic**:
- All files fail `< CUTOFF_DATE` check
- All added to `SKIPPED_FILES`
- `CHANGED_FILES` remains empty
- Line 94-98: Empty check succeeds, outputs `has_sessions=false`

**Expected Output**:
- Line 96: "No validatable session files (all historical)"
- Output: `has_sessions=false`
- Output: `session_files=[]`
- Validate job skipped (condition `if: needs.detect-changes.outputs.has_sessions == 'true'`)

### Test 6: Mix of Old and New Files

**Input**:
- `.agents/sessions/2025-12-18-session-01.md` (old)
- `.agents/sessions/2025-12-20-session-02.md` (old)
- `.agents/sessions/2025-12-21-session-03.md` (cutoff, new)
- `.agents/sessions/2025-12-25-session-04.md` (new)

**Expected**: Only new files (2025-12-21, 2025-12-25) in matrix
**Verification Logic**:
- 2025-12-18 < 2025-12-21: TRUE → SKIPPED
- 2025-12-20 < 2025-12-21: TRUE → SKIPPED
- 2025-12-21 < 2025-12-21: FALSE → VALIDATED
- 2025-12-25 < 2025-12-21: FALSE → VALIDATED

**Expected Output**:
- Skipped: 2025-12-18-session-01.md, 2025-12-20-session-02.md
- JSON array: `[".agents/sessions/2025-12-21-session-03.md", ".agents/sessions/2025-12-25-session-04.md"]`
- Validate job runs 2 times (matrix with 2 files)

## Edge Case Analysis

### Edge Case 1: Exact Cutoff Date Boundary

**Critical Question**: Is 2025-12-21 included or excluded?
**Answer**: INCLUDED for validation

**Rationale**:
- The requirement states "Session End checklist requirement introduced 2025-12-21"
- Sessions ON 2025-12-21 should comply with the requirement
- Bash comparison `<` is strictly less than (not <=)
- Therefore 2025-12-21 is NOT less than 2025-12-21 → validated

**Risk**: None. This is correct behavior.

### Edge Case 2: Malformed Date (Invalid Format)

**Input**: `.agents/sessions/20251220-session.md` (missing hyphens)
**Expected**: VALIDATED (safe default)

**Verification**:
```bash
file_date="20251220-s"  # First 10 chars
[[ "$file_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]  # FALSE
# Line 79-80: Non-standard filename, include for validation
```

**Risk**: None. Safe default is correct (validate unknown formats).

### Edge Case 3: Empty Session Files List

**Input**: PR changes no session files
**Expected**: `has_sessions=false`, workflow exits early

**Verification**: Lines 52-57 handle this
**Risk**: None.

### Edge Case 4: Session Filename with Description

**Input**: `.agents/sessions/2025-12-20-session-01-autonomous-development.md`
**Expected**: SKIPPED (date extraction works correctly)

**Verification**:
```bash
filename="2025-12-20-session-01-autonomous-development.md"
file_date="${filename:0:10}"  # "2025-12-20"
[[ "$file_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]  # TRUE
[[ "2025-12-20" < "2025-12-21" ]]  # TRUE → SKIPPED
```

**Risk**: None. Extraction works correctly.

## JSON Array Output Validation

### Valid JSON Test

**Scenario**: Multiple files to validate
**Input**:
```
.agents/sessions/2025-12-21-session-53.md
.agents/sessions/2025-12-29-session-98.md
```

**JSON Construction (Line 106)**:
```bash
JSON_ARRAY=$(echo "$CHANGED_FILES" | jq -R -s -c 'split("\n") | map(select(length > 0))')
```

**Expected Output**:
```json
[".agents/sessions/2025-12-21-session-53.md",".agents/sessions/2025-12-29-session-98.md"]
```

**Verification**:
- `jq -R`: Read raw strings
- `-s`: Slurp entire input
- `-c`: Compact output
- `split("\n")`: Split on newlines
- `map(select(length > 0))`: Filter empty strings
- Result: Valid JSON array

**Risk**: None. jq produces valid JSON.

### Empty JSON Test

**Scenario**: All files historical
**Expected Output** (Line 98):
```json
[]
```

**Risk**: None. Valid empty JSON array.

## Date Comparison Logic Verification

### Bash String Comparison for ISO 8601 Dates

**Question**: Does lexicographic `<` work for YYYY-MM-DD dates?
**Answer**: YES

**Proof**:
- ISO 8601 format (YYYY-MM-DD) has most significant units first
- Lexicographic sorting matches chronological sorting
- Examples:
  - "2025-12-20" < "2025-12-21" → TRUE ✓
  - "2025-12-21" < "2025-12-21" → FALSE ✓
  - "2024-12-31" < "2025-01-01" → TRUE ✓
  - "2025-01-15" < "2025-12-21" → TRUE ✓

**Risk**: None. This is a well-known property of ISO 8601.

### Alternative Implementation (Not Used)

If we needed numeric comparison, we could convert to epoch:
```bash
file_epoch=$(date -d "$file_date" +%s)
cutoff_epoch=$(date -d "$CUTOFF_DATE" +%s)
[[ $file_epoch -lt $cutoff_epoch ]]
```

But string comparison is simpler and sufficient for ISO 8601 dates.

## Execution Flow Test

### Workflow Execution Path: All Historical

1. PR changes 2 files: `2025-12-18-session-01.md`, `2025-12-19-session-02.md`
2. detect-changes job:
   - Reads files via GitHub API
   - Both fail date check (< 2025-12-21)
   - Both added to `SKIPPED_FILES`
   - `CHANGED_FILES` empty
   - Outputs: `has_sessions=false`, `session_files=[]`
3. validate job:
   - Condition: `if: needs.detect-changes.outputs.has_sessions == 'true'`
   - Skipped (condition false)
4. aggregate job:
   - Condition: `if: needs.detect-changes.outputs.has_sessions == 'true'`
   - Skipped (condition false)
5. Workflow: SUCCESS (no validation jobs ran)

### Workflow Execution Path: Mixed Files

1. PR changes 3 files: `2025-12-20.md`, `2025-12-21.md`, `2025-12-29.md`
2. detect-changes job:
   - `2025-12-20.md`: SKIPPED
   - `2025-12-21.md`: VALIDATED
   - `2025-12-29.md`: VALIDATED
   - Outputs: `has_sessions=true`, `session_files=["...-21.md","...-29.md"]`
3. validate job:
   - Matrix: 2 entries
   - Runs validation for both files in parallel
   - Uploads artifacts
4. aggregate job:
   - Downloads 2 artifacts
   - Aggregates verdicts
   - Posts PR comment
   - Enforces MUST requirements
5. Workflow: SUCCESS/FAIL based on validation results

## Issues Discovered

None.

## Quality Assessment

| Category | Status | Notes |
|----------|--------|-------|
| **Date comparison logic** | [PASS] | Bash string `<` correct for ISO 8601 |
| **Cutoff boundary (2025-12-21)** | [PASS] | Correctly included for validation |
| **Malformed filename handling** | [PASS] | Safe default (validate unknown) |
| **JSON array output** | [PASS] | jq produces valid JSON |
| **Empty list handling** | [PASS] | `has_sessions=false` path correct |
| **Mixed old/new files** | [PASS] | Correctly filters and builds matrix |
| **Non-standard filenames** | [PASS] | Safe default (validate unknown) |

## Coverage Analysis

| Scenario | Covered | Test Case |
|----------|---------|-----------|
| Before cutoff | ✓ | Test 1 |
| On cutoff | ✓ | Test 2 |
| After cutoff | ✓ | Test 3 |
| Non-standard name | ✓ | Test 4 |
| All historical | ✓ | Test 5 |
| Mixed old/new | ✓ | Test 6 |
| Malformed date | ✓ | Edge Case 2 |
| Filename with description | ✓ | Edge Case 4 |
| Empty list | ✓ | Edge Case 3 |

**Coverage**: 9/9 scenarios (100%)
