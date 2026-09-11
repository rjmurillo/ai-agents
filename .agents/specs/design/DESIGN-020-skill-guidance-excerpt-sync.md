---
type: design
id: DESIGN-020
title: Mustache-compiled pilot skills under a template-owned class
status: draft
priority: P1
source: GH-5706
related:
  - REQ-021
  - REQ-003
  - TASK-024
  - TASK-025
  - TASK-026
created: 2026-09-11
updated: 2026-09-11
author: spec
tags:
  - skills
  - generation
  - templates
---

# DESIGN-020: Mustache-compiled pilot skills under a template-owned class

## Decision history

Two designs were drafted on 2026-09-11. The first kept `.claude/skills/<name>/SKILL.md` hand-maintained and pinned HTML-comment-fenced spans to excerpt files with a validator; it needed no policy change. The owner chose the second (decision D1, plan `5706-skill-guidance-excerpts`): the design in issue #5706, templates as canonical, rendered into `.claude/skills/`, which needs ADR-108 to amend ADR-107 property 1 and REQ-003-010. This document describes the chosen design. The declined alternative is kept at the end for the record.

## Why an amendment is required

| Constraint | Where | Effect on the issue's design |
|---|---|---|
| REQ-003-010 | `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:358` | "The build shall never write to `.claude/<artifact>/`" |
| The guard | `build/scripts/build_all.py:793` `assert_no_claude_writes`, called at `:2226`, exit 2 | A before-and-after content diff of `.claude/`: a compile step that writes `.claude/skills/<name>/SKILL.md` exits 2 whenever the render differs from the committed file, which is every regeneration that does work |
| ADR-107 property 1 | `ADR-107-...md:61` | "Generators read canonical trees and write mirror trees. They never write under `.claude/`", listed as settled |
| REQ-003 D4 | `REQ-003-...md:80` | `.claude/<artifact>/` is canonical |
| Epic #5698 correction | issue body | "#5706 must not create ... a generator that writes over canonical `.claude/` content" |

ADR-108 amends the first three for exactly one class and satisfies the fifth by making the class explicit, enumerated at run time, and gated.

## Component architecture

```text
templates/skills/<name>.SKILL.md.tmpl      canonical (new)
templates/skills/partials/<slug>.mustache  canonical excerpt (new); {{! rule-source: x.md }} pins it to .claude/rules/x.md
        | build/scripts/skill_templates.py: discover, grammar-check, render (chevron), compare
        v
.claude/skills/<name>/SKILL.md             derived (template-owned); loaded by Claude Code unchanged
        | build/scripts/generate_skills.py: existing directory copy + copilot_body_translation (unchanged)
        v
src/copilot-cli/skills/<name>/SKILL.md     mirror (unchanged pipeline)

build/scripts/build_all.py                 runs the compile inside the guarded window; passes allowed_paths to assert_no_claude_writes; --check runs validate mode
scripts/validation/pre_pr_sequence.py      _Gate("Skill Template Drift") runs generate_skills.py --validate
```

## Template grammar

A template is the current `SKILL.md` text with two kinds of tag and no others:

- `{{> slug}}` on its own line, optionally indented: expands to the partial `templates/skills/partials/<slug>.mustache`. Chevron preserves the indentation on every line of the partial (verified 2026-09-11 with `chevron==0.14.0`).
- `{{! text }}`: a comment, rendered as nothing.

