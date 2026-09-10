---
id: ADR-107
status: proposed
date: 2026-09-09
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-03-09
---

# ADR-107: Canonical Skill Contracts and Generated Harness Projections

## Status

Proposed. **Critical and load-bearing**, as issue #5603 requires this record to state. Scope that
claim precisely, because two review seats read the bold label against the next sentence and
called it self-assigned weight:

- **On merge**, this record governs. It defines the layer boundary, the precedence chain, the
  provenance rule, and the predicate vocabulary that every later slice consumes. It moves no
  generator, no config, and no routing default.
- **It enforces nothing until M1 lands.** The single artifact it ships asserts that the gates its
  conformance table names exist and that each class either names one or is marked missing. That
  is a citation gate, not a behavior gate.

Three of six review seats voted BLOCK on the first revision. This is the second. The debate log
is `.agents/critique/ADR-107-debate-log.md`.

## Evidence labels

Every claim below carries one of four labels. They are not interchangeable, and this record holds
itself to them: the first revision carried a `repo-observed` citation that was false, and the
correction is recorded under "Flagged during the investigation".

| Label | Meaning |
|---|---|
| `repo-observed` | Read in this repository at the cited path and line, at HEAD, during the investigation for this record |
| `docs-say` | Asserted by a repository document or a vendor document. Not independently reproduced here, even when the document is in this tree |
| `runtime-verified` | Reproduced by executing the code, with the command and the result recorded |
| `hypothesis` | Reasoned, not verified. Never load-bearing for a MUST |

Unlabeled prose is argument, not evidence.

## Context

The repository authors behavior once and ships it to several harnesses. Seven generators run from
the `GENERATORS` list at `build/scripts/build_all.py:497-505` (`repo-observed`).
`.agents/governance/GENERATOR-FILES.md:13-20` indexes source-to-output pairs (`repo-observed`).
**The two sets differ**, which matters later: the index has six rows and names
`build/scripts/generate_pr_quality_prompts.py`, which is not in `GENERATORS`; the `GENERATORS`
list has seven entries including `agent-catalog` and `adr-index`, which have no index row. Three
plugin roots ship: `.claude/`, `src/claude/`, and `src/copilot-cli/` (`docs-say`,
`.claude/rules/plugin-self-containment.md`).

Two properties of that pipeline are settled and are not reopened here.

1. Generators read canonical trees and write mirror trees. They never write under `.claude/`.
   `assert_no_claude_writes` at `build/scripts/build_all.py:788` is called at `:2221`, and a
   violation sets `audit.overall_exit = 2` at `:2227` (`repo-observed`).
2. The seam is asymmetric. There is no single template-in, everything-out pipeline. Agents for
   Copilot CLI and VS Code come from `templates/agents/*.shared.md`; rules, skills, hooks, and lib
   come from `.claude/` directly; `src/claude/`, `.claude/agents/`, and `.github/agents/` are
   hand-maintained (`repo-observed`, `GENERATOR-FILES.md:28-38`).

What is missing is not another checker. It is the contract the checkers would check against, and
the scope of that claim needs stating honestly, because the first revision overstated it.

### Where the gap is, and where it is not

Each current gate substitutes a proxy for equivalence, because no predicate is declared:

- Skills and rules get byte equality after regeneration, through
  `build/scripts/build_all.py --check`, wrapped by
  `scripts/validation/check_generated_staleness.py` (`repo-observed`). **This class is effectively
  covered.** It has a working predicate in all but name.
- Agent install pairs get co-change in a diff. `build/scripts/validate_install_parity.py:198-202`
  lists `.claude/agents/`, `.github/agents/`, and `src/claude/` as hand-maintained prefixes and
  `:205-208` applies the predicate (`repo-observed`). The measured asymmetry, that a solo edit to
  `src/claude/architect.md` exits 0 while a solo template edit exits 1, is stated at
  `.claude/rules/claude-agents.md:20-22` (`docs-say`), along with 54 of 173 commits touching a
  hand-maintained shared-agent member without touching the template.
- `templates/agents/*.shared.md` bodies are compared to `src/claude/*.md` bodies by nothing.
  `.claude/rules/claude-agents.md:11` states no check compares that content, and `:52` records
  that `detect_agent_drift.py` reads the template directory for filenames only (`docs-say`).
- `.github/agents/` content is held to a word-set similarity floor. `detect_agent_drift.py`
  hardcodes 100.0 for comparisons whose section allowlist matches nothing, treats install-pair
  drift as advisory unless `--fail-on-install-drift`, and runs that flag only in the weekly
  `.github/workflows/drift-detection.yml` (`docs-say`, `.claude/rules/claude-agents.md:84`,
  `:120-122`).
- A lexical floor cannot see a contradiction. Sixty appended identical lines move the score by
  zero, and a contradiction reusing the surrounding vocabulary scores high and passes
  (`docs-say`, `.claude/rules/claude-agents.md:104-118`).

So the honest scope of the claim is: **the contract is missing for the hand-maintained agent
trees**, three of the five agent surfaces. It is not missing for the generated classes, which
have a working predicate under a different name.

### What PR #5059 does and does not show

