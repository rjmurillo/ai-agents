---
id: ADR-108
status: proposed
date: 2026-09-11
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-03-11
---

# ADR-108: Template-Owned Skill Files Under `.claude/skills/`

## Status

Proposed. This record amends ADR-107 settled property 1, REQ-003-010, and REQ-003 decision D4 for exactly one artifact class: canonical skill files rendered from `templates/skills/`. The repository owner selected this path on 2026-09-11 over an in-file excerpt design that needed no amendment; that alternative is recorded in `.agents/specs/design/DESIGN-023-skill-guidance-excerpt-sync.md` and in the Alternatives table below. It enforces nothing until the first implementation slice lands; the amendment is policy text plus one allowlist argument on an existing guard.

## Evidence labels

Same vocabulary as ADR-107. `repo-observed`: read from the tree at `cd0f9561d` on 2026-09-11. `docs-say`: a document or an upstream source states it. `hypothesis`: reasoned, not measured. A `hypothesis` is never load-bearing for a MUST.

## Context

Issue #5706, a sub-issue of epic #5698, asks for `SKILL.md` to be compiled from mustache templates so rule guidance can be bundled into the skill that needs it, at the step that needs it, from one source. The epic names the outcome: "Skill guidance is compiled into SKILL.md from templates so the always-on rule set can shrink without losing ordering" (`docs-say`, issue #5698).

Eight canonical skill files carry the line `@CLAUDE.md` today: `sync`, `test`, `spec`, `ship`, `research`, `plan`, `checkpoint`, `build` (`repo-observed`, `grep -n '^@CLAUDE.md$' .claude/skills/*/SKILL.md`). Copilot CLI 1.0.66-1 treats that line as literal text; `build/scripts/copilot_body_translation.py:14` records the probe and the include-line transform at `:140` rewrites it into an HTML comment for the mirror (`repo-observed`). No templating step for skills exists anywhere under `build/` (`repo-observed`: `templates/` holds `agents/`, `platforms/`, `toolsets.yaml`, and three guide files, none of them a skill template).

The design in issue #5706 renders `templates/skills/<name>.SKILL.md.tmpl` into `.claude/skills/<name>/SKILL.md` from inside `build/scripts/generate_skills.py`, wired through `build_all.py`. Four constraints block that on the current tree, and the issue's own step 1 says what to do when they do: "stop and route an ADR amendment through the repository review process; do not create a second ADR or implement around the conflict" (`docs-say`, issue #5706).

| Constraint | Where | What it says |
|---|---|---|
| REQ-003-010 | `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:358-359` | "The build shall never write to `.claude/<artifact>/` or `.claude/settings.json`." (`docs-say`) |
| The guard | `build/scripts/build_all.py:793` `assert_no_claude_writes`, called at `:2226`; a violation sets `overall_exit = 2` | A before-and-after content diff of the `.claude/` tree. A render that differs from the committed file is reported as `REQ-003-010 VIOLATION` (`repo-observed`). Introduced with REQ-003 in commit `c00a32e5f` (2026-04-30), hardened in issues #2613, #3773, #4632, #5464 (`repo-observed`, docstring) |
| ADR-107 property 1 | `ADR-107-canonical-skill-contracts-and-harness-projections.md:61` | "Generators read canonical trees and write mirror trees. They never write under `.claude/`." Listed as settled and not reopened (`docs-say`) |
| REQ-003 decision D4 | `REQ-003-multi-tool-artifact-build.md:80` | "`.claude/<artifact>/` is canonical" (`docs-say`) |
| Epic correction | issue #5698, "Review corrections" | "#5706 must not create a second ADR-107 or a generator that writes over canonical `.claude/` content" (`docs-say`) |

Two designs deliver the outcome. One keeps the canonical file hand-maintained and pins marked spans to excerpt files with a validator; it needs no amendment. The other makes the template canonical and renders the file; it needs this record. The owner chose the second on 2026-09-11 (decision D1, recorded in `.agents/plans/active/5706-skill-guidance-excerpts.md`).

## Decision Drivers

