# PR Review: Acknowledgment Protocol

## Skill-PR-Comment-001: Acknowledgment BLOCKING Gate

**Statement**: Phase 3 BLOCKED until eyes reaction count equals comment count.

**Atomicity**: 100% | **Tag**: critical

```bash
COMMENT_COUNT=$(gh api repos/O/R/pulls/PR/comments --jq 'length')
EYES_COUNT=$(gh api repos/O/R/pulls/PR/comments --jq '[.[].reactions.eyes] | add')
[ "$EYES_COUNT" -lt "$COMMENT_COUNT" ] && echo "BLOCKED" && exit 1
```

## Skill-PR-Comment-002: Session-Specific Work Tracking

**Statement**: Track 'NEW this session' separately from 'DONE prior sessions'.

**Atomicity**: 100% | **Tag**: critical

**Anti-Pattern**: Conflating prior session replies with current session obligations.

## Skill-PR-Comment-003: API Verification Before Phase Completion

**Statement**: Verify mandatory step completion via API before marking phase complete.

**Atomicity**: 100% | **Tag**: critical

## Skill-PR-Comment-004: PowerShell Fallback to gh CLI

**Statement**: PowerShell script failure requires immediate gh CLI fallback attempt.

```bash
if ! pwsh Add-CommentReaction.ps1 -CommentId $ID -Reaction "eyes"; then
  gh api repos/O/R/pulls/comments/$ID/reactions -X POST -f content="eyes"
fi
```
