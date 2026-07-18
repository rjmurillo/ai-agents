---
id: ADR-083
status: accepted
date: 2026-07-18
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-083: Dogfood the Shipped Copilot Base and Separate Ship-vs-Internal Surface

## Status

Accepted (2026-07-18). Requested by issue #3222. Three owner decisions are locked
in that issue thread (D1, D2, D3 below); this ADR is the design of record they
point to. Validated by a 6-agent adr-review debate: 3 Accept, 3 Disagree-and-Commit,
no blocks, all P0 and P1 findings resolved. Evidence:
`.agents/critique/ADR-083-debate-log.md`. The review added an overlay decision gate
(Decision item 6) and reordered the phases so the symlink dogfood install and the
base-alone e2e ship before the two-plugin split. The owner confirmed decision A on
2026-07-18: the four session skills (`session-init`, `session-end`, `session`,
`session-log-fixer`) stay `surface: ship`, so the initial internal partition is
empty and the overlay stays deferred until a skill is tagged `surface: internal`.

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
`.githooks`, CI, and `pre_pr.py`, the layers that already enforce them. Issue
#3216 enumerates which hooks are customer-facing versus internal. That plan is
evidence-backed and mid-flight. Skills have no equivalent home. A skill is only
deliverable as a plugin, so an internal skill cannot be "re-homed into a git
hook"; it must load as a plugin or not at all.

## Decision

Adopt a per-item surface tag, split the Copilot form-factor into a shipped base
plus a local-only internal overlay, and dogfood both by installing them the way a
customer installs the base.

1. **Per-item `surface: ship|internal` tag (D2).** Every skill, agent, and
   instruction source declares `surface: ship` or `surface: internal` in its
   frontmatter. The build hard-fails on any untagged item. There is no silent
   default. The tag reader accepts only the two literal values `ship` and
   `internal`; any other value, an empty string, or a null fails the build, so a
   typo cannot default-route an item into the customer base. The gate runs in CI on
   every PR, not only in a local `build_all.py` invocation, and it is not skippable
   by a workflow-dispatch input or a label override. The ship-vs-internal call is a
   subtle per-item judgment, so the build forces the decision to be made and
   recorded at the item, not inferred from a name pattern.

2. **Two Copilot plugin trees, split by tag (D3, skills/agents/instructions
   only).** `build_all.py` routes `surface: ship` items into `src/copilot-cli`
   (the base, listed in `.github/plugin/marketplace.json`) and `surface: internal`
   items into a new `src/copilot-cli-internal` overlay plugin. The overlay is
   never added to any `marketplace.json`. Customers receive the base only.

3. **Dogfood by loading both plugins locally.** A dogfood-install step links the
   base (and the overlay, once it exists) into `~/.copilot/installed-plugins/` so
   our Copilot sessions run the real packaged artifacts. Copilot CLI already loads
   multiple plugins at once. The install uses a symlink on
   Unix and a copy on Windows, matching the gstack `_link_or_copy` pattern. The
   symlink tracks the repo, which kills the 0.5.248 copy rot. Windows cannot rely on
   a symlink by default, so instead of an advisory note the install script runs a
   freshness check: on session start (and as a CI step) it compares the
   `plugin.json` version in the installed copy against the repo `HEAD` version, then
   re-copies when they differ or blocks with an actionable message. That closes the
   Windows staleness path rather than trusting a developer to read a note.