Any other tag is a configuration error (exit 2) before rendering: `{{var}}`, `{{{raw}}}`, `{{#s}}`, `{{^s}}`, `{{/s}}`, `{{=<% %>=}}`. Reason: chevron renders an unknown variable and a missing partial as empty text with no error (probed 2026-09-11), so the grammar check is the only thing that turns a typo into a failure. Slug pattern `^[a-z0-9]+(-[a-z0-9]+)*$`. Every partial file MUST end with exactly one trailing newline; `check_grammar` (or the partial loader) rejects a partial without one, exit 2, because chevron inserts the partial's bytes verbatim and a missing newline joins the following template line into the excerpt (probed 2026-09-11: `render("Line before.\n{{> p}}\nLine after.\n", {}, partials_dict={"p": "X"})` returns `Line before.\nXLine after.\n`). The rule-source substring check strips exactly that one trailing newline before comparing. The eight pilot `SKILL.md` files contain no `{{` today (`grep -c '{{'` returns 0 for each), so the grammar check has no false positives on the pilot.

A partial's first line MAY be `{{! rule-source: <file>.md }}`. When present, the rest of the file MUST be a verbatim contiguous substring of `.claude/rules/<file>.md`, enforced by `tests/build_scripts/test_skill_partials_rule_parity.py`. The comment renders as nothing, so the rendered skill carries the excerpt and not the pin.

## Compile module: `build/scripts/skill_templates.py`

| Function | Contract |
|---|---|
| `discover(repo_root) -> dict[str, Path]` | `{name: templates/skills/<name>.SKILL.md.tmpl}`; name is the filename minus `.SKILL.md.tmpl` |
| `owned_targets(repo_root) -> set[Path]` | `{.claude/skills/<name>/SKILL.md}` for every discovered template; the allowlist `build_all.py` passes to the guard |
| `check_grammar(text) -> list[str]` | Offending tags; empty when only partial and comment tags are present |
| `render(tmpl_path, partials_dir) -> str` | Grammar check, partial existence check, `chevron.render(text, {}, partials_path=..., partials_ext="mustache")`, then a `{{` scan of the output |
| `compile_all(repo_root, *, validate, what_if) -> CompileResult` | For each template: skip with NOTICE when `regen_guard.detect_reason(target)` is not `None` (in both write and validate mode; the file is never rewritten, the skip is reported at WARN rather than NOTICE, and the result is exit 1 in every mode, because the sentinel exempts the file from the class's only gate; both the in-file token and the `.noregen` sidecar count; this diverges from issue #5706 step 10 and ADR-108 section 4 records why); in validate mode compare and record drift; otherwise write when the bytes differ. Returns written, skipped, drifted, and an exit code (0 pass, 1 drift or unresolved `{{`, 2 grammar, missing partial, or missing target directory) |

Errors are classed by `AGENTS.md` Standards: 0 ok, 1 logic, 2 config. The worst class wins, matching `scripts/validation/evidence.py:exit_code_for`.

## Wiring

- `build/scripts/generate_skills.py`: `generate_skills()` calls `compile_all` before the copy loop, honoring `what_if`; a nonzero compile exit returns before any copy. New `--validate` flag runs `compile_all(validate=True)` and returns its exit code without copying. Module docstring cites ADR-108 and the REQ-003-010 amendment.
- `build/scripts/build_all.py`: `_build_skills` passes `check` through so the compile runs in validate mode under `--check` and reports drift as staleness (exit 2, the existing staleness code). The `GENERATORS` callable signature gains no parameter; `_run_generators` already knows `check`, so `_build_skills` reads it from a module-level context set by `run()`, or the tuple entry for `skills` is called with `check` explicitly. Pick the smaller diff at build time and document it in the docstring. `assert_no_claude_writes` gains `allowed_paths: set[Path] | None`; `run()` passes `skill_templates.owned_targets(repo_root)`.
- `pyproject.toml`: `chevron==0.14.0` in both dev tables; `uv lock`.
- `scripts/validation/checks_portability.py`: `validate_skill_template_drift(repo_root)` wrapping `generate_skills.py --validate`; `pre_pr_sequence.py`: `_Gate("Skill Template Drift", _root_only(validate_skill_template_drift))` after `Generated Artifact Staleness`; `pre_pr.py` facade re-export; `tests/validation/test_pre_pr_sequence_registry.py` `EXPECTED_ORDER` entry.
- `.agents/governance/GENERATOR-FILES.md`: new generated-trees row (`build/scripts/generate_skills.py` compile step, source `templates/skills/<name>.SKILL.md.tmpl` and `templates/skills/partials/*.mustache`, output `.claude/skills/<name>/SKILL.md`, spec ADR-108); the hand-maintained paragraph gains the exception; Regenerating gains the validate command.
- `build/AGENTS.md:8`, `.claude/rules/generated-artifacts.md:196`, `.claude/rules/templates.md` MUST 1: one sentence each naming the exception and the regeneration command. The two rule edits regenerate their instruction mirrors through `build_all.py`.
- `templates/AGENTS.md`: one line naming `skills/` and `skills/partials/`.
- `.github/CODEOWNERS`: entries for `/templates/skills/` and the pilot-scope test (landed in A0).
- A2 adds one sentence to `.claude/skills/CLAUDE.md`, `.agents/steering/claude-skills.md`, and `.agents/governance/SKILL-CREATION-CRITERIA.md`: the eight pilot skills are template-owned; edit the template, not `SKILL.md`.

## Pilot content

Six partials. Each is a contiguous span of one always-on rule file, chosen so the span carries no repository path the portability ratchet would flag.

| Slug | rule-source | Span |
|---|---|---|
| `no-dashes` | `voice.md` | `Use commas, periods, colons, parentheses, hyphens, or restructure.` |
| `completion-tail-audit` | `voice.md` | The blockquote line beginning `> After reporting a completed requested result` |
| `clear-the-gate` | `voice.md` | From `A gate is any check whose failure would falsify your conclusion.` through `If blocked, name who can clear it.` |
| `conventional-commits` | `universal.md` | `Commit messages MUST follow` ... `when authored with an AI agent.` |
| `bound-the-search` | `search-before-building.md` | The paragraph beginning `**Bound the search.**` |
| `terminal-predicate` | `builder-ethos.md` | The blockquote line beginning `> When every requested deliverable satisfies the frozen task contract` |

Placement, at the step each excerpt governs. Each template is the current `SKILL.md` with the `@CLAUDE.md` line deleted and `{{> slug}}` lines inserted:

| Pilot skill | Partials | Where |
|---|---|---|
| `sync` | `clear-the-gate`, `no-dashes` | verification step; output section |
| `test` | `clear-the-gate`, `completion-tail-audit` | gate reporting; final report |
| `spec` | `no-dashes`, `bound-the-search` | `## Output`; directly under `### Step 0.5: Memory-First Gate` in `SKILL.md` (line 60 today), not in `references/` |
| `ship` | `conventional-commits`, `clear-the-gate`, `completion-tail-audit`, `terminal-predicate` | commit step; pre-flight; PR summary; terminal |
| `research` | `bound-the-search`, `no-dashes` | search step; write-up |
| `plan` | `no-dashes`, `bound-the-search` | output; step 2 code mapping |
| `checkpoint` | `conventional-commits`, `clear-the-gate` | commit; verification |
| `build` | `conventional-commits`, `terminal-predicate`, `completion-tail-audit` | commit step; exit gates; report |

Claude Code loads `CLAUDE.md` as project instructions on its own, so deleting the include loses nothing there; on Copilot it was literal text.

## Copilot mirror

Unchanged pipeline. The include-line transform finds nothing in the eight rendered files, so each mirror loses its `<!-- Copilot CLI: project instructions (CLAUDE.md) ... -->` comment. `build_all.py --check` and `check_generated_staleness.py` keep pinning mirror to rendered file, and the compile's validate mode pins rendered file to template.

## Tests

`tests/build_scripts/test_generate_skills_template_compile.py`, against a temporary repo layout with a fixture template, partials, and target:

| Case | Kind | Expect |
|---|---|---|
| template with two partials renders byte-identical to a fixture | positive | exit 0, file written |
| template names a missing partial | config | exit 2, slug and path printed, target untouched |
| partial file lacks a trailing newline | config | exit 2, partial path printed, target untouched |
| template carries `{{var}}` | config | exit 2, tag printed |
| rendered output would contain `{{` | negative | exit 1 |
| skill with no template | edge | untouched, not counted as written |
| target carries a NO-REGEN sentinel (in-file token, and separately the `.noregen` sidecar) | edge | file unchanged, WARN printed, exit 1 in write and validate mode |
| `--validate` on a hand-edited target | negative | exit 1, path printed, target untouched |
| `--validate` on a clean tree | positive | exit 0 |
| CLI as subprocess | contract | exit codes 0, 1, 2 observed end to end |

`tests/build_scripts/test_skill_templates_pilot_scope.py`: asserts `discover(repo_root)` on the real tree returns exactly the names in a `PILOT` constant (empty set in A1, the eight pilot names after A2); its docstring states that widening the set is an owner decision recorded in that file. This is the control on the allowlist (ADR-108 section 1): a ninth `.tmpl` fails the suite until the owner adds the name.

`tests/build_scripts/test_build_all.py`: an allowlisted template-owned write passes the guard; a write to any other `.claude/` path still exits 2; `--check` with a drifted template exits 2 and restores nothing under `.claude/` (it never wrote).

`tests/build_scripts/test_skill_partials_rule_parity.py`: every partial with a `rule-source` line is a verbatim contiguous substring of that rule file; a negative control with a one-byte change fails.

`tests/skills/_template_contract.py` helper plus one `tests/skills/<pilot>/test_skill_md_contract.py` per pilot: the rendered file equals `render()` of its template; no `^@CLAUDE\.md$` line in rendered or mirror; no `{{` in either.

`tests/test_frontgate_crosslink_1927.py:163`: flipped to assert `@CLAUDE.md` is absent from the plan source and mirror.

## Rollback

Revert A2, then A1; move ADR-108 to `rejected`. The eight `SKILL.md` files return to hand-maintained content identical to `main` today.

## Declined alternative: excerpt blocks pinned by a validator, no amendment

`.claude/skills/<name>/SKILL.md` stays canonical and hand-maintained. Guidance spans sit between `<!-- excerpt: <slug> -->` and `<!-- /excerpt -->`; `scripts/validation/check_skill_excerpts.py` pins each span byte for byte to `templates/skills/partials/<slug>.md` and each sourced excerpt as a substring of its rule file, exits 0/1/2, with an author-run `--fix`. No `chevron`, no ADR change, no `.tmpl` files. Declined by the owner on 2026-09-11 in favor of templates as the canonical source.
