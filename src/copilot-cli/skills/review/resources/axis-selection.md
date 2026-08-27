# Axis selection reference

Detail for Process steps 4 and 4b of the `review` skill. `select_axes.py`, in this
skill's own script directory, is the source of truth for which Stage-2 axes run;
this file explains its inputs, its output, and the rules behind the mapping.
`python3 <select_axes.py> --help` prints the same flag list.

This directory is not `references/`. `/review` discovers its canonical axis set by
globbing `references/*.md`, so a non-axis document placed there would enroll a
phantom axis.

## Inputs

| Flag | Meaning |
|------|---------|
| `--changed-path PATH` | One path from the verified three-dot diff collected in Process step 1. Repeatable. Pass the real diff, never a guess: an unverified path list selects the wrong axes. |
| `--effect NAME` | One diff effect read from the diff body, where no path glob can see it. Repeatable. Declare every effect that applies. |
| `--pin AXIS` | One caller-pinned always-on axis, canonical or local. Repeatable. |
| `--deep` | Explicit deep review: select every candidate axis regardless of risk. |
| `--references-dir DIR` | Override the canonical axis directory. Defaults to `references/` next to the script, which resolves in both the source project and a vendored plugin install. |

### Diff-effect vocabulary

`error-handling`, `type-change`, `public-api`, `integration-point`,
`new-code-path`, `dependency-change`, `agent-behavior`, `decision-record`,
`comments-or-docstrings`.

An effect outside this list fails closed rather than being ignored, so a typo
costs a full review instead of silently selecting nothing.

## Output

JSON on stdout:

| Field | Meaning |
|-------|---------|
| `canonical_selected` | Axes to run with `Task(subagent_type="{stem}")` and `references/{stem}.md`. Always contains `analyst`. |
| `local_selected` | Local-only skill axes to run with `Skill(skill="{name}")`. Never overlaps `canonical_selected`. |
| `selection_reasons` | Per axis, why it was selected: the risk categories, the effects, `always-on`, `caller-pinned`, `deep review`, or `fail-closed`. |
| `skipped` | Per unselected axis, the skip reason. Copy it into the output table verbatim. A skipped axis is never PASS. |
| `fail_closed` | True when the change could not be classified and every candidate axis was selected. Intended behavior, not an error. |
| `matched_categories`, `unclassified_paths`, `unknown_effects` | The classification evidence behind the three fields above. |

Exit codes: `0` a selection was emitted; `2` config error (an unknown pinned
axis name, or the references directory is missing or empty).

## Risk categories

Additive: one change can match several categories, and every matched category
contributes its axes.

| Category | Matches | Canonical axes | Local axes |
|----------|---------|----------------|------------|
| `tests-or-fixtures` | a `tests/` or `fixtures/` path, a `test_*` or `*_test` file | `qa` | |
| `auth-secrets-execution` | `auth`, `secret`, `credential`, `password`, `token`, `crypto`, `sanitiz`, `permission` in the path, or a `.env*` file | `security` | |
| `dependencies` | a dependency manifest or lockfile (`pyproject.toml`, `uv.lock`, `package.json`, `*.csproj`, `go.mod`, `requirements*.txt`, and peers) | `security`, `devops` | |
| `ci-deploy-artifacts` | `.github/workflows/`, `.github/actions/`, `lefthook.yml`, a Dockerfile, a Terraform file, a deploy or release path | `devops`, `security` | |
| `types-or-public-api` | `*.d.ts`, `types.*`, `models.py`, `schema.py`, `schemas/`, `*.proto`, `interfaces/`, `protocols.py`, `api.*` | `architect` | |
| `agent-artifacts` | a `SKILL.md`, or a `skills/`, `agents/`, `hooks/`, `prompts/`, or `commands/` path | `agent-safety` | |
| `decision-records` | an `ADR-*` file, or an `architecture/` or `decisions/` path | `decision-rigor` | |
| `roadmap-or-spec-docs` | a `roadmap/`, `planning/`, or `specs/` path | `roadmap` | |
| `docs-and-instructions` | `*.md`, `*.mdx`, `*.rst`, `*.txt` | | |
| `executable-code` | a source file in a supported language | `code-quality` | `code-qualities-assessment`, `taste-lints` |
| `toolkit-governance` | an agent artifact, a workflow, or a `rules/` path | | `golden-principles` |

`docs-and-instructions` contributes no specialist on purpose. A docs-only change
still gets `spec-compliance` plus the always-on `analyst`, which is the
"low-risk changes run fewer axes" case: 1 Stage-2 axis instead of 14.

`golden-principles` is scoped to toolkit artifacts because that is the surface
its GP rules govern; a clean result elsewhere means no rule applied, not that
design was reviewed.

## Diff-effect mapping

| Effect | Canonical axes |
|--------|----------------|
| `error-handling` | `reliability`, `qa` |
| `type-change`, `public-api` | `architect` |
| `integration-point` | `reliability` |
| `new-code-path` | `observability` |
| `dependency-change` | `security`, `devops` |
| `agent-behavior` | `agent-safety` |
| `decision-record` | `decision-rigor` |
| `comments-or-docstrings` | `code-quality` |

## Why selection is not left to prompt prose

Process step 4 once told the reviewer to decide each axis from that axis
prompt's `When This Axis Applies` section. Six of the eleven canonical prompts
have no such section (`analyst`, `architect`, `qa`, `security`, `devops`,
`roadmap`), so for most axes there was nothing to read and the routing was
re-derived on each run. The selector is a pure function of its arguments, so the
same change selects the same axes every time, and the source repository's review
skill test suite asserts each rule above against the script's real output. Issue
#4981 records the reopening that motivated this.