4. **e2e the base first, then base plus overlay (D1).** A durable CI test loads
   the shipped `src/copilot-cli` base in isolation and asserts customer-visible
   behavior using the signal hierarchy `tests/e2e/test_plugin_load_smoke.py`
   already established. The PRIMARY signal is a real shipped hook firing from the
   packaged `hooks.json`, which proves the plugin loaded and dispatched. The
   CO-PRIMARY signal is `skill list` succeeding with no loader warning. Skill
   enumeration under `source: plugin` is only a SECONDARY soft signal, because
   Copilot CLI 1.0.69 and later can omit `source: plugin` records from
   `skill list --json` for a known-good plugin dir even though the plugin loads
   (issues #2990, #3014, #3090, #3135).
   The test also asserts a real shipped skill script resolves under the plugin
   root. Loading the base alone is what catches base-only form-factor bugs; loading
   the `.claude` superset (today's behavior) never exercises the base by itself. A
   second test loads base plus overlay to prove our runtime; this overlay e2e is
   deferred per Decision item 6 until an internal skill exists. The base-alone
   test wires into `.github/workflows/nightly-cli-smoke.yml`, gated by
   `RUN_CLI_E2E`, on Linux and Windows.

5. **Hooks stay with #3197 (D3).** This ADR does not build a hook overlay.
   Internal hooks are deleted from the vendored surface and re-homed by #3197.
   The `surface` tag is applied to hooks as well, but for hooks the tag is only the
   shared declarative source that #3197's purge and #3216's enumeration read. The
   mechanism for hooks is delete-and-re-home, not overlay.

   Binding constraint on the hook surface: the customer-facing security controls in
   the shipped base, specifically `invoke_security_gate` (Write and Edit) and
   `invoke_security_commit_gate` (Bash), are `surface: ship` and MUST remain in the
   base. #3197's purge and #3216's enumeration MUST NOT tag them `internal` or strip
   them, because a customer install depends on them for its own security posture.
   Moving any security control off the shipped base requires its own ADR, not a
   hook-ROI reclassification.

6. **Overlay decision gate (kill criterion).** The genuinely-internal skill set is
   expected to be empty at first: per the owner's classification, even the session
   family stays shippable, so the honest initial skill partition is all `ship`. The
   overlay tree (`src/copilot-cli-internal`) is therefore designed now but
   materialized only when phase-3 tagging produces at least one `surface: internal`
   item of any plugin-routed type (skill, agent, or instruction) we need on our own
   Copilot runtime. Hooks are outside this gate; they follow the #3197
   delete-and-re-home path, not the overlay. Until that trigger fires, the split is
   deferred: all items route to the base (the `internal` set is empty by
   hypothesis), and no third tree, no fourth version line, and no overlay e2e job
   are built. The mechanism is specified so it
   can be turned on without redesign, but it is not stood up for a population of
   zero. The review date below re-checks this.

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
- **Is there a better solution now?** Yes. gstack demonstrates a symlink-based
  local install that tracks the repo. Copilot CLI's multi-plugin loading makes a
  base-plus-overlay merge a load-time concern, not a build-time concatenation.
- **What are the risks of change?** The parity gate and version-bump gate assume
  the `.claude` and `src/copilot-cli` pair. A third plugin tree
  (`src/copilot-cli-internal`) must be reconciled with both gates. Blast radius is
  concentrated in `build/scripts/` and `templates/platforms/copilot-cli.yaml`.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Per-item `surface` tag + two-plugin split + symlink dogfood (chosen) | Real dogfood of the shipped base; declared per-item boundary; internal items still run for us; kills copy rot | Two mechanisms (git/CI for hooks, overlay for skills); third manifest to gate | Selected: fits each surface to its correct delivery mechanism |
| Keep filename/name-pattern excludes (status quo) | Zero new machinery | Cannot express borderline items; no dogfood of the base; silent leaks | Rejected: it is the problem |
| Delete internal from the vendored surface entirely | Simplest ship base; matches #3197 for hooks | Skills have no `.githooks`/CI home; deleting an internal skill removes it from our own Copilot runtime | Rejected for skills; adopted for hooks by #3197 |
| Single merged plugin with runtime filtering | One plugin to install | Copilot has no per-item runtime include/exclude; plugin load is all-or-nothing | Rejected: the host cannot filter within a plugin |
| gstack live team-mode clone | Auto-updating, no vendored files | Couples the customer install path to repo internals; the base must stay a clean vendored artifact | Rejected for the customer base; the symlink idea is adopted for the local dogfood install only |
| Tag now, defer the overlay split (build-time exclude only) | Declares the boundary; zero third-tree cost while the internal set is empty | Loses an internal skill from our own Copilot runtime the moment one is tagged internal | Partially adopted: this is Decision item 6, the overlay is designed but deferred until an internal skill exists |

### Trade-offs

The design accepts two mechanisms for two surfaces: hooks flow to `.githooks`/CI
via #3197, skills flow to a load-time overlay. That is more conceptual surface
than one uniform mechanism, but it matches reality. A hook can run at commit,
push, or PR time from a git hook or CI; a skill can only be delivered as a plugin.
Forcing both into one mechanism would either strand internal skills (delete
approach) or duplicate hook governance in two enforcement points (overlay-hooks
approach), which #3197's audit found net-negative.

The `surface` tag adds a per-item maintenance obligation and a build gate. That
cost buys a recorded, reviewable decision on every item and prevents the silent
leak of a borderline item such as the session family.

## Consequences

### Positive

- Our Copilot sessions can run the real shipped base, so form-factor bugs surface
  in our own use instead of in a customer install.
- The base-alone e2e catches base-only failures that the `.claude` superset masks.
- The symlink dogfood install tracks the repo and ends the 0.5.248 copy rot.
- Customers receive a clean base without this repo's internal session and
  governance machinery.
- The `surface` tag is one declarative source consumed by #3197's hook purge,
  #3216's enumeration, and the new skill overlay.

### Negative

- `build_all.py` and the generators grow a third Copilot output tree and a tag
  router. More code in the build seam.
- A third plugin manifest (`src/copilot-cli-internal`) needs version handling and
  gate reconciliation.
- Every new skill, agent, and instruction now requires a `surface` tag or the
  build fails. This is intended friction, but it is friction.

### Neutral

- The internal overlay is expected to be empty for skills at first. The mechanism
  is designed and gate-reconciled now, so it can be turned on without redesign, but
  it is materialized only when an internal skill actually exists, per the overlay
  decision gate (Decision item 6). #3216 proves internal items exist on the hook
  surface, and the session family sits on the skill boundary, so the boundary itself
  is real even when the skill overlay starts empty.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `build/scripts/build_all.py` | Direct | Route items by `surface` tag into base vs overlay; emit the third tree; `--check` snapshot must cover `src/copilot-cli-internal/` | Medium |
| `build/scripts/generate_skills.py`, `generate_agents.py`, `generate_rules.py` | Direct | Read `surface` frontmatter; hard-fail on untagged; route output | Medium |
| `templates/platforms/copilot-cli.yaml` | Direct | Replace crude `excludeFilenames` with tag routing; declare the overlay output | Medium |
| `.github/plugin/marketplace.json` | Direct | Must NOT list the overlay; base entry unchanged | Low |
| `build/scripts/check_plugin_manifest_parity.py` | Direct | Parity stays `.claude` version == `src/copilot-cli` base version (version strings, not content). Overlay is not in the parity pair | Low |
| `build/scripts/validate_plugin_version_bump.py` | Direct | Add the overlay as a fourth version line; a content change under the overlay requires its own bump. The base pair bump is unchanged | Medium |
| `.github/workflows/nightly-cli-smoke.yml` | Direct | Add the base-alone e2e job, Linux and Windows; the overlay e2e is deferred per Decision item 6 | Low |
| `tests/e2e/` | Direct | New real-artifact tests replacing the synthetic marker probe for shipped-surface coverage | Medium |

## Implementation Notes

Phased, matching issue #3222. Each phase is its own PR under the atomic-commit and
plugin-version-bump rules.

1. This ADR (fires adr-review).
2. Base-artifact e2e against the current `src/copilot-cli` base. This delivers the
   D1 dogfood-verification value before any tag or split exists, and it establishes
   the assertion primitives (fired hook primary, `skill list` co-primary,
   enumeration secondary, real skill script resolves under the plugin root).
3. The symlink dogfood install (Unix symlink, Windows copy plus the freshness check
   above). This kills the 0.5.248 rot and is the highest-value, lowest-risk phase,
   so it ships early rather than last. It depends on nothing in the tag or split.
4. `surface` tag reader plus build hard-fail on untagged, with strict enum
   validation and CI enforcement, and all current items tagged. Default posture
   leans ship; internal is the narrow, deliberate exception.
5. The two-plugin split in `build_all.py`, emitting `src/copilot-cli-internal`,
   gated by Decision item 6 (built only when an internal skill exists). Reconcile
   the parity and version-bump gates per the detail below.

Gate reconciliation detail (resolves the open question in #3222): splitting does
not break parity. `check_plugin_manifest_parity.py` compares version strings across
exactly two manifests in its `_MANIFESTS` tuple (`.claude/.claude-plugin/plugin.json`
and `src/copilot-cli/.claude-plugin/plugin.json`) and asserts `len(unique) == 1`.
Content is never compared, and `.claude` and `src/copilot-cli` already differ in
content today. The overlay manifest is NOT added to `_MANIFESTS`; the parity check
stays a two-way base-vs-`.claude` version-string equality, which the base pair keeps
by bumping together. The overlay IS added to `validate_plugin_version_bump.py` as a
fourth `PluginManifest` entry (`source_dir="src/copilot-cli-internal"`,
`manifest="src/copilot-cli-internal/.claude-plugin/plugin.json"`), joining the three
existing entries (`.claude`, `src/claude`, `src/copilot-cli`). The overlay carries
its own independent version line that bumps only when content under
`src/copilot-cli-internal` changes; it is never forced to equal the base version.
Because the local Unix dogfood install is a symlink to live source, the overlay's
version-based cache-busting is moot on Unix; the version line matters only for the
Windows copy install, addressed by the freshness check above. This wiring exists
only once the overlay decision gate (Decision item 6) fires; until then the gates
are unchanged.

Tag location: `surface:` frontmatter key in `SKILL.md`, `*.agent.md`, and the rule
source files under `.claude/rules/`. The tag lives in the canonical source and the
generators propagate the routing decision; it is not hand-added to generated output.
This tag subsumes the existing `keepInternalGlobsFor` rule-glob mechanism (#2892):
once every rule source carries a `surface` tag, `keepInternalGlobsFor` is removed,
not left as a parallel second boundary mechanism. Hooks carry the tag in their
registration entry so #3197 and #3216 can read it without an overlay build. When the
overlay exists, the base and overlay use distinct plugin `name` fields so Copilot CLI
treats them as two plugins, and a build check rejects a skill, agent, or instruction
name that appears in both trees so the overlay can never silently shadow a base item.

## Reversibility

Each phase is independently revertible and ordered so the irreversible-looking
pieces come last. The base-alone e2e and the symlink dogfood install (the
early-value phases) are pure additions: reverting them removes a CI job and an
install script with no effect on the shipped base. The `surface` tag is additive
frontmatter; reverting it means deleting a key and restoring the filename excludes.
The overlay split is the only structural change, and it is gated (Decision item 6)
so it is not built until an internal skill exists. If the overlay is stood up and
later proves unwarranted, the unwind is: remove the fourth `PluginManifest` entry
from `validate_plugin_version_bump.py`, delete `src/copilot-cli-internal`, drop its
`OWNED_PREFIXES` entry and the overlay e2e job, then re-tag its items `ship` or
delete them. No customer-facing artifact changes, because the overlay was never in
any `marketplace.json`.

## Confirmation Criteria

- The base-alone e2e passes on Linux and Windows in `nightly-cli-smoke.yml`, with a
  fired hook as the primary assertion, for two consecutive scheduled runs.
- The `surface` tag gate fails a CI run when an untagged item is added and passes
  when it is tagged, proven by a positive, a negative, and an invalid-value test
  case.
- CI asserts both shipped security hooks (`invoke_security_gate`,
  `invoke_security_commit_gate`) are present in the base and classified
  `surface: ship`; the run fails if either is missing or reclassified `internal`.
- The symlink dogfood install makes `copilot` load the repo `HEAD` version in an
  interactive session, verified by the loaded `plugin.json` version matching `HEAD`
  rather than 0.5.248.
- If the overlay gate fires, the parity gate stays green (two-way) and the
  version-bump gate flags an unbumped overlay content change.

## Review Date

Re-review by 2026-10-18 (90 days). At that review: if no skill has been tagged
`surface: internal`, the overlay mechanism stays deferred or is removed per the
Reversibility section, and this ADR is amended to record that the tag plus the
dogfood install (not the split) were the durable outcome.

## Related Decisions

- ADR-079 (plugin version bump stays at PR time): the host-freshness constraints
  that bound the overlay's version handling.
- ADR-042 (Python migration): the split logic and install script are Python.
- Issue #3197 (hook ROI reduction program): owns the hook surface; this ADR does
  not build a hook overlay.
- Issue #3216 (purge non-customer hooks from vendored surface): the authoritative
  hook ship-vs-internal taxonomy the `surface` tag encodes.
- Issue #2892 (`keepInternalGlobsFor`): the existing instruction-glob split this
  ADR generalizes into a per-item tag.

## References

- `.claude-plugin/marketplace.json` and `.github/plugin/marketplace.json`: the
  two marketplace sources whose `project-toolkit` entries expose the asymmetry.
- gstack (`github.com/garrytan/gstack`): the `_link_or_copy` symlink-on-Unix,
  copy-on-Windows install pattern adopted for the local dogfood install.
- `build/scripts/build_all.py`, `build/scripts/generate_skills.py`: the generation
  seam this ADR extends.
