# ADR-092 Debate Log

## Summary

ADR review ran on 2026-08-01 for `ADR-092: Post-Merge Bot Owns Parity Plugin Versions`.
The review evaluated three candidate directions from issue #4080 and reached consensus
on the post-merge bot (option 1) over merge queue (option 2) and git merge driver (option 3).

## Reviewers

| Reviewer | Verdict | Main findings |
|----------|---------|---------------|
| architect | Approve | Clean separation: bot owns a scalar, PRs own content. Torn-main window (30-120s) is acceptable vs Copilot CLI's hours-long refresh cadence. |
| independent-thinker | Approve with note | Git merge driver does not fix server-side merge; issue correctly dismisses option 3. Merge queue alone does not remove the conflict class. |
| security | Approve | Bot commits with `[skip ci]`; no new external trust surface beyond the existing `GITHUB_TOKEN`. |
| analyst | Approve | Consumer enumeration complete: Copilot CLI (version field required), Claude Code (falls back to SHA), verify_npm_package_metadata.py (reads package.json, unaffected). |
| critic | Approve | Shallow-clone hazard for `git rev-list --count` correctly identified and documented. Post-merge bot avoids the hazard entirely. |
| high-level-advisor | Approve | At 11 manifest-only conflicts (O(N^2) rebump cost), the cost of the status quo exceeds the bot's operational risk by a wide margin. |

## Key findings and resolution

| Finding | Resolution in ADR-092 |
|---------|----------------------|
| Torn-main window | Documented: 30-120s window; Copilot CLI refresh is hours; no practical user impact. |
| Shallow clone hazard | Option 1 does not use `git rev-list --count`; bot bumps patch from existing SemVer instead. |
| Copilot CLI requires committed version | Verified in shipped `app.js`: `previousVersion !== newVersion` check. Omitted version permanently breaks update detection. |
| Merge driver option | Correctly dismissed: does not fix GitHub server-side merge; `mergeable` still reports CONFLICTING. |
| Merge queue option | Noted as insufficient alone: serializes correctly but does not remove the conflict class. |
| `taste_count_baseline.txt` same shape | Covered: bot runs `--update` ratchets post-merge; PRs no longer need to edit baseline files. |

## Decision

Post-merge bot (ADR-092 option 1) chosen. Implementation: `scripts/ci/auto_bump_plugin_version.py`
triggered by `.github/workflows/post-merge-version-bump.yml` on push to `main` for parity
source paths. Gate change: `validate_plugin_version_bump.py` blocks manual version changes
on bot-managed plugins (`manually-bumped` violation). Count ratchet change: `count < baseline`
without `--update` now passes (bot handles lowering after merge).

Supersedes ADR-079 (2026-07-08) which rejected the post-merge bot on torn-main and trust-surface
grounds. Re-evaluation at N=11 conflicts overturns that rejection.
