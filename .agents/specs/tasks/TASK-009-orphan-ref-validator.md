---
type: task
id: TASK-009
title: Orphan-Ref Validator Skill Implementation Tasks
status: in-progress
complexity: M
priority: P2
related: [REQ-009, DESIGN-009]
created: 2026-05-10
updated: 2026-05-10
author: richard
---

# TASK-009: Orphan-Ref Validator Skill Implementation Tasks

## Milestones

PR1 (this PR, wedge per REQ-009 Q4 revision; expanded to include AC3 during PR #1979 review):

| ID | Milestone | ACs covered | Blocking | Effort |
|---|---|---|---|---|
| M1 | Skill skeleton + scan.py core | AC1, AC2, AC3, AC5, AC6 | none | 2.5h |
| M2 | Count-claim regex extraction (canonical mirror) | AC4 partial (detect, not enforce) | M1 | 1h |
| M3 | Test suite | AC8 (subset: AC2/AC3/AC4/AC5/AC6) | M1, M2 | 1h |
| M4 | Wire into /build Mandatory Exit Gates | AC7 | M1-M3 | 0.25h |
| M5 | Self-test: scan repo, fix surfaced orphans | (validation) | M1-M4 | 0.5h |

PR1 total: ~5.25h. ACs delivered: AC1, AC2, AC3, AC4 (extract-only; emission delegated to canonical), AC5, AC6, AC7, AC8.

PR2 (follow-up, per REQ-009 "PR2 follow-up" section):

| ID | Milestone | Item | Effort |
|---|---|---|---|
| F1 | Optional `--enforce-counts` for single-plugin count_claim emission | AC4 emission (opt-in) | 1h |
| F2 | Wire into /test Gate 5 | /test wiring | 0.25h |

PR2 total: ~1.25h.

## Tasks

### TASK-009-01: Create skill skeleton

- Create `.claude/skills/orphan-ref-validator/` directory.
- Write `SKILL.md` with frontmatter (name, description, license, version) and body sections (Triggers, Inputs, Outputs, Behavior, Failure modes, References).
- Body ≤500 lines.
- Acceptance: skill directory exists; `python3 -c "import yaml; yaml.safe_load(open('.claude/skills/orphan-ref-validator/SKILL.md').read().split('---')[1])"` parses frontmatter; section anchors match DESIGN-009.

### TASK-009-02: Implement scan.py core (AC1-AC3, AC5, AC6)

- File: `.claude/skills/orphan-ref-validator/scripts/scan.py`
- Functions per DESIGN-009 components.
- CLI: `argparse` with `--targets PATH...`, `--output {json,human}`, `--repo-root PATH`.
- Main: `def main(argv=None) -> int` returning ADR-035 exit code.
- Reference patterns (defined in `patterns.py`):

  ```python
  SKILL_REF_RE  = re.compile(r"`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`")
  SCRIPT_REF_RE = re.compile(
      r"`((?:build/scripts|scripts/validation|scripts)/[a-zA-Z0-9_/-]+\.py)`"
  )
  ```

- Skill enumeration: `[d.name for d in (repo_root / ".claude/skills").iterdir() if d.is_dir() and (d / "SKILL.md").exists()]`
- Vendored install: each missing target path logs INFO and continues.
- Output: ADR-056 envelope to stdout, then literal final line `VERDICT: <pass|warn|critical_fail>` (UPPERCASE in actual emit).
- Acceptance: scan.py runs `--help` without error; exits 0 on `--targets /tmp/empty.md`; exits 1 with critical_fail finding on a fixture mentioning `nonexistent-skill`. <!-- orphan-ref-ignore -->

### TASK-009-03: Implement count-claim detection (AC4 partial - extraction only)

- Mirror canonical `COUNT_PATTERN` and `LABEL_MAP` from `build/scripts/validate_marketplace_counts.py` byte-for-byte in `patterns.py` (matches `specialized agent definition`, `agent definition`, `agent`, `slash command`, `lifecycle hook`, `reusable skill` with optional plural).
- Detection only in PR1: `extract_count_claims` yields `(lineno, count, canonical_label)` triples; emission of `Finding(kind=count_claim)` is delegated to the canonical validator per `.claude/rules/canonical-source-mirror.md`. The canonical reads `templates/marketplace-counters.yaml` for per-plugin `sourceDir` and `exclude` lists and supports `--fix`; orphan-ref-validator does not duplicate that surface.
- An opt-in `--enforce-counts` flag (`scan_file(enforce_counts=True)`) is reserved for PR2 single-plugin enforcement.
- Acceptance: extractor emits the canonical labels; no `count_claim` findings emitted in default mode; `tests/test_validate_marketplace_counts.py` continues to enforce counts at the canonical seam.

### TASK-009-04: Test suite (AC8)

- File: `.claude/skills/orphan-ref-validator/tests/test_scan.py`
- Use `pytest` and `tmp_path` fixtures.
- Cases per DESIGN-009 test table (AC2/3/4 positive+negative, AC5 envelope, AC6 vendored, AC8 edge cases).
- Coverage gate: `pytest --cov=scripts.scan --cov-fail-under=80`.
- Acceptance: all tests green; coverage report ≥80% line on scan.py.

### TASK-009-05: Wire into /build (AC7)

- Edit `.claude/commands/build.md` "Mandatory Exit Gates" section.
- Add bullet for orphan-ref-validator alongside code-qualities-assessment, taste-lints, doc-accuracy.
- Acceptance: grep `.claude/commands/build.md` returns the new bullet; `/build` documentation reads correctly.

### TASK-009-06 (PR2 follow-up): Wire into /test Gate 5

PR2 work, tracked in REQ-009's "PR2 follow-up" section. Not part of PR1.

- Edit `.claude/commands/test.md` Gate 5 (DX) section.
- Add bullet for orphan-ref-validator.
- Acceptance: grep `.claude/commands/test.md` returns the new bullet.

### TASK-009-07: Self-test on the source repo

- Run `python3 .claude/skills/orphan-ref-validator/scripts/scan.py` from repo root.
- Triage findings: classify each as (a) real orphan to fix, (b) false positive to refine pattern, or (c) deferred.
- Fix real orphans in this PR (≤3 atomic commits); document false positives in pattern refinement.
- Acceptance: clean scan or documented exceptions; PR description lists triaged findings.

### TASK-009-08: Pre-PR validation

- Run `python3 scripts/validation/pre_pr.py`.
- Run pytest on the new tests.
- Run markdownlint on touched .md files.
- Confirm no new BLOCKING issues.
- Acceptance: pre_pr.py exit 0; pytest exit 0; markdownlint exit 0.

## Definition of Done (PR1)

- PR1-scope acceptance criteria satisfied: AC1, AC2, AC3, AC4 (regex extraction only; emission delegated to canonical), AC5, AC6, AC7, AC8.
- `/test` Gate 5 wiring lives in REQ-009's "PR2 follow-up" section, not as an AC of PR1; PR2 also adds the opt-in `--enforce-counts` flag for single-plugin count emission.
- Tests green with ≥80% coverage on scan.py.
- /build gate wired (gate 4 in `.claude/commands/build.md`); /test gate is PR2.
- Self-scan on this PR is clean or documents exceptions.
- pre_pr.py passes.
- PR description lists Step 0 evidence + linkage to issue #1939, epic #1933.
