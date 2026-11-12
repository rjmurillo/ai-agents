<!-- # taste-lint: ignore file-size, the gate fences are one carrier the status-grep suite executes; splitting the file would hide a gate from it. -->
# Verification Gates

These gates implement RFC 2119 MUST requirements. Proceeding without passing causes artifact drift.

## Comment Map Status Vocabulary

Every comment in `comments.md` carries exactly one status from this table. This table is
the only place the vocabulary is defined. Every gate derives its counts from it.

| Status | Meaning | Terminal |
|--------|---------|---------|
| `[NEW]` | Fetched, not yet acknowledged | No |
| `[ACKNOWLEDGED]` | Reaction posted, fix not yet committed | No |
| `[COMPLETE]` | Fix committed and pushed | Yes |
| `[WONTFIX]` | Explicitly decided not to change | Yes |
| `[DUPLICATE]` | Same point already resolved by another comment | Yes |
| `[DEFERRED] Refs #<issue>` | Tracked in a filed issue, not fixed in this PR | Yes, only with the `Refs #<issue>` suffix |

Comment map fields render as `**Status**: [NEW]`, so every status grep must match the
bold field at line start. Dropping the `**` delimiters or the `^` anchor matches nothing
and reports zero.

`[DEFERRED]` is terminal only when the status line carries an inline `Refs #<issue>`
reference, as in `**Status**: [DEFERRED] Refs #<number>`. A bare `[DEFERRED]` names no
tracking issue, so nobody can find the work later and the gate keeps it pending.

The issue number matches `#[1-9][0-9]*`, never `#[0-9]+`. GitHub numbers issues and
pull requests from 1, so `#0` can never resolve. Admitting it would let a guaranteed
non-reference mark deferred work terminal, which is the same lost-work failure a bare
`[DEFERRED]` causes. `**Status**: [DEFERRED] Refs #0` stays pending.

The terminal pattern ends at `[[:space:]]*$`, so a status line counts as terminal only
when it ends at the status token, or at the `Refs #<issue>` reference for `[DEFERRED]`.
`**Status**: [COMPLETE]oops` and `**Status**: [DEFERRED] Refs #<number>garbage` match no
terminal alternative and stay pending. Without the end anchor a matching prefix was
enough, so a malformed value passed the gate.

Every gate proves the comment map exists before counting. `grep -Ec` on a missing file
exits non-zero and prints nothing, `|| true` turns that into an empty string, and shell
arithmetic reads an empty string as 0. An absent map would otherwise compute zero pending
and clear every gate with no artifact to verify.

Every gate proves the map is complete before trusting the subtraction. Stripped `**Status**:`
fields count zero total and zero terminal, so the gate clears a map that describes nothing.
Each gate compares `TOTAL` with `$TOTAL_COMMENTS`, the API count Phase 1 recorded, then
reconciles per comment ID: one status per `### Comment <id>` block, IDs match
`comment_ids.txt`.

No gate enumerates pending statuses. Every gate counts the terminal statuses and
subtracts. A status outside this table therefore fails closed: it matches no terminal
pattern, so it counts as pending and blocks.

The Comment Index that Step 2.2 renders carries no status cell. Gate 3 rewrites
the `**Status**:` detail line and nothing else, so an index column would keep
whatever Step 2.2 rendered for the life of the artifact and disagree with the
detail entry it summarizes. One representation, in the detail entry.

```bash
COMMENT_MAP=".project-toolkit/pr-comments/PR-[number]/comments.md"
if [ ! -f "$COMMENT_MAP" ]; then
  echo "[BLOCKED] Comment map missing: $COMMENT_MAP"
  exit 1
fi
TOTAL=$(grep -Ec "^\*\*Status\*\*: " "$COMMENT_MAP" || true)
TERMINAL=$(grep -Ec "^\*\*Status\*\*: (\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)[[:space:]]*$" "$COMMENT_MAP" || true)
PENDING=$((TOTAL - TERMINAL))

# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac

if [ "$TOTAL" -ne "$TOTAL_COMMENTS" ]; then
  echo "[BLOCKED] Comment map carries $TOTAL status fields, API reported $TOTAL_COMMENTS"
  exit 1
fi

# Reconcile per comment ID, not in aggregate. Matching counts cannot tell one
# block with two status lines plus one block with none from two clean blocks,
# or a deleted comment plus a new one from no change at all. Phase 1 recorded
# the API comment IDs beside the count. Block when any block lacks exactly one
# status line, or when the map's IDs differ from the recorded ones. This runs
# at read time, in every gate, because Gate 3 guards only the writes it makes: a
# hand edit or an external delete-plus-add never passes through it.
IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
if [ ! -f "$IDS_FILE" ]; then
  echo "[BLOCKED] API comment IDs not recorded: $IDS_FILE"
  exit 1
fi
BLOCK_FAULTS=$(awk '
  function close_block() { if (id != "" && n != 1) printf "%s(%d) ", id, n }
  /^### Comment / { close_block(); id = $3; n = 0; next }
  /^\*\*Status\*\*: / { if (id == "") stray++; else n++ }
  END { close_block(); if (stray) printf "unowned(%d) ", stray }
' "$COMMENT_MAP") || { echo "[BLOCKED] Cannot read comment blocks: $COMMENT_MAP"; exit 1; }
if [ -n "$BLOCK_FAULTS" ]; then
  echo "[BLOCKED] Comment blocks without exactly one status line: $BLOCK_FAULTS"
  exit 1
fi
if ! ID_DIFF=$(diff <(awk '/^### Comment / { print $3 }' "$COMMENT_MAP" | LC_ALL=C sort) <(LC_ALL=C sort "$IDS_FILE")); then
  echo "[BLOCKED] Comment map IDs differ from the API IDs (< map only, > API only):"
  echo "$ID_DIFF"
  exit 1
fi
```

