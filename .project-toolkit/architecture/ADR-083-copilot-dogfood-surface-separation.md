---
id: ADR-083
status: accepted
date: 2026-07-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
review-by: 2027-01-17
---

# ADR-083: Dogfood the Shipped Copilot Base and Separate Ship-vs-Internal Surface

## Status

Accepted (2026-07-18). Requested by issue #3222. Three owner decisions are locked
in that issue thread (D1, D2, D3 below); this ADR is the design of record they
point to. Validated by a 6-agent adr-review debate: 3 Accept, 3 Disagree-and-Commit,
no blocks, all P0 and P1 findings resolved. Evidence:
`.project-toolkit/critique/ADR-083-debate-log.md`. The review added an overlay decision gate
(Decision item 6) and reordered the phases so the dogfood install and the
base-alone e2e ship before the two-plugin split. The owner confirmed decision A on
2026-07-18: the four session skills (`session-init`, `session-end`, `session`,
`session-log-fixer`) stay `surface: ship`, so the initial internal partition is
empty and the overlay stays deferred until a skill is tagged `surface: internal`.

Amended (2026-07-19) by issue #3252 to match the shipped installer. PR #3251 shipped
the phase 3 dogfood install as copy on all platforms, not the symlink-on-Unix plus
copy-on-Windows split with an automatic session-start freshness check that this ADR
first proposed. A second 6-agent adr-review debate ratified the reconciliation:
6 Accept, no blocks. The one recurring finding (copy-only drops the automatic
staleness guard) is tracked in issue #3256, not a blocker. Evidence:
`.project-toolkit/critique/ADR-083-debate-log.md` (Amendment section). Only phase 3 had
shipped then; phases 2, 4, and 5 remained, so `implemented: false` reflected
partial delivery.

Amended (2026-10-19) by issue #6742 after the 90-day review. The owner retired
the `surface` tag (Decision item 1) and removed the internal overlay (Decision
items 2 and 6). Decision item 5 now records that the two security hooks are
retired and that ADR-097 governs the hook surface. Confirmation Criterion 1 now
uses `skill list` as its primary signal. The dogfood install (item 3) is the
durable outcome of the tag-and-overlay plan. The base-alone e2e (item 4) stays
in force with that restated signal. `implemented` is now `true`: ADR-073 flips
it at the first merged change, and PR #3251 merged on 2026-07-19. The title
still names the retired ship-versus-internal split, and is kept so existing
citations resolve. Evidence: the 2026-10-19 amendment below and
`.project-toolkit/critique/ADR-083-debate-log-2.md`.

## Amendment 2026-07-27: Security hook absence recorded, authorization not found

Status of this amendment: Proposed by issue #3399 follow-up review. This section
records observed repository state only. It does not authorize removing a security
control from the shipped base.

Observed state: the removed `invoke_security_gate` hook file and the removed
`invoke_security_commit_gate` hook file were previously required. Both are absent
from `.claude/hooks/` and `src/copilot-cli/hooks/` in PR #3488. No ADR was found
that supersedes this ADR's requirement that those customer-facing security
controls remain in the base. The absence therefore remains an implementation and
governance gap, not a relaxed decision.

Closed by the 2026-10-19 amendment below, which records the owner decision.

## Amendment 2026-10-08: base-alone e2e runs on pull requests (issue #6069)

Status of this amendment: records a workflow move. The decision is unchanged.
`.github/workflows/nightly-cli-smoke.yml` is deleted. The base-alone e2e test it
ran now runs in `.github/workflows/plugin-cli-smoke.yml` on pull requests that
change a smoke path, on Linux, macOS, and Windows (ADR-114 Decision 13). Where
Decision item 4, the Impact table, and the Confirmation Criteria name the
nightly workflow, read `plugin-cli-smoke.yml`. The criterion "two consecutive
scheduled runs" becomes two consecutive green runs on pull requests.

## Amendment 2026-10-19: 90-day review outcome (issue #6742)