- D1: the owner's stated outcome, guidance authored once and bundled at the step it governs, with the always-on set free to shrink afterwards (issue #5698).
- D2: one generation authority. ADR-107 R3 forbids a second registry or generator; the class must live inside `generate_skills.py` and the existing register.
- D3: fail-closed on every path the class does not enumerate. REQ-003-010 keeps its teeth for all other `.claude/` writes.
- D4: drift is a gate, not prose. A hand edit to a derived file must fail before merge.
- D5: bounded dependency surface. Whatever renders the template must be swappable without touching templates.

## Decision

Adopt one new artifact class and amend the three texts that forbid it: REQ-003-010, REQ-003 decision D4, and ADR-107 property 1.

### 1. The class: template-owned skill file

| Field (ADR-107 section 4) | Value |
|---|---|
| Canonical source | `templates/skills/<name>.SKILL.md.tmpl` plus the partials it names under `templates/skills/partials/<slug>.mustache`. `<name>` MUST match `^[a-z0-9]+(-[a-z0-9]+)*$` and MUST name an existing `.claude/skills/<name>/` directory that is not a symlink and whose resolved path lies inside the resolved `.claude/skills/` root; a template failing any of those checks is a configuration error, exit 2, so no malformed name and no redirected path reaches the allowlist |
| Declarative transform | Mustache partial expansion with a restricted grammar: a template may contain `{{> slug}}` partial tags and `{{! comment}}` tags and nothing else. Any other tag (`{{var}}`, `{{#section}}`, `{{^inverted}}`, `{{{raw}}}`, set-delimiter) is a configuration error, exit 2. A partial tag naming a file that does not exist is a configuration error, exit 2. Every partial file MUST end with exactly one trailing newline, and a partial without one is a configuration error, exit 2: `chevron` inserts a partial's bytes verbatim, so a partial with no trailing newline joins the line after the tag into the excerpt's last line, and the corrupted render contains no `{{` for the brace scan to catch (`docs-say`, probe on 2026-09-11 with `chevron==0.14.0`). Rendered output containing the literal `{{` is a logic error, exit 1. The engine is `chevron` 0.14.0 (pure Python, MIT, zero runtime dependencies, released 2021-01-02, `docs-say`, PyPI). A1 pins it as a dev dependency in both dev tables of `pyproject.toml`; it is not in the tree at `cd0f9561d` |
| Output | `.claude/skills/<name>/SKILL.md`, which Claude Code loads unchanged and which the existing `generate_skills.py` directory copy mirrors into `src/copilot-cli/skills/<name>/` through the existing body translation (`copilot_body_translation.py:311-322` rewrites `allowed-tools` and the body), which this record leaves unchanged |
| Equivalence predicate | `derived`: regenerate, then byte-compare. `generate_skills.py --validate` and `build_all.py --check` both apply it |

A skill joins the class by the presence of `templates/skills/<name>.SKILL.md.tmpl` and leaves it by that file's deletion, after which its `SKILL.md` is hand-maintained again with no other step. Membership is read from the directory at run time. Two controls bound widening. `tests/build_scripts/test_skill_templates_pilot_scope.py` asserts that `discover()` returns exactly the names in its `PILOT` constant (empty until A2, the eight pilots after A2), so a ninth `.tmpl` cannot land without an edit to that file in the same diff, which makes the widening visible to review rather than implicit. `.github/CODEOWNERS` lists `/templates/skills/` and that test file under `@rjmurillo` (added by A0), so GitHub requests the owner's review on both. Neither is a hard gate unless the branch ruleset requires code-owner review; this record does not claim it does. The run-time allowlist alone is not the control.

### 2. REQ-003-010, amended

The requirement text at `REQ-003-multi-tool-artifact-build.md:359` is amended in place by this record's change set and now reads: "The build shall never write to `.claude/<artifact>/` or `.claude/settings.json`, except the template-owned skill files whose template exists under `templates/skills/<name>.SKILL.md.tmpl` at run time (ADR-108). All other generation targets `src/copilot-cli/` or `.github/instructions/`." A note beneath it records the amendment date; the note is provenance, not a second statement of the rule.

