# SESSION-PROTOCOL Merge Workflow Debate

## Final decision

Use GitHub squash auto-merge with:

- `strict_required_status_checks_policy: true`
- one front PR updated and tested at a time
- no native merge queue, which is unavailable to this user-owned repository
- no external merge queue
- post-merge main-health verification before advancing
- stacked PRs for dependent new work

Strict freshness is the server-side stale-merge guard. The one-front rule is a
cost control.

## Evidence

| Claim | Evidence |
|-------|----------|
| Strict enabled | Ruleset 11104075 API returned `strict: true` |
| Native queue unavailable | GitHub merge queue requires an organization-owned repository |
| Trunk removed | PR #4814 and issues #4815/#4818 closed; branches deleted |
| Parallel refresh cost | 41 branch updates triggered 820 queued/in-progress runs |
| Cost rollback | 41 auto-merge requests disabled; 818 runs cancelled |
| Serial proof | Exactly one front PR remained armed after rollback |

## Review evolution

The panel reviewed three materially different designs:

1. Strict freshness plus broad auto-merge.
2. Strict off plus a procedural one-front guard.
3. Final: strict freshness plus one front at a time.

The strict-off review identified a merge-time TOCTOU and an unenforceable
single-front safety claim. Restoring strict closes the stale-merge race in
GitHub. Retaining one front avoids the measured parallel CI explosion without
weakening branch protection.

## Final controls

1. Disable every other auto-merge request and verify zero remain.
2. Update only the front PR to main.
3. Run local deterministic and canonical AI gates before the final push.
4. Let required CI pass.
5. Enable squash auto-merge.
6. GitHub strict freshness blocks the PR if main moved.
7. Wait until `MERGED`.
8. Require green main push workflows before advancing.
9. Use stacked PRs for dependent changes, not unrelated backlog work.

## Consensus

The six-role panel accepted the strict model in its earlier round. The later
strict-off review findings are resolved structurally by restoring strict while
keeping the measured one-front cost control. No custom queue, daemon, lock
service, or repository bot is introduced.
