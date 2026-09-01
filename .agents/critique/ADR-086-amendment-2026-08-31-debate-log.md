# ADR Debate Log: ADR-086 Worktree Shim Amendment

## Summary

- **Rounds**: 1
- **Outcome**: Proposed amendment rejected
- **Final status**: ADR-086 remains accepted and unchanged

## Round 1 Summary

The proposed amendment added a repository-owned shim installer. Five reviewers
blocked it. One accepted only after major changes.

An exact two-worktree probe resolved the disputed premise:

- Native Lefthook wrote a branch-local absolute fallback into the shared shim.
- The configured `uv run --frozen lefthook` branch remained first and executed.
- Removing the installing worktree did not break a commit from the survivor.
- `lefthook check-install` failed only when another branch installed a different
  hook configuration.

The runtime worked. The checksum gate reported the false failure from issue
#4789.

### Agent Positions

| Agent | Position |
| --- | --- |
| architect | Accept with changes |
| critic | Block |
| independent thinker | Block |
| security | Block |
| analyst | Block |
| high-level advisor | Block |

### Resolution

- Delete the proposed custom installer and shell parser.
- Keep Lefthook's native installer from ADR-086.
- Set `no_auto_install: true` to stop runtime checksum churn.
- Verify the configured Lefthook runtime instead of `check-install`.
- Keep the adjacent Git Hook Health gate as installation evidence.

This resolution removes code instead of widening ADR-086's ownership boundary.