## Phase 1 Recording

Run this once, right after Step 1.3 retrieves the comments. Every gate below reads
the two artifacts it writes. Without them Gate 1 through Phase 8.1 block, because
no count and no ID list exist to compare against. Run exactly one of the two
fences, matching how you retrieved the comments.

Retrieve with the github skill (preferred), then record:

```bash
# IMPORTANT: --include-issue-comments captures AI Quality Gate, CodeRabbit summaries, etc.
COMMENTS=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request [number] --include-issue-comments; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
TOTAL_COMMENTS=$(echo "$COMMENTS" | jq '.TotalComments')
echo "Total comments: $TOTAL_COMMENTS"

# Record the API count where every later gate reads it. Shell variables do not
# survive between fenced blocks, so the count has to reach them as an artifact.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
mkdir -p "$(dirname "$COUNT_FILE")"
printf '%s\n' "$TOTAL_COMMENTS" > "$COUNT_FILE"

# Record the comment IDs beside the count, sorted. Counts cannot see a
# duplicate-plus-missing or delete-plus-add pair, so every gate also diffs the
# map's `### Comment <id>` headers against this list.
IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
( set -o pipefail; printf '%s' "$COMMENTS" | jq -r '.Comments[].Id' | LC_ALL=C sort > "$IDS_FILE" ) \
  || { echo "[BLOCKED] Cannot record comment IDs from the payload"; exit 1; }
```

Fallback when the github skill scripts are unavailable and `gh` is usable (see
the Transport section of [workflow.md](workflow.md)). Paginate to the last page:

```bash
# Review comments (code-level) - paginate until a page returns zero rows
PAGE=1
ALL_REVIEW_COMMENTS="[]"
while true; do
  BATCH=$(gh api "repos/[owner]/[repo]/pulls/[number]/comments?per_page=100&page=$PAGE")
  COUNT=$(echo "$BATCH" | jq 'length')
  if [ "$COUNT" -eq 0 ]; then break; fi
  ALL_REVIEW_COMMENTS=$(echo "$ALL_REVIEW_COMMENTS $BATCH" | jq -s 'add')
  PAGE=$((PAGE + 1))
done
REVIEW_COMMENT_COUNT=$(echo "$ALL_REVIEW_COMMENTS" | jq 'length')

# Issue comments (PR-level) - paginate until a page returns zero rows
PAGE=1
ALL_ISSUE_COMMENTS="[]"
while true; do
  BATCH=$(gh api "repos/[owner]/[repo]/issues/[number]/comments?per_page=100&page=$PAGE")
  COUNT=$(echo "$BATCH" | jq 'length')
  if [ "$COUNT" -eq 0 ]; then break; fi
  ALL_ISSUE_COMMENTS=$(echo "$ALL_ISSUE_COMMENTS $BATCH" | jq -s 'add')
  PAGE=$((PAGE + 1))
done
ISSUE_COMMENT_COUNT=$(echo "$ALL_ISSUE_COMMENTS" | jq 'length')

TOTAL_COMMENTS=$((REVIEW_COMMENT_COUNT + ISSUE_COMMENT_COUNT))
echo "Total comments: $TOTAL_COMMENTS (Review: $REVIEW_COMMENT_COUNT, Issue: $ISSUE_COMMENT_COUNT)"

# Same artifacts as the preferred path, so every gate reconciles against them.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
mkdir -p "$(dirname "$COUNT_FILE")"
printf '%s\n' "$TOTAL_COMMENTS" > "$COUNT_FILE"

IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
( set -o pipefail; printf '%s\n%s\n' "$ALL_REVIEW_COMMENTS" "$ALL_ISSUE_COMMENTS" | jq -r '.[].id' | LC_ALL=C sort > "$IDS_FILE" ) \
  || { echo "[BLOCKED] Cannot record comment IDs from the payload"; exit 1; }
```

## Gate 0: Continuity

Before work, read the current per-issue handoff when one exists. Session log
creation is discontinued.

```bash
# Create the PR comment run log consumed by Gate 1. Step 2.1 appends one
# `reaction eyes ...` record per comment it acknowledges.
PR_COMMENT_LOG=".project-toolkit/pr-comments/PR-[number]/session.log"
mkdir -p "$(dirname "$PR_COMMENT_LOG")"
: > "$PR_COMMENT_LOG"
```

**Evidence required**: PR comment run log exists. Transcript identifies any
loaded handoff.

## Gate 1: Acknowledgment Verification

**After Phase 2**: Verify eyes reaction count equals total comment count. A comment the
reaction helper skipped by its live-state gate (resolved, missing, or wrong PR) is still
recorded by Step 2.1, because the helper exits 0 only when every id was reacted or
deliberately skipped.

```bash
REACTIONS_ADDED=$(cat .project-toolkit/pr-comments/PR-[number]/session.log | grep -c "reaction.*eyes")
# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac
COMMENT_COUNT=$TOTAL_COMMENTS

