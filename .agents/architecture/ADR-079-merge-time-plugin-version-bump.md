---
id: ADR-079
status: superseded
date: 2026-07-08
decision-makers: [rjmurillo]
supersedes: []
superseded-by: ADR-091
explainer: null
implemented: true
---

# ADR-079: Plugin Version Bump Stays at PR Time (Reject Merge-Time Automation)

## Status

Superseded by ADR-091 (2026-07-31), the immediate successor, which moved plugin-version maintenance to a post-merge bot. ADR-091 states the supersession in its own accepted Status: "Supersedes ADR-079 (Plugin Version Bump Stays at PR Time)." ADR-091 was itself superseded one day later by ADR-092 (2026-08-01), the live record, which deletes the `version` field from all three manifests so Claude Code resolves freshness from the commit SHA. ADR-092 does not contradict the objection below: that objection is to a post-merge *stamp*, and omitting the field stamps nothing at any point. The premise that has changed is the Copilot one: the shipped 1.0.78-0 bundle calls `updatePlugin` unconditionally, and the official CLI plugin reference lists `version` as optional metadata.

Accepted (2026-07-08). Requested by issue #2855 (labels `bug`, `agent-qa`, `area-workflows`, `area-infrastructure`, `area-skills`, `priority:P1`, `technical-debt`). The issue surfaces a real throughput cost: parallel plugin-source PRs serialize on the monotonic version-bump gate.

The first draft of this ADR recommended moving the bump to merge time via a post-merge auto-bump bot. Owner review (2026-07-07) rejected that direction on first principles and selected the opposite: keep the bump in the PR, accept the serialization, and add no automation. The decisive objection: any post-merge stamp leaves `main` carrying changed content under an unchanged version until the follow-up commit lands, which is a torn state that violates the repo rule that release-participating artifacts ship with the change that necessitates them.

