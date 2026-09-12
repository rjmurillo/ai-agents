---
id: ADR-072
status: proposed
date: 2026-06-09
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-072: JTBD-Based Plugin Architecture with Per-Harness Emission

## Status

Proposed. Amended 2026-09-09 after a six-seat `adr-review` round. This ADR
may exist as `Proposed` but MUST clear the conditions in "Conditions to reach
Accepted" before its status moves to `Accepted` and any milestone is
implemented. Requested by issue #1774 (parent epic #1072, v0.4.0 Framework
Extraction). Refines the plugin taxonomy of ADR-045 (see Decision Drivers). No
code moves on this ADR alone.

**Round outcome.** Five seats returned Block recommending `rejected`, on the
shared premise that Decision 3's `dependencies` field and Decision 4's
marketplace alias are capabilities the platform does not offer. The sixth seat
refused that premise and ran a probe instead. The probe refuted it, and the
amendment below records what it measured, so the record is amended rather than
rejected. What the five seats found that survives the probe is real and is
carried into the blockers: falsified premises, not an unbuildable mechanism.

**Why not `rejected`.** In this repository `rejected` means a proposal declined
and not returning (ADR-031 and ADR-095 both open "Recorded so the proposal is
findable and does not return"). Every seat endorsed the JTBD direction, so that
enum would record the opposite of the panel's position. ADR-073 line 57 blesses
the alternative directly, naming this record's conditional `proposed` state as
the case the prose Status section exists to carry.

**Blockers, all of them this record's own defects rather than platform limits:**

1. The Definition-of-Ready questions below are unanswered.
2. Decision 1 names five plugins, zero of which exist; see the note there.
3. The distribution premise was falsified; see "Distribution context".
4. Decision 4's M1 to M3 are dead as written; see the note there.
5. ~~Issue #1774 is closed `not_planned` (2026-06-19, ten days after this record
   was authored) and parent epic #1072 is closed, so nothing tracks this work.~~
   **Closed 2026-09-09.** Successor filed per the ADR-052 precedent and named
   here: **issue #5669**, which tracks settling this record and carries blockers
   1 through 4 as its checklist. It deliberately does not track implementation,
   because this round established the record is not ready to implement.

## Date

2026-06-09

## Distribution context

**Corrected 2026-09-09; the original figure was not a measurement.** This record
opened by asserting an installed base of roughly 400 engineers. That number is
ADR-045's distribution *target*, restated as a fact. ADR-045 line 24 reads "The
framework must be distributed to ~400 users within 30 days", line 38 "targets
~400 users via plugin marketplace within 30 days of extraction completion", and
line 56 "targets ~400 users in an organizational rollout". All three are
future-tense and conditional on the ADR-045 extraction into
`rjmurillo/awesome-ai`, which never happened: `.claude-plugin/marketplace.json`
still ships from in-repo sources.

The installed population is therefore unknown, and no measurement of it exists in
this repository. That matters because the number was the denominator for every
impact and reversibility claim here, including the argument that M5's blast
radius makes this an ADR rather than a refactor. The argument survives without
the number, because breaking an install contract is bad at any population, but it
must be made qualitatively until someone measures.

The marketplace ships two plugins from `.claude-plugin/marketplace.json`
(`claude-agents` from `./src/claude`, `project-toolkit` from `./.claude`) and a
third from `.github/plugin/marketplace.json` (`project-toolkit` from
`./src/copilot-cli`). Three plugin roots, two marketplaces.

## Context

Plugins are sliced today by where files live, not by the job the user hires them
to do. ADR-045 already began framework extraction into concern-based plugins
(`core-agents`, `framework-skills`, `session-protocol`, `quality-gates`); this ADR
re-expresses those boundaries in job-to-be-done terms and adds per-harness emission
for the non-agent artifact classes.

