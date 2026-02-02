#!/bin/bash
# Test harness for large PR diff handling logic
# Used by Pester tests to validate pagination and fallback strategies
# Extracted from action.yml:400-478 for testability

# Simulate the large PR handling logic
# Args: $1=scenario, $2=file_count, $3=max_pages
handle_large_pr() {
  local SCENARIO="$1"
  local FILE_COUNT="${2:-0}"
  local MAX_PAGES="${3:-5}"
  local PER_PAGE=100

  local CONTEXT_MODE="full"
  local CONTEXT=""
  local EXIT_CODE=0
  local WARNING_ISSUED=""

  case "$SCENARIO" in
    http_406)
      # Simulate HTTP 406 error (>300 files)
      CONTEXT_MODE="summary"

      # Simulate pagination
      local PAGE=1
      local FILES_RETRIEVED=0
      local FILE_LIST=""

      while [ $PAGE -le $MAX_PAGES ]; do
        local REMAINING=$((FILE_COUNT - FILES_RETRIEVED))
        if [ $REMAINING -le 0 ]; then
          break
        fi

        local PAGE_FILES=$((REMAINING > PER_PAGE ? PER_PAGE : REMAINING))

        # Simulate file names
        for i in $(seq 1 $PAGE_FILES); do
          FILE_LIST="${FILE_LIST}file_$((FILES_RETRIEVED + i)).txt"$'\n'
        done

        FILES_RETRIEVED=$((FILES_RETRIEVED + PAGE_FILES))

        # Check if we've retrieved all files
        if [ $FILES_RETRIEVED -ge $FILE_COUNT ]; then
          break
        fi

        PAGE=$((PAGE + 1))
      done

      # Check for truncation - if we didn't retrieve all files, we hit the limit
      if [ $FILES_RETRIEVED -lt $FILE_COUNT ]; then
        WARNING_ISSUED="File list truncated at $((MAX_PAGES * PER_PAGE)) files"
        CONTEXT="[Large PR - >300 files (GitHub diff limit exceeded), showing file list only]"$'\n\n'"Changed files:"$'\n'"$FILE_LIST"
      elif [ -n "$FILE_LIST" ]; then
        CONTEXT="[Large PR - >300 files (GitHub diff limit exceeded), showing file list only]"$'\n\n'"Changed files:"$'\n'"$FILE_LIST"
      else
        CONTEXT="ERROR: No files retrieved"
        EXIT_CODE=1
      fi
      ;;

    api_pagination_failure)
      # Simulate API pagination failing, fall back to --name-only
      CONTEXT_MODE="summary"
      CONTEXT="[Large PR - showing file list only]"$'\n'"file1.txt"$'\n'"file2.txt"
      ;;

    all_fallbacks_fail)
      # Simulate all fallback methods failing
      CONTEXT="ERROR"
      EXIT_CODE=1
      ;;

    normal_diff)
      # Normal diff succeeded
      CONTEXT_MODE="full"
      CONTEXT="diff --git a/file1.txt b/file1.txt"
      ;;

    large_diff)
      # Diff succeeded but exceeds MAX_DIFF_LINES
      CONTEXT_MODE="summary"
      CONTEXT="[Large PR - 1000 lines, showing summary only]"$'\n'"file1.txt"
      ;;

    *)
      echo "Unknown scenario: $SCENARIO"
      exit 2
      ;;
  esac

  # Output results in JSON format for easy parsing
  echo "{"
  echo "  \"context_mode\": \"$CONTEXT_MODE\","
  echo "  \"exit_code\": $EXIT_CODE,"
  echo "  \"warning\": \"$WARNING_ISSUED\","
  echo "  \"context_preview\": \"$(echo "$CONTEXT" | head -c 100 | sed 's/"/\\"/g')\""
  echo "}"

  exit $EXIT_CODE
}

# Main: call function with args
SCENARIO="${1:-normal_diff}"
FILE_COUNT="${2:-0}"
MAX_PAGES="${3:-5}"

handle_large_pr "$SCENARIO" "$FILE_COUNT" "$MAX_PAGES"
