---
# taste-lint: ignore file-size, one decision record; the measured probes and the
# round-by-round repair history are the evidence for its decisions, and splitting
# them out would separate each claim from its proof.
id: ADR-072
status: accepted
date: 2026-06-09
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-072: JTBD-Based Plugin Architecture with Per-Harness Emission

## Status

Accepted.

Accepted 2026-09-12, after three `adr-review` rounds and with all five conditions
in "Conditions to reach Accepted" met and all four Definition-of-Ready questions
answered. Requested by issue #1774 (parent epic #1072, v0.4.0 Framework
Extraction). Refines the plugin taxonomy of ADR-045 (see Decision Drivers).
`implemented` stays `false`: accepting the direction moves no code, and M1 to M5
remain unshipped work tracked under issue #5669.

**What Accepted does and does not mean here.** It means the direction, the plugin
partition, the dependency mechanism and the emission model are settled and a future
change does not get to relitigate them without new evidence. It does not mean the
milestones are funded or scheduled, and it does not repair the one gap this record
has carried since round 1: the JTBD premise is an unmeasured design hypothesis,
recorded as such in Negative consequences. Two round 3 seats reached that
independently. M1 and beyond should not be funded on the premise alone.

**What round 3 actually returned, since round 1's tally is narrated above and
omitting round 3's would flatter this record.** Round 3 split six ways: architect
Block, critic Block, independent-thinker and security Disagree-and-Commit, analyst
and high-level-advisor Accept. Both Blocks carried a P0. The architect's was a
quotation attributed to ADR-064 that does not exist in it, removed in that round.
The critic's was M5's alias route being named rather than chosen, decided in
Decision 4 here. Round 4 then ran against this text. So acceptance rests on two
P0s closed and a fourth round, not on a panel that agreed the first time, and a
reader should not infer more consensus than that.

**Where the authority for this acceptance comes from, stated so a reader can
check it rather than take the record's word.** The repository owner directed, in
the working session that produced this change, that ADR-072 and ADR-101 reach
`accepted`. That instruction is not a repository artifact and cannot be cited as
one. The verifiable act is the merge: the owner merging the pull request that
carries this status flip is the ratification, and until that merge this record's
`accepted` is a proposal like any other. An earlier revision of this paragraph
said the answers were taken "under delegated authority" and cited nothing, which
is a self-evidencing claim of exactly the kind this record spent three rounds
removing. Round 4's critic and independent-thinker seats both caught it.

AGENTS.md lists "New ADRs" under **Ask First**, and this record's frontmatter
names `decision-makers: [rjmurillo]`. Neither is satisfied by an agent asserting
it was authorized. They are satisfied by the owner's merge, which is why the four
answers below are written to be reversible: each records the evidence it rests on,
so reversing one means producing better evidence rather than re-arguing taste.

**This record's `accepted` status is not evidence for its own premise.** A future
ADR may cite ADR-072 as the settled decision on plugin partitioning, dependency
declaration and emission timing. It may not cite this record's acceptance as
evidence that the job-shaped install menu is validated, because it is not: see
Negative consequences. That is the laundering path by which ADR-045's unexecuted
`implemented: true` became citable authority, and it is closed here explicitly.

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

**The five blockers that held this record at `proposed`, all of them its own
defects rather than platform limits. All five are closed.** They are kept struck
rather than deleted so the path from `proposed` to `accepted` stays auditable.

1. ~~The Definition-of-Ready questions below are unanswered.~~ **Closed
   2026-09-12.** All four are answered: build-time emission in Decision 2, and the
   `keywords` carrier, the Cursor-now-Codex-later split and the additive shape of
   a future Codex emitter in Decision 5.
2. ~~Decision 1 names five plugins, zero of which exist.~~ **Closed 2026-09-11.**
   Decision 1 now states that none of the four capability plugins exists, names
   the three real plugin roots, and marks the table as a target state.
3. ~~The distribution premise was falsified.~~ **Closed 2026-09-09.** Withdrawn in
   "Distribution context", with the installed population recorded as unknown
   rather than replaced with a second unmeasured number.
4. ~~Decision 4's M1 to M3 are dead as written.~~ **Closed 2026-09-11.** The
   commands leg is recorded as deleted by ADR-064, M1 to M3 is retargeted to
   user-invocable skills, and the Cursor and Codex halves are priced separately
   because only one of them is greenfield.
5. ~~Issue #1774 is closed `not_planned` (2026-06-19, ten days after this record
   was authored) and parent epic #1072 is closed, so nothing tracks this work.~~
   **Closed 2026-09-09.** Successor filed per the ADR-052 precedent and named
   here: **issue #5669**, which tracked settling this record and carried blockers
   1 through 4 as its checklist.

