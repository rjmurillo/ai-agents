# ADR Review Protocol: ADR-092 (omit the plugin manifest version)

> Renumbering note. This debate ran under the adr-review skill against the same decision when it
> carried the number ADR-092. That number was taken by PR #4147 (post-merge version bot), merged as
> `edecb8e85` while this work was in flight, so the decision was renumbered to ADR-092. The findings
> and dispositions below are unchanged; only the identifier moved.
>
> Scope limit, stated rather than glossed. This debate was held before #4147 merged. It therefore did
> not review the section "Why ADR-092 is superseded within hours of landing", which was added
> afterwards. Every factual claim in that section was verified directly against the merged commit:
> the unchanged version across `edecb8e85`, the zero workflow runs, the `[skip ci]` in the merge
> message, and the sole ruleset bypass actor. The commands and their output are recorded in issue
> #4168.

# ADR-092 Review: Omit `version` From Plugin Manifests

Subject: `.agents/architecture/ADR-092-omit-plugin-manifest-version.md`, which supersedes ADR-079.
Date: 2026-08-01. Branch: `fix/4080-omit-plugin-version`.

## How this review ran, and what that limits

Single-model structured review across the six `adr-review` lenses (architect,
critic, independent thinker, security, analyst, high-level advisor). It is not a
six-agent fan-out: this execution context has no subagent tool, so one model
argued each lens in turn. Treat the consensus line below as one reviewer's
verdict per lens, not six independent judgments. Every finding below was
checked against a file, a command, or a shipped bundle before it was written;
nothing here is asserted from memory.

Two external anchors keep this from being a closed loop:

1. The official Claude Code and GitHub Copilot CLI documentation, quoted
   verbatim in the ADR with URLs.
2. The shipped Copilot bundle at `~/.copilot/pkg/linux-x64/1.0.78-0/app.js`,
   read directly, newer than the 1.0.69-0 build ADR-079 relied on.
3. The executed merge-conflict demonstration recorded in the session log: two
   branches touching different files under plugin source trees merge clean on
   the fixed `main` (exit 0) and conflict on `plugin.json` before the fix
   (exit 1) when each branch bumps to a different next version. The third
   measurement is recorded too, because it is the less flattering one: before
   the fix, two branches that pick the *same* next version produce identical
   blobs and do not conflict textually. That case deadlocked on the
   strictly-greater gate after the first branch merged, which is what the
   recovery recipe in `.claude/rules/plugin-version-bump.md` existed to unstick.

## Findings

### F1. Copilot's native update path is unread (critic, analyst). Residual risk, accepted.

`updateAll()` in 1.0.78-0 iterates installed plugins and calls
`updatePlugin(spec)` with no version comparison in the decision path. Every
`previousVersion!==newVersion` occurrence is a display string or the
`version_changed` telemetry property. Cache invalidation keys off
`skillsCacheDirty` returned by the native operation. But `updatePlugin`
delegates to `pluginOperationsUpdatePlugin`, a native binding that was not
readable, so the JS evidence bounds the claim rather than closing it.

ADR-079 recorded the opposite conclusion from 1.0.69-0, where the JS layer
itself compared version strings for inequality. That comparison is gone from the
current bundle, and the official CLI plugin reference lists `version` under
"Optional metadata fields" with `name` as the only required field. Documentation
plus the readable layer both point the same way; the native layer is the gap.

Falsifier, not run here: install the Copilot plugin from the marketplace, push a
commit that changes a shipped file, run `copilot plugin update project-toolkit`,
and check whether the installed file changes. That needs an authenticated CLI
and a published marketplace ref, neither available in this worktree. Recorded in
the ADR's Negative consequences and in the session log as unverified.

Verdict: not blocking. The documented contract is the binding one, and if a
future Copilot build gates on the field, the fix is to re-verify against that
build, not to keep a field that conflicts on every PR today.

### F2. Downgrade protection moves from the gate to branch protection (security).