Users think in jobs ("ship code safely", "enforce standards", "understand this
codebase"), and they run different harnesses that each consume a different file
format for the same capability. "Write and ship code" is `/build`/`/test`/`/review`
/`/ship` commands plus quality skills and hooks on Claude Code; `.github/prompts/`
plus agents on Copilot CLI; `AGENTS.md` directives on Codex CLI; `.cursor/rules/*.mdc`
on Cursor.

### Current generation model (corrected; the seam is asymmetric)

The architect review corrected a premise in #1774 that this ADR carried in draft.
The repository does NOT use one uniform `templates/*.shared.md` source for every
artifact class. It uses two seams:

- **Agents:** canonical source is `templates/agents/*.shared.md` (dual frontmatter);
  `build/generate_agents.py` emits `src/{claude,copilot-cli,vs-code-agents}/`.
  Neither output tree is itself the source.
- **Rules and hooks:** generation ALREADY exists (`generate_rules.py`,
  `generate_hooks.py`, wired into `build/scripts/build_all.py`). Their canonical
  source is `.claude/` (`.claude/rules/*.md`, `.claude/hooks/*.py`), which Claude
  Code consumes directly; the generators transform that source into
  `.github/instructions/` and `src/copilot-cli/`. See the artifacts stanza in
  `templates/platforms/copilot-cli.yaml` (`sourceDir: .claude/...`).
- **Commands:** this leg is gone. ADR-064 deleted `.claude/commands/` and
  `build/scripts/generate_commands.py`; both are absent from the tree today. An
  earlier revision of this subsection listed the generator as existing and
  `.claude/commands/*.md` as a canonical source, and the 2026-09-09 amendment
  corrected that in Decision 4 without correcting it here. Skills are now the
  single user-invocable surface, generated by `generate_skills.py`.

So rules and hooks already have per-harness emission from a single source. The
job is not to build that seam; it is to make the per-harness coverage complete
(Codex, Cursor) and to map capabilities onto plugins.

## Decision

Adopt two coupled changes. Capability slicing without complete per-harness emission
still leaves harness gaps; per-harness emission without capability slicing still
presents a storage-shaped install menu.

### 1. Slice plugins by job-to-be-done (capability)

Reconcile against the five-plugin set named in #1774 (the four below plus
`agent-team`), not the four-plugin draft summary. Authoritative list:

| Plugin | Job to be done | Contents (capability) |
|--------|----------------|-----------------------|
| `dev-lifecycle` | Write and ship code safely | spec -> plan -> build -> test -> review -> ship workflows, supporting quality skills, shipping hooks |
| `quality-gates` | Enforce standards | PR review skills, golden principles, taste lints, security scan, pipeline validator, enforcement hooks |
| `session-protocol` | Learn and improve | session init/end, handoff protocol, retrospective, memory documentary |
| `agent-team` | Understand + plan | the specialist agents, routing, and the memory the agents share |
| `project-toolkit` | All of the above | meta-plugin that DEPENDS ON the above, retained for one-install convenience |

**None of the first four exists.** The tree holds three plugin roots carrying a
`.claude-plugin/plugin.json`: `.claude/` (`project-toolkit`), `src/claude/`
(`claude-agents`), and `src/copilot-cli/` (`project-toolkit`). This table is a
target state, and an earlier revision read as though it described one.

Two contents cells also name assets that do not exist. `.claude/hooks/hooks.json`
and `src/copilot-cli/hooks/hooks.json` both read `"hooks": {}`, because ADR-097
(accepted) retired every tool-use registration, so neither the "shipping hooks"
nor the "enforcement hooks" half of that partition has anything to partition.
The four surviving session-boundary registrations live in `.claude/settings.json`,
which is repo-local configuration rather than a plugin surface, so they are not
assignable to a plugin either. Whoever implements M4 partitions capabilities,
not hooks.

One job description had drifted from its source and is repaired above. The
plugin table in issue #1774 gives `agent-team` the job "Understand + plan", and
an earlier revision of this table renamed it to "Delegate to specialists" while
claiming to reconcile against #1774's set. The table now carries #1774's
wording.

### 2. Reuse the existing source seam; do NOT relocate canonical sources

Default to the lower-risk mechanism the architect recommended: reuse the existing
`.claude/ -> generated` seam for commands/rules/hooks rather than relocating every
rule/command/hook source into `templates/`. The agent seam (`templates/agents`)
stays as is. New work is limited to:

