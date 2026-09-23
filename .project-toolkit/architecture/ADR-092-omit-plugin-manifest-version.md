---
id: ADR-092
status: accepted
date: 2026-08-01
decision-makers: [rjmurillo]
supersedes: [ADR-091]
superseded-by: null
explainer: null
implemented: true
---

# ADR-092: Omit `version` From Plugin Manifests and Resolve Freshness From the Commit SHA

## Status

Accepted (2026-08-01). Requested by issue #4080. Supersedes ADR-091 directly and reverses ADR-079, which decided to keep a hand-set `version` in every packaged plugin manifest and to reject every automation that moved the bump.

Supersession chain: ADR-079 (2026-07-08) to ADR-091 (2026-07-31) to ADR-092 (2026-08-01). The `supersedes` and `superseded-by` fields name immediate neighbors only, so this record's frontmatter lists ADR-091 alone and ADR-079 is retired transitively; ADR-091's own accepted Status records "Supersedes ADR-079 (Plugin Version Bump Stays at PR Time)." Why this record also reverses ADR-079's reasoning is set out under "Why ADR-079's objection does not apply" and "Why ADR-091 is superseded within hours of landing" below. Refs issue #5192.

## Date

2026-08-01

## Context

Three plugins publish from source directories, each carrying a `.claude-plugin/plugin.json`:

- `.claude/.claude-plugin/plugin.json` (project-toolkit, Claude)
- `src/copilot-cli/.claude-plugin/plugin.json` (project-toolkit, Copilot)
- `src/claude/.claude-plugin/plugin.json` (claude-agents)

Until this ADR each carried a `version` string that every plugin-source PR had to hand-bump, policed by two gates: a strictly-greater bump check (`build/scripts/validate_plugin_version_bump.py`) and a parity check holding the two project-toolkit manifests equal (`build/scripts/check_plugin_manifest_parity.py`).

### The measured cost

Issue #4080 measured the result on the open-PR queue. Of 22 conflicting PRs, **14 conflicted on nothing but the version line**. Merging #4077 immediately re-conflicted the next four green PRs. The field is a single-line counter that every plugin-source PR must write, so any two such PRs conflict pairwise by construction. ADR-079 already recorded the frequency behind this: issue #3875 found 20 of 60 recent merged PRs touching packaged plugin source (33%).

### What the hosts actually do

**Claude Code**, https://docs.claude.com/en/docs/claude-code/plugins-reference, section "Version management", verbatim:

> "Claude Code uses the plugin's version as the cache key that determines whether an update is available. When you run /plugin update or auto-update fires, Claude Code computes the current version and skips the update if it matches what's already installed. The version is resolved from the first of these that is set:
>
> 1. The version field in the plugin's plugin.json
> 2. The version field in the plugin's marketplace entry in marketplace.json
> 3. The git commit SHA of the plugin's source, for github, url, git-subdir, and relative-path sources in a git-hosted marketplace
> 4. unknown, for npm sources or local directories not inside a git repository"

The same page documents two supported approaches, not one. Of the explicit-version approach it says:

> "Explicit version | Set \"version\": \"2.1.0\" in plugin.json | Users get updates only when you bump this field. Pushing new commits without bumping it has no effect, and /plugin update reports 'already at the latest version'."

Of the other:

> "Commit-SHA version | Omit version from both plugin.json and the marketplace entry"

And https://docs.claude.com/en/docs/claude-code/plugin-marketplaces, release channels, verbatim:

> "If you omit version, the distinct commit SHAs already distinguish the channels. If two refs resolve to the same version string, Claude Code treats them as identical and skips the update."

**GitHub Copilot CLI**, https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference: `name` is the only required `plugin.json` field. `version` is listed under "Optional metadata fields" ("Semantic version (e.g., 1.0.0)"). No update-gating on version is documented; `copilot plugin update NAME` is documented only as "Update a named plugin."

