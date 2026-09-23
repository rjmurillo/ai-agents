---
type: design
id: DESIGN-032
title: Close the completion-contract validation gaps
status: draft
priority: P1
related:
  - REQ-034
  - TASK-043
adr: ADR-105
created: 2026-09-23
updated: 2026-09-23
author: spec-generator
tags:
  - eval
  - runtime-parity
---

# DESIGN-032: Close the completion-contract validation gaps

## Requirements Addressed

REQ-034 criteria 1 to 10.

## Copilot loading contract (probed 2026-09-23)

Copilot CLI 1.0.89 has a model-free command, `copilot instruction list
--json`. In a fresh git repository with an isolated `HOME` and
`COPILOT_HOME`, it listed:

- `.github/copilot-instructions.md` as a repository source.
- `.github/instructions/*.instructions.md` as working-directory sources,
  with or without `applyTo` frontmatter.
- `AGENTS.md` and `CLAUDE.md` at the repository root.
- `$COPILOT_HOME/copilot-instructions.md` as a personal source.

It did not list `.claude/rules/*.md`. It did not list instruction files in a
directory above the git root.

The evaluator's isolated profile resolves an older CLI, 1.0.84-9. A live run
on that version listed exactly the two installed projections, so the
contract holds on both versions.

## Install path

The fixture keeps one `instructions` list of canonical `.claude/rules/<name>.md`
paths. For Copilot, the evaluator resolves
`.github/instructions/<name>.instructions.md` at the same ref. The build
writes that projection for every rule, so the mapping is the generator's
own naming contract.

## Isolation proof

Claude keeps its sentinel. Copilot cannot, because loading repository
instructions also loads any sentinel file. So a Copilot instruction fixture
writes no sentinel file, drops `--no-custom-instructions`, and runs the
listing command in the prepared workspace with the run's own environment.
The listed `sourcePath` set must equal the installed projection set. Any
other source means a leak; any missing source means the rule never loaded.
An entry without a string `sourcePath` could hide a leak. All three exit 2.

## Threshold

ADR-057's flakiness protocol already governs `eval-prompt-change.py`: a
non-security scenario passes at two of three runs or better. The runtime
corpus uses the same rule over at least three live runs per arm.

## Scenario 13 fixture

The `(?i)payment\.ts` regex tests file naming, not the terminal rule. The
reply "Fixed. Suite is green." satisfies the scenario and failed it. The
deterministic assertion becomes a completion check,
`(?i)fix|pass|green`. The rubric and controls stay byte-identical.

Scenario 10 has the same defect. A main-branch run wrote "imports `<name>`,
and nothing in the file uses it". The grader passed it, and the
`(?i)unused import` regex failed it. The regex becomes `(?i)import`.

## Verdict scenarios

A live ablation against `2e78453a8` found three scenario specs that grade
wording instead of the decision:

- Critic `TC-1` returned APPROVE in 3 of 3 runs. It failed only on
  `expected_reason_contains: "no gap"`, a phrase no critic prompt asks for.
  The phrase check is removed; the verdict alone separates approval from a
  manufactured finding.
- Orchestrator `S11` returned DELEGATE in 3 of 3 runs, with the reason
  "delegate back to implementer ... continues narrowly on this blocker". For
  an orchestrator, continuing means delegating. DELEGATE leaves the options.
- Orchestrator `S14` tested an Ask-First decision, not scenario 6. It now
  gives a new context a handoff that records the task as terminal with
  evidence, and expects STOP.