Mechanism: `assert_no_claude_writes` gains an `allowed_paths` argument holding exactly the set `{.claude/skills/<name>/SKILL.md for each templates/skills/<name>.SKILL.md.tmpl}`, computed by the compile module and passed by `build_all.py`. Every other write under `.claude/` is still reported as `REQ-003-010 VIOLATION` and still exits 2. The compile step runs after the baseline snapshot, inside the guarded window, so a compile bug that writes anywhere else is caught. Running it before the snapshot, where the guard could not see it, is rejected below.

The verification sentence at `:361` is amended in the same change set: `git diff` after `build_all.py` shows changes only under `src/copilot-cli/`, `.github/instructions/`, and template-owned `.claude/skills/<name>/SKILL.md` files.

REQ-003 decision D4 (`:80`) is amended in the same change set with the same exception clause: `.claude/<artifact>/` is canonical except template-owned skill files, whose canonical source is the template.

### 3. ADR-107 property 1, amended

Property 1 at `ADR-107-...md:61-62` is amended in place by this record's change set and reads: "Generators read canonical trees and write mirror trees. They never write under `.claude/`, except the template-owned skill files ADR-108 enumerates (amended 2026-09-11)." Its stale line anchors for the guard (`:788`, `:2221`, `:2227`) are re-anchored to `:793`, `:2226`, `:2232` in the same edit. Property 2 (the seam is asymmetric) is unchanged. ADR-107's Related Decisions gains one bullet naming this record. In ADR-107's layer table, the semantic contract of a template-owned skill lives in its template, and the rendered file is a projection for Claude Code that is also the source the Copilot mirror is derived from. ADR-107's provenance rule is unchanged: loading the rendered file promotes nothing.

### 4. Drift is a gate, not a header

A hand edit to a template-owned `SKILL.md` is drift. `generate_skills.py --validate` renders every template and exits 1 naming each file that differs from the committed one; `build_all.py --check` reports the same as staleness; `scripts/validation/pre_pr_sequence.py` carries a `Skill Template Drift` gate that runs the validate command. No generated-file banner is added to the rendered file (`.claude/rules/universal.md` MUST NOT 5). A rendered file carrying a NO-REGEN sentinel recognized by `build/scripts/regen_guard.py:detect_reason`, in any of the three forms it recognizes (the in-file `<!-- NO-REGEN` token or a line starting `# NO-REGEN`, both within the first 4 KiB, or the `.noregen` sidecar), is never rewritten: the write path skips it, as `_copy_skill_tree` does at `generate_skills.py:105-109` (`repo-observed`). The severity and exit code differ from that copy path, because for this class the sentinel exempts a file from its only gate. The skip is reported at WARN, elevated from the NOTICE the copy path prints, and it makes the compile exit 1 in both its modes, the write path and `--validate`; `build_all.py` reports that as its own nonzero exit (2, its staleness and configuration code) in a normal run and under `--check`, and therefore the pre-PR gate and CI go red. A template-owned file with a sentinel is a contradiction the author resolves by deleting the template (the file leaves the class and is hand-maintained again) or by removing the sentinel. The A2 byte report names every such file (none expected). This diverges from issue #5706's step 10 edge case, which asks for the copy path's silent skip; the divergence is recorded here and in the A1 pull request.

### 5. Partials stay pinned to the rule they excerpt

A partial whose first line is `{{! rule-source: <file>.md }}` MUST appear verbatim and contiguously in `.claude/rules/<file>.md`; a test under `tests/build_scripts/` enforces it. The rule file remains authoritative and unchanged by this record; the partial is an excerpt for bundling. A partial with no `rule-source` line is standalone, which is the shape a partial takes once a later issue cuts the rule text.

### 6. Precedence

Template over rendered file; rendered file over Copilot mirror. This is one more rung inside ADR-107's `canonical semantic contract > harness projection` step, not a change to that chain.

### 7. Scope

The eight skills carrying `@CLAUDE.md` are the pilot. Converting any other skill, cutting any rule file, or narrowing any `paths: ["**"]` scope is out of scope and waits on the owner's word after the pilot's before-and-after bytes are reported.

## Prior Art Investigation

### What currently exists