Round 4's architect seat found items 1 and 4 still reading as open roughly thirty
lines below a paragraph saying all four questions were answered. That is the
seventh restatement drift logged against this record and the first one inside a
single section, which is worth recording because the previous six were all far
enough apart to be explicable by distance.

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
  corrected that in Decision 4 while leaving this subsection stale; this bullet is
  the repair. Skills are now the single user-invocable surface, generated by
  `generate_skills.py`.

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
`.claude/ -> generated` seam for rules and hooks rather than relocating every rule
and hook source into `templates/`. The agent seam (`templates/agents`) stays as
is. An earlier revision of this paragraph named commands as a third class; ADR-064
deleted that leg and this is the sixth place in this record where that correction
reached the argument and not a restatement of it. New work is limited to:

- Completing per-harness emitters where coverage is missing (Codex `AGENTS.md`
  fragments, Cursor `.cursor/rules/*.mdc`), each behind a drift check matching the
  existing generators.
- Mapping capabilities to plugins (manifests), not moving files.

Relocating sources into `templates/*.shared.md` for all classes is recorded as a
considered alternative (see Alternatives), not the decision, because it is a real
migration with no demonstrated benefit over the working `.claude/` seam.

**Emission happens at build time, not at install time. Decided 2026-09-12**, which
answers the first Definition-of-Ready question. Artifacts are generated by this
repository's build, committed, and guarded by the drift checks that already exist,
which is what the seam above already does for rules and hooks. Install-time
emission was considered and is not constructible today: the documented Claude Code
hook event set in
`.claude/skills/agent-harness-reference/references/official-hook-contracts.md`
contains no plugin-install or post-install transform event, and the earliest hook
fires at `SessionStart`, inside a session and after install completes. Scoping a
milestone against install-time emission would be committing to a host capability
nobody has measured, which is the exact premise failure round 1 blocked on.

REQ-003-008's NO-REGEN sentinel remains the escape hatch for a consumer who wants
to hand-edit a generated file, so build-time emission does not cost them that.
Revisit only if a host ships a documented install-time transform hook.

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

- ~~`build/scripts/validate_plugin_manifests.py` omits `dependencies` from
  `ALLOWED_KEYS` and fails unknown keys, so the field would fail this
  repository's own gate.~~ **Staged in this same change**, ahead of M4, because it
  was a settle-the-record blocker rather than implementation. It is not on `main`
  until this merges, and an earlier revision of this sentence said "Shipped",
  which described unmerged working-tree code as delivered. `dependencies` is now in
  `ALLOWED_KEYS` and `_validate_dependencies` checks the value: it must be a list
  of non-empty, trimmed strings, and an entry carrying a version specifier is
  rejected because ADR-092 leaves a bare name or `name@marketplace` as the only
  possible form. Nine test functions, sixteen collected cases once the
  version-specifier parametrization expands, cover positive, negative and edge,
  and the three shipped manifests stay valid because none declares the field.
  The specifier pattern rejects `<`, `<=` and `!=` as well as `@` plus a digit,
  `==`, `>=`, `~` and `^` plus a digit; the first three were added in round 4
  after the security seat found `cap-b<2.0.0` passing as a bare name.

  **What M4 still owes, so this is not read as finished.** The value check is a
  shape check. It does not constrain the target to a marketplace this repository
  declares, so a dependency naming a plugin that exists in no declared marketplace
  passes today. That constraint is the first of the two supply-chain requirements
  below and remains M4 work.
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
2.1.122" in three places: the comment above `_is_repo_marketplace_manifest`, the
comment above `_MARKETPLACE_RUNTIME_FORBIDDEN_KEYS`, and the error string inside
`_check_marketplace_runtime_forbidden_keys`. The version was measured in commit
`a4ed5850c` on 2026-05-01. Cited by symbol because the line numbers for this
exact string have now drifted three times: an earlier revision said lines 86 and
120 with 120 blank, a later one said 86, 99 and 133, and adding the
`dependencies` validator above them in this very change moved them again. Five of six seats read that comment as a standing platform law and
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
- M4: capability plugin manifests with declared `dependencies`. Per ADR-092 a
  dependency here can only ever be a bare name or `name@marketplace`, never
  version-constrained, and M4 must say so rather than implying a constrained edge.
- M5: cut `project-toolkit` to depend on the capability plugins and deprecate the
  directory-named plugins. This is the irreversible, install-contract-breaking
  milestone and MUST ship with an installed-user migration path and a marketplace
  alias so existing install commands do not 404.

None of these milestones is funded or scheduled. They are the shape the work
would take, not a commitment that it will be done; see Status and Negative
consequences for why the demand premise has to be measured before M1 is funded.

Each milestone is a separate issue under issue #5669 with its own acceptance
criteria and tests. **An earlier revision put them under epic #1072, which is
closed, as is issue #1774, this record's own tracker, closed `not_planned` on
2026-06-19, ten days after this record was authored.** That is the same shape
ADR-064's record diagnosed for issue #2139, and the remedy is the one ADR-052
set: file successors and name them in the Status section rather than reopening a
closed tracker. Issue #5669 is that successor, is named in the Status section
above, and is where the milestone issues belong.