Status of this amendment: records the review that the 2026-10-18 date required,
and four owner decisions. The owner chose them on 2026-10-19 in issue #6742.
The review evidence is the #6742 comment marked `adr083-review-6742`. The
decisions are the comment marked `adr083-owner-decisions`. No code, hook, or
security control changes with this amendment. It changes this record only.

### Review result

Measured on `origin/main` at 6baae9f616 (2026-10-18, US Pacific). Run windows are UTC.

| Criterion | Result | Evidence |
|---|---|---|
| 1. Base-alone e2e, fired hook primary | Not met. The primary signal could not exist. | The base ships zero hooks: `src/copilot-cli/hooks/hooks.json` is `{"hooks": {}, "version": 1}`. The review comment counted the last 80 `plugin-cli-smoke.yml` runs (2026-10-18T18:58Z to 2026-10-19T00:01Z): 0 Copilot legs completed. They waited on the `agent-copilot` environment approval. |
| 2. `surface` tag gate | Not met. Phase 4 never shipped. | `git grep -nE "surface: ?(ship\|internal)" -- build scripts tests templates` returned nothing. No item carries the tag, and no reader exists. |
| 3. CI asserts both security hooks in the base | Falsified. | Neither hook exists in the tree. See Decision item 5 below. |
| 4. Dogfood `--check` exits 0 on HEAD, 1 after an edit | Met. | `tests/test_dogfood_copilot_plugin.py` and `tests/test_dogfood_copilot_plugin_drift.py`: 50 passed (re-run 2026-10-19). |
| 5. Parity and version gates if the overlay gate fires | Not triggered. | No `surface: internal` item exists. The overlay tree was never created. |

The Review Date section had pre-written an outcome: "the tag plus the dogfood
install (not the split) were the durable outcome." That sentence is false. The
tag never shipped. Only the dogfood install and the base-alone e2e did. This
amendment records the true outcome instead.

### Owner decisions

1. **Retire the `surface` tag (Decision item 1).** No item carries it after 90
   days, and no build reads it. The dogfood install is the durable outcome.
   `scripts/dev/dogfood_copilot_plugin.py --check` is its observable.
   Ship-versus-internal separation stays where it was: `excludeFilenames` in
   `templates/platforms/copilot-cli.yaml` and `keepInternalGlobsFor` for rules.
2. **Remove the internal overlay (Decision items 2 and 6).** The kill criterion
   in item 6 held for the full 90 days: no item was tagged `surface: internal`.
   The Reversibility section names removal as the exit. The overlay was never
   built, so the unwind deletes nothing. No manifest, gate entry, or e2e job
   existed for it.