- **Structure being changed**: the `.claude/` no-write invariant, REQ-003-010, enforced by `assert_no_claude_writes` in `build/scripts/build_all.py` (`repo-observed`).
- **When introduced**: commit `c00a32e5f`, 2026-04-30, PR #1819, with the REQ-003 series (`repo-observed`).
- **Original author and context**: `rjmurillo`, sole `decision-makers` entry across the lineage (`repo-observed`, ADR-036, ADR-052, ADR-107 frontmatter).

### Historical rationale

- **Why it was built this way**: "Customers editing `.claude/` directly shall not have their changes overwritten" (`docs-say`, REQ-003-010). The generators exist because agents drifted across platform trees faster than humans reconciled them, so generation replaced replication for the trees a generator could own (`docs-say`, ADR-107 Prior Art).
- **What alternatives were considered**: ADR-107's alternatives table records "Promote every tree to generated, delete the hand-maintained ones" as deferred because REQ-003-010 forbids it and ADR-052 is unimplemented (`docs-say`, ADR-107 Rationale).
- **What constraints drove it**: the 2025-12-15 incident, where an agent "fixed" a drift failure by editing the canonical source to match the generated output and the commit was reverted (`docs-say`, `.claude/skills/ai-agents-change-control/SKILL.md`). A one-direction rule was the cheapest defense against source-of-truth inversion.

### Why change now

- **Has the original problem changed?** No. Inversion is still the risk, which is why section 4 gates drift and section 2 keeps the guard on every non-enumerated path.
- **Is there a better solution now?** The owner wants guidance authored once and bundled at the step that needs it. That needs a template layer skills do not have. The no-amendment alternative exists (DESIGN-023) and the owner declined it on 2026-09-11.
- **Risks of change**: eight files whose canonical location moves from `.claude/skills/<name>/SKILL.md` to `templates/skills/<name>.SKILL.md.tmpl`; a contributor who edits the rendered file loses the edit at the next build. Mitigations: the drift gate at pre-PR and CI, the NO-REGEN sentinel, and the `GENERATOR-FILES.md` row that names the source.

## Rationale

### Alternatives considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| Excerpt blocks in the hand-maintained file, pinned by a validator (DESIGN-023, declined alternative) | No amendment, no dependency, canonical file stays hand-edited | The canonical file stays under `.claude/` and the excerpt files are secondary, so a whole-skill migration to templates would need a second design later; a `--fix` mode writes spans into a canonical file | Owner decision D1, 2026-09-11: the canonical file moves out of `.claude/` into a template, matching issue #5706 and the path to migrating all 111 skills |
| Compile before the guard's baseline snapshot so the write is invisible | No guard change | Implements around REQ-003-010 rather than amending it; a compile bug writing elsewhere under `.claude/` would also be invisible | Rejected by issue #5706 step 1 and by the guard's own reason for existing |
| Render into a new tree and point Claude Code at it | No `.claude/` write | Claude Code discovers project skills under `.claude/skills/` (`docs-say`, Claude Code documentation); a second tree is a second source | Rejected: ADR-107 R3 forbids a second generation authority |
| Translate `@CLAUDE.md` only, no bundling | Portability fixed today | Does nothing for the epic's outcome; the always-on set cannot shrink | Rejected: solves the smaller of the two problems |
| Full mustache grammar (sections, lambdas, variables) | Future flexibility | Every feature is a way for a template to render differently from what a reader expects; `chevron` renders a missing partial and an unknown variable as empty text silently (`docs-say`: a probe run outside the tree on 2026-09-11 with `chevron==0.14.0`, `render("A{{> nope}}B", {}, partials_dict={})` and `render("A{{x}}B", {})` both return `AB`) | Rejected: partials and comments are the whole need; the grammar is enforced, exit 2 |
| In-tree restricted-grammar expander, no dependency | About 40 lines; no unmaintained dependency; no mypy override or dev-table entry | A second mustache-like syntax to document and test; `chevron` 0.14.0 is 746 lines across five modules (`docs-say`, measured 2026-09-11) implementing sections, lambdas, and set-delimiter, all forbidden by section 1, so the dependency buys standard syntax and nothing else | Not chosen for A1: issue #5706 step 3 names `chevron` and the owner's D1 selection cited it; the restricted grammar makes the swap a bounded change, and REQ-024 defers it |

