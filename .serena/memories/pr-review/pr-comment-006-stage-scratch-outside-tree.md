# Skill: Write Scratch Artifacts Outside the Working Tree

## Statement

Reply drafts, intermediate command bodies, and agent rough notes go to `$TMPDIR` via `mktemp`. Never `.agents/`, the working tree, or any path that survives the session.

## Trigger

Whenever an agent needs to stage a multi-line body for `--body-file`, redirect intermediate command output, or write rough notes during PR review or any other task.

## Action

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

REPLY_FILE="$(mktemp -t pr-reply-XXXXXX.md)"
trap 'rm -f "$REPLY_FILE"' EXIT
cat > "$REPLY_FILE" <<'EOF'
[response body]
EOF
python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py" \
  --pull-request "$PR" --comment-id "$COMMENT_ID" --body-file "$REPLY_FILE"
```

The `mktemp -t` form puts the file in `$TMPDIR` (or `/tmp`). The `trap` removes it on shell exit, including failure paths.

## Benefit

- Reply drafts have no enduring value once posted to the PR thread; staging them in the repo creates untracked workspace clutter.
- Future agents cannot tell intentionally-archived artifacts apart from leftover drafts when both live under `.agents/audit/`.
- `mktemp` paths are unique per process, so concurrent agent runs do not collide.

## Evidence

- 2026-04-30 to 2026-05-02: PR #1790 left 17 untracked draft files under `.agents/audit/pr-1790-replies/` after merge. Same pattern observed for PRs #1819 (`pr1819-reply-*.md`) and #1829 (`pr1829-reply-*.md`), strewn at the top level of `.agents/audit/`. PR #1795 accidentally committed its `pr-1795-replies/` directory as part of the merge, which then served as a precedent the workflow could not distinguish from drift.
- 2026-05-02: rule landed in `AGENTS.md ## Boundaries > Never` (`Scratch in working tree (use $TMPDIR/mktemp)`), and `.gitignore` gained safety-net entries for `.agents/audit/pr-*-replies/` and `.agents/audit/pr*-reply-*.md` so unintended writes do not enter git even if guidance is ignored. The compact phrasing is intentional: AGENTS.md has a 3000-byte per-file workspace budget that the long form blew through; the full rationale (no enduring value once posted; mktemp staging required) lives in this memory file, which AGENTS.md cross-references.
- Skill template updated: `.claude/skills/pr-comment-responder/references/templates.md` `## Reply API Usage`.

## Anti-Pattern

Writing reply drafts to a relative path (`reply.md`) or an `.agents/audit/pr-<N>-replies/` directory. The agent's CWD becomes the staging surface, the file outlives the session, and either accumulates as untracked clutter or accidentally gets committed.

## Related

- [pr-comment-004-bot-response-templates](pr-comment-004-bot-response-templates.md): structured response bodies for bot review comments
- [pr-comment-005-branch-state-verification](pr-comment-005-branch-state-verification.md): pre-edit branch verification
- [pr-comment-index](../pr-comment-index.md)
- `AGENTS.md` `## Boundaries > Never`
- `.claude/skills/pr-comment-responder/references/templates.md` `## Reply API Usage`

## Atomicity

**Score**: 95%

**Justification**: Single concept (where to stage agent scratch artifacts). Highly actionable: one rule, one canonical command pattern, one explicit anti-pattern.

## Category

pr-comment-responder

## Created

2026-05-02