On PR #5059, round-cap wiring was hand-edited into `src/copilot-cli/skills/pr-autofix/SKILL.md`,
which is generated. Twenty-six of twenty-six skill tests passed, the agent generator validated,
`pre_pr.py` reported unrelated findings only, and CI then showed the generator stripping all 43
lines (`docs-say`, `scripts/validation/check_generated_staleness.py:1-30`, issue #5079).

**CI caught it.** The local gate also existed: `check_generated_staleness.py` is wired into
`scripts/validation/pre_pr_sequence.py` (`repo-observed`). What failed is that nobody ran it
before pushing. That is a feedback-loop cost, and it motivates C1, not C3. It is cited here as
the cost of a late signal, not as evidence that a projection silently dropped meaning. No such
case is measured in this repository, which is why section 5 is labeled the way it is.

### The capability-evidence problem

Capability claims about a harness or a model arrive as marketing, as documentation, and as
runtime observation, and the three are routinely conflated. The repository already holds the
corrective vocabulary in two places and uses neither as a general contract: the grading table in
`.claude/skills/agent-harness-reference/SKILL.md` (`OFFICIAL`, `CODE`, `EMPIRICAL`,
`DOCS SILENT`), and the fail-closed status lattice landed for issue #5423 in
`scripts/eval/_harness_capability.py:52-73`: statuses `VERIFIED`, `UNSUPPORTED`, `UNVERIFIED`,
and four evidence kinds `BACKEND`, `CLIENT_ECHO`, `CONFIG`, `NONE`, with `VERIFIED` reachable
only from `BACKEND` (`repo-observed`). Issue #5423 itself is still open; the lattice landed, the
issue did not close.

### Corrections to the framing in issue #5603

All `repo-observed`:

- `.agents/HANDOFF.md` does not exist. ADR-014 distributed handoffs; per-issue handoffs live under
  `.agents/handoffs/`.
- `.claude/commands/` is retired. ADR-064 records implementation on 2026-09-08 via issue #5632 at
  its line 16, so "commands" is a historical surface, not a live authored one.
- ADR-072 is `proposed` with `implemented: false`, and issue #5669 tracks settling it. Its plugin
  taxonomy is not available as a dependency.

## Decision Drivers

Five drivers, in priority order. Each alternative in the Rationale section is scored against them.
They are listed because the first revision had none, so its alternatives table stated per-option
pros and cons with no shared criterion to compare them on.

| # | Driver | Why it ranks here |
|---|---|---|
| D1 | **Falsifiability.** A contract no check can fail is prose. | The failure this record exists to prevent is a green gate over an unchecked property. A rule with no possible failure reproduces it. |
| D2 | **Single mechanism.** No second registry, routing authority, or generation system. | Issue #5391's scope correction and issue #5396's ownership rule both forbid it, and the repository already carries one orphaned second mechanism (see R3). |
| D3 | **Debt visibility.** Unchecked classes must be countable, not implicit. | Three of five agent surfaces have no equivalence check today and nothing says so in a machine-readable place. |
| D4 | **Blast radius.** Prefer the change that reverts in one commit. | 27 of 108 records in this corpus are decided and unbuilt. A record that moves generators before it is proven compounds that. |
| D5 | **Cost to the schema validator and the generators.** | `build/scripts/validate_templates_schema.py:151` rejects unknown keys under `artifacts.<name>`, so any config-declared field is a code change, not a config change. |

## Decision

### 1. Six layers, named and separated

Issue #5603 requires this record to distinguish semantic contract, harness projection, capability
profile, advisory model tactic, host authorization, and generated or vendor output. Two of the six
are boundaries rather than layers of an artifact, and saying so is part of the distinction rather
than a weakening of it: host authorization sits outside the tree, and generated output is the
projection layer's product rather than its peer.

| Layer | What it holds | Where it lives today | Who may own it |
|---|---|---|---|
| Semantic contract | Intent, scope, inputs, outputs, ordered steps, completion criteria, evidence requirements, failure states, approval states, idempotence, rollback, safety invariants. Capabilities stated abstractly: read, search, write, execute, network, confirm, delegate | The canonical authored file for the class (`.claude/rules/*.md`, `.claude/skills/<name>/`, `.claude/hooks/`, `templates/agents/*.shared.md`, `src/claude/*.md`) | The canonical file, and only it |
| Harness projection | Discovery path, packaging, frontmatter shape, tool and event translation, lifecycle registration, permission mapping, working directory, exit codes, timeouts, host syntax | The generator, its stanza in `templates/platforms/copilot-cli.yaml`, and the imperative transforms in `build/scripts/copilot_body_translation.py` | The generator and its declared config, never the output |
| Capability profile | Dated, versioned observations about what a harness or model can do | `.claude/skills/agent-harness-reference/references/` | That reference skill |
| Model tactic | Advisory wording, decomposition, context budget, presentation, structured-output hints | `.claude/rules/claude-model-patches.md` | One file per model family, subordinate |
| Host authorization (a boundary, not a layer) | What the running host and the user actually permit | The harness permission surface, outside the tree | The host. Never the repository |
| Generated or vendor output (the projection layer's product) | The projected artifact a consumer installs | `src/copilot-cli/`, `src/vs-code-agents/`, `.github/instructions/`, `.github/prompts/`, `docs/agent-catalog.md` | Nobody. It owns nothing |

The semantic contract states capabilities abstractly because a concrete tool name is a projection
detail. `Read` and `read` and `view` are the same abstract capability wearing three harness
spellings.

### 2. Precedence

```text
host/system policy > user authorization in session > harness permission surface > repository mandatory policy > canonical semantic contract > harness projection > advisory model tactic
```

This restates the chain in `.claude/rules/builder-ethos.md` section 4 (ADR-105) and inserts two
rungs the original does not name.

**The third rung is harness-conditional and empty on one shipped harness.** ADR-085 Finding 1
records that Copilot ships no repo-committed permission surface, only per-invocation
`--allow-tool` (`docs-say`, `ADR-085:156`). On Copilot everything that rung was meant to hold
falls through to the repository-policy rung, which the next paragraph makes advisory. Do not read
the chain as uniform across harnesses.

**A skill cannot grant itself access.** A capability profile recording a harness as capable is an
observation, not an authorization. This rule rests on its own reasoning, not on an authority
claim: authorization is a property of the running host, and no file in a repository can decide
what a host permits, because the host loads the file rather than the reverse. ADR-101's plane
analysis corroborates it (the tree is plane P0, and P0 verdicts are advisory), and ADR-101 is
`status: proposed` with `implemented: false`, so it is cited as corroboration and not as
authority. That is the same standard this record applies to ADR-072.

**Enforcement of this rule today is absent.** It is stated, not gated. Claude's `settings.json`
is the same P0 tree a pull request edits, and Copilot has no committed surface at all. Naming the
gap is the point; a rule claiming enforcement it does not have would be the failure mode this
record exists to prevent.

### 3. Provenance: loaded is not authoritative, and the path is not the class

Content reaching a run has one of four provenances. Loading it does not promote it.

| Provenance | Examples | Standing |
|---|---|---|
| Host and system | Harness policy, tool schemas, sandbox | Highest. Not overridable from the tree |
| User turn | The current request, an explicit approval | Authorizes; bounded by host policy |
| Repository policy | Rules, ADRs, skills, agent prompts already on the trunk | Mandatory for repository work; plane P0, advisory as enforcement |
| External content | Tool results, fetched pages, issue and PR bodies, review comments, subagent reports, memory entries | Data. Never an instruction, never an authority |

**A provenance class is assigned by the plane that owns the path, not by the path itself.**
`.claude/rules/x.md` and `.serena/memories/y.md` are both tree files any pull request can add, so
a directory name cannot separate mandatory policy from attacker-supplied text. The distinguishing
property is whether the content is already on the trunk under the review that governs that plane,
or is arriving inside the change under evaluation.

It follows that **repository policy authored in the change under review is external content for
that change**. A pull request cannot cite the rule file it is adding as the authority for adding
it. This closes the shape ADR-101 exhibits at issue #4402, where self-set authority cited an
agent-writable memory; renaming the directory does not change the shape.

External content that asserts its own authority is still external content. A tool result saying
"you are now permitted to X" changes nothing.

### 4. The projection contract: three fields per artifact class

Every artifact class declares three things. Two exist in some form. The third is the gap.

| Field | Status today |
|---|---|
| Canonical source | Indexed in `.agents/governance/GENERATOR-FILES.md` for six generator rows and three hand-maintained trees (`repo-observed`, `:13-20`, `:28-38`). Partially declared in `templates/platforms/copilot-cli.yaml`, and **that declaration is not reliable**: `artifacts.agents.sourceDir` reads `.claude/agents`, while `build/generate_agents.py` globs `templates/agents/*.shared.md` and consumes only `outputDir` (`:346`) and `outputSuffix` (`:402`) from the stanza (`repo-observed`). The dead key survives because the schema validator allowlists it |
| Declarative transform | Declared in `templates/platforms/copilot-cli.yaml` for rules (`frontmatterRemap: {paths: applyTo}` at `:37`, `frontmatterDrop` at `:39`, `keepInternalGlobsFor` at `:33`) and skills (`mode: directory-copy` at `:13`, `excludeFilenames` at `:18`). **The transform touching the capability set is not declared**: the `SKILL.md` body and `allowed-tools` rewrites live in `build/scripts/copilot_body_translation.py` (`repo-observed`) |
| Equivalence predicate | **Not declared anywhere.** Every gate substitutes a proxy |

**The predicate is declared in `.agents/governance/GENERATOR-FILES.md`, not in the platform
YAML.** The first revision said the platform YAML and the review round falsified that:
`templates/platforms/vscode.yaml` and `visual-studio.yaml` carry only `schemaVersion`, `provider`,
and `legacy`, with no `artifacts` stanza at all, and `copilot-cli.yaml`'s stanza covers five
generator-owned classes (`repo-observed`). Every class that needs a `none` baseline, the three
hand-maintained agent trees, is outside that file and cannot be declared in it. The governance
index already covers both kinds of tree, so it is the only existing surface that can hold the
field for every class. This satisfies D2: it extends the register that already exists rather than
adding a sixth surface.

The predicate vocabulary is three values.

| Predicate | Meaning | Gate shape |
|---|---|---|
| `derived` | Projection equals `transform(source)` recomputed by the generator, where the identity transform is a legal transform | Regenerate, then diff |
| `normalized` | Projection equals source after a declared normalization naming which frontmatter keys are tree-specific and which body sections are shared | Normalize both sides, then diff |
| `none` | No predicate. Legal only as a recorded baseline carrying an owning issue and an expiry | None. This is debt, not a state |

The first revision had a fourth value, `byte`. It is `derived` with an identity transform, and the
only plausible holder (`lib`) is a directory copy, which is a transform. Three values.

`none` is closed to new artifact classes. An existing class carrying `none` records its issue
number and a `review-by` date, and M1 installs a count ratchet over the number of `none` rows in
the same baselined style the four portability checks already use (`docs-say`,
`.claude/rules/plugin-self-containment.md`). Without both the expiry and the ratchet, `none`
legalizes the status quo under a new name, which is the six-month regret two seats named.

### 5. Invariants that a projection must preserve

A `normalized` predicate may drop tree-specific frontmatter and platform-specific tool spellings.
It may not drop any of these eight.

1. Ordered semantic steps, and their order.
2. Completion criteria.
3. Evidence requirements.
4. Failure states and how each is handled.
5. Approval and confirmation gates.
6. Authorization requirements and the abstract capability set.
7. Idempotence and rollback statements.
8. The documented exit-code contract, where one exists.

**Label: `hypothesis` as a completeness claim.** No measured case exists in this repository of a
projection silently dropping one of these. The list is reasoned from what a semantic contract
holds, not derived from an incident. It is written as MUST because a projection that drops one is
a defect by construction, and it is labeled here because this record's own rule says a
`hypothesis` is never load-bearing for a MUST. What that costs: section 5 cannot on its own
justify building C3. The justification for C3 is item 6, which is measurably violated today.

**Only items 6 and 8 are machine-checkable against a representation that exists.**

| Invariant | Representation today | Enforceable at M2 |
|---|---|---|
| 6, capability set | `allowed-tools` frontmatter, a machine-readable list | Yes |
| 8, exit-code contract | A documented `## Exit Codes` table, with the enforcement precedent in `.claude/rules/claude-agents.md` MUST 7 and `scripts/validation/check_skill_contract_tests.py` (`repo-observed`) | Yes |
| 1, 2, 3, 4, 5, 7 | Prose. No extractor exists and none is scoped in M1 through M6 | No. Advisory until a representation is named |

Naming an extractor for the prose invariants is out of scope for this record and is not smuggled
into a follow-up as though it were scoped. Until one exists, items 1 to 5 and 7 bind authors and
reviewers, not gates.

**Invariant 6 is unverified on the trunk today.** `.claude/skills/push-pr/SKILL.md:6` declares
`allowed-tools` with argument-scoped entries including `Bash(git push:*)` and
`Edit(.agents/scratch/pr-body-*.md)`, and `src/copilot-cli/skills/push-pr/SKILL.md:6` carries the
identical line; `translate_allowed_tools` respells `mcp__*` names only and passes argument-scoped
entries through untouched (`repo-observed`). The skill's own body names the argument scoping as
what makes it safe to auto-approve (`repo-observed`). Whether Copilot honors, ignores, or widens
that scoping is `hypothesis`: ADR-085 Finding 1 records no committed permission surface on that
harness, and no probe of the projected grant has been run. Either way the invariant is unverified
rather than preserved, and no gate reads it. Issue #5691 owns settling it, and the class carries
`none` until it is settled.

### 6. Capability profiles are dated evidence, not a matrix

- One owner: `.claude/skills/agent-harness-reference/references/`. No second capability registry.
  Issue #5396 owns the machine-readable capability ownership and dependency mechanism; this record
  consumes whatever #5396 lands and does not invent a parallel one.
- Every capability row carries grade, source, date, and harness version, using the existing
  vocabulary (`OFFICIAL`, `CODE`, `EMPIRICAL`, `DOCS SILENT`).
- Runtime claims use the #5423 lattice as landed in `scripts/eval/_harness_capability.py:52-73`:
  statuses `VERIFIED`, `UNSUPPORTED`, `UNVERIFIED`; evidence kinds `BACKEND`, `CLIENT_ECHO`,
  `CONFIG`, `NONE`; `VERIFIED` reachable only from `BACKEND`. `CONFIG` is a static registry value
  and never supports `VERIFIED`, which is the case this record's no-second-registry rule turns on.
- **Unknown is fail-closed, and the branch is named.** An unknown capability is not an invitation
  to pick the permissive reading. Concretely: the affected class carries `none`, the projection
  for that harness is refused by adding the artifact to that stanza's `excludeFilenames` rather
  than shipped unverified, and M2 ships a negative-control fixture that fails if the artifact
  ships anyway. "Byte-identical text, therefore the invariant is preserved" is the permissive
  branch wearing the compliant label, and section 5's invariant-6 case is that argument already in
  the tree.
- No harness-by-model matrix. Profiles are indexed by harness. A model row is admitted only
  through the exception process below.
- Vendor and model marketing claims enter as `hypothesis`. They are never promoted to fact without
  a `runtime-verified` observation carrying a version.

### 7. Model tactics are advisory and bounded

A model tactic MAY affect: wording, decomposition of a step into sub-steps that preserve order,
context budget, presentation format, and structured-output hints.

A model tactic MUST NOT affect: required steps, their order, authorization, approval gates, tool
arguments, provenance handling, verification, user intent, or failure semantics.

`.claude/rules/claude-model-patches.md` is the only such overlay today, and its own Precedence
section already subordinates it to skill workflows, STOP points, and gates (`repo-observed`). New
overlays named after a model family or release are refused unless they carry ADR-080-shaped
evidence: a measured, reproduced capability difference, a named owner, and an expiry recorded as
`review-by`.

### 8. What this record rejects

**R1. Universal lowest-common-denominator prose as the long-term source.** One bland text every
harness can run erases differences that are real and measured. ADR-085 records that Copilot has no
committed permission surface while Claude does, so a single prose contract would either assume the
weaker surface everywhere or lie about the stronger one. It is also unfalsifiable, which fails D1:
prose that says nothing specific cannot be checked.

**R2. A hand-maintained model-by-harness overlay mesh.** It scales multiplicatively and decays
silently. The evidence is already in the tree: five agent surfaces, three hand-maintained, no
body-level comparator between them, and a lexical floor standing in for meaning. A model dimension
would multiply a surface that already cannot be kept fresh.

**R3. A second registry, routing authority, or generation system.** `GENERATOR-FILES.md` is the
register; `templates/platforms/copilot-cli.yaml` plus the generators own the transform. Extend
them. The cost of ignoring this is visible: `src/copilot-target-emitter.ts`, `src/types.ts`,
`src/agent-registry-schema.ts`, `src/transforms/command-syntax-translator.ts`, and their tests at
`tests/copilot-target-emitter.test.ts` and `tests/command-syntax-translator.test.ts` were added by
PR #1645 and are orphaned. There is no root `package.json`, `tsconfig.json`, or `bunfig.toml`; the
live CLI is `packages/ai-agents-cli/`, and `.github/workflows/cli-smoke.yml:156` sets
`working-directory: packages/ai-agents-cli` before `bun test` at `:179` (`repo-observed`). Those
files carry passing-looking tests that nothing runs.

## Prior Art Investigation

### What currently exists

- **Structure being extended**: the generator pipeline registered by
  `.agents/governance/GENERATOR-FILES.md` and configured by
  `templates/platforms/copilot-cli.yaml`, orchestrated by `build/scripts/build_all.py`.
- **When introduced**: REQ-003 series. The `.claude/` no-write invariant is REQ-003-010; the
  staleness question is REQ-003-005.
- **Original author and context**: attributable to the repository owner (`rjmurillo`), the sole
  `decision-makers` entry on every ADR in this lineage, including ADR-036 and ADR-052
  (`repo-observed`). No second author is recorded on any of them.
- **Why it was built this way**: agents drifted across platform trees faster than humans could
  reconcile them, so generation replaced manual replication for the trees a generator could own.

### Historical rationale

The two-source agent architecture (ADR-036) exists because Claude prompts need harness-specific
depth that a platform-neutral template does not model, while three fully independent sources would
drift. ADR-036 is `superseded` by ADR-052 but its procedure remains operative, because ADR-052 is
`accepted` with `implemented: false` and `templates/agents/` still exists (`repo-observed`). Cite
ADR-036 as "superseded, procedure still operative", never as "accepted".

ADR-052 chose Claude-first: Claude agents become canonical and platform outputs derive from them.
Its own text records the correction that the template layer does deliver the synchronization it
claims for its stated purpose, and that the rejection rests on maintenance cost rather than on a
synchronization failure (`repo-observed`).

### Why change now

The original problem has not changed; it has been narrowed. Generation solved replication for the
trees it owns. It did not define equivalence, so every gate covering a tree a generator does not
own had to invent a proxy. The three proxies in use, co-change, lexical similarity, and byte
equality after regeneration, each fail on a different class of change, and none fails on a
contradiction.

Risk of the change: low by construction. This record moves no generator and no default. The
scaffolding it ships asserts that the gates it names exist and that every conformance class either
names one or is marked missing.

## Rationale

### Alternatives considered

Scored against drivers D1 to D5.

| Alternative | D1 falsifiable | D2 single mechanism | D3 debt visible | D4 blast radius | D5 cost | Verdict |
|---|---|---|---|---|---|---|
| **Declare the predicate in `GENERATOR-FILES.md`, one row per class (selected)** | Yes, per class | Yes, extends the existing register | Yes, `none` rows are countable and ratcheted | One file plus a checker | Low: a Markdown table and a parser | **Chosen.** The only surface reaching both generated and hand-maintained trees |
| Declare it in `templates/platforms/*.yaml` (first revision) | Yes for five classes | Yes | **No.** Cannot express the three hand-maintained trees; emits zero `none` rows | One file plus a schema change | Medium: `validate_templates_schema.py:151` rejects unknown keys | Rejected on D3. The classes needing `none` have no stanza |
| One universal prose contract, no per-harness projection | **No** | Yes | No | Large | Low | Rejected as R1 |
| Model-by-harness overlay mesh | Partly | **No** | No | Large | High | Rejected as R2 |
| A capability registry owned by this record | Yes | **No** | Yes | Medium | High | Rejected as R3. Issue #5396 owns that mechanism; issue #5391's scope correction forbids a second one |
| Promote every tree to generated, delete the hand-maintained ones | Yes, one predicate everywhere | Yes | Yes | **Large** | High | Deferred. REQ-003-010 forbids generators writing under `.claude/`, and ADR-052's migration is accepted but unimplemented and pending a six-surface re-scope (#5282). Named as M3, not decided here |

### Trade-offs

Declaring `none` a legal value admits debt into the contract on purpose. The alternative is a
fabricated predicate for the hand-maintained trees, which produces a green gate over an unchecked
property. A visible `none` with an issue number and an expiry is worth more than a green light
that means nothing. The expiry and the count ratchet are what keep it from becoming permanent.

Putting the predicate in a Markdown governance table rather than a YAML config trades machine
ergonomics for coverage. A parser over a Markdown table is more fragile than a YAML load. It is
the only surface holding every class, and D3 outranks D5.

## Consequences

### Positive

- Every artifact class gets a stated answer to "what does equivalent mean here", the question
  every current gate answers by proxy.
- Debt becomes countable and expiring. A `none` predicate carries an issue and a date, and the
  ratchet stops the count from rising.
- Capability claims stop being interchangeable with capability marketing, because the grade, the
  evidence kind, and the date travel with the row.
- A new skill proves conformance mechanically: its class has a predicate, and its projection
  satisfies it.
- The unverified invariant-6 case in `push-pr` gets an owner instead of staying invisible.

### Negative

- One more field to keep honest. A stale predicate is worse than none, because it claims a check
  that is not running. The expiry and the ratchet are the mitigation, and they are M1 work, not M0
  work.
- Six of the eight invariants have no extractor and stay advisory. A reader taking section 5 as
  enforced will overestimate coverage; the table in section 5 exists to stop that.
- The normalization contract for hand-maintained agent trees is real work this record defers.
- `GENERATOR-FILES.md` has six generator rows against seven `GENERATORS` entries. M1 must
  reconcile that before it can declare a predicate per class.

### Neutral

- No generator behavior changes on merge.
- No routing default changes.

## Impact on Dependent Components

### Dependent artifact classes

Skills, rules, agents across five surfaces (`templates/agents/`, `src/claude/`, `.claude/agents/`,
`.github/agents/`, and the two generated platform trees), hooks and the Copilot dispatcher, the
shared Python lib mirror, PR-quality CI prompts, the agent catalog, the ADR index, plugin
manifests, and both instruction mirrors.

| Component | Dependency type | Required update | Risk |
|---|---|---|---|
| `.agents/governance/GENERATOR-FILES.md` | Direct | Reconcile to the full `GENERATORS` set, then add the predicate column with `none` baselines carrying issue and expiry (M1) | Medium |
| `templates/platforms/copilot-cli.yaml` | Direct | Fix or delete the dead `artifacts.agents.sourceDir` before any further field joins that stanza (M1) | Low |
| `build/scripts/validate_templates_schema.py` | Indirect | Unchanged under the selected alternative; touched only if a later slice moves the field into the YAML | Low |
| `scripts/validation/check_generated_staleness.py` | Indirect | No change. Already enforces sync-then-build order | Low |
| `build/scripts/validate_install_parity.py` | Indirect | Unchanged until M3 supplies a predicate for the hand-maintained pairs | Low |
| `build/scripts/detect_agent_drift.py` | Indirect | Its lexical floor stops standing in for equivalence once M3 lands | Medium |
| `build/scripts/copilot_body_translation.py` | Direct | The undeclared transform. M1 either declares its remap table or records the class as transform-undeclared | Medium |
| `.claude/rules/templates.md`, `claude-agents.md`, `generated-artifacts.md` | Direct | Cite the predicate as the equivalence authority once M1 lands | Low |
| `.claude/skills/agent-harness-reference/` | Direct | Becomes the named capability-profile owner; refresh rules unchanged | Low |
| Every new skill | Direct | Must belong to a class with a declared predicate | Low |

## Implementation Notes

### Conformance checks

Six classes. Five name a gate that exists. One is open work.

| Class | Gate | State |
|---|---|---|
| C1 source digest and staleness | `scripts/validation/check_generated_staleness.py`, which runs `scripts/sync_plugin_lib.py` then `build/scripts/build_all.py` in that order, each under `--check` | Exists |
| C2 projection snapshot | `build/scripts/build_all.py` under `--check`, plus the generator tests under `tests/build_scripts/` | Exists |
| C3 invariant preservation | Asserts invariants 6 and 8 survive the transform | **Missing.** M2 |
| C4 generated drift | `build/scripts/validate_install_parity.py`, `build/scripts/check_agent_content_parity.py`, `build/scripts/detect_agent_drift.py` | Exists; the third is advisory |
| C5 capability-profile provenance | `scripts/eval/_harness_capability.py` fail-closed contract, plus the refresh rules in `.claude/skills/agent-harness-reference/SKILL.md` | Exists |
| C6 negative controls | `.claude/rules/generated-artifacts.md` MUST 2, requiring a runtime-contract test with a negative control and a gate over the committed artifact | Exists as policy; per-class fixtures are M2 |

This record ships one artifact: `tests/validation/test_adr107_conformance_gates.py`. It parses the
table above, asserts the class-id set is exactly C1 through C6, and asserts every row either cites
a repository path that resolves or carries an explicit missing marker. Its negative controls
exercise the row predicate itself, including a row citing a fabricated path and a row citing
nothing at all.

**What it does not do.** It cannot fail because a projection dropped an invariant, because a class
carries a fabricated predicate, or because a gate was hollowed to `return 0`. It binds citations,
not behavior. That limit is why the Status section says this record enforces nothing until M1.

### Pilot

Two skills, because one cannot exercise the invariants that matter:

- **`push-pr`, for invariant 6.** Source `.claude/skills/push-pr/SKILL.md`, projection
  `src/copilot-cli/skills/push-pr/SKILL.md`. This is where the invariant is measurably unverified
  today, and it is the only pilot input that can fail.
- **`security-scan`, for invariant 8.** It documents exit codes 0, 1, and 10 in its
  `## Exit Codes` table, so the contract is already testable through
  `scripts/validation/check_skill_contract_tests.py`.

Transform under test: `build/scripts/copilot_body_translation.py`, which rewrites `@file`
includes, `$ARGUMENTS`, `Skill(...)` and `Task(...)` call syntax, and respells `mcp__*`
identifiers in `allowed-tools` (`repo-observed`).

**What the pilot cannot falsify.** That transform rewrites syntax and respells identifiers. It
cannot reorder steps, delete a completion criterion, or change an exit code, so invariants 1 to 5
and 7 survive it by construction. A pilot reporting them green would be measuring nothing. The
suite therefore asserts invariants 6 and 8 only, with one negative-control fixture each, and the
prose invariants wait for M3, where hand-maintained pairs can actually diverge.

### Migration order

No flag day. Each step is a separate pull request with its own issue.

| Step | Issue | Work | Gate it closes |
|---|---|---|---|
| M0 | #5603 | This record plus the conformance-class test | None; establishes the contract |
| M1 | #5686 | Reconcile `GENERATOR-FILES.md` to the full `GENERATORS` set; add the predicate column; baseline every `none` with an issue and an expiry; install the `none` count ratchet; fix or delete the dead `artifacts.agents.sourceDir` | Makes the predicate readable by tooling and the debt countable |
| M2 | #5687 | Invariant 6 and 8 checks plus negative controls for the `derived` classes; run the two-skill pilot | C3, C6 |
| M3 | #5688 | Normalization contract and predicate for the hand-maintained agent trees | The template-versus-`src/claude` gap and the `.github/agents/` content gap |
| M4 | #5689 | Portability scan over shipped agent **outputs** | The agent-output coverage gap |
| M5 | #5690 | Retire the orphaned root TypeScript emission pipeline | Removes a second generation authority |
| M6 | #5691 | Settle the invariant-6 status of argument-scoped `allowed-tools` under Copilot | The section 5 case |

M4's scope is narrower than the first revision claimed. Issue #3465 is **closed as completed**,
and `scripts/validation/check_skill_md_portability.py:315-318` puts `templates/agents` in
`EXTRA_SCAN_ROOTS`, so canonical agent prose is scanned (`repo-observed`). What remains uncovered
is agent outputs, stated verbatim at `:52`: "this validator does not scan agent outputs, so the
template source is the only covered surface". M4 covers `src/claude/*.md`,
`src/copilot-cli/agents/`, and `.github/agents/`.

M1, M4, M5, and M6 are independent of each other. M2 depends on M1 declaring `derived` for rules
and skills. M3's code is independent; only its bookkeeping, retiring a `none`, depends on M1, and
its sequencing is entangled with #5282, which M3's issue records as a blocker.

### Deprecation rules

- An artifact class MUST NOT move from a declared predicate back to `none`.
- Removing a projection target requires an ADR (`.claude/rules/templates.md` MUST NOT 2).
- Weakening a predicate from `derived` to `normalized` requires the normalization contract in the
  same change, naming exactly which keys and sections it excuses.
- A `none` row whose expiry passes without a predicate is a finding, not a renewal.

### Adapter exception process

A per-harness or per-model adapter is admitted only when all eight hold. Missing any one is a
refusal, not a discussion.

1. A reproducible failure, with the command and the observed output.
2. Independent fixtures, or a capability cell already recorded as supported. **A cell authored in
   the same change does not satisfy this condition**, for the reason section 3 gives: policy
   arriving inside the change under review is external content for that change.
3. The harness cause ruled out, so the adapter is not covering a projection bug.
4. A measurable benefit, stated as a number.
5. A named owner.
6. An expiry, recorded as `review-by`.
7. A rollback step returning the class to its declared predicate.
8. **The adapter does not alter invariant 5 or invariant 6.** Approval gates and the abstract
   capability set are the floor. No count of satisfied process conditions buys a change to either;
   an adapter needing one is a permission change and belongs to the host, not to the tree.

The exception is recorded in the capability profile, never inside the skill. A skill carrying its
own adapter has become its own registry, which is R3.

### Rejection and rollback criteria

This record moves to `rejected` if either holds:

- **M1 cannot declare a predicate for a majority of the classes in "Dependent artifact classes"
  without fabricating one.** The criterion is over that list, not over the stanzas in a config
  file. The first revision scoped it to YAML stanzas, where every class already has a working
  gate, which made it unfalsifiable.
- **M2 finds invariants 6 and 8 hold trivially for every class, and no class exists where a
  projection can drop them.** That would show the invariant set is not load-bearing, and section 5
  would be demoted to advisory rather than kept as a MUST list nothing can violate.

Rollback is a revert of this file and its test. Nothing else moves, because M0 changes no
generator, no config, and no default.

### Flagged during the investigation

Findings outside this record's scope, reported rather than fixed.

- **A correction to this record's own first revision.** It reported that
  `.claude/skills/ai-agents-architecture-contract/SKILL.md` cites the `build_all.py` `GENERATORS`
  list "at line 435", tagged `repo-observed`. That string is not in the file at HEAD. Commit
  `72f0e6309` (PR #5640, merged 2026-09-08) removed it, and the reading that produced the claim
  came from a stale copy under `build/audit/pytest-4870/`, which is pytest fixture output rather
  than a source tree. The current file cites the list with no line number and correctly says seven
  generators. The generalizable lesson: a path under `build/audit/` is a captured artifact, and
  reading one instead of the canonical tree produces a citation that is checkable, wrong, and
  confidently labeled.
- **`.claude/rules/plugin-self-containment.md` cites issue #3465 as a live gap tracker.** #3465 is
  closed as completed, and `templates/agents` is now scanned (`repo-observed`). That rule's "Known
  coverage gap" section needs re-scoping to agent outputs. Not fixed here; it is a rule file with
  its own review requirements.
- **`scripts/validation/check_model_pins.py` runs `--mode warn` locally through
  `pre_pr_sequence.py` and `--mode enforce` only in CI** (`repo-observed`), so a new pin gets no
  local block.
- **`.agents/governance/GENERATOR-FILES.md` indexes six generators; `GENERATORS` has seven.**
  `agent-catalog` and `adr-index` have no index row, and `generate_pr_quality_prompts.py` has a row
  but no `GENERATORS` entry. M1 must reconcile this.

## Related Decisions

- ADR-101 (enforcement planes, `proposed`, `implemented: false`): corroborates, does not
  authorize, the P0-advisory reading in section 2.
- ADR-105 (terminal-state completion contract): source of the precedence chain this record
  extends.
- ADR-085 (cross-harness permission surface asymmetry, `accepted`): evidence that harness
  differences are real, which is why R1 is rejected and why the permission rung is
  harness-conditional.
- ADR-094 (govern Copilot CLI compatibility through executable surfaces, `accepted`): executable
  configuration is the version record; ADR prose must not freeze versions or counts.
- ADR-080 (model pin justification policy): owns `model:` on any authored artifact. Source of the
  evidence, owner, and expiry shape used by the adapter exception process.
- ADR-052 (template strategy, `accepted`, `implemented: false`): the governing target for agent
  canonicalization. Do not assume it has landed.
- ADR-036 (two-source agent templates, superseded by ADR-052, procedure still operative).
- ADR-064 (commands to skills migration, `implemented: true` 2026-09-08): skills are the single
  user-invocable surface.
- ADR-092 (omit plugin manifest version), ADR-097 (zero tool-use hooks, `implemented: false`),
  ADR-045 (marketplace extraction): constrain the projection surfaces this record governs.
- ADR-072 (JTBD plugin architecture, `proposed`): **not** a dependency. Issue #5669 tracks settling
  it.
- ADR-069 (context corpus is the product, `proposed`): thesis only.

## References

Issue states below were read with `gh issue view` on 2026-09-09 (`repo-observed`).

- Issue #5603 (open), this record's tracker.
- Issues #5686, #5687, #5688, #5689, #5690, #5691 (all open), the implementation slices M1 through
  M6. They are opened by this record and close no part of it on merge.
- Issue #5391 (open), authoritative placement contract. Owns the rule-skill-agent-memory placement
  taxonomy; its scope correction forbids a second capability registry.
- Issue #5396 (open), capability ownership and dependency graph. Owns the machine-readable
  capability metadata mechanism this record consumes rather than duplicates.
- Issue #1774 (closed, not planned, 2026-06-19), per-harness emission. Successor #5669.
- Issue #5282 (open), Claude-first template migration. ADR-052 Phases 1 to 3.
- Issue #5423 (open), harness capability evidence. The fail-closed lattice landed in
  `scripts/eval/_harness_capability.py`; the issue did not close.
- Issue #5424 (open), matched harness benchmark contracts. Blocked by #5423.
- Issue #2840, evidence-backed model pins. Satisfied in part by ADR-080.
- Issue #5079 and PR #5059, the measured cost of a late signal on a hand edit to a generated skill.
- Issue #3465 (closed, completed, 2026-07-28), markdown portability ratchet coverage. Cited here
  only to correct the first revision, which treated it as open.
- `.agents/governance/GENERATOR-FILES.md`, the generator register.
- `.claude/rules/generated-artifacts.md`, `.claude/rules/canonical-source-mirror.md`,
  `.claude/rules/templates.md`, `.claude/rules/claude-agents.md`,
  `.claude/rules/plugin-self-containment.md`.
