---
type: design
id: DESIGN-039
title: Provenance and authority gate in the build skill
status: implemented
priority: P1
related:
  - REQ-041
  - DESIGN-036
  - TASK-050
created: 2026-09-26
updated: 2026-09-26
author: spec-generator
tags:
  - skills
  - build
  - routing
  - validation
---

# DESIGN-039: Provenance and authority gate in the build skill

## Requirements Addressed

REQ-041 criteria 1 to 10.

## Where the gate sits

`build` gets a new Phase 2b between the pre-mortem and the slices. It runs
before any code changes, and again whenever a slice adds a path that the
first run did not see.

1. Run `validation_trigger.py` with the planned changed paths and the
   verified effects. On `skip`, record the reason and continue.
2. On `activate`, invoke `analysis-provenance` for each matched target.
3. Invoke `validation-authority` with the provenance output. It writes the
   decision record.
4. Run `validation_record.py` on the record and the changed paths. Exit 0
   lets Phase 3 edit only the permitted locations. Exit 1 stops edits to the
   named targets. Exit 2 is a configuration error.

The build passes the record path to `/test` Gate 4, and copies the record
summary into the PR body. `/review` runs after `/test`, so it needs no second
consume step.

## Trigger: `.claude/skills/build/scripts/validation_trigger.py`

Arguments: `--changed-path` (repeatable) and `--effect` (repeatable).

Path cues:

| Cue | Match |
|---|---|
| `validator-code` | under `scripts/validation/`, a `validators` or `linters` directory, or a skill script whose stem starts with `validat` (validate, validation, validator), `verify`, `check`, `lint`, or `scan` |
| `ratchet-or-baseline` | a file stem containing `ratchet` or `baseline` |
| `validator-config` | a known linter or gate config file, for example `.markdownlint*`, `ruff.toml`, `.yamllint*`, `PSScriptAnalyzerSettings.psd1`, `.qualityrc.json`, `.pre-commit-config.yaml`, `lefthook.yml`, `.gitleaks.toml` |
| `validation-fixture` | under `tests/validation/`, or a `fixtures` directory below a validation test root |
| `generated-output` | under a root from `OWNED_PREFIXES` in `build/scripts/build_all.py`, or a `.claude/skills/<name>/SKILL.md` whose template `templates/skills/<name>.SKILL.md.tmpl` exists |

The generated cue alone does not activate the gate. It activates only when
the same path also matches a validation cue, or when the caller passes the
`generated-validator` effect. A generated mirror of an ordinary skill is not
a validation target.

Effect cues (each activates): `pass-fail-semantics`, `severity-change`,
`baseline-update`, `fixture-redefines-case`, `validator-config`,
`vendored-logic`, `generated-validator`. An unknown effect name exits 2.

The trigger reads `OWNED_PREFIXES` with `ast.literal_eval` on the assignment
node, found by walking up from the current directory to the first directory
that holds `build/scripts/build_all.py`. When that file is absent, the output
carries `generated_roots_source: null` and a note.

Output JSON: `decision` (`activate` or `skip`), `targets` (path and cues),
`effects`, `reason`, `generated_roots_source`.

## Record: `.claude/skills/validation-authority/scripts/validation_record.py`

Arguments: `--record` (required) and `--changed-path` (repeatable).

Rules:

1. Each target needs `target`, `component`, `provenance`, and `authority`.
2. `provenance.category` is one of `LOCAL`, `GENERATED`, `VENDOR`,
   `UPSTREAM`, `UNKNOWN`. `owner` and `evidence` are non-empty.
3. `authority.diagnosis` is one of the six diagnoses. `contract` and
   `permitted_change_location` are non-empty.
4. `UNKNOWN` category or `unknown` diagnosis is a blocking defect. The
   message says to stop semantic edits and request ownership evidence.
5. `GENERATED` needs `canonical_source`, and the permitted location must
   equal it.
6. `VENDOR` or `UPSTREAM`: the permitted location must not equal the target.
   `upstream-defect` needs a non-empty `escalation`.
7. `baseline-update` needs `baseline_justification` with a `policy_source`
   that is a relative path to an existing file inside the repository, a non-empty `reason`, and `added_entries` where each
   entry has a non-empty `justification`.
8. With changed paths: every path the trigger would flag must be a record
   target. A `VENDOR` or `UPSTREAM` target must not be a changed path. A
   changed `GENERATED` target needs its canonical source changed too.
   A changed mirror with no validation cue is outside this gate;
   `build_all.py --check` owns mirror parity for it.
9. `trigger` is the trigger's JSON object with `decision` `activate` or
   `skip`. A `skip` that lists effects or targets is refused. An activated
   trigger needs at least one record target, and each path it named needs a
   record target.
10. Paths compare after normalization (forward slashes, no `.` segments).
    One run reports every defect.

Exit codes follow ADR-035: 0 pass, 1 defects, 2 configuration error.

## Record location

`.project-toolkit/scratch/validation-authority-record.json` in the working
tree. That directory is already git-ignored for agent PR scratch files. The
PR body carries the summary, so the record does not need a commit.

## Routing

- `analysis-provenance`: `conditional-adjunct`, invoker `build`.
  `spec-generator` keeps its mention; the manifest records one primary role.
- `validation-authority`: `conditional-adjunct`, invoker `build`.

## Why not reuse `dx_trigger.py`

`dx_trigger.py` maps paths to developer journeys. Validation semantics is a
different question, and a shared classifier would couple two gates that
change for different reasons.