### Trade-offs

One new dev dependency against writing a partial expander by hand. `chevron` is 0.14.0, pure Python, MIT, no dependencies, 746 lines across five modules, and its last release is 2021-01-02, so it is stable and also unmaintained; this record uses one of its features. The restricted grammar in section 1 keeps the surface small enough that replacing it with an in-tree expander later is a bounded change. Eight files move from hand-maintained to derived, which is the cost the owner accepted for a canonical template layer.

## Consequences

### Positive

- Rule guidance is authored once and rendered into the skill at the step it governs.
- The eight pilot skills lose a Claude-only include that Copilot renders as literal text.
- Drift between template and rendered file fails at pre-PR and at CI.
- Every later skill migrates by adding one `.tmpl` file; nothing else in the pipeline changes.

### Negative

- A contributor who edits `.claude/skills/<pilot>/SKILL.md` directly loses the edit at the next writing build; `--check` and the pre-PR gate catch the edit only when they run before a writing build does.
- `chevron` joins the dev dependency set and both dev tables in `pyproject.toml` must list it (`tests/test_pyproject_dev_deps_parity.py`).
- The rendered pilot files grow by the bundled guidance while the always-on set is unchanged, so the pilot adds bytes until the follow-up cut lands. The pilot PR reports both numbers.

### Neutral

- The Copilot mirror pipeline, `copilot_body_translation.py`, and `templates/platforms/copilot-cli.yaml` are untouched.

## Impact on Dependent Components

| Component | Dependency type | Required update | Risk |
|---|---|---|---|
| `build/scripts/build_all.py` | Direct | `assert_no_claude_writes(..., allowed_paths=...)`; a compile step inside the guarded window; `--check` runs it in validate mode | Medium |
| `build/scripts/generate_skills.py` | Direct | Compile step before `_copy_skill_tree`; `--validate` flag; NO-REGEN honored | Medium |
| `build/scripts/skill_templates.py` (new) | Direct | Discovery, grammar check, render, compare | Medium |
| `pyproject.toml`, `uv.lock` | Direct | `chevron==0.14.0` in `[project.optional-dependencies].dev` and `[dependency-groups].dev` | Low |
| `.agents/governance/GENERATOR-FILES.md` | Direct | New generated-trees row for the class; the hand-maintained paragraph gains the exception | Low |
| `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:358-361` (`The build shall never write`, `Verification:`) | Direct | Exception clause in the requirement sentence and the verification sentence, plus a dated note. | Low |
| `.agents/architecture/ADR-107-canonical-skill-contracts-and-harness-projections.md:61-62` (`They never write under`) and its Related Decisions | Direct | Exception clause in property 1; re-anchored guard line numbers; one Related Decisions bullet. | Low |
| `build/AGENTS.md:8` (`no generator may write under`) | Direct | The no-write sentence gains the exception. | Low |
| `.claude/rules/generated-artifacts.md:196` (`REQ-003-010 forbids generators from writing under`), `.claude/rules/templates.md` | Direct | One sentence each: the exception, and the regeneration command for skill templates | Low |
| `scripts/validation/pre_pr_sequence.py`, `tests/validation/test_pre_pr_sequence_registry.py` | Direct | `Skill Template Drift` gate row and its `EXPECTED_ORDER` entry | Low |
| `tests/test_frontgate_crosslink_1927.py:163` | Indirect | Asserts `@CLAUDE.md` is present in the plan skill; flips to absence when the pilot lands | Low |
| `tests/build_scripts/test_build_all.py` | Indirect | Allowlisted write passes; other `.claude/` writes still exit 2 | Low |
| `tests/build_scripts/test_skill_templates_pilot_scope.py` (new) | Direct | Pins the discovered template set to the pilot names | Low |
| `.github/CODEOWNERS` | Direct | Entries for `/templates/skills/` and the pilot-scope test under `@rjmurillo` | Low |
| `.claude/skills/CLAUDE.md`, `.agents/steering/claude-skills.md`, `.agents/governance/SKILL-CREATION-CRITERIA.md` | Direct | One sentence each: the eight pilot skills are template-owned; edit `templates/skills/<name>.SKILL.md.tmpl`, not `SKILL.md`. The first ships inside the plugin and is what a contributor reads before hand-editing | Low |
| `scripts/validation/check_skill_md_portability.py` | Indirect | Scans `SKILL.md` and reference files in the plugin roots; the rendered pilot files are in scope, the templates and partials are not; A2 runs it and reports no new offender | Low |
| `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:80` (D4) | Direct | Exception clause | Low |