Because the recommendation changed materially from the reviewed draft, the `adr-review` skill re-ran the 6-agent debate against the current PR-time-retention decision (Round 3 in the debate log at `.agents/critique/ADR-079-debate-log.md`). Outcome: 6/6 Accept. Both acceptance criteria are met: (a) the re-review completed with no blocking findings, and (b) the owner confirmed the decision to keep PR-time bumping and reject automation (issue #2855 thread, 2026-07-08). The ADR filename retains the historical `merge-time` slug to preserve inbound links; the title and decision are authoritative.

Issue #3875 revisited Decision point 4 with measured traffic data, as the original ADR requested if the traffic assumption changed. The decision stays the same, but the cost model changes: recent merged PRs show packaged-plugin-source changes in one third of merges, so collision handling is a common coordination cost, not a rare tail event.

## Date

2026-07-08

## Context

Three plugins are published from source directories, each carrying a `.claude-plugin/plugin.json` with a semantic `version`:

- `.claude/.claude-plugin/plugin.json`
- `src/copilot-cli/.claude-plugin/plugin.json`
- `src/claude/.claude-plugin/plugin.json`

Two CI gates govern these versions:

1. **Version-bump gate** (`build/scripts/validate_plugin_version_bump.py`, enforced by `.github/workflows/validate-plugin-version-bump.yml`). When any content file under a packaged plugin's source directory changes in the diff, that plugin's `version` MUST be strictly greater than the version at the base ref. The validator's docstring states the reason: "Installed plugin caches key off that version: when the version does not change, existing installs never re-sync, so deletions and edits inside the source dir silently fail to reach consumers." This is the silent-staleness bug the gate prevents (PR #1942).

2. **Manifest-parity gate** (`build/scripts/check_plugin_manifest_parity.py`). The `.claude` and `src/copilot-cli` manifests MUST carry identical versions.

The bump is monotonic and evaluated at PR-CI time against the base ref. Each of the two version lines (see Decision) serializes independently. Within one line, K open PRs can each hold `N+1` in their own branch, but only one can merge at `N+1`; when it does, `main` advances and every other open PR on that line now equals base and fails the gate. Each must rebase onto `main` and re-bump, up to once per sibling that merges ahead (O(K) worst case). A `project-toolkit` PR and a `claude-agents` PR never contend with each other; only same-line PRs collide.

### How the plugin hosts key freshness (verified)

The freshness requirement is a host constraint, not a repo preference. Both hosts consume these manifests as raw source at the repo's HEAD; there is no build or publish step between the repo and the host, so nothing can stamp the version ephemerally at build time.

- **Claude Code.** If `version` is omitted, resolution falls back to the git commit SHA, so every commit is a new version and installs stay fresh automatically. Version-resolution order (code.claude.com plugin-marketplaces docs): `plugin.json` `version`, then marketplace entry `version`, then the commit SHA.
- **GitHub Copilot CLI (v1.0.69-0, verified in the shipped `app.js` bundle).** The plugin parse defaults an omitted version to the constant string `"unknown"` (`version: s.version||"unknown"`); there is no SHA fallback. The update check compares the version string for **inequality** (`previousVersion!==newVersion`) and prints "already at latest" when the strings are equal. A second inequality check (`l.version!==a[c]?.version`) drives the skill-reload/cache-clear path, so an unchanged version also skips re-sync. Neither path does SemVer ordering, and neither reads the source ref for the version.

Two facts follow, and they bound every option below:

1. **A changing in-tree `version` is mandatory for Copilot CLI.** Omitting it pins every install at `"unknown"` and updates are never detected. The version must be a real, changing value checked into the manifest the host reads. There is no way to make Copilot derive freshness from git; it reads only the manifest content.
2. **The host requires inequality, not monotonicity.** Copilot detects an update whenever the string differs. Monotonic increase is a human-legibility choice (people expect version numbers to go up), not a host requirement. This repo keeps monotonic on that basis.

### The core tension

The invariant that must hold is: **a distinct, greater version per content-changing merge.** The current gate approximates it with a PR-time check that cannot know what `main` will be at merge time. That mismatch is the source of the serialization. The draft ADR tried to close the mismatch by moving the write to merge time. Owner review found that cure worse than the disease, because the write itself cannot be removed (both hosts read the raw checked-in value) and moving it after the merge tears `main`.

## Decision

Keep the plugin version bump where it is: hand-set in the PR, shipped in the same commit as the content change, enforced by the existing PR-time strictly-greater gate. Reject the post-merge auto-bump bot and every other automation that removes the bump from the PR. Accept the parallel-PR rebump cost as the price of simplicity.

1. **One versioning scheme, two independent version lines.** Every manifest uses the same monotonic-SemVer scheme, but the values are not globally shared. `.claude` and `src/copilot-cli` are the same plugin (`project-toolkit`) emitted per harness; the parity gate (`check_plugin_manifest_parity.py`) holds their two versions identical. `src/claude` is a distinct plugin (`claude-agents`) that carries its own independent monotonic line and is not in the parity gate. Within each line, the version is hand-set in the PR. No per-host bifurcation of the *scheme* (for example, omit-for-Claude and stamp-for-Copilot): Copilot needs a real, changing value, so every line supplies one. A split scheme is more surface for no benefit.

2. **The bump ships in the PR.** The version change lands in the same commit as the content change. `main` is never in a state where content changed but the version did not. This preserves the repo rule that generated and release-participating artifacts ship with the change that necessitates them, never in a follow-up sync commit.

3. **The existing PR-time gate stays blocking and monotonic.** `validate_plugin_version_bump.py` continues to require a strictly-greater version when packaged plugin content changes. Monotonic because humans expect version numbers to increase, and because a strictly-greater value is a trivially correct way to guarantee the inequality the Copilot host needs. Strictly-greater is also the only guard against a *downgrade*: because Copilot's check is string inequality, a decreased version still differs and would push to installs as an "update," so the gate, not the host, is what blocks a rollback from reaching consumers. The gate enforces strictly-greater regardless of host semantics, so a lower-or-equal version fails even though the host itself would accept any inequality.

4. **Cross-PR collision is accepted with measured traffic, not engineered away.** Two PRs on the same version line, off the same base, both bump to `N+1`; when one merges, the other equals base and must rebase and re-bump, up to once per sibling that merges ahead (O(K) worst case for K concurrent same-line PRs). This serializes same-line plugin-source merges. Issue #3875 measured the earlier traffic assumption: 26 open PRs included 14 that touched packaged plugin source (54%), but that sample was biased by one campaign; the defensible merged-PR sample was 60 most recently merged PRs, of which 20 touched packaged plugin source (33%). One in three merged PRs is not a small fraction, so this ADR now accepts a common-case coordination cost rather than a rare tail cost. The per-collision cost is also not just a rebase: a version-line conflict can require manual conflict resolution and a rerun of the pre-push hook gate chain. Two mitigations bound the pain and stay in place: the merge-resolver rule that resolves a version-only `plugin.json` conflict to one patch above the higher side (issue #2543), re-checked by the same PR-time gate before merge; and an auto-loaded recovery-recipe instruction file that teaches the `max(open-PR versions) + 1` plus immediate-auto-merge move (PR #2873, a mitigation for #2855).

This ADR ships no code. It keeps the current gates and mitigations and records why the automation alternatives were rejected.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern**: the PR-time monotonic version-bump gate (`validate_plugin_version_bump.py`) plus the manifest-parity gate (`check_plugin_manifest_parity.py`), backed by `validate-plugin-version-bump.yml`.
- **When introduced**: the version gate traces to the silent-staleness failure (PR #1942, hand-caught in PR #2114); the tactical conflict resolver to issue #2543; the recovery-recipe instruction file to PR #2873.
- **Original context**: repo-owner-driven release-engineering guards to keep installed plugin caches fresh.

### Historical Rationale

- **Why built this way?** Installed plugin caches key off `version`. A content change under an unchanged version never re-syncs to consumers (#1942). A strictly-greater bump on every content change prevents that.
- **Constraints**: PR-time CI is the cheapest enforcement point and needs no self-committing workflow or branch-protection exception.

### Why Not Automate

- **The scale pain is real** and common: issue #3875 measured 20 of 60 recent merged PRs touching packaged plugin source (33%). Each collision costs conflict resolution plus a rerun of the pre-push hook gate chain, not just a rebase.
- **Every automation still costs more than the pain it removes.** Post-merge stamping tears `main`; a merge queue adds infrastructure and still serializes; git-height and content-hash still write a value and either tear `main` or collide; a git merge driver has clone-local configuration and fail-closed semantics that must be proven before it can become policy; relaxing the gate reopens #1942. Detail in Alternatives.
- **The write cannot be removed.** Both hosts read the raw checked-in value from HEAD; there is no build boundary to stamp ephemerally. So the only real choices are where the write happens (PR vs post-merge) and how the value is produced (hand vs derived). PR-time hand-bump is the only one of those that is correct at merge with zero new trust surface.

## Rationale

### Alternatives Considered

| Alternative | Why chosen / rejected |
|-------------|-----------------------|
| **PR-time monotonic bump in the PR + tactical mitigations (CHOSEN)** | Correct at merge; `main` never torn; zero new infrastructure; zero new trust surface; one legible monotonic scheme for both hosts. Cost is the accepted rebump on concurrent plugin-source PRs. Issue #3875 measures that cost as common enough to document explicitly; #2543 and #2873 bound, but do not remove, the pain. |
| **Post-merge auto-bump bot** | Rejected. Between the content merge and the bot's bump commit, `main` carries changed content under an unchanged version: a torn state that violates the "artifacts ship with the change" rule. Adds a new trusted actor committing to protected `main`, a branch-protection carve-out, a recursion guard, and a serialized queue as the correctness mechanism. High complexity that may or may not hold, to remove a common but still bounded coordination cost. |
| **GitHub merge queue with a bump step** | Rejected. Heavier infrastructure and a merge-queue dependency; still serializes plugin-source merges; does not remove the bump. |
| **Derived version from git height (NBGV-style)** | Rejected. Still commits a value to the manifest the host reads, so the write is not eliminated. Computed at PR time it collides identically to the hand-counter; computed post-merge it tears `main` like the bot. NBGV's zero-write property comes from stamping at build time and never checking in; there is no build boundary here (hosts read raw HEAD), so that escape is unavailable. |
| **Content-addressable freshness key (hash of packaged source)** | Rejected on legibility. A per-plugin content hash would actually cut the version-only collisions, since a hash of that plugin's own tree does not change when a sibling touches different content. But it drops the monotonic ordering humans expect from a version, for no host benefit, since Copilot needs only inequality, which monotonic SemVer already provides. A checked-in hash of the merged tree also reintroduces the write-timing problem (tears `main` post-merge, or is stale at PR-time). Legibility is the decisive reason to decline. |
| **Git merge driver for `plugin.json` version-only conflicts** | Not chosen in this ADR. A merge driver that resolves a version-only `plugin.json` conflict to one patch above the higher side would mechanize the existing #2543 rule inside the PR branch, so it does not tear `main` and deserves a separate spike. It is not adopted here because merge drivers are clone-local configuration, not repository policy by default; it must prove it fires on pull, rebase, and bot merges; and it must fail closed when a conflict is not version-only. |
| **Relax the PR-time gate to `>=`** | Rejected. Reopens the silent-staleness bug (#1942): a content change under an unchanged version never reaches Copilot installs, whose update check is `!=` (equal means no update). |
| **Do nothing, remove the mitigations** | Rejected. The rediscovery cost (#2873) and conflict thrash (#2543) return. The mitigations are cheap and stay. |

### Trade-offs

The chosen option trades a common coordination cost (rebump on concurrent plugin-source PRs) for zero new infrastructure and zero new trust surface. The trade is still favorable after issue #3875: 20 of 60 recent merged PRs touched packaged plugin source (33%), and each collision can require conflict resolution plus a pre-push hook gate-chain rerun, not just a rebase. The cost is real, measured, and higher than originally assumed. The decision accepts that cost because the higher-risk alternatives add a torn-`main` window, a self-committing bot, or a clone-local merge-driver policy that is not proven safe enough to make binding here.

## Consequences

### Positive

- `main` is never torn: version and content always change together, satisfying the "artifacts ship with the change" rule.
- No new trusted actor, no bot committing to protected `main`, no branch-protection carve-out, no recursion guard, no post-merge queue.
- One monotonic SemVer scheme across all manifests; the two `project-toolkit` emissions are held equal by the parity gate while `claude-agents` versions on its own line; human-legible; parity gate unchanged.
- Correct for both hosts: monotonic SemVer gives Copilot CLI the inequality it needs and Claude Code a real version.
- Simplest possible mechanism. Nothing new to build, test, or operate.

### Negative

- Parallel same-line plugin-source PRs still serialize: only one merges at `N+1`, the rest rebase and re-bump (O(K) worst case). Accepted with measured frequency: issue #3875 found 20 of 60 recent merged PRs touched packaged plugin source (33%). Bounded by issue #2543 (auto-resolve) and PR #2873 (recovery recipe), but still a common coordination cost.
- Contributors and fleet agents must remember to bump. The auto-loaded instruction (#2873) and the gate's failure message keep this a pit of success rather than tribal knowledge.

### Neutral

- The manifest-parity gate stays. The version scheme (SemVer core, strictly-greater precedence) is unchanged. The only outcome of this ADR is the decision to keep the current mechanism and reject automation.

## Impact on Dependent Components

| Component | Required Update | Risk |
|-----------|-----------------|------|
| `.github/workflows/validate-plugin-version-bump.yml` | None. Stays blocking and monotonic. | None |
| `build/scripts/validate_plugin_version_bump.py` | None. | None |
| `build/scripts/check_plugin_manifest_parity.py` | None. Parity stays. | None |
| `.github/instructions/plugin-version-bump.instructions.md` (#2873) | Keep. It is the accepted coping mechanism, not a stopgap. Optionally sharpen the `max(open-PR versions) + 1` wording and add the one-line reason (Copilot's update check is `!=`, so a distinct version is mandatory). | Low |
| Tactical merge-resolver auto-bump (#2543) | Keep. | Low |
| Repository branch protection | None. No bot writes to `main`. | None |

## Implementation Notes

No code implementation. Optional documentation follow-ups:

1. Add the cross-harness facts from this ADR's Context to the #2873 instruction file so the next agent does not re-derive Copilot vs Claude version semantics.
2. Ensure the version-bump gate's failure message points at the #2873 recovery recipe.

## Acceptance Criteria

This ADR is accepted when (a) the mandatory `adr-review` debate has completed with its findings resolved, and (b) the owner confirms the decision to keep PR-time bumping and reject automation. No code lands. Issue #2855 closes as "decided: keep PR-time monotonic bump in the PR; automation (post-merge bot, merge queue, git-height, content-hash) rejected; mitigations #2543 and #2873 retained," linking this ADR.

## Related Decisions

- ADR-006 (thin workflows, testable modules): unchanged; no new workflow logic is added.
- ADR-026 (PR automation concurrency and safety controls): referenced only to note the rejected post-merge design would have depended on it.
- ADR-072 (JTBD plugin architecture): defines the packaged-plugin model whose versions this ADR governs.
- Issue #2543 (tactical merge-resolver auto-bump); PR #2873 (auto-loaded recovery recipe, a mitigation for #2855); PR #1942 (the silent-staleness failure the version gate prevents, hand-caught in PR #2114).

## References

- Issue #2855 (this ADR's request and evidence).
- Issue #3875 (measured Decision point 4 traffic and cost).
- `build/scripts/validate_plugin_version_bump.py` (RULE docstring).
- `build/scripts/check_plugin_manifest_parity.py` (manifest parity).
- `.github/workflows/validate-plugin-version-bump.yml`, `.github/workflows/validate-generated-agents.yml`, `.github/workflows/agent-drift-detection.yml`.
- `.github/instructions/plugin-version-bump.instructions.md`.
- Cross-harness evidence: GitHub Copilot CLI bundle `app.js` v1.0.69-0 (plugin parse `version: s.version||"unknown"`; update check `previousVersion!==newVersion`); Claude Code plugin-marketplaces docs (version-resolution order, commit-SHA fallback).
- SemVer 2.0.0 (https://semver.org/#spec-item-11).