if [ "$REACTIONS_ADDED" -ne "$COMMENT_COUNT" ]; then
  echo "[BLOCKED] Reactions: $REACTIONS_ADDED != Comments: $COMMENT_COUNT"
  exit 1
fi
```

## Gate 2: Artifact Creation Verification

**After generating comment map and task list**: Verify files exist and contain expected counts.

```bash
test -f ".project-toolkit/pr-comments/PR-[number]/comments.md" || exit 1
test -f ".project-toolkit/pr-comments/PR-[number]/tasks.md" || exit 1

# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac
ARTIFACT_COUNT=$(grep -c "^| [0-9]" .project-toolkit/pr-comments/PR-[number]/comments.md)
if [ "$ARTIFACT_COUNT" -ne "$TOTAL_COMMENTS" ]; then
  echo "[BLOCKED] Artifact count: $ARTIFACT_COUNT != API count: $TOTAL_COMMENTS"
  exit 1
fi
```

## Gate 3: Artifact Update After Fix

**After EVERY terminal outcome**: Update BOTH artifacts atomically.

Gate 4, Gate 5, and Phase 8.1 count `comments.md` and nothing else. A step that
moves only `tasks.md` leaves every status at the value the comment map was
generated with, so pending never reaches zero and Phase 8 blocks on finished
work. Set `TERMINAL_STATUS` to the value the Comment Map Status Vocabulary
table above marks terminal for this outcome.

```bash
COMMENT_MAP=".project-toolkit/pr-comments/PR-[number]/comments.md"
TASK_LIST=".project-toolkit/pr-comments/PR-[number]/tasks.md"
TERMINAL_STATUS="[COMPLETE]"

# The id reaches a sed address, so refuse anything but digits (CWE-78).
case "$COMMENT_ID" in
  ''|*[!0-9]*) echo "[BLOCKED] COMMENT_ID is not numeric: $COMMENT_ID"; exit 1 ;;
esac

# Refuse a status the gates will not accept, before anything is written. The
# pattern is Gate 4's, so a value that clears here clears there, and the four
# shapes it admits carry no sed metacharacter.
printf '%s\n' "**Status**: $TERMINAL_STATUS" \
  | grep -Eq "^\*\*Status\*\*: (\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)[[:space:]]*$" || {
    echo "[BLOCKED] TERMINAL_STATUS is not a terminal value: $TERMINAL_STATUS"
    exit 1
  }

# Preflight the comment map before either file is written. Every step below is
# a write, so an unreachable target has to stop the gate here: a task list that
# moved while the comment map did not is the split state Gate 4 reads as
# finished work still pending. One check covers both ways the map can fail, no
# detail entry for this comment and an entry carrying no status field.
sed -n "/^### Comment $COMMENT_ID /,/^---$/p" "$COMMENT_MAP" \
  | grep -Eq "^\*\*Status\*\*: " || {
    echo "[BLOCKED] Comment $COMMENT_ID has no status field in $COMMENT_MAP"
    exit 1
  }

# The task row is optional. Phase 6 opens a TASK only for a comment it
# implements; an immediate-reply outcome is answered in Phase 5 and never gets
# one. Absent is fine. Present means it must move. The row starts with "- ",
# which grep reads as a flag, so "--" terminates the option list.
TASK_ROW="- [ ] **TASK-$COMMENT_ID**:"
if grep -qF -- "$TASK_ROW" "$TASK_LIST"; then
  sed -i "s|^- \[ \] \*\*TASK-$COMMENT_ID\*\*:\(.*\)$|- [x] **TASK-$COMMENT_ID**:\1 $TERMINAL_STATUS|" "$TASK_LIST"
  grep -F -- "- [x] **TASK-$COMMENT_ID**:" "$TASK_LIST" | grep -qF -- "$TERMINAL_STATUS" || {
    echo "[BLOCKED] TASK-$COMMENT_ID is not $TERMINAL_STATUS in $TASK_LIST"
    exit 1
  }
fi

# The write every later gate depends on. The address range is this comment's
# detail entry, so a sibling comment's status is never touched.
sed -i "/^### Comment $COMMENT_ID /,/^---$/ s|^\*\*Status\*\*: .*$|**Status**: $TERMINAL_STATUS|" "$COMMENT_MAP"

# Verify the write. Whole-line and literal, so a status with trailing garbage
# fails here instead of surviving to Phase 8.1.
sed -n "/^### Comment $COMMENT_ID /,/^---$/p" "$COMMENT_MAP" \
  | grep -qxF "**Status**: $TERMINAL_STATUS" || {
    echo "[BLOCKED] Comment $COMMENT_ID is not $TERMINAL_STATUS in $COMMENT_MAP"
    exit 1
  }