## Implementation Notes

Three pull requests, each with its own review.

| Step | Work | Gate it closes |
|---|---|---|
| A0 | This record, the ADR-107 cross-reference, the REQ-003-010 amendment note, and the spec artifacts | None; establishes the class |
| A1 | Compile module, `generate_skills.py` compile and `--validate`, `build_all.py` allowlist and check mode, dev dependency, tests, `pre_pr` gate, governance rows | `derived` predicate for the class, with negative controls |
| A2 | Eight templates, the partials with `rule-source` pins, the rendered files, the regenerated mirrors, per-skill contract tests, the before-and-after byte report; closes issue #5706 | The pilot |

Conformance: A1 ships positive, negative, and edge tests for the compile (render with partials byte-identical to a fixture; missing partial exit 2; forbidden tag exit 2; skill without a template untouched; NO-REGEN skipped) and for the guard (allowlisted write passes; any other `.claude/` write still exits 2). A2 ships the `rule-source` parity test and a per-pilot test that the rendered and mirrored files carry no `^@CLAUDE\.md$` line and no `{{`.

Rollback: revert A2, then A1, then move this record to `rejected`. A rejection before A1 also reverts the A0 edits: the REQ-003-010 clause, verification sentence, and note, the D4 clause, the ADR-107 property 1 clause and bullet, the two CODEOWNERS entries, and the six spec artifacts under `.agents/specs/` that depend on this record. The plan moves to `.agents/plans/abandoned/`.

## Related Decisions

- ADR-107 (canonical skill contracts, `proposed`, `implemented: false`): amended in property 1 by this record; its predicate vocabulary is consumed unchanged.
- ADR-052 (template strategy, `accepted`, `implemented: false`): governs agent canonicalization. This record does not implement it for agents and does not depend on it; it applies the same shape to eight skills.
- ADR-064 (commands to skills, `implemented: true`): skills are the single user-invocable surface, so the rendered `SKILL.md` is the artifact Claude Code loads.
- ADR-042 (Python migration): the compile module and validator are Python.
- ADR-092 (no plugin manifest version): a template change requires no manifest edit.
- Issue #5686 (ADR-107 M1): owns the predicate column in `GENERATOR-FILES.md`. This class declares `derived` in that register's existing row shape; when M1 lands its column, the row carries the value with no further change. Issue #5687 (M2) runs the two-skill invariant pilot on `push-pr` and `security-scan`; neither is in this pilot, and the eight template-owned skills stay `derived` under the same transform M2 tests. Issues #5688 to #5691 are untouched.

## References

- Issue #5706 and epic #5698, read with `gh issue view` on 2026-09-11.
- `.agents/specs/requirements/REQ-024-skill-guidance-excerpts.md`, `.agents/specs/design/DESIGN-023-skill-guidance-excerpt-sync.md`, `.agents/plans/active/5706-skill-guidance-excerpts.md`.
- `build/scripts/build_all.py:793` and `:2226`; `build/scripts/generate_skills.py:76-124`; `build/scripts/regen_guard.py:52`; `build/scripts/copilot_body_translation.py:14`, `:140`.
- `build/scripts/copilot_body_translation.py:9-14`, the recorded Copilot CLI 1.0.66-1 probe: "`@CLAUDE.md` first line -> treated as LITERAL-TEXT (not auto-inlined)". That docstring names a Serena memory as its source; the memory directory it points at is empty in the tree, so the docstring is the citable source.
- `chevron` on PyPI: version 0.14.0, uploaded 2021-01-02, MIT, no `requires_dist`.
