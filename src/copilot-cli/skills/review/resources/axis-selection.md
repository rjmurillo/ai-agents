# Axis selection reference

Detail for Process steps 4 and 4b of the `review` skill. `select_axes.py`, in this
skill's own script directory, is the source of truth for which Stage-2 axes run;
this file explains its inputs, its output, and the rules behind the mapping.
`python3 <select_axes.py> --help` prints the same flag list.

This directory is not `references/`. `/review` discovers its canonical axis set by
globbing `references/*.md`, so a non-axis document placed there would enroll a
phantom axis.

## Enrolling an axis

Discovery is a runtime glob, so a new `references/{role}.md` file routes with no
change to `select_axes.py`. Enrollment is not edit-free, though: the axis names
and the counts stated in SKILL.md (the convergence contract, Process step 7,
Output, Verification) document that directory rather than drive it, and
`tests/skills/review/test_select_axes_contract.py::TestSkillCountClaimsMatchTheCode`
reds when they drift. Measured: copying `references/qa.md` to
`references/perf.md` reds 5 tests in that suite, 4 of them count claims read
straight out of SKILL.md. Enrolling an axis is the prompt file plus a prose
update, never a routing-logic change.

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
`comments-or-docstrings`, `command-execution`, `untrusted-input`,
`artifact-or-rollback`.

An effect outside this list fails closed rather than being ignored, so a typo
costs a full review instead of silently selecting nothing.

## Output

JSON on stdout:

| Field | Meaning |
|-------|---------|
| `canonical_selected` | Axes to run with `Task(subagent_type="{stem}")` and `references/{stem}.md`. Contains `analyst` whenever `references/analyst.md` exists; if that prompt is absent, `analyst` is reported in `unresolved_axes` and the run fails closed instead. |
| `local_selected` | Local-only skill axes to run with `Skill(skill="{name}")`. Never overlaps `canonical_selected`. |
| `selection_reasons` | Per axis, why it was selected: the risk categories, the effects, `always-on`, `caller-pinned`, `deep review`, or `fail-closed`. |
| `skipped` | Per unselected axis, the skip reason. Copy it into the output table verbatim. A skipped axis is never PASS. |
| `unresolved_axes` | Axes a matched risk category or diff effect demanded that have no `references/{stem}.md` prompt to load. Non-empty sets `fail_closed`. Report each as UNKNOWN; an axis the change demanded is never silently absent from both `canonical_selected` and `skipped`. |
| `fail_closed` | True when the change could not be classified, or `unresolved_axes` is non-empty, and every candidate axis was selected. Intended behavior, not an error. |
| `matched_categories`, `unclassified_paths`, `unknown_effects` | The classification evidence behind the fields above. |

Exit codes: `0` a selection was emitted; `2` config error (an unknown pinned
axis name, or the references directory is missing or empty).

An incomplete prompt set widens the review rather than narrowing it: a demanded
axis with no prompt cannot be dispatched, so the selector reports it and runs
every candidate instead of quietly reviewing less than the change warrants.

## Risk categories

Additive: one change can match several categories, and every matched category
contributes its axes.

| Category | Matches | Canonical axes | Local axes |
|----------|---------|----------------|------------|
| `tests-or-fixtures` | a whole `tests/` or `fixtures/` path segment, a `test_*` or `test.*` filename, or a `.test.`, `.tests.`, `.spec.`, `_test.`, `_tests.`, or `_spec.` name segment whatever suffix follows | `qa` | |
| `auth-secrets-execution` | a whole path word of `auth`, `authn`, `authz`, `oauth`, `secret(s)`, `credential(s)`, `password(s)`, `token(s)`, `permission(s)`, a word starting `sanitiz` or `crypto`, or a `.env*` file | `security` | |
| `dependencies` | a dependency manifest or lockfile (`pyproject.toml`, `uv.lock`, `package.json`, `*.csproj`, `go.mod`, `requirements*.txt`, and peers) | `security`, `devops` | |
| `ci-deploy-artifacts` | `.github/workflows/`, `.github/actions/`, a `lefthook`, `Dockerfile`, `docker-compose`, `deploy.*`, or `release.yml` file, a `*.tf`/`*.tfvars` file, or a `deploy/` or `release/` directory | `devops`, `security` | |
| `types-or-public-api` | a `*.d.ts` or `*.proto` file, a whole `schemas/` or `interfaces/` path segment, or a whole basename of `types`, `api`, `models`, `schema`, `protocols`, or `interfaces` carrying any supported source suffix (`types.go` and `models.ts` count; `prototypes.py` does not) | `architect` | |
| `agent-artifacts` | a file named `SKILL.md`, or a whole path segment of `skills/`, `agents/`, `hooks/`, `prompts/`, or `commands/` | `agent-safety` | |
| `decision-records` | an `ADR-*` file, or a whole `architecture/` or `decisions/` path segment | `decision-rigor` | |
| `roadmap-or-spec-docs` | a whole `roadmap/`, `planning/`, or `specs/` path segment | `roadmap` | |
| `docs-and-instructions` | `*.md`, `*.mdx`, `*.rst`, `*.txt` | | `doc-accuracy` |
| `executable-code` | a source file in a supported language | `code-quality` | `code-qualities-assessment`, `taste-lints` |
| `toolkit-governance` | an agent artifact, a workflow, or a whole `rules/` path segment | | `golden-principles` |

