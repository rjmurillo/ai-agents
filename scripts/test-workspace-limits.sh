#!/usr/bin/env bash
# test-workspace-limits.sh - E2E tests for workspace file budget
# Target: 6.6KB total for injected files, 3KB per file max

set -euo pipefail

WORKSPACE="${WORKSPACE:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
MAX_TOTAL=6758      # 6.6KB
MAX_PER_FILE=3072   # 3KB

# Files that get injected into agent context
INJECTED_FILES=(
    "AGENTS.md"
    "CLAUDE.md"
)

# Check if files exist and calculate sizes
TOTAL=0
FAILED=0

echo "=== Workspace Budget Test ==="
echo ""

for file in "${INJECTED_FILES[@]}"; do
    filepath="$WORKSPACE/$file"
    if [[ -f "$filepath" ]]; then
        size=$(wc -c < "$filepath")
        TOTAL=$((TOTAL + size))
        
        if [[ $size -gt $MAX_PER_FILE ]]; then
            echo "❌ $file: ${size} bytes (exceeds ${MAX_PER_FILE} max)"
            FAILED=1
        else
            echo "✓ $file: ${size} bytes"
        fi
    fi
done

echo ""
echo "---"
echo "Total: ${TOTAL} / ${MAX_TOTAL} bytes"

if [[ $TOTAL -gt $MAX_TOTAL ]]; then
    echo "❌ FAIL: Total exceeds budget by $((TOTAL - MAX_TOTAL)) bytes"
    exit 1
elif [[ $FAILED -eq 1 ]]; then
    echo "❌ FAIL: One or more files exceed per-file limit"
    exit 1
else
    echo "✓ ALL TESTS PASSED — $(echo "scale=1; $TOTAL/1024" | bc)KB / $(echo "scale=1; $MAX_TOTAL/1024" | bc)KB budget"
    exit 0
fi
