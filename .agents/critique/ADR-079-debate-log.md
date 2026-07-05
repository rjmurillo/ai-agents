# ADR-079 — Multi-Agent Debate Log

**ADR**: `.agents/architecture/ADR-079-merge-time-plugin-version-bump.md`
**Decision**: Move the plugin version bump from PR-authoring time to a post-merge workflow
**Triggering context**: Issue #2855 (P1, parallel plugin-source PRs deadlock on the monotonic version-bump gate)
**Date**: 2026-07-05
**Reviewers**: architect, critic, independent-thinker, security, analyst, high-level-advisor
**Outcome**: CONSENSUS (6/6 Accept after one convergence round)

---

## Round 1 — Initial Review

Positions: architect Accept, critic Accept (approved-with-concerns), analyst Accept, high-level-advisor Accept, security Conditional Accept, independent-thinker Disagree-and-Commit. No hard Block. The two non-plain-Accept positions carried the binding P1 items.

### Consolidated blocking items (deduplicated across reviewers)

| ID | Item | Raised by | Priority | Resolution |
|----|------|-----------|----------|------------|
| B1 | Content-hash freshness key not evaluated as an alternative | independent-thinker | P1 | Added Option 4 to Alternatives + Context force 2: the cache key is owned by the external plugin host (Claude Code / marketplace), not this repo, so a content-addressable key is not unilaterally available. Rejected on that ground. |
| B2 | Rapid-succession merge race (two merges → same `N+1`) | critic, independent-thinker | P1 | Decision item 3: deterministic idempotent rule `max(main_version, any_version_in_commit) + patch` + `concurrency: { group: plugin-version-bump, cancel-in-progress: false }` per ADR-026. |
| B3 | Bot token model unspecified | security | P1 | Decision item 3 + Impact table + Impl Notes: GitHub App installation token, `contents: write` least-privilege, not a repo-scoped classic PAT. |
| B4 | Path constraint aspirational, not enforced | security | P1 | Decision item 3: pre-push `git diff --name-only` allow-list assertion that aborts on any out-of-list path. Impl Notes note branch protection cannot path-scope a bypass actor; the workflow enforces it (ruleset path-restricted bypass preferred if available). |
| B5 | No rollback / fail-safe for a broken post-merge bump | advisor, analyst, architect, critic, independent-thinker | P1/P2 | New "Failure Recovery" subsection: reconciliation detector opens an issue on any unbumped content commit; N-consecutive-failure rollback re-enables the PR-time blocking gate; idempotent re-run. |
| B6 | `decision-makers: []` empty | architect | P1 | Set to `[rjmurillo]`. |
| B7 | No acceptance / kill criteria | critic | P1 | New "Acceptance Criteria" section (6 numbered, testable criteria). |
| B8 | Recursion guard mechanism undecided (`[skip ci]` menu) | security, critic, independent-thinker | M/P2 | Bound to an author filter on the bot identity; explicit prohibition of `[skip ci]` (would suppress unrelated required checks). |
| B9 | "Advisory" semantics undefined | advisor | P2 | Decision item 2: check runs, status non-required, warns on downward version edits only. |
| B10 | Merge-to-bump transient staleness window unacknowledged | advisor, independent-thinker | P2 | Consequences: window explicitly named, bounded to workflow runtime, safe because installed caches key off released versions, not `main` HEAD. |
| B11 | ADR-006 "Python module" over-attribution (ADR-006 says PowerShell) | analyst, critic | P2 | Related Decisions: cite ADR-006 principle (testable modules) + ADR-042 for the Python specificity. |

### Citation audit (analyst)

All file-path, workflow-name, version (`.claude`/`src/copilot-cli` 0.6.3 lockstep; `src/claude` 0.3.35), and RULE-docstring citations verified against on-disk state. One cosmetic over-attribution (B11) fixed. New citations introduced during revision (ADR-026, ADR-042) verified to resolve to their stated titles before inclusion.

---

## Round 2 — Convergence

The two reviewers holding binding positions (security Conditional Accept; independent-thinker Disagree-and-Commit) re-reviewed the revised ADR against their own P1 items.

### security: Accept

Both P1 items verified resolved with enforced, testable controls (GitHub App least-privilege token; pre-push allow-list assertion codified by acceptance criterion 5). Recursion guard, supply-chain rollback, and transient-window all [PASS]. Risk Score revised 6/10 → 3/10.

### independent-thinker: Accept

B1 (content-hash) rejection sound: no evidence this repo controls the consumer cache layer. B2 (race) resolved by concurrency group + idempotent bump rule, codified by acceptance criterion 4. P2 items verified. No unresolved blocking concerns.

---

## Final Tally

| Reviewer | Round 1 | Round 2 |
|----------|---------|---------|
| architect | Accept | — |
| critic | Accept (concerns) | resolved via B2/B5/B7/B8 |
| analyst | Accept | resolved via B11 |
| high-level-advisor | Accept | resolved via B5/B9/B10 |
| security | Conditional Accept | **Accept** (3/10) |
| independent-thinker | Disagree-and-Commit | **Accept** |

**Consensus: 6/6 Accept.** No dissent carried forward. The ADR remains `status: proposed` pending owner acceptance; consensus authorizes moving it forward, not auto-accepting it.