The shipped bundle agrees. Read at `~/.copilot/pkg/linux-x64/1.0.78-0/app.js`, newer than the 1.0.69-0 build ADR-079 relied on: `updateAll()` iterates installed plugins and calls `updatePlugin(spec)` unconditionally, with no version comparison anywhere in the decision path. Every `previousVersion!==newVersion` occurrence is presentation or telemetry: the display strings `` ` (v${prev} → v${new})` `` and `` ` (v${new}, already at latest)` ``, and `version_changed: String(t.previousVersion!==t.newVersion)` inside a telemetry payload. Cache invalidation keys off a `skillsCacheDirty` flag returned by the native operation, not off the version. Caveat: `updatePlugin` delegates to a native binding (`pluginOperationsUpdatePlugin`); the JS layer provably does not gate on version, and the native layer was not readable.

This is the correction to ADR-079's decisive premise. ADR-079 recorded, from the 1.0.69-0 bundle, that "a changing in-tree `version` is mandatory for Copilot CLI" because "the update check compares the version string for inequality". Under the current bundle the update path does not consult the version at all, and the official reference classifies the field as optional metadata.

### This repository, measured

- `.claude-plugin/marketplace.json` lists `claude-agents` (source `./src/claude`) and `project-toolkit` (source `./.claude`). Neither entry carries a `version`.
- `.github/plugin/marketplace.json` lists `project-toolkit` (source `./src/copilot-cli`). No `version`.
- Only the three `plugin.json` files carried one.

Relative-path sources in a git-hosted marketplace are exactly case 3 in the resolution order. So deleting the field from the three manifests makes Claude Code resolve freshness from the commit SHA, which changes on every merge.

## Decision

Delete `version` from all three packaged plugin manifests and keep it deleted. Freshness resolves from the git commit SHA.

1. **No packaged manifest carries a `version` field.** `build/scripts/validate_plugin_version_bump.py` is inverted: it now fails, exit 1, when any of the three manifests carries the key. The module keeps its name, CLI shape, and exit-code contract (0 clean, 1 violation, 2 config error) so existing callers keep working. `--base` and `--files` are still accepted and no longer affect the verdict, because the field's presence is not a function of the diff.

2. **The marketplace entries stay version-free too.** A marketplace `version` is resolution step 2 and would re-pin freshness ahead of the SHA even with `plugin.json` clean. A repository-state test in `tests/build_scripts/test_validate_plugin_version_bump.py` fails if one appears in either marketplace file.