3. **Amend Decision item 5 to record the security hooks as retired.** PR #3306
   (issue #3295) deleted `invoke_security_gate` and
   `invoke_security_commit_gate` on 2026-07-22. Issue #3219 records why the
   #3197 review killed both: as shipped they were net-negative, and their only
   production records were outages (#2610, #2523). ADR-097 (accepted
   2026-08-19) lists both as already retired in its
   Decision section 4. It also sets the vendored surface to zero `PreToolUse`,
   `PostToolUse`, and `PostToolUseFailure` hooks. ADR-097 therefore governs
   whether either hook may return. This ADR no longer carries the MUST. The
   deletion used the hook-ROI purge, which ADR-084's carve-out does not permit
   for a security control. This owner decision is the after-the-fact
   authorization, and it closes the gap the 2026-07-27 amendment recorded. No
   control changes: the shipped base had neither hook before this amendment
   and has neither after it.
4. **Restate Confirmation Criterion 1.** The base ships no hooks, so a fired
   base hook cannot be the primary signal. The primary signal is now `copilot
   skill list` on a base-alone install. The fired-hook probe stays best-effort.

### What changes in this record

- Decision items 1, 2, and 6 are marked retired. They keep their numbers, so
  existing citations still resolve.
- Decision items 3 and 4 drop the overlay. Item 4 names `plugin-cli-smoke.yml`
  and the current signal order.
- Decision item 5 records the retirement and points to ADR-097.
- Confirmation Criteria 1 is restated. Criteria 2, 3, and 5 are retired.
- Implementation Notes mark phases 4 and 5 retired. The overlay gate
  reconciliation detail is removed.
- `implemented` flips to `true`, per ADR-073: the first change merged in July.
- Consequences > Negative states the security gate consumers lost in July.
- `review-by` moves to 2027-01-17. That review checks Criterion 1.

Noticed, not changed: Decision item 4 asks the test to assert that a shipped
skill script resolves under the Copilot plugin root. On 2026-10-18,
`tests/e2e/test_plugin_load_smoke.py` asserts that for Codex and Grok, and has
no such test for Copilot. This amendment records the gap and does not change
the requirement.

Noticed, not changed: ADR-097 does not cite this ADR. The lifecycle checks
require reciprocal edges for supersession only, and this is not a supersession.
An ADR-097 edit needs its own review, so this amendment leaves ADR-097 as it is.
The cross-citation is one-way, from this ADR to ADR-097.

Debate log: `.project-toolkit/critique/ADR-083-debate-log-2.md`.

## Date

2026-07-18

## Context

We ship one toolkit as two marketplace plugins. We only dogfood one of them.

- `.claude-plugin/marketplace.json:17` ships `project-toolkit` from `./.claude`.
  On Claude, the plugin we run is the plugin we ship. Full dogfood parity.
- `.github/plugin/marketplace.json:12` ships `project-toolkit` from
  `./src/copilot-cli`. On Copilot, our own sessions load `.claude/` skills and
  `.github/instructions/` rules, not the shipped `src/copilot-cli/` mirror. The
  Copilot customer artifact is never exercised by our own use.

The consequence is concrete. A skill script that resolves under `.claude` but not
under the plugin root (`COPILOT_PLUGIN_ROOT`), a hook whose registration works in
`settings.json` but not in the packaged `hooks.json`, or an instruction glob that
matches in-repo but not on a customer install, all pass our daily use and ship
broken. The `check_skill_md_exec_portability.py` gate catches the static path
shape, but only real execution against the packaged tree catches the runtime
form-factor failures.

To be precise about existing coverage: `tests/e2e/test_plugin_load_smoke.py` and
`tests/e2e/test_cli_hook_e2e.py` already load the shipped `src/copilot-cli` tree
in CI and assert a fired hook plus skill enumeration. The shipped base is not
wholly untested. Two gaps remain. First, our own interactive Copilot sessions
still load `.claude`, not the base, so day-to-day dogfooding never exercises the
customer artifact. Second, the installed dogfood plugin has rotted: the copy at
`~/.copilot/installed-plugins/_direct/project-toolkit` is pinned at version
0.5.248, months behind the shipped 0.6.70. Manual installs do not track the repo,
so the artifact we occasionally load is neither current nor the one customers
receive. The rot is the proven gap; the base-alone e2e is defense in depth on the
existing suite.

Second problem: there is no declared boundary between what ships to customers and
what is repo-internal. `src/copilot-cli/skills/` ships 109 skills. Most are
correctly customer-facing: `adr-review`, `adr-generator`, `pr-autofix`, and
`pr-comment-responder` are general workflows the owner uses outside this repo. A
small set leans repo-internal: the `session-init`, `session-end`, `session`, and
`session-log-fixer` family encodes this repo's session-log schema and HANDOFF
protocol, though even those are usable by customers and have earned their keep
here. The genuinely-internal skill set is small, possibly empty. The point is
that no mechanism records the decision per item, and the current separation is a
crude filename filter (`_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")` in
`build/scripts/generate_skills.py:39`, plus an `excludeFilenames` list in
`templates/platforms/copilot-cli.yaml`). That filter cannot express a borderline
item, and it cannot keep an internal item available to us while withholding it
from customers.

Hooks are a separate story with an existing owner. Issue #3197 (the 2026-07-17
hook ROI reduction program, 15 child issues) already decided how internal hooks
are handled: delete them from the vendored surface and re-home them into
Lefthook, CI, and `pre_pr.py`, the layers that already enforce them. Issue
#3216 enumerates which hooks are customer-facing versus internal. That plan is
evidence-backed and mid-flight. Skills have no equivalent home. A skill is only
deliverable as a plugin, so an internal skill cannot be "re-homed into a git
hook"; it must load as a plugin or not at all.