### 5. The remaining Definition-of-Ready answers

Decided 2026-09-12 on the evidence below, and ratified by the owner's merge of
the change that carries them (see Status for why the merge, not the assertion, is
the authority). Each is revocable; none is load-bearing for the JTBD direction
itself.

**A `jobs` label rides on `keywords`, not a new schema field.** `keywords` is
already in `ALLOWED_KEYS` in `build/scripts/validate_plugin_manifests.py`, is
accepted by the host, and is currently unset in all three shipped manifests, so it
is an open slot costing no gate change. A dedicated `jobs` key buys nothing at
runtime: the 2026-09-09 probe measured the host printing `Unknown field 'jobs'.
Claude Code ignores it at load time.` and passing, and nothing in this repository
invokes the host's own validator, so a new key would be enforced only by our
reimplementation. Use a `jtbd:` prefixed keyword, and have the M4 gate require
exactly one such keyword per capability plugin, which buys the one-job-per-plugin
enforcement Decision 1 wants without a schema extension. Promote to a typed field
only when a consumer needs typed values a string convention cannot carry.

**Cursor ships in v0.4.0. Codex is deferred.** They are not the same size of work,
which is why the third question could not be answered as one. Cursor is greenfield:
`find . -name '.cursor' -o -name '*.mdc'` returns nothing outside `.git/`, so a new
emitter writes into empty space and cannot regress a workflow that does not exist.
Codex is not greenfield, and deferring it is the conservative half of the split.

**A Codex emitter, when it is scoped, writes a new generated surface and leaves
the hand-authored guides alone.** This is the fourth question, which the record did
not name until round 3 surfaced it, and answering the third without it would have
hidden the real cost. `git ls-files '*AGENTS.md'` returns eleven tracked files that
`generate_skills.py` deliberately excludes via `_DEFAULT_EXCLUDES`. Converting any
of them would reverse a live generator policy and take away the direct editing
every maintainer uses today, for no gain the JTBD direction requires. So the Codex
emitter is additive by construction, and a future record that wants conversion has
to argue for it separately rather than inheriting it from this one.

## Conditions to reach Accepted (architect review, APPROVE WITH CHANGES)

All five are met as of 2026-09-12. Each carries where it was met so a reader can
check rather than trust the checkmark.

1. **Met.** Generation-architecture description corrected to the asymmetric model
   and the existing `.claude/ -> generated` seam reused as default. The Context
   subsection now separates the rules and hooks seam from the commands leg ADR-064
   deleted, and Decision 2 carries the same correction.
2. **Met.** Cross-plugin coupling reconciled with issue #1773 decision D3 and the
   #1148 analysis via declared `plugin.json` dependencies and fail-loud partial
   install, in Decision 3, with the host-side resolver measured rather than
   assumed. Two supply-chain requirements were added to that section in round 3.
   The analyst re-verification of #1148 currency remains scoped to before M4, not
   before Accepted, which is where the original condition put it.
3. **Met.** ADR-045 is cited as binding precedent and the relationship is stated as
   refine-within-epic. ADR-045's Related Decisions now carries the reciprocal
   pointer, because it is `accepted` with `implemented: true` and named this record
   nowhere, so the refinement was legible from only one side.
4. **Met.** Reversibility treats M5 as contract-breaking with a migration path and
   marketplace alias, and the alias is now measured with two negative controls
   rather than asserted. Decision 4 pins route 1 at a Claude Code 2.1.268 floor.
5. **Met.** Plugin count and contents fixed to one authoritative five-plugin list
   in Decision 1, with the note there recording that none of the four capability
   plugins exists yet and that the table is a target state.

**All four Definition-of-Ready questions are answered.** Build-time emission in
Decision 2; the `keywords` carrier, the Cursor-now-Codex-later split, and the
additive shape of a future Codex emitter in Decision 5. The fourth question, the
shape of a Codex emitter, was not in the original three and was surfaced by the
round 3 panel; answering the Cursor and Codex scope without it would have priced
two different kinds of work as one.

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

**M5 uses route 1, the dual marketplace entry, with a floor of Claude Code
2.1.268. Decided 2026-09-12.** It is the route this record measured, with the
negative controls above establishing that the validator reads the array and
enforces name uniqueness, so a passing dual entry is a real alias rather than a
duplicate the host ignores. Route 2 is recorded as the unprobed alternative and
must not be adopted without the same three-case measurement. M5 MUST re-run the
route 1 probe against the then-current client before it ships, because the floor
is a measurement and not a guarantee, and MUST fail loudly rather than silently
dropping the alias if that re-run does not reproduce. No
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
