---
type: task
id: TASK-008
title: Orphan-Ref Validator Skill Implementation Tasks
status: draft
priority: P2
related: [REQ-008, DESIGN-008]
created: 2026-05-10
updated: 2026-05-10
author: richard
---

# TASK-008: Orphan-Ref Validator Skill Implementation Tasks

## Milestones

PR1 (this PR, wedge per REQ-008 Q4 revision):

| ID | Milestone | ACs covered | Blocking | Effort |
|---|---|---|---|---|
| M1 | Skill skeleton + scan.py core | AC1, AC2, AC5, AC6 | none | 2h |
| M2 | Count-claim detection | AC4 | M1 | 1h |
| M3 | Test suite | AC9 (subset: AC2/AC4/AC5/AC6 only) | M1, M2 | 1h |
| M4 | Wire into /build Mandatory Exit Gates | AC7 | M1-M3 | 0.25h |
| M5 | Self-test: scan repo, fix surfaced orphans | (validation) | M1-M4 | 0.5h |

PR1 total: ~5h. ACs delivered: AC1, AC2, AC4, AC5, AC6, AC7, AC9 (subset).

PR2 (follow-up, deferred per REQ-008):

| ID | Milestone | ACs covered | Effort |
|---|---|---|---|
| F1 | Script-path detection (AC3) | AC3 + AC9 extension | 1h |
| F2 | Wire into /test Gate 5 (AC8) | AC8 | 0.25h |

PR2 total: ~1.25h.

## Tasks

### TASK-008-01: Create skill skeleton

- Create `.claude/skills/orphan-ref-validator/` directory.
- Write `SKILL.md` with frontmatter (name, description, license, version) and body sections (Triggers, Inputs, Outputs, Behavior, Failure modes, References).
- Body ≤500 lines.
- Acceptance: skill directory exists; `python3 -m yaml safe_load` parses frontmatter; section anchors match DESIGN-008.

### TASK-008-02: Implement scan.py core (AC1-AC3, AC5, AC6)

- File: `.claude/skills/orphan-ref-validator/scripts/scan.py`
- Functions per DESIGN-008 components.
- CLI: `argparse` with `--targets PATH...`, `--output {json,human}`, `--repo-root PATH`.
- Main: `def main(argv=None) -> int` returning ADR-035 exit code.
- Reference patterns:
  - `SKILL_NAME_RE = re.compile(r"`([a-z][a-z0-9-]+)`")` (kebab-case in backticks)
  - `SCRIPT_PATH_RE = re.compile(r"`((build/scripts|scripts/validation|scripts)/[a-zA-Z0-9_/-]+\.py)`")`
- Skill enumeration: `[d.name for d in (repo_root / ".claude/skills").iterdir() if d.is_dir() and (d / "SKILL.md").exists()]`
- Vendored install: each missing target path logs INFO and continues.
- Output: ADR-056 envelope to stdout, then literal final line `VERDICT: <pass|warn|critical_fail>` (UPPERCASE in actual emit).
- Acceptance: scan.py runs `--help` without error; exits 0 on `--targets /tmp/empty.md`; exits 1 with critical_fail finding on a fixture mentioning `nonexistent-skill`. <!-- orphan-ref-ignore -->

### TASK-008-03: Implement count-claim detection (AC4)

- Reuse strategy patterns from `build/scripts/validate_marketplace_counts.py`.
- Pattern: `\b(\d+)\s+(skills|agents|commands|hooks)\b` in plugin/marketplace JSON `description` fields.
- Enumerator delegates: skills count = `len(enumerate_skills(repo_root))`; agents count = directory count under `.claude/agents/`; commands count = directory count under `.claude/commands/`; hooks count = file count under `.claude/hooks/**`.
- Expected vs actual logged in Finding.expected / Finding.actual.
- Acceptance: fixture manifest claiming wrong count emits Finding with severity=critical.

### TASK-008-04: Test suite (AC9)

- File: `.claude/skills/orphan-ref-validator/tests/test_scan.py`
- Use `pytest` and `tmp_path` fixtures.
- Cases per DESIGN-008 test table (AC2/3/4 positive+negative, AC5 envelope, AC6 vendored, AC9 edge cases).
- Coverage gate: `pytest --cov=scripts.scan --cov-fail-under=80`.
- Acceptance: all tests green; coverage report ≥80% line on scan.py.

### TASK-008-05: Wire into /build (AC7)

- Edit `.claude/commands/build.md` "Mandatory Exit Gates" section.
- Add bullet for orphan-ref-validator alongside code-qualities-assessment, taste-lints, doc-accuracy.
- Acceptance: grep `.claude/commands/build.md` returns the new bullet; `/build` documentation reads correctly.

### TASK-008-06: Wire into /test (AC8)

- Edit `.claude/commands/test.md` Gate 5 (DX) section.
- Add bullet for orphan-ref-validator.
- Acceptance: grep `.claude/commands/test.md` returns the new bullet.

### TASK-008-07: Self-test on the source repo

- Run `python3 .claude/skills/orphan-ref-validator/scripts/scan.py` from repo root.
- Triage findings: classify each as (a) real orphan to fix, (b) false positive to refine pattern, or (c) deferred.
- Fix real orphans in this PR (≤3 atomic commits); document false positives in pattern refinement.
- Acceptance: clean scan or documented exceptions; PR description lists triaged findings.

### TASK-008-08: Pre-PR validation

- Run `python3 scripts/validation/pre_pr.py`.
- Run pytest on the new tests.
- Run markdownlint on touched .md files.
- Confirm no new BLOCKING issues.
- Acceptance: pre_pr.py exit 0; pytest exit 0; markdownlint exit 0.

## Definition of Done

- All 9 acceptance criteria satisfied.
- Tests green with ≥80% coverage on scan.py.
- /build and /test gates wired.
- Self-scan on this PR is clean or documents exceptions.
- pre_pr.py passes.
- PR description lists Step 0 evidence + linkage to issue #1939, epic #1933.