- Completing per-harness emitters where coverage is missing (Codex `AGENTS.md`
  fragments, Cursor `.cursor/rules/*.mdc`), each behind a drift check matching the
  existing generators.
- Mapping capabilities to plugins (manifests), not moving files.

Relocating sources into `templates/*.shared.md` for all classes is recorded as a
considered alternative (see Alternatives), not the decision, because it is a real
migration with no demonstrated benefit over the working `.claude/` seam.

### 3. Declare cross-plugin dependencies so a partial install cannot break

Issue #1773 decision D3 keeps `project-toolkit` bundled because agents/commands/hooks/
skills are interdependent (per the #1148 analysis): installing one without the
others breaks. JTBD slicing increases the cross-plugin dependency surface, so each
capability plugin MUST declare its `dependencies` in `plugin.json`, and a partial
install must fail loud at install time rather than degrade to a silent no-op (the
#2205 customer-wedge failure class). Whether #1148's coupling claim still holds is
an evidence question routed to the analyst before M4.

**Measured 2026-09-09 against Claude Code 2.1.266, because the review round
blocked on the belief that this field does not exist.** `dependencies` is a
first-class, type-checked manifest field, and the host ships a resolver for it.
Three probes, the second and third being the negative controls that make the
first mean something:

- A manifest carrying `dependencies: ["cap-b@mkt"]` plus explicit `skills` and
  `commands` path keys passes `claude plugin validate` with only the routine
  missing-`version` and missing-`author` warnings.
- An unrecognized key produces `zzzUnknownKey: Unknown field 'zzzUnknownKey'.
  Claude Code ignores it at load time.` and validation still PASSES. So a
  tolerated-but-ignored key is distinguishable from a real one.
- `dependencies: "nope"` produces `dependencies: Invalid input` and validation
  FAILS. A field the host merely ignored could not be type-checked, so this is
  the discriminating result.

The reviewing seat that ran the equivalent probe also installed a two-plugin
local marketplace end to end and observed `Successfully installed plugin:
cap-a@probe-mkt (+ 1 dependency: cap-b)` on install and a dependency-no-longer-
needed notice on uninstall, with `claude plugin prune` available for collection.
That is the fail-loud partial-install contract this section asks for, already
implemented by the host.

The requesting issue said so first. Issue #1774's open question 4 reads
"**Dependency resolution**: If `dev-lifecycle` depends on skills from
`quality-gates`, how does the install flow handle this? (Claude Code supports
`dependencies` in plugin.json.)" So the premise five seats blocked on was
contradicted in writing by this record's own tracker, three months before the
round sat.

**What actually blocks Decision 3, then, is local and small.** Two repository
facts, neither a platform limit:

- `build/scripts/validate_plugin_manifests.py` omits `dependencies` from
  `ALLOWED_KEYS` and fails unknown keys, so the field would fail this
  repository's own gate. That is a one-line addition with a test, in the same PR
  as M4.
- ADR-092 (accepted, implemented) deleted `version` from all three manifests and
  `build/scripts/validate_plugin_version_bump.py` fails on its return, so a
  dependency here can only ever be a bare name. M4 must say so explicitly and
  cite ADR-092, rather than implying a version-constrained edge.

**Two supply-chain requirements round 3 added, both for M4.** This section
specified fail-loud for a dependency that is missing, and said nothing about the
opposite risk, a declared dependency silently widening what a consumer receives:

- Validate the dependency value, not only the key. The validator has no
  dependency-value check today, and ADR-092 leaves a bare name as the only
  possible form, so M4 must constrain the target to a marketplace this
  repository declares rather than accepting any name.
- Justify each declared edge in the pull request that adds it, naming the
  capability the dependency supplies and why it cannot be optional. The host's
  install notice (`+ 1 dependency: cap-b`) is informational rather than a
  confirmation gate, so reviewing that edge is the only place a widened install
  footprint gets examined.

**A stale constraint that misled the round, recorded so it does not mislead
again.** `validate_plugin_manifests.py` pins its rationale to "Claude Code
2.1.122" at lines 86, 99 and 133, a version measured in commit `a4ed5850c` on
2026-05-01. An earlier revision cited lines 86 and 120; line 120 is blank. Five of six seats read that comment as a standing platform law and
blocked on it. The forbidden-key check it guards is also narrower than it reads:
`_is_repo_marketplace_manifest` matches three hardcoded paths, so a new
capability-plugin root at any other path is unaffected by it today.

### 4. Milestoned, with M5 as the contract-breaking step

- M1 to M3: complete the per-harness emitters for rules and hooks (additive,
  revertible: add generated output plus drift check, delete nothing).

  **Amended 2026-09-09: the commands emitter is gone and this milestone cannot
  be completed as originally written.** ADR-064 reached `accepted` and
  `implemented: true` on 2026-09-08 via issue #5632, which converted every
  command in `.claude/commands/` into a skill, deleted the tree, and deleted
  `build/scripts/generate_commands.py`. An earlier revision of this record
  committed M1 to M3 to "complete the per-harness emitters for commands, rules,
  hooks" and described `.claude/commands/*.md` as a canonical source. Both are
  now false. ADR-064 settled first, and the tension is resolved in its favour by
  a shipped change rather than by argument.

  An earlier revision attributed that reasoning to ADR-064's Related Decisions
  section and quoted it as saying the two records "cannot both stand as written".
  No such sentence exists. `grep -rn "cannot both stand as written" .
  --include=*.md` returns only this record, and ADR-064 does not mention ADR-072
  anywhere: `grep -n '072' .agents/architecture/ADR-064-commands-to-skills-migration.md`
  exits 1. The point stands on the shipped change alone and never needed the
  citation.

  What survives is real and untouched by that: rules and hooks still have the
  `.claude/ -> generated` seam, and the Codex and Cursor emitters this milestone
  was mainly about remain unwritten. Retarget "commands" to "user-invocable
  skills" and the rest of this record stands.

  **The two remaining emitters are not the same kind of work, and an earlier
  revision called both greenfield.** Measured 2026-09-11 by searching the whole
  tree from its root. Cursor is greenfield: `find . -name '.cursor' -o -name
  '*.mdc'` returns nothing outside `.git/`, so that emitter writes into empty
  space. Codex is not: `git ls-files '*AGENTS.md'` returns eleven tracked files,
  from the repository root down to per-directory guides, and generation
  deliberately excludes them. `build/scripts/generate_skills.py` sets
  `_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")` and applies it wherever a
  platform stanza supplies no `excludeFilenames`.

  That exclusion is real in code, and its stated requirement backing is one hop
  short. The generator's docstring attributes it to "the AGENTS.md/CLAUDE.md
  exclude policy (REQ-003-010)". REQ-003-010, in
  `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md`, is titled
  "`.claude/` is read-only to the build" and constrains where the build may
  write, not which filenames it may emit. It says nothing about excluding these
  two. ADR-108 amended it on 2026-09-11 to carve out template-owned skill files,
  which changes what the build may write and still adds no filename exclusion.

  Cited by requirement id and symbol name rather than by line number on
  purpose. Four line citations in this record have now drifted, three of them
  within hours of being written. REQ-003-010 sat at line 358 when the paragraph
  above was written and at 359 an hour later, when ADR-108 amended the file.
  `_DEFAULT_EXCLUDES` sat at line 39 and moved to 59 when PR #5726 landed the
  skill-template compiler. The first correction fixed only the requirement
  citation and left the symbol citation beside it as a line number, which is why
  the same failure recurred in the same paragraph. A requirement id and a symbol
  name survive an edit above them; a line number does not.

  An earlier revision of this paragraph said a Codex emitter would "reverse a
  requirement". It would reverse a generator policy whose cited requirement does
  not carry it. The docstring citation is a separable defect in
  `generate_skills.py`, not in this record.

  A Codex emitter therefore means converting hand-authored guides into generated
  output, not filling an empty surface, and M1 to M3 must price the two
  separately. The Cursor/Codex Definition-of-Ready question also hides a fourth
  decision the record never names: whether a Codex emitter writes a new,
  additional generated surface and leaves the eleven hand-authored files alone,
  or converts some of them. Those are different costs and different risks, and
  the answer to the third question is incomplete without it.
- M4: capability plugin manifests with declared `dependencies`.
- M5: cut `project-toolkit` to depend on the capability plugins and deprecate the
  directory-named plugins. This is the irreversible, install-contract-breaking
  milestone and MUST ship with an installed-user migration path and a marketplace
  alias so existing install commands do not 404.

Each milestone is a separate issue under issue #5669 with its own acceptance
criteria and tests. **An earlier revision put them under epic #1072, which is
closed, as is issue #1774, this record's own tracker, closed `not_planned` on
2026-06-19, ten days after this record was authored.** That is the same shape
ADR-064's record diagnosed for issue #2139, and the remedy is the one ADR-052
set: file successors and name them in the Status section rather than reopening a
closed tracker. Issue #5669 is that successor, is named in the Status section
above, and is where the milestone issues belong.

## Conditions to reach Accepted (architect review, APPROVE WITH CHANGES)

1. Generation-architecture description corrected to the asymmetric model and the
   existing `.claude/ -> generated` seam reused as default.
2. Cross-plugin coupling reconciled with #1773 D3 / #1148 via declared `plugin.json`
   dependencies and fail-loud partial install (Decision section 3). Analyst
   to re-verify #1148 currency before M4.
3. ADR-045 cited as binding precedent; relationship stated as refine-within-epic,
   and ADR-045 amended if its taxonomy is superseded.
4. Reversibility assessment treats M5 as contract-breaking with a migration path and
   marketplace alias (Decision section 4 and Reversibility).
5. Plugin count and contents fixed to one authoritative five-plugin list (Decision
   section 1).

Open Definition-of-Ready questions to answer before Accepted: install-time vs
build-time emission; whether a `jobs` field is a plugin.json schema extension or
expressible via `keywords`; Cursor/Codex emission scope for v0.4.0 vs deferred.

## Consequences

### Positive

- Install menu matches user mental model (install by job, not directory).
- Per-harness correctness with no hand-maintained format drift, reusing the seam and
  drift checks that already exist.
- New harnesses are one emitter, not a re-authoring of every capability.

### Negative / Costs

- Cross-cutting change to the install contract, for an installed population this repository does not measure. An earlier revision said ~400 consumers; "Distribution context" above withdraws that figure as ADR-045's future-tense target restated as a measurement, and this line kept it.
- New emitters and drift checks for Codex and Cursor are net new code.
- The user-facing premise, that a job-shaped install menu fits user mental models
  better than a directory-shaped one, is an unmeasured design hypothesis rather
  than a measured finding. A repository-wide search on 2026-09-11 for install
  friction reports, user research, or any complaint about the current
  `claude-agents` versus `project-toolkit` split returned none, and "Distribution
  context" above already records the installed population as unknown. Two round 3
  seats reached this independently. It does not block a record that moves no
  code, and it does mean M1 and beyond should not be funded on the premise
  alone. The same evidence discipline that closed the mechanism question has
  never been applied to the demand question.
- Transition window where directory-named and capability plugins coexist.

### Tracked follow-ups (not silent deferrals)

- M1 to M5 issues opened before implementation, under issue #5669 rather than under epic #1072, which is closed. An earlier revision pointed this follow-up at the closed epic.
- Analyst re-verification of #1148 coupling currency before M4.
- ADR-045 amendment for the taxonomy relationship.
- Deprecation note plus marketplace alias for directory-named plugins (M5).

## Alternatives Considered

1. **Keep directory-based plugins, document the JTBD mapping in prose.** Does not
   fix harness coverage gaps or the storage-shaped menu. Rejected.
2. **Relocate all sources to `templates/*.shared.md` (the draft's original
   mechanism).** A real migration that moves the canonical source of every rule,
   command, and hook out of `.claude/` and regenerates `.claude/` as output. No
   demonstrated benefit over the working `.claude/ -> generated` seam. Rejected as
   default; may be revisited if a concrete benefit appears.
3. **One mega-plugin with runtime harness detection.** Harnesses consume static
   files at install time, not a runtime service. Rejected.

## Reversibility and Vendor Lock-in

M1 to M4 are reversible at the milestone boundary (additive generated output behind
drift checks; revert by dropping the emitter). M5 is the contract-breaking
milestone and is reversible only with a migration window: it MUST ship a marketplace
alias mapping the deprecated plugin names to the new capability plugins so installed
users' commands keep resolving, plus a documented migration.

**The alias is constructible, and round 3 measured it instead of reasoning about
it.** The review round blocked partly on the absence of an `alias` or `renames`
key from `.claude-plugin/marketplace.json`, whose entries carry `{name,
description, source}`. That absence is real. What follows from it is not that the
requirement is unimplementable. Measured 2026-09-11 against Claude Code 2.1.268
with `claude plugin validate`, three runs, the second and third being the
negative controls that make the first mean something:

- Two entries with different `name` values (`capability-new` and
  `project-toolkit`) pointing at one `source` PASS, exit 0, with only the routine
  missing-`version` and missing-`author` warnings. The deprecated install name
  stays resolvable, which is the migration path M5 requires.
- `plugins: "nope"` FAILS with `plugins: Invalid input`, exit 1. The validator
  is really reading this array.
- Two entries carrying the SAME `name` and one `source` FAIL, exit 1. Name
  uniqueness is enforced, so the passing case is a genuine alias rather than an
  unchecked duplicate.

An earlier revision asserted the first result without running it, in the same
confident register as Decision 3's probed finding and in the section immediately
after it. That is the round 1 failure shape reproduced inside the amendment
written to diagnose it, on the mitigation guarding the one irreversible
milestone.

`build/scripts/check_plugin_manifest_parity.py` records a second route, that a
marketplace entry may carry any manifest-schema field as catalog metadata and
under `strict: false` may be the whole definition. That route is NOT probed.
M5 must still name which of the two it uses, because this is the one
irreversible milestone and its only stated mitigation; route 1 now has a
measured floor of Claude Code 2.1.268 and route 2 has none. No
harness-proprietary format enters the canonical sources; per-harness specifics live
only in emitters, so dropping a harness is removing one emitter.

## References

- Issue #1774 (this decision), parent epic #1072.
- ADR-045 (framework extraction via plugin marketplace; the 4-plugin taxonomy this
  refines). Note its frontmatter reads `implemented: true` while its decision,
  extraction into `rjmurillo/awesome-ai` with four named plugins, has not
  happened: none of `core-agents`, `framework-skills`, `session-protocol`, or
  `quality-gates` exists and the marketplace ships from in-repo sources. That
  flag needs its own correction, tracked separately from this record.
- ADR-064 (retire `.claude/commands/`; skills are the single user-invocable
  surface). `accepted`, `implemented: true` as of 2026-09-08. It settled first;
  see the M1 to M3 note in Decision 4 for what that removed and what survives.
  ADR-064 does not cite this record, and an earlier revision of this bullet said
  it "named the conflict with this record first", which is the same unsupported
  attribution corrected in Decision 4.
- ADR-107 (canonical skill contracts and harness projections, `proposed`). It
  governs the layer boundary and provenance rules for generated harness
  projections, which is the surface M1 to M3's Codex and Cursor emitters would
  write into. ADR-107 names this record and declares it "**not** a dependency";
  this bullet records the reverse direction so a future emitter implementer
  learns that a sibling record claims that territory before starting.
- ADR-002 (agent generation seam), ADR-042 (Python-first hooks), ADR-006 (thin
  workflows, testable modules: the generator and drift-check shape).
- Issue #1773 decision D3 and the #1148 component-interdependence analysis.
- `build/generate_agents.py`, `build/scripts/{build_all,generate_rules,generate_hooks,generate_skills}.py`, `templates/platforms/copilot-cli.yaml`, `.claude-plugin/marketplace.json`. `generate_commands.py` was listed here until ADR-064 deleted it.