`docs-and-instructions` routes to the `doc-accuracy` skill, which verifies
documentation claims against the code they describe. A docs-only change still
runs far fewer axes than a code change: `spec-compliance`, the always-on
`analyst`, and `doc-accuracy`, which is the "low-risk changes run fewer axes"
case, 2 Stage-2 axes instead of 15.

`golden-principles` is scoped to toolkit artifacts because that is the surface
its GP rules govern; a clean result elsewhere means no rule applied, not that
design was reviewed.

Every category above matches whole path segments and whole filenames, for the
same reason `auth-secrets-execution` matches whole path words. Bare substrings
failed in both directions at once. `skill.md` inside
`req-019-autoplan-router-skill.md` selected `agent-safety` and
`golden-principles` on a requirements document (5 such files in the corpus
below), while `/skills/` with its leading slash could not match a repo-root
`skills/` directory at all, so an agent artifact in the vendored plugin layout
skipped `agent-safety` silently. Segment matching drops those 5 and keeps every
real `SKILL.md`.

The same shape reached four more categories, and there the under-fire is the
one that costs coverage, because the path still classifies as something else,
so `fail_closed` stays false and the missing axis reads as a deliberate skip:

- `Button.test.tsx` and `router.spec.js` matched no `(name, extension)` pair,
  classified as `executable-code` alone, and skipped the required `qa` axis.
- `fixtures/sample.json` at the repository root matched neither `/fixtures/`
  nor any suffix, classified as nothing, and paid for a full fail-closed review.
- `src/prototypes.py` contains the substring `types.py` and selected
  `architect`; `src/types.go` matched no pair and skipped it.
- `roadmap/plan.md`, `planning/work.md`, and `decisions/record.md` needed a
  leading slash, so `docs-and-instructions` claimed each one and `roadmap` or
  `decision-rigor` never ran.

## Corpus

Counts on this page are measured over the tracked files at this branch's HEAD:
`git ls-tree -r -z --name-only HEAD` returns 9589 paths. A count is a
measurement of one commit, so re-run it rather than carrying the number
forward.

`dependencies` routes to `security` and `devops`, not `architect`. The issue
row reads "dependency and security review": `security` covers the supply-chain
half and `devops` owns build and dependency wiring here. A manifest bump does
not change a public interface, so pulling in `architect` would add an axis with
nothing in the diff to review.

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
| `command-execution` | `security` |
| `untrusted-input` | `security` |
| `artifact-or-rollback` | `devops`, `security` |

The last three cover the issue rows "Auth, secrets, execution, or untrusted
input" and "CI, deployment, artifacts, or rollback". Their `auth`, `secrets`,
`CI`, and `deployment` halves are path-shaped and live in the risk table above;
the execution, untrusted-input, artifact, and rollback halves are not. Matching
those as path words was measured against the whole corpus above and produced no
true risk surface at all: `eval` matched 183 paths (an analysis corpus of
`eval-*` reports), `commands` 58, `artifact` and `artifacts` 63 (mostly an
eval-artifact report directory), `execution` 28 (ADR titles), `rollback` 1
(an operations runbook). Declaring them from the diff body keeps the routing
faithful to the issue without re-creating the over-fire the risk table's whole
path word matching exists to prevent.

## Why selection is not left to prompt prose

Process step 4 once told the reviewer to decide each axis from that axis
prompt's `When This Axis Applies` section. These canonical prompts have no such
section: `analyst`, `architect`, `qa`, `security`, `devops`, `roadmap`. For most
axes there was nothing to read and the routing was re-derived on each run. The selector is a pure function of its arguments, so the
same change selects the same axes every time, and the source repository's review
skill test suite asserts each rule above against the script's real output. Issue
#4981 records the reopening that motivated this.