## Decision

Dogfood the shipped Copilot base by installing it the way a customer installs
it, and prove in CI that the base alone loads. As first accepted, this ADR also
adopted a per-item surface tag and a local-only internal overlay. The
2026-10-19 amendment retired both. Items 1, 2, and 6 keep their numbers so that
existing citations still resolve.

1. **Retired 2026-10-19: per-item `surface: ship|internal` tag (D2).** The
   original item required every skill, agent, and instruction source to
   declare `surface: ship` or `surface: internal`, with a CI build gate that
   failed on an untagged item or any other value. Phase 4 never shipped. After
   90 days no item carried the tag and no build read it. The owner retired the
   tag in issue #6742. Ship-versus-internal separation stays with the existing
   filename filter (`excludeFilenames` in `templates/platforms/copilot-cli.yaml`)
   and `keepInternalGlobsFor` (#2892).

2. **Retired 2026-10-19: two Copilot plugin trees split by tag (D3).** The
   original item routed `surface: internal` items into a second, unlisted
   overlay plugin. The overlay was never built. The owner removed it in issue
   #6742, by the exit the Reversibility section names. Customers receive the
   base, and the base is the only Copilot plugin tree.

3. **Dogfood by loading the shipped base locally.** A dogfood-install step
   copies the base into `~/.copilot/installed-plugins/` so our Copilot sessions
   run the real packaged artifact. The install copies the tree on every
   platform, the same mechanism every other artifact in this repo already uses
   (marketplace install, build pipeline). The repo has no symlinked artifact,
   and a symlink cannot be universal because Windows needs elevation to create
   one, so one consistent copy mechanism beats a platform split. A copy does not
   auto-track the repo, so the refresh is explicit: edit the source, re-run the
   install, and the next session loads the change. The install step
   (`scripts/dev/dogfood_copilot_plugin.py --install`) stashes any prior copy as
   a one-time backup and re-copies. This trades the symlink's automatic tracking
   for a single uniform path and a one-command refresh, and it ends the 0.5.248
   rot that came from untracked manual copies rather than from copying itself.
   It also drops the automatic session-start freshness check the original
   design proposed. Staleness is surfaced on demand: `--status` reports when
   the install trails the working tree, `--check` exits 1 when the installed
   content differs from the source, and re-running `--install` closes the gap.
   Nothing blocks automatically, so keeping the dogfood copy current is an
   explicit developer step (tracked for an opt-in or CI guard in issue #3256).

4. **e2e the base alone (D1).** A durable CI test loads the shipped
   `src/copilot-cli` base in isolation and asserts customer-visible behavior.
   The PRIMARY signal is `copilot --plugin-dir src/copilot-cli skill list
   --json` on a base-alone install: it exits 0, prints no `argument-hint`
   loader warning, and lists every `EXPECTED_SKILLS` name from a
   `source: plugin` record under the base. The base ships zero hooks
   (`src/copilot-cli/hooks/hooks.json` is empty, and ADR-097 forbids tool-use
   hooks), so a fired base hook cannot be the primary signal. A probe plugin's fired hook stays a best-effort check of the hook
   path, with an empty-plugin negative control. The test also asserts a real
   shipped skill script resolves under the plugin root. Loading the base alone
   is what catches base-only form-factor bugs; loading the `.claude` superset
   never exercises the base by itself. The test lives in
   `tests/e2e/test_plugin_load_smoke.py` and runs in
   `.github/workflows/plugin-cli-smoke.yml`, gated by `RUN_CLI_E2E`, on Linux,
   macOS, and Windows, for pull requests that change a smoke path (ADR-114
   Decision 13).

5. **Hooks stay with #3197 and ADR-097 (D3).** This ADR does not build a hook
   overlay or tag hooks. Internal hooks were deleted from the vendored surface
   and re-homed by #3197.

   As first accepted, this item made `invoke_security_gate` (Write and Edit)
   and `invoke_security_commit_gate` (Bash) a binding MUST: both had to remain
   in the shipped base, and removing either needed its own ADR. That MUST is
   withdrawn by the 2026-10-19 amendment, on the owner's decision in issue
   #6742. The record is:

   - PR #3306 (issue #3295) deleted both hooks on 2026-07-22, under the #3197
     hook-ROI purge. Issue #3219 records the #3197 finding: as shipped, both
     were net-negative, their guarded auth patterns matched no tracked file
     here, and their only production records were outages (#2610, the
     Copilot payload defect, and #2523, a timeout). `invoke_security_gate` ran
     in consumer repos. `invoke_security_commit_gate` was
     `skip_if_consumer_repo` gated and did not (ADR-084). Issue #3219 tracked
     a portable rebuild on real customer demand, and is closed.
   - The 2026-07-27 amendment above recorded the deletion as a governance
     gap, because no ADR had withdrawn this MUST.
   - ADR-097 (accepted 2026-08-19) lists both hooks as already retired in its
     Decision section 4. It sets the vendored plugin surface to zero
     `PreToolUse`, `PostToolUse`, and `PostToolUseFailure` hooks, and its
     Re-evaluation Triggers govern any new tool-use hook.

   ADR-084's carve-out says its ROI bar does not authorize retiring a security
   control. No record shows that carve-out was weighed for these two hooks.
   The owner's 2026-10-19 decision in issue #6742 is the after-the-fact
   authorization for their retirement. ADR-097 is the decision of record for
   the hook surface from here on. A proposal to restore a security control on
   a tool-use event goes through ADR-097's Re-evaluation Triggers, ADR-084
   rule 6, and `.claude/rules/tool-use-hook-bar.md`, not through this ADR. This
   amendment changes no control: the shipped base carried neither hook before
   it and carries neither after it.

6. **Retired 2026-10-19: overlay decision gate (kill criterion).** The
   original item deferred the overlay until at least one plugin-routed item
   was tagged `surface: internal`, and the review date re-checked it. No item
   was tagged in 90 days, and the tag itself is retired (item 1). The owner
   removed the overlay in issue #6742, so the gate has nothing left to guard.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: `.claude` is canonical. `build_all.py`
  generates the Copilot mirror. `generate_rules.py` emits instruction files to
  both `.github/instructions` and `src/copilot-cli/instructions` via an
  `outputDirs` list. `generate_skills.py` and `generate_hooks.py` mirror skills
  and hooks. Ship-vs-internal separation today is a filename filter
  (`_DEFAULT_EXCLUDES`, `excludeFilenames`) plus rule-glob filtering
  (`keepInternalGlobsFor: [".github/instructions"]`).
- **When introduced**: The mirror generators predate this ADR. `keepInternalGlobsFor`
  was added for issue #2892. The marketplace split (`.claude` for Claude,
  `src/copilot-cli` for Copilot) is the standing packaging model.
- **Original author and context**: The generation seam exists so one canonical
  `.claude` source produces both harness form-factors without hand-maintained
  duplication.

### Historical Rationale

- **Why was it built this way?** Copilot and Claude have different plugin
  form-factors (path resolution, hook registration, instruction globs). Generating
  from one source avoids drift between the two.
- **What alternatives were considered?** The crude filename excludes were the
  minimum viable separation: strip a handful of Claude-only files
  (`AGENTS.md`, `CLAUDE.md`) from the Copilot mirror.
- **What constraints drove the design?** The plugin hosts read manifests as raw
  source at HEAD (ADR-079). There is no publish step to stamp or filter content
  ephemerally, so every distinction must be materialized in-tree.

### Why Change Now

- **Has the original problem changed?** Yes. The Copilot artifact grew to 109
  skills and a full hook and agent surface. The crude excludes cannot express the
  ship-vs-internal boundary, and nothing exercises the shipped Copilot artifact.
- **Is there a better solution now?** Yes. gstack demonstrates a scripted local
  install that loads the packaged tree. Copilot CLI's multi-plugin loading makes a
  base-plus-overlay merge a load-time concern, not a build-time concatenation.
- **What are the risks of change?** As first accepted: the parity gate and
  version-bump gate assumed the `.claude` and `src/copilot-cli` pair, so a third
  plugin tree (`src/copilot-cli-internal`) would have needed reconciling with
  both gates. The 2026-10-19 amendment retired that tree before it was built.

## Rationale

The table and trade-offs below record the reasoning as first accepted. The
2026-10-19 amendment retired the `surface` tag and the overlay, so the chosen
row now delivers only its copy-dogfood and base-alone e2e parts. Hooks follow
#3197 and ADR-097, and skills keep the filename excludes.

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Per-item `surface` tag + two-plugin split + copy dogfood (chosen) | Real dogfood of the shipped base; declared per-item boundary; internal items still run for us; one uniform copy mechanism ends the untracked-copy rot | Two mechanisms (git/CI for hooks, overlay for skills); third manifest to gate; copy needs an explicit re-run to refresh | Selected: fits each surface to its correct delivery mechanism. Tag and split retired 2026-10-19 |
| Keep filename/name-pattern excludes (status quo) | Zero new machinery | Cannot express borderline items; no dogfood of the base; silent leaks | Rejected at first; kept for skills after the 2026-10-19 amendment, because no internal item appeared in 90 days |
| Delete internal from the vendored surface entirely | Simplest ship base; matches #3197 for hooks | Skills have no Lefthook or CI execution home; deleting an internal skill removes it from our own Copilot runtime | Rejected for skills; adopted for hooks by #3197 |
| Single merged plugin with runtime filtering | One plugin to install | Copilot has no per-item runtime include/exclude; plugin load is all-or-nothing | Rejected: the host cannot filter within a plugin |
| gstack live team-mode clone | Auto-updating, no vendored files | Couples the customer install path to repo internals; the base must stay a clean vendored artifact | Rejected for the customer base; the scripted local-install idea is adopted for the dogfood install, copy-based rather than symlinked |
| Tag now, defer the overlay split (build-time exclude only) | Declares the boundary; zero third-tree cost while the internal set is empty | Loses an internal skill from our own Copilot runtime the moment one is tagged internal | Partially adopted as Decision item 6; retired 2026-10-19 with the tag |

### Trade-offs

The design accepted two mechanisms for two surfaces: hooks flow to Lefthook and
CI via #3197, skills flow to a load-time overlay. A hook can run at commit, push,
or PR time from a git hook or CI; a skill can only be delivered as a plugin.
Forcing both into one mechanism would either strand internal skills (delete
approach) or duplicate hook governance in two enforcement points (overlay-hooks
approach), which #3197's audit found net-negative.

The `surface` tag would have added a per-item maintenance obligation and a build
gate, to buy a recorded decision on every item. In 90 days no item needed the
`internal` value, so the cost bought nothing. The 2026-10-19 amendment retired
it. A borderline item now relies on the filename excludes and on review.

## Consequences

The tag and overlay consequences below were retired with those items on
2026-10-19. They are kept so a reader can see what the review weighed.

### Positive

- Our Copilot sessions can run the real shipped base, so form-factor bugs surface
  in our own use instead of in a customer install.
- The base-alone e2e catches base-only failures that the `.claude` superset masks.
- The copy dogfood install is scripted in-repo and ends the 0.5.248 untracked-copy
  rot: re-running `--install` refreshes it to repo `HEAD`.
- Retired 2026-10-19: customers receive a base without this repo's internal
  machinery, and the `surface` tag is one declarative source for #3197 and
  #3216. Neither shipped.

### Negative

- Retired 2026-10-19: a third Copilot output tree, a tag router, a third plugin
  manifest, and a build failure on every untagged item. None was built.
- After the amendment: no per-item record says whether a skill is meant for
  customers. A repo-internal skill ships unless a filename exclude drops it.
- Since 2026-07-22, a plugin consumer install has no agent-time security gate
  on Write and Edit. `invoke_security_gate` ran in consumer repos (ADR-084);
  `invoke_security_commit_gate` never did. Consumers rely on host-native
  permissions and their own review. The 2026-10-19 amendment records this loss
  and does not restore the gate. A rebuild needs a new proposal under ADR-097.

### Neutral

- The internal overlay was expected to start empty for skills, and it stayed
  empty for the full 90 days. #3216 found internal items on the hook surface,
  and #3197 deleted them, so the hook boundary was real. The skill boundary
  never produced an internal item.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `scripts/dev/dogfood_copilot_plugin.py` | Direct | Copy install, `--status`, `--check` (shipped, phase 3) | Low |
| `tests/e2e/test_plugin_load_smoke.py` | Direct | Base-alone `skill list` primary assertion and best-effort probe hook (shipped, phase 2) | Medium |
| `.github/workflows/plugin-cli-smoke.yml` | Direct | Runs the base-alone e2e on pull requests on Linux, macOS, and Windows (moved from the nightly workflow by the 2026-10-08 amendment) | Low |
| `.github/plugin/marketplace.json` | Direct | Lists the base only; unchanged | Low |

Retired 2026-10-19 with Decision items 1, 2, and 6: the tag reader in the
generators, tag routing in `templates/platforms/copilot-cli.yaml`, the overlay
tree, and the overlay entries in the parity and version gates. None was built.

## Implementation Notes

Phased, matching issue #3222. Each phase is its own PR under the atomic-commit
rule.

1. This ADR (fires adr-review).
2. Base-artifact e2e against the `src/copilot-cli` base. Shipped. The 2026-10-19
   amendment set its primary signal to `skill list`, because the base ships no
   hooks.
3. The copy dogfood install (copy on every platform via an explicit install step).
   Shipped by PR #3251. It kills the 0.5.248 rot and depends on nothing in the
   tag or split.
4. Retired 2026-10-19: the `surface` tag reader and its build gate. Never built.
5. Retired 2026-10-19: the two-plugin split and its gate reconciliation. Never
   built.

The original notes for phases 4 and 5 (tag location, the overlay manifest, and
the parity and version-gate wiring) described machinery that was never built.
The 2026-10-19 amendment removed them. They remain in git history before that
date.

## Reversibility

Each phase is independently revertible. The base-alone e2e and the copy dogfood
install are pure additions: reverting them removes a CI job and an install
script with no effect on the shipped base.

The 2026-10-19 amendment used this section's exit for the overlay. The overlay
was never stood up, so the unwind had nothing to delete: no overlay manifest,
no fourth version-gate entry, no overlay e2e job, and no tagged items. The tag
was never added, so retiring it deletes no frontmatter. Reverting the amendment
is a revert of this file and its debate log. It changes no code, gate, or
customer artifact.

## Confirmation Criteria

Restated by the 2026-10-19 amendment. Each criterion keeps its number.

1. On a base-alone install, `copilot --plugin-dir src/copilot-cli skill list
   --json` exits 0 with no `argument-hint` loader warning and lists every
   `EXPECTED_SKILLS` name in `tests/e2e/test_plugin_load_smoke.py` from a
   `source: plugin` record under the base. This is the primary signal. It
   passes on Linux, macOS, and Windows in `plugin-cli-smoke.yml` for two
   consecutive pull-request runs in which the Copilot legs completed. The
   fired-hook probe is best-effort and does not count toward this criterion.
   Measured state at 6baae9f616 (2026-10-18): not yet met. The review comment
   counted 80 runs from 2026-10-18T18:58Z to 2026-10-19T00:01Z (UTC), and 0
   Copilot legs completed. They waited on the `agent-copilot` environment approval,
   whose only required reviewer is the owner (ADR-114).
2. Retired 2026-10-19 with the `surface` tag (Decision item 1).
3. Retired 2026-10-19. Decision item 5 no longer requires the security hooks in
   the base. ADR-097 owns the tool-use hook surface and its confirmation.
4. The copy dogfood install makes `copilot` load the repo `HEAD` content in an
   interactive session. Restated by ADR-092 (2026-08-01), which deleted the
   manifest `version` this criterion originally read: the observable is now the
   content fingerprint, so `scripts/dev/dogfood_copilot_plugin.py --check` exits 0
   against an install taken from `HEAD` and exits 1 after any edit under
   `src/copilot-cli/`. Met on 2026-10-18.
5. Retired 2026-10-19 with the overlay (Decision items 2 and 6).

## Review Date

The first review was due 2026-10-18 and was held on 2026-10-19 under issue
#6742. Its outcome is the 2026-10-19 amendment above.

Re-review by 2027-01-17 (90 days). At that review, check Criterion 1. If the
Copilot legs of `plugin-cli-smoke.yml` have passed two consecutive pull-request
runs, record that and set `review-by` to null. If no Copilot leg has completed by
then, the owner decides at that review between two exits: approve Copilot legs
until the criterion can be measured, or drop Criterion 1 and record why. A
second "not yet met" with no decision is not an outcome.

## Related Decisions

- ADR-097 (zero tool-use hooks, accepted 2026-08-19): the decision of record
  for the vendored hook surface. It lists `invoke_security_gate` and
  `invoke_security_commit_gate` as already retired and forbids new tool-use
  hooks outside its Re-evaluation Triggers. Decision item 5 defers to it.
- ADR-084 (vendored-hook ROI bar): its security carve-out bars retiring a
  security control by ROI alone. Its rule 6 and `tool-use-hook-bar.md` govern
  any proposal to restore one.
- ADR-092 (omit plugin manifest version): restated Confirmation Criterion 4 and
  retired the version half of the parity gate.
- ADR-114 (agent workflows approval): Decision 13 moved the base-alone e2e into
  `plugin-cli-smoke.yml`, where the Copilot legs wait on the `agent-copilot`
  environment approval.
- ADR-079 (plugin version bump stays at PR time): bounded the overlay's version
  handling. Moot since the overlay was retired.
- ADR-042 (Python migration): the install script is Python.
- Issue #3197 (hook ROI reduction program): owns the hook surface; this ADR does
  not build a hook overlay.
- Issue #3216 (purge non-customer hooks from vendored surface): the hook
  ship-vs-internal taxonomy the retired `surface` tag would have encoded.
- Issue #2892 (`keepInternalGlobsFor`): the instruction-glob split that stays in
  place now that the per-item tag is retired.
- Issue #6742: the 90-day review and the owner decisions behind the 2026-10-19
  amendment.

## References

- `.claude-plugin/marketplace.json` and `.github/plugin/marketplace.json`: the
  two marketplace sources whose `project-toolkit` entries expose the asymmetry.
- gstack (`github.com/garrytan/gstack`): the scripted local-install idea. This repo
  adopts a copy-on-all-platforms variant rather than gstack's symlink-on-Unix,
  copy-on-Windows `_link_or_copy`, because the repo has no other symlinked artifact
  and a symlink cannot be universal on Windows.
- `build/scripts/build_all.py`, `build/scripts/generate_skills.py`: the generation
  seam the retired phases 4 and 5 would have extended.