3. **The version half of the parity gate is retired.** `check_plugin_manifest_parity.py` keeps only the description-count check (#2187, #3651). With no version there is nothing to hold equal.

4. **PRs never touch the field.** `.claude/rules/plugin-version-bump.md` is rewritten from a rebump recipe into that rule, and `.claude/rules/knowledge-persistence.md` drops its MUST to bump the manifests.

### Why ADR-079's objection does not apply

ADR-079 rejected merge-time automation on one decisive ground, quoted from its Status section: "any post-merge stamp leaves `main` carrying changed content under an unchanged version until the follow-up commit lands, which is a torn state that violates the repo rule that release-participating artifacts ship with the change that necessitates them."

That objection is correct and this ADR does not contest it. It applies to a post-merge *stamp*. Omitting the field has no post-merge stamp at all: nothing writes a version, before or after the merge, so there is no window in which `main` carries content under a stale version. ADR-079 framed the choice as zero-tear versus zero-conflict and picked zero-tear. That trade only held while the version stayed committed. Removing the field gets both.

ADR-079's other premise, that "the write cannot be removed" because "both hosts read the raw checked-in value from HEAD", was true of Copilot in 1.0.69-0 and is not true of the documented contract or the current bundle. Claude Code's step 3 is exactly a way to read freshness from git rather than from a checked-in value.

## Prior Art Investigation

### What Currently Exists

- **Structure/pattern**: the PR-time strictly-greater version gate plus the manifest-parity gate, backed by `.github/workflows/validate-plugin-version-bump.yml`. Decided by ADR-079 (2026-07-08).
- **When introduced**: the version gate traces to the silent-staleness failure in PR #1942, hand-caught in PR #2114; the tactical conflict resolver to issue #2543; the recovery-recipe instruction file to PR #2873.
- **Original context**: keep installed plugin caches fresh when a plugin's source changes.

### Historical Rationale

The gate existed because an installed plugin cache keyed off the version, so a content change under an unchanged version never re-synced (#1942). The commit-SHA path serves the same purpose strictly better on Claude Code: the SHA changes on every merge, so no content change can ship under a repeated key, and no human has to remember anything.

## Rationale

### Alternatives Considered

| Alternative | Why chosen / rejected |
|-------------|-----------------------|
| **Omit the field; resolve from the commit SHA (CHOSEN)** | Documented, supported approach, not a workaround. Per-commit freshness on Claude Code, strictly finer than a hand counter. No post-merge stamp, so no torn `main`. No line for concurrent PRs to conflict on. Removes two gates' worth of policy and one recovery recipe. |
| **Keep the PR-time hand bump (ADR-079's decision)** | Rejected now. Its cost is measured: 14 of 22 conflicting PRs conflicted on nothing but this line, and merging #4077 re-conflicted the next four green PRs. Its decisive justification (Copilot requires a changing in-tree value) does not hold against the current documentation or the 1.0.78-0 bundle. |
| **Post-merge auto-bump bot** | Rejected, ADR-079's reasoning stands unchanged. Between the content merge and the bot's commit, `main` carries changed content under an unchanged version. Adds a trusted actor committing to protected `main`, a branch-protection carve-out, a recursion guard, and a serialized queue as the correctness mechanism. |
| **GitHub merge queue** | Rejected. It ejects entries that conflict with the queue head, so it cannot help in the case that actually hurts here: every plugin-source entry conflicts pairwise, so the queue would eject rather than serialize them. It also adds infrastructure and does not remove the bump. |
| **Distinct version slots per PR (each PR picks a different number)** | Rejected. Proven this session to fix the *gate comparison*, since each branch is strictly greater than base, while leaving the *textual conflict* intact: two branches still edit the same line to different values, which is a conflict regardless of what the gate thinks. |
| **Relax the gate to `>=`** | Rejected on the same ground ADR-079 gave: it reopens silent staleness for any host that keys on the field, and it still leaves the conflicting line in place. |

### Trade-offs

The chosen option gives up a human-legible semantic version in `/plugin` listings and gives up any version signal for a host that ignores git. In exchange it removes a per-PR write that 14 of 22 conflicting PRs collided on, removes the rebump recovery loop, and upgrades Claude Code freshness from hand-bumped to per-commit.

## Why ADR-091 is superseded within hours of landing

ADR-091 (PR #4147, merged as `edecb8e85`) chose a post-merge bot to own the parity versions. The
direction was not unreasonable: it removes the per-PR write, which is the actual conflict source, and
it covered the count baselines too, which this ADR does not. It is superseded because its mechanism
cannot run in this repository, and its failure mode is silent.

Four facts, each verified against the merged commit:

1. **It tore `main` on its own merge.** `edecb8e85` changed packaged plugin source
   (`.claude/rules/plugin-version-bump.md` and both instruction mirrors, 179 lines each) and left the
   version at `0.6.5493`, identical to `edecb8e85^`. Content changed, freshness key did not.

2. **The bot never ran, and could not have.** The squashed merge message quotes the bot's own commit
   template and so contains the literal `[skip ci]`, which suppresses push-triggered workflows on that
   commit. `gh run list --workflow post-merge-version-bump.yml` returned 0 runs.

3. **The bot could not push even when triggered.** Protection is ruleset 11104075, whose sole bypass
   actor is `RepositoryRole id=5`. `github-actions[bot]` is not one, and the `pull_request` rule
   refuses direct pushes regardless of `contents: write`. ADR-091 asserted a branch-protection
   carve-out; its diff contained no ruleset change and its migration plan listed no manual step.

4. **A human could not repair it either.** The same PR marked both parity manifests `bot_managed=True`
   and raised `manually-bumped` when a PR changed their version, so the obvious repair bump failed a
   required check. Bot blocked, human blocked, tear open.

The deciding property is not that a bot is wrong in principle. It is that a bot fails *silently*: a
workflow that does not fire produces no red check, so the tear is invisible until someone measures a
manifest against its source. Omitting the field has no runtime component at all, so there is nothing
that can fail to fire.

What is lost, stated plainly: ADR-091 also relaxed `count_ratchet` and handed baseline `--update` to
the bot, which covered `taste_count_baseline.txt` and `ruff_count_baseline.txt`. Removing the bot
removes that coverage. This ADR restores `EXIT_REGRESSION` on an unrecorded improvement so the
ratchets stay honest, and the baseline conflict class is tracked separately in issue #4171 rather than
being treated as solved here.

## Consequences

### Positive

- No line for concurrent plugin-source PRs to conflict on. The pairwise conflict that #4080 measured cannot recur.
- Claude Code freshness becomes per-commit: every merge is a new cache key, with no human step.
- `main` is never torn. Nothing stamps a version at any point, so there is no window between content and version.
- Two gates collapse into one absolute check, and the parity gate loses half its surface.
- The plugin-version-bump recovery recipe and its ~15 minute loop are deleted rather than mitigated.

### Negative

- **Cosmetic**: `/plugin` listings show a commit SHA instead of a semantic version. There is no `0.6.5448` for a human to quote in a bug report; they quote a SHA, which is more precise and less readable.
- No semantic ordering. Nothing in the manifest says whether an install is newer or older than another; the git history answers that instead.
- The Copilot conclusion rests on the documented optional-metadata classification plus the readable JS layer of bundle 1.0.78-0. The native `pluginOperationsUpdatePlugin` binding was not readable. If a future Copilot build gates updates on the version, this decision needs re-verification against that build.
- Roughly 25 open PRs carry a version-bump hunk. Each becomes a content conflict on the `version` line exactly once, resolved by taking the empty incoming side. See Implementation Notes.

### Neutral

- The module name `validate_plugin_version_bump.py`, its CLI flags, and its workflow keep their names so no caller changes. The gate behind them is inverted.
- `src/claude` and the `project-toolkit` pair no longer have separate version lines, because they have no version lines.

## Impact on Dependent Components

| Component | Required Update | Risk |
|-----------|-----------------|------|
| `build/scripts/validate_plugin_version_bump.py` | Inverted: fails when the field is present. Same CLI, same exit codes. | Low |
| `build/scripts/check_plugin_manifest_parity.py` | `check_version_parity` removed; description-count check kept. | Low |
| `.github/workflows/validate-plugin-version-bump.yml` | Header and failure message rewritten to the new rule. Path filter unchanged; it already covers the three manifests. | Low |
| `scripts/validation/run_plugin_version_bump_ci.py` | Docstring only. Base resolution stays, since a shallow checkout still has to resolve the head ref. | Low |
| `.claude/rules/plugin-version-bump.md` (+ two generated mirrors) | Rewritten: PRs never touch the field. | Low |
| `.claude/rules/knowledge-persistence.md` (+ two generated mirrors) | MUST-3 (bump the plugin manifests) removed. | Low |
| `AGENTS.md` | "Bump plugin manifest" removed from the Always list. | Low |
| `.claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py` | Extended, not left alone. `_resolve_conflicted_file` short-circuits on any plugin manifest, so a manifest conflict it cannot resolve is reported blocked and never reaches the ordinary `checkout --theirs` path. It now resolves the migration shape: when either side omits `version`, the merged manifest carries none. | Low |
| `scripts/dev/dogfood_copilot_plugin.py` | Rewritten drift signal. `_is_stale` compared two manifest versions, which are both absent now, so `--check` could never fire. It now compares a content fingerprint of the shipped files, which also catches the unbumped hook edit the version comparison never saw. | Medium |
| `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json` | Covered by the same gate. A per-plugin `version` in a marketplace entry is resolution step 2 and pins freshness the same way, and a marketplace-only change fires no other check: the pytest workflow filters on Python paths. `validate-plugin-version-bump.yml` gained both paths to its filter. | Medium |
| Six shipped skills (`ai-agents-change-control`, `ai-agents-config-catalog`, `ai-agents-architecture-contract`, `ai-agents-generation-and-release`, `ai-agents-debugging-playbook`, `autoplan`) plus `.agents/governance/GENERATOR-FILES.md` | Rewritten. They instructed a strictly-greater bump, which the new gate fails on; the debugging playbook's remedy row was the exact inverse of the fix. The Copilot mirrors regenerate from the same sources. | Medium |
| ADR-083 acceptance criteria | Two of them named the manifest version as the observable. Restated against the content fingerprint and the inverted gate. | Low |
| Open PRs carrying a bump hunk | One content conflict each on the `version` line. The merge-resolver skill now resolves it automatically. | Medium, one-time |

## Implementation Notes

Landed with this ADR:

1. `version` deleted from the three manifests, every other field byte-identical.
2. `validate_plugin_version_bump.py` inverted, with positive, negative, and edge tests driven through the CLI.
3. Version parity retired from `check_plugin_manifest_parity.py`.
4. Marketplace guard test added.
5. `.claude/rules/plugin-version-bump.md` and `.claude/rules/knowledge-persistence.md` rewritten and mirrors regenerated.
6. The gate extended to both `marketplace.json` files, and `validate-plugin-version-bump.yml` given those two paths so a marketplace-only change runs it.
7. `scripts/dev/dogfood_copilot_plugin.py` re-keyed from the manifest version to a content fingerprint of the shipped tree.
8. `resolve_pr_conflicts.py` taught the versionless-side resolution so the migration below is automatic.
9. Six shipped skills and `GENERATOR-FILES.md` rewritten off the strictly-greater rule, Copilot mirrors regenerated.

Migration for the roughly 25 open PRs that carry a bump hunk: each hits a conflict on the `version` line exactly once, on its first merge of the fixed `main`. Measured with `git merge-tree --write-tree --name-only`: git reports `CONFLICT (content)` in `.claude/.claude-plugin/plugin.json`, with the branch side holding its bumped value, the base holding the old value, and the incoming side empty. The resolution is to take the empty side. The new gate forces it: a rebase that keeps the line leaves a manifest carrying `version`, and the gate fails that at exit 1 on the branch, before merge. The `merge-resolver` skill resolves the conflict without a hand edit: `resolve_plugin_manifest_conflict` takes the versionless side whenever either side omits the field, and `_resolve_conflicted_file` then reports the manifest resolved rather than blocked. The one-time cost is one conflict resolution per open plugin-source PR, and after it those PRs stop conflicting with each other on this line permanently.

## Scope: which conflict class this closes

This ADR closes one conflict class: the plugin manifests, where every
plugin-source PR had to write the same single line. It does not close the
general shared-single-line class. Two per-repo counters remain, and this PR
touches both: `scripts/ci/taste_count_baseline.txt` (one exact integer, so two
PRs that each lower it conflict, and equal values merge to a baseline that is
too high for the combined tree until someone re-runs `--update`) and
`scripts/validation/vendor_portability_baseline.txt` (append-at-end, so two PRs
adding a path conflict). Those are ratchet files rather than published metadata,
their gates carry an `--update` path, and the fix shape is different from
deleting a field. They are out of scope here and tracked separately.

## Acceptance Criteria

Accepted when the field is absent from all three manifests and both marketplace
files, the inverted gate passes on `main` and fails on a manifest or marketplace
entry carrying the field, and two branches touching different files under plugin
source trees merge with no conflict. Issue #4080 closes linking this ADR.

## Related Decisions

- ADR-079 (plugin version bump stays at PR time): superseded by this ADR. Its objection to post-merge stamping is preserved and is not contradicted; it simply does not reach an approach that stamps nothing.
- ADR-083 (Copilot dogfood surface separation): two of its acceptance criteria named the manifest version as the observable, and neither could be evaluated once the field was deleted. Both are restated in ADR-083 against the content fingerprint and the inverted gate.
- ADR-072 (JTBD plugin architecture): defines the packaged-plugin model whose freshness this ADR governs.
- ADR-035 (exit code standardization): the gate's 0/1/2 contract.
- Issue #2543 (tactical merge-resolver auto-bump) and PR #2873 (recovery recipe): both were mitigations for a cost this ADR removes.

## References

- Issue #4080 (this ADR's request and the 14-of-22 measurement).
- Issue #2855, issue #3875 (the cost ADR-079 accepted).
- https://docs.claude.com/en/docs/claude-code/plugins-reference, "Version management" (resolution order, the two supported approaches).
- https://docs.claude.com/en/docs/claude-code/plugin-marketplaces, release channels (omitted version, distinct SHAs).
- https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference (`name` required, `version` optional metadata).
- GitHub Copilot CLI bundle `app.js` v1.0.78-0 at `~/.copilot/pkg/linux-x64/1.0.78-0/app.js` (`updateAll` calls `updatePlugin` unconditionally; version feeds display and telemetry only).
- `build/scripts/validate_plugin_version_bump.py`, `build/scripts/check_plugin_manifest_parity.py`.