```

The task row is the one Phase 6 renders, `- [ ] **TASK-[id]**: [description]`.
It carries no `pending` token, so a step that matched one moved nothing and then
failed its own verification. Marking a task done ticks the box and appends the
terminal status: `- [x] **TASK-[id]**: [description] [COMPLETE]`.

Not every comment has a task row. Phase 6 opens a `TASK-[id]` only for a comment
it implements; a `[WONTFIX]`, `[DUPLICATE]`, or question outcome is answered in
the Phase 5 immediate-reply table and never gets one. An absent row is the
normal case for those outcomes, so the gate skips the task-list write rather
than blocking. The comment-map write is not optional for any outcome.

Atomic here means both artifacts move or neither does. The comment map is
checked before either file is written, because a task list that moved while the
map did not is exactly the split state Gate 4 reads as finished work still
pending.

## Gate 4: State Synchronization Before Resolution

**Before Phase 8**: Verify artifact state matches intended API state.

```bash
COMMENT_MAP=".project-toolkit/pr-comments/PR-[number]/comments.md"
if [ ! -f "$COMMENT_MAP" ]; then
  echo "[BLOCKED] Comment map missing: $COMMENT_MAP"
  exit 1
fi
TOTAL=$(grep -Ec "^\*\*Status\*\*: " "$COMMENT_MAP" || true)
TERMINAL=$(grep -Ec "^\*\*Status\*\*: (\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)[[:space:]]*$" "$COMMENT_MAP" || true)
PENDING=$((TOTAL - TERMINAL))

# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac

if [ "$TOTAL" -ne "$TOTAL_COMMENTS" ]; then
  echo "[BLOCKED] Comment map carries $TOTAL status fields, API reported $TOTAL_COMMENTS"
  exit 1
fi

# Reconcile per comment ID, not in aggregate. Matching counts cannot tell one
# block with two status lines plus one block with none from two clean blocks,
# or a deleted comment plus a new one from no change at all. Phase 1 recorded
# the API comment IDs beside the count. Block when any block lacks exactly one
# status line, or when the map's IDs differ from the recorded ones. This runs
# at read time, in every gate, because Gate 3 guards only the writes it makes: a
# hand edit or an external delete-plus-add never passes through it.
IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
if [ ! -f "$IDS_FILE" ]; then
  echo "[BLOCKED] API comment IDs not recorded: $IDS_FILE"
  exit 1