ADR-079 point 3 argued the strictly-greater rule was "the only guard against a
downgrade", because a decreased version still differs from the installed one and
would push to installs as an update. With the field gone there is no version to
decrease. The equivalent regression is now a rewind of `main`, which
`.claude/rules/universal.md` MUST NOT 1 already forbids ("MUST NOT force-push
shared branches") and which branch protection enforces independently of this
gate. Net: the protection did not disappear, it moved to a control that was
already stronger.

### F3. The module keeps a name that now misdescribes it (architect). Accepted debt.

`build/scripts/validate_plugin_version_bump.py` no longer validates a bump. The
name survives because four callers, one workflow, and one paths-filter reference
it by path: `scripts/validation/run_plugin_version_bump_ci.py`,
`scripts/validation/checks_plugin.py`, `scripts/validation/git_hook_policy.py`,
and `.github/workflows/validate-plugin-version-bump.yml`. Renaming is a
mechanical follow-up with a wider blast radius than the fix itself. The module
docstring states the current rule in its first sentence, so a reader who opens
the file is not misled; only the filename lags.

### F4. The merge-resolver auto-bump rule becomes unreachable (analyst).

`.claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py` carries a rule
(issue #2543) that resolves a version-only `plugin.json` conflict to one patch
above the higher side. With no `version` key in any manifest, a version-only
conflict cannot occur, so the branch is dead but harmless: it matches on the
manifest path and then finds no version line. Left in place rather than deleted,
because deleting it belongs in a separate change that can test the resolver
end to end. Recorded in the ADR's Impact table.

### F5. The SHA granularity question resolves either way (independent thinker).

The docs say freshness resolves to "the git commit SHA of the plugin's source".
Two readings: the marketplace repository's commit, or something scoped to the
plugin's own subtree. Under the first, every merge is a new key, which is what
the ADR claims. Under the second, a merge that touches no file under
`.claude/` produces no new key for that plugin, which is also correct behavior:
nothing in that plugin changed, so no re-sync is needed. Neither reading breaks
the decision, so the ambiguity does not need resolving before landing.

### F6. Stale prose survives the change (critic). Bounded and listed.

Nineteen files still describe the strictly-greater rule. Four were corrected in
this change because they are live instructions an agent obeys:
`.claude/rules/plugin-version-bump.md`, `.claude/rules/knowledge-persistence.md`,
`AGENTS.md`, and `.github/AGENTS.md`, plus the generated mirrors. The remainder
are the `ai-agents-*` knowledge packs and the `validation-authority` and
`merge-resolver` skills, which describe repository history and tooling rather
than instructing a bump. Leaving them is a known documentation debt, named here
so the next reader does not mistake silence for currency.

### F7. The migration is forced, not requested (high-level advisor).

Roughly 25 open PRs carry a version-bump hunk. Each hits a modify/delete
conflict once on its first rebase onto the fixed `main`. Dropping the hunk is the
only resolution that passes the new gate: keeping the line leaves a manifest
carrying `version`, and the gate fails that at exit 1 on the branch before
merge. So the gate makes the migration self-enforcing rather than relying on
every author to remember. One-time cost, after which those PRs stop conflicting
with each other on this line permanently.

## Verdict by lens

| Lens | Verdict | Basis |
|---|---|---|
| Architect | Accept | F3 is naming debt with a stated reason, not a design flaw. |
| Critic | Accept | F1 bounded and recorded with a falsifier; F6 listed rather than hidden. |
| Independent thinker | Accept | F5 resolves either way; no unexamined premise found. |
| Security | Accept | F2: downgrade protection moved to a stronger existing control. |
| Analyst | Accept | F4 dead-but-harmless; migration cost measured, not estimated. |
| High-level advisor | Accept | F7 is one-time and self-enforcing; removes a recurring loop. |

Consensus: 6/6 Accept from one reviewer per lens, with F1 recorded as the
standing risk to re-verify if a future Copilot build changes its update path.

## Relationship to ADR-079

ADR-079's objection is preserved and not contradicted. It rejected a post-merge
*stamp* because `main` would carry changed content under an unchanged version
until the follow-up commit landed. Omitting the field stamps nothing at any
point, so no such window exists. The premise that changed is the Copilot one:
ADR-079 concluded from 1.0.69-0 that a changing in-tree value was mandatory, and
that conclusion does not survive the current bundle or the official reference.

## Relationship to ADR-091

ADR-092 supersedes ADR-091 as well, and that half of the review was adversarial
against a decision that had already merged, so the bar was evidence from the
merged artifact rather than argument about the design.

ADR-091 chose a post-merge bot to own the version and the count baselines. Its
conflict measurement is sound and ADR-092 reuses it. The mechanism is what
failed, on four counts, each checked against the merged commit `edecb8e85`:

1. It tore `main` on its own merge. `edecb8e85` changed packaged plugin source,
   the `plugin-version-bump` rule and both generated mirrors at 179 lines each,
   and left the version identical to `edecb8e85^`.
2. The bot never ran. Its squashed merge message quotes its own commit template,
   so the commit body carries a literal `[skip ci]`, which suppressed push
   workflows on that commit. 0 runs recorded.
3. It could not have pushed if it had run. Ruleset 11104075's only bypass actor
   is `RepositoryRole id=5`; `github-actions[bot]` is not one, and the
   `pull_request` rule refuses direct pushes regardless of `contents: write`.
4. A human could not repair it either. ADR-091 marked both manifests
   `bot_managed`, raising `manually-bumped` on any PR-side version change, so
   the repair bump would have failed a required check.

The lens that mattered here was the silent-failure one. A workflow that never
fires emits no red check, so all four failures presented as success. That is the
property ADR-092 removes rather than fixes: deleting the field leaves no runtime
component, so there is nothing left that can fail to fire.

What ADR-091 covered and ADR-092 does not: the count-baseline conflict class
(`taste_count_baseline.txt`, `ruff_count_baseline.txt`), which has the same
one-shared-line shape. That coverage dies with the bot and is not replaced.
Tracked in issue #4171 with the measurement, 2 of 24 blocked PRs conflicting
only on the taste baseline. `count_ratchet` therefore returns to
`EXIT_REGRESSION` on an unrecorded improvement, since the slack ADR-091 opened
no longer has an owner.