fi
BLOCK_FAULTS=$(awk '
  function close_block() { if (id != "" && n != 1) printf "%s(%d) ", id, n }
  /^### Comment / { close_block(); id = $3; n = 0; next }
  /^\*\*Status\*\*: / { if (id == "") stray++; else n++ }
  END { close_block(); if (stray) printf "unowned(%d) ", stray }
' "$COMMENT_MAP") || { echo "[BLOCKED] Cannot read comment blocks: $COMMENT_MAP"; exit 1; }
if [ -n "$BLOCK_FAULTS" ]; then
  echo "[BLOCKED] Comment blocks without exactly one status line: $BLOCK_FAULTS"
  exit 1
fi
if ! ID_DIFF=$(diff <(awk '/^### Comment / { print $3 }' "$COMMENT_MAP" | LC_ALL=C sort) <(LC_ALL=C sort "$IDS_FILE")); then
  echo "[BLOCKED] Comment map IDs differ from the API IDs (< map only, > API only):"
  echo "$ID_DIFF"
  exit 1
fi

# Count unresolved review threads separately
UNRESOLVED_API=$(gh api graphql -f query='...' --jq '.data...unresolved.length')

# Verify alignment
if [ "$PENDING" -ne 0 ]; then
  echo "[BLOCKED] Comment map still has $PENDING pending comment(s)"
  exit 1
fi

echo "Unresolved API threads: $UNRESOLVED_API"
```

## Gate 5: Final Verification

**After Phase 8**: Verify all threads resolved AND artifacts updated.

```bash
REMAINING=$(gh api graphql -f query='...' --jq '.data...unresolved.length')
COMMENT_MAP=".project-toolkit/pr-comments/PR-[number]/comments.md"
if [ ! -f "$COMMENT_MAP" ]; then
  echo "[BLOCKED] Comment map missing: $COMMENT_MAP"
  exit 1
fi
TOTAL=$(grep -Ec "^\*\*Status\*\*: " "$COMMENT_MAP" || true)
TERMINAL=$(grep -Ec "^\*\*Status\*\*: (\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)[[:space:]]*$" "$COMMENT_MAP" || true)
PENDING=$((TOTAL - TERMINAL))

# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac

if [ "$TOTAL" -ne "$TOTAL_COMMENTS" ]; then
  echo "[BLOCKED] Comment map carries $TOTAL status fields, API reported $TOTAL_COMMENTS"
  exit 1
fi

# Reconcile per comment ID, not in aggregate. Matching counts cannot tell one
# block with two status lines plus one block with none from two clean blocks,
# or a deleted comment plus a new one from no change at all. Phase 1 recorded
# the API comment IDs beside the count. Block when any block lacks exactly one
# status line, or when the map's IDs differ from the recorded ones. This runs
# at read time, in every gate, because Gate 3 guards only the writes it makes: a
# hand edit or an external delete-plus-add never passes through it.
IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
if [ ! -f "$IDS_FILE" ]; then
  echo "[BLOCKED] API comment IDs not recorded: $IDS_FILE"
  exit 1
fi
BLOCK_FAULTS=$(awk '
  function close_block() { if (id != "" && n != 1) printf "%s(%d) ", id, n }
  /^### Comment / { close_block(); id = $3; n = 0; next }
  /^\*\*Status\*\*: / { if (id == "") stray++; else n++ }
  END { close_block(); if (stray) printf "unowned(%d) ", stray }
' "$COMMENT_MAP") || { echo "[BLOCKED] Cannot read comment blocks: $COMMENT_MAP"; exit 1; }
if [ -n "$BLOCK_FAULTS" ]; then
  echo "[BLOCKED] Comment blocks without exactly one status line: $BLOCK_FAULTS"
  exit 1
fi
if ! ID_DIFF=$(diff <(awk '/^### Comment / { print $3 }' "$COMMENT_MAP" | LC_ALL=C sort) <(LC_ALL=C sort "$IDS_FILE")); then
  echo "[BLOCKED] Comment map IDs differ from the API IDs (< map only, > API only):"
  echo "$ID_DIFF"
  exit 1
fi

if [ "$REMAINING" -ne 0 ] || [ "$PENDING" -ne 0 ]; then
  echo "[BLOCKED] API unresolved: $REMAINING, Artifact pending: $PENDING"
  exit 1
fi

echo "[PASS] All gates cleared"
```

## Phase 8 Sub-Gates

### Phase 8.1: Comment Status Verification

```bash
COMMENT_MAP=".project-toolkit/pr-comments/PR-[number]/comments.md"
if [ ! -f "$COMMENT_MAP" ]; then
  echo "[BLOCKED] Comment map missing: $COMMENT_MAP"
  exit 1
fi
TOTAL=$(grep -Ec "^\*\*Status\*\*: " "$COMMENT_MAP" || true)
TERMINAL=$(grep -Ec "^\*\*Status\*\*: (\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)[[:space:]]*$" "$COMMENT_MAP" || true)
PENDING=$((TOTAL - TERMINAL))

# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac

if [ "$TOTAL" -ne "$TOTAL_COMMENTS" ]; then
  echo "[BLOCKED] Comment map carries $TOTAL status fields, API reported $TOTAL_COMMENTS"
  exit 1
fi

# Reconcile per comment ID, not in aggregate. Matching counts cannot tell one
# block with two status lines plus one block with none from two clean blocks,
# or a deleted comment plus a new one from no change at all. Phase 1 recorded
# the API comment IDs beside the count. Block when any block lacks exactly one
# status line, or when the map's IDs differ from the recorded ones. This runs
# at read time, in every gate, because Gate 3 guards only the writes it makes: a
# hand edit or an external delete-plus-add never passes through it.
IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
if [ ! -f "$IDS_FILE" ]; then
  echo "[BLOCKED] API comment IDs not recorded: $IDS_FILE"
  exit 1
fi
BLOCK_FAULTS=$(awk '
  function close_block() { if (id != "" && n != 1) printf "%s(%d) ", id, n }
  /^### Comment / { close_block(); id = $3; n = 0; next }
  /^\*\*Status\*\*: / { if (id == "") stray++; else n++ }
  END { close_block(); if (stray) printf "unowned(%d) ", stray }
' "$COMMENT_MAP") || { echo "[BLOCKED] Cannot read comment blocks: $COMMENT_MAP"; exit 1; }
if [ -n "$BLOCK_FAULTS" ]; then
  echo "[BLOCKED] Comment blocks without exactly one status line: $BLOCK_FAULTS"
  exit 1
fi
if ! ID_DIFF=$(diff <(awk '/^### Comment / { print $3 }' "$COMMENT_MAP" | LC_ALL=C sort) <(LC_ALL=C sort "$IDS_FILE")); then
  echo "[BLOCKED] Comment map IDs differ from the API IDs (< map only, > API only):"
  echo "$ID_DIFF"
  exit 1
fi

if [ "$PENDING" -ne 0 ]; then
  echo "[BLOCKED] INCOMPLETE: $PENDING comment(s) not terminal"
  grep -En "^\*\*Status\*\*: " "$COMMENT_MAP" \
    | grep -Ev "\*\*Status\*\*: (\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)[[:space:]]*$" || true
  exit 1
fi
```

### Phase 8.2: Conversation Resolution

```bash

# Resolve all threads for a PR
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_threads.py --pull-request [number] --unresolved-only; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) | \
  jq -r '.threads[].thread_id' | while read tid; do
    ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/resolve_pr_review_thread.py --expected-pull-request [number] --thread-id "$tid"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
  done
```

Each single-thread resolve requeries the target after the PR-level gate.
`Data.action=SKIP` means the thread is resolved, missing, or belongs to another
PR. Do not retry a safe skip with a lower-level mutation.

### Phase 8.3: Re-check for New Comments

```bash
sleep 45
# This re-fetch is the only thing that can see a comment posted since the last
# pass, so both halves of it have to block on failure. Left unchecked, a
# nonzero exit from the fetch or a payload jq cannot parse leaves NEW_COMMENTS
# empty or `null`; `[ -ne ]` on a non-numeric operand then raises `integer
# expression expected`, which is a nonzero exit from `[` and reads as false to
# `if`, so the append check below never fires and the pass continues as though
# the API reported no new comments.
RECHECK_PAYLOAD=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_review_comments.py --pull-request [number] --include-issue-comments; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
RECHECK_STATUS=$?
if [ "$RECHECK_STATUS" -ne 0 ]; then
  echo "[BLOCKED] Comment re-fetch failed (exit $RECHECK_STATUS)"
  exit 1
fi
NEW_COMMENTS=$(printf '%s' "$RECHECK_PAYLOAD" | jq '.TotalComments')
JQ_STATUS=$?
if [ "$JQ_STATUS" -ne 0 ]; then
  echo "[BLOCKED] Comment re-fetch payload is not parseable JSON (jq exit $JQ_STATUS)"
  exit 1
fi
case "$NEW_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Re-fetched comment count is not numeric: $NEW_COMMENTS"; exit 1 ;;
esac

# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac

# Reconcile by comment ID, not by count. A count only grows when a comment is
# added. One comment deleted plus a different one posted leaves the total where
# it was, so a count comparison never ran the append and the map kept the
# deleted comment's stale terminal row. Diff the map's IDs against the fresh
# payload's IDs instead.
COMMENT_MAP=".project-toolkit/pr-comments/PR-[number]/comments.md"
if [ ! -f "$COMMENT_MAP" ]; then
  echo "[BLOCKED] Comment map not found: $COMMENT_MAP"
  exit 1
fi
IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
RECHECK_IDS=$( set -o pipefail; printf '%s' "$RECHECK_PAYLOAD" | jq -r '.Comments[].Id' | LC_ALL=C sort ) \
  || { echo "[BLOCKED] Cannot read comment IDs from the re-fetched payload"; exit 1; }
REMOVED_IDS=$(LC_ALL=C comm -23 \
  <(awk '/^### Comment / { print $3 }' "$COMMENT_MAP" | LC_ALL=C sort) \
  <(printf '%s\n' "$RECHECK_IDS" | sed '/^$/d') | paste -s -d ' ' -)
ADDED_IDS=$(LC_ALL=C comm -13 \
  <(awk '/^### Comment / { print $3 }' "$COMMENT_MAP" | LC_ALL=C sort) \
  <(printf '%s\n' "$RECHECK_IDS" | sed '/^$/d') | paste -s -d ' ' -)
if [ -n "$REMOVED_IDS" ]; then
  echo "[BLOCKED] Comments in the map are gone from the API: $REMOVED_IDS (new in the API: ${ADDED_IDS:-none})"
  echo "Bring comments.md, total_comments.txt, and comment_ids.txt back in line with the API, then re-run."
  exit 1
fi

if [ -n "$ADDED_IDS" ]; then
  echo "[NEW COMMENTS] New in the API: $ADDED_IDS"
  # Append every comment the map has never seen, at status [NEW]. Every gate
  # counts `**Status**:` fields out of the map, so a comment that arrives here
  # and never lands in the map is invisible to every completion check: the pass
  # can reach Gate 4 reporting zero pending work on a comment nobody read.
  # Comment bodies are deliberately not inlined here. A reviewer comment can
  # itself contain a line reading `**Status**: [COMPLETE]`, and the gates count
  # that field with a line-anchored grep, so an inlined body would let a comment
  # forge a terminal row for itself. Fill Context, Comment, and Analysis from
  # the payload during triage instead.
  #
  # jq's @tsv escapes tabs and newlines inside field values, so a body, author,
  # or path carrying either cannot break the field split below.
  printf '%s' "$RECHECK_PAYLOAD" \
    | jq -r '.Comments[] | [(.Id|tostring), (.Author // "unknown"), (.CommentType // "Review"), (.Path // "-"), (.Line // "-"), (.CreatedAt // "-")] | @tsv' \
    | while IFS="$(printf '\t')" read -r ID AUTHOR CTYPE CPATH CLINE CREATED; do
        if grep -q "^### Comment $ID " "$COMMENT_MAP"; then
          continue
        fi
        {
          printf '### Comment %s (@%s)\n\n' "$ID" "$AUTHOR"
          printf '**Type**: %s\n' "$CTYPE"
          printf '**Path**: %s\n' "$CPATH"
          printf '**Line**: %s\n' "$CLINE"
          printf '**Created**: %s\n' "$CREATED"
          printf '**Status**: [NEW]\n\n'
          printf -- '---\n\n'
        } >> "$COMMENT_MAP"
      done

  # The count artifact records how many status fields the comment map should
  # carry, so it moves with the append. Left at the Phase 1 snapshot it is
  # smaller than the map from this point on, and Gate 4's
  # `TOTAL -ne TOTAL_COMMENTS` invariant blocks every later pass on correct
  # work: the map holds the new rows the recorded count has never heard of.
  #
  # Refresh AFTER the rows are appended, never before. The invariant compares
  # the map against this file, so a file written first would clear a map that
  # never received the new rows, which is the fail-open case the invariant
  # exists to catch.
  #
  # The append above is what earns the refresh, so prove it landed before
  # writing. A refresh over a map that never grew is the very fail-open the
  # invariant exists to catch, written by the one line that feeds it.
  APPENDED_STATUS=$(grep -c "^\*\*Status\*\*: " "$COMMENT_MAP" || true)
  if [ "$APPENDED_STATUS" -ne "$NEW_COMMENTS" ]; then
    echo "[BLOCKED] Comment map carries $APPENDED_STATUS status fields after the append, API reported $NEW_COMMENTS"
    exit 1
  fi
  printf '%s\n' "$NEW_COMMENTS" > "$COUNT_FILE"
  # The ID list moves with the count, for the same reason and in the same
  # order: after the append is proven, never before.
  printf '%s\n' "$RECHECK_IDS" | sed '/^$/d' > "$IDS_FILE"
fi
```

The append and the refresh together are what make this loop repeatable. Without it the second pass
reaches Gate 4 with a comment map the recorded count contradicts, and no amount
of correct work clears it.

### Phase 8.4: CI Check Verification

**CI-failure triage step 1 (issue #5073)**: when any check is failing, run
`triage_red_check.py` for that check name BEFORE reading logs or starting any
local investigation. The cause frequently lives on main, and each missed
attribution costs a full investigation.

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/triage_red_check.py --check-name "[failing check name]" --pull-request [number]; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
# Exit 0 = GREEN_ON_MAIN: the PR introduced the failure; investigate the PR.
# Exit 1 = RED_ON_MAIN: inherited from main; cite Data.EvidenceUrl (the main
#          run) in the thread instead of debugging the PR.
# Exit 3 = cannot determine; read Data.Verdict (never treat as green):
#          PR_ONLY: the check never reports on main (pull_request-only), so
#          it cannot be inherited; read the PR run with
#          `gh run view <run-id> --log-failed`. Widen --history-depth only
#          for path-filtered or scheduled workflows.
#          CANCELLED_ON_MAIN: main has only cancelled or stale runs; rerun
#          Data.EvidenceRunId with `gh run rerun <run-id>`.
#          UNKNOWN: probe failure is not absence.
```

```bash
checks=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request [number]; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
merge_ref_usable=$(echo "$checks" | jq -r '.Data.MergeRefUsable')
all_passing=$(echo "$checks" | jq -r '.Data.AllPassing')
failed_count=$(echo "$checks" | jq '.Data.FailedCount')

if [ "$merge_ref_usable" = "false" ]; then
    echo "[BLOCKED] PR merge ref cannot be built, so CI status is incomplete"
    exit 1
elif [ "$all_passing" != "true" ]; then
    echo "[BLOCKED] CI checks are not all passing"
    exit 1
elif [ "$failed_count" -gt 0 ]; then
    echo "[BLOCKED] $failed_count CI check(s) not passing"
    exit 1
fi
```

Exit codes:

- `0`: All checks passing
- `1`: One or more checks failed
- `7`: Timeout waiting for checks

### Phase 8.5: Completion Criteria Checklist

**ALL criteria must be true before completion**:

| Criterion | Check | Status |
|-----------|-------|--------|
| All comments resolved | Phase 8.1 reports `PENDING` (`TOTAL` minus `TERMINAL`) of 0 | [ ] |
| No new comments | Re-check returned 0 new | [ ] |
| CI checks pass | `get_pr_checks.py --pull-request [number]` MergeRefUsable = true and AllPassing = true | [ ] |
| No unresolved threads | `gh pr view --json reviewThreads` all resolved | [ ] |
| Commits pushed | `git status` shows "up to date with origin" | [ ] |

```bash
# Final verification
# Re-derive the counts. This fence is a separate shell from Phase 8.1, so
# $TOTAL and $TERMINAL do not survive into it and the summary would otherwise
# report an empty numerator over an empty denominator.
COMMENT_MAP=".project-toolkit/pr-comments/PR-[number]/comments.md"
if [ ! -f "$COMMENT_MAP" ]; then
  echo "[BLOCKED] Comment map missing: $COMMENT_MAP"
  exit 1
fi
TOTAL=$(grep -Ec "^\*\*Status\*\*: " "$COMMENT_MAP" || true)
TERMINAL=$(grep -Ec "^\*\*Status\*\*: (\[COMPLETE\]|\[WONTFIX\]|\[DUPLICATE\]|\[DEFERRED\] Refs #[1-9][0-9]*)[[:space:]]*$" "$COMMENT_MAP" || true)
PENDING=$((TOTAL - TERMINAL))

# Phase 1 recorded the API count in this artifact. Shell variables do not
# survive between fenced blocks: each one runs in its own shell, so a gate that
# read $TOTAL_COMMENTS directly saw an empty string, `[ -ne ]` raised `integer
# expression expected`, and that nonzero exit from `[` reads as false to `if`,
# so the BLOCKED body never ran. Read the artifact and fail closed instead.
COUNT_FILE=".project-toolkit/pr-comments/PR-[number]/total_comments.txt"
if [ ! -f "$COUNT_FILE" ]; then
  echo "[BLOCKED] API comment count not recorded: $COUNT_FILE"
  exit 1
fi
TOTAL_COMMENTS=$(cat "$COUNT_FILE")
case "$TOTAL_COMMENTS" in
  ''|*[!0-9]*) echo "[BLOCKED] Recorded comment count is not numeric: $TOTAL_COMMENTS"; exit 1 ;;
esac

if [ "$TOTAL" -ne "$TOTAL_COMMENTS" ]; then
  echo "[BLOCKED] Comment map carries $TOTAL status fields, API reported $TOTAL_COMMENTS"
  exit 1
fi

# Reconcile per comment ID, not in aggregate. Matching counts cannot tell one
# block with two status lines plus one block with none from two clean blocks,
# or a deleted comment plus a new one from no change at all. Phase 1 recorded
# the API comment IDs beside the count. Block when any block lacks exactly one
# status line, or when the map's IDs differ from the recorded ones. This runs
# at read time, in every gate, because Gate 3 guards only the writes it makes: a
# hand edit or an external delete-plus-add never passes through it.
IDS_FILE=".project-toolkit/pr-comments/PR-[number]/comment_ids.txt"
if [ ! -f "$IDS_FILE" ]; then
  echo "[BLOCKED] API comment IDs not recorded: $IDS_FILE"
  exit 1
fi
BLOCK_FAULTS=$(awk '
  function close_block() { if (id != "" && n != 1) printf "%s(%d) ", id, n }
  /^### Comment / { close_block(); id = $3; n = 0; next }
  /^\*\*Status\*\*: / { if (id == "") stray++; else n++ }
  END { close_block(); if (stray) printf "unowned(%d) ", stray }
' "$COMMENT_MAP") || { echo "[BLOCKED] Cannot read comment blocks: $COMMENT_MAP"; exit 1; }
if [ -n "$BLOCK_FAULTS" ]; then
  echo "[BLOCKED] Comment blocks without exactly one status line: $BLOCK_FAULTS"
  exit 1
fi
if ! ID_DIFF=$(diff <(awk '/^### Comment / { print $3 }' "$COMMENT_MAP" | LC_ALL=C sort) <(LC_ALL=C sort "$IDS_FILE")); then
  echo "[BLOCKED] Comment map IDs differ from the API IDs (< map only, > API only):"
  echo "$ID_DIFF"
  exit 1
fi

if [ "$PENDING" -ne 0 ]; then
  echo "[BLOCKED] $PENDING comment(s) not terminal"
  exit 1
fi

echo "=== Completion Criteria ==="
echo "[ ] Comments: $TERMINAL/$TOTAL resolved"
echo "[ ] New comments: None after 45s wait"

# CI check verification using skill. PASS needs both a buildable merge ref and
# every check passing: a small green set on an unbuildable merge ref is not evidence.
checks=$( ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/get_pr_checks.py --pull-request [number]; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 ) )
all_passing=$(echo "$checks" | jq -r '.Data.AllPassing')
merge_ref_usable=$(echo "$checks" | jq -r '.Data.MergeRefUsable')
if [ "$all_passing" = "true" ] && [ "$merge_ref_usable" = "true" ]; then
    echo "[ ] CI checks: PASS"
elif [ "$merge_ref_usable" = "false" ]; then
    echo "[ ] CI checks: merge ref unusable, CI status incomplete"
else
    echo "[ ] CI checks: $(echo "$checks" | jq '.Data.FailedCount') failures, $(echo "$checks" | jq '.Data.PendingCount') pending"
fi

echo "[ ] Pushed: $(git status -sb | head -1)"
```

**If ANY criterion fails**: Do NOT claim completion. Return to appropriate phase.

---

## Comment Map Template (Step 2.2)

Step 2.2 renders `comments.md` from this template. The gates parse its shape: one
`### Comment <id>` block per comment and one `**Status**:` line inside each block.
The Comment Index carries no status cell, by design (see the vocabulary section).
Keep this section last in the file: it nests fences, and the status-grep suite's
fence reader mispairs every fence after it.

````markdown
# PR Comment Map: PR #[number]

**Generated**: [YYYY-MM-DD HH:MM:SS]
**PR**: [title]
**Branch**: [head] → [base]
**Total Comments**: [N]
**Reviewers**: [list]

## Comment Index

| ID | Author | Type | Path/Line | Priority | Plan Ref |
|----|--------|------|-----------|----------|----------|
| [id] | @[author] | review/issue | [path]#[line] | TBD | - |

## Comments Detail

### Comment [id] (@[author])

**Type**: Review / Issue
**Path**: [path]
**Line**: [line]
**Created**: [timestamp]
**Status**: [ACKNOWLEDGED]

**Context**:
```diff
[diff_hunk - last 5-10 lines]
```

**Comment**:
> [body - first 15 lines]

**Analysis**: [To be filled by orchestrator]
**Priority**: [To be determined]
**Plan**: [Link to plan file]
**Resolution**: [Pending / Won't Fix / Implemented / Question]

---

[Repeat for each comment]

````
