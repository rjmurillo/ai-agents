---
type: design
id: DESIGN-010
title: M4 rework warning recalibration
status: draft
priority: P1
related:
  - REQ-010
  - TASK-010
adr: []
author: Richard Murillo
created: 2026-05-10
updated: 2026-05-10
---

# DESIGN-010: M4 Rework Warning Recalibration

## Requirements Addressed

- REQ-010 (all four acceptance criteria: REQ-010-01 through REQ-010-04)

## Design Overview

The M4 rework detector's threshold of 6 is empirically correct. The exclusion list is incomplete. Adding `.agents/memory/episodes/` to `_REWORK_EXCLUDED_PREFIXES` and pinning the contract with a real-fixture test closes both defects in two targeted edits totalling fewer than 10 lines of production change.

## Section 1: Why the Threshold Was Wrong About Being Wrong

Calibration across four sampled branches produced the following per-file maximum edit counts:

| Branch | Max edits (excluded paths removed) | Notes |
|---|---|---|
| feat/req-008-step-0-5 | 13 | real rework |
| feat/issue-1939-orphan-ref | 19 (scan.py, 14 net) | episode-2026-05-10.json at 19 is generated |
| feat/issue-1988 | 4 | small PR, no rework |
| feat/1066-retire-pester | 3 | small PR, no rework |

The rework signal lives at 8-19 edits. Non-rework sits at 1-4. `REWORK_THRESHOLD = 6` sits between the two clusters. It is the correct value.

PR #1989 returned 0 warnings not because the threshold was wrong but because episode-2026-05-10.json (19 edits, generated) was not excluded. When the highest-edit-count file is generated noise, the detector's output does not reflect source rework. Removing generated files from the candidate set lets the threshold operate on the distribution it was calibrated against.

The chestertons-fence constraint is satisfied: the constant has three prior commits with no written justification for the value, making it revisable. The calibration data now provides the justification. The decision is PRESERVE constant, MODIFY exclusion list.

## Section 2: Component Map

| Acceptance Criterion | Code Location | Change |
|---|---|---|
| REQ-010-01: scan.py included, episode excluded | `tests/skills/session-end/test_rework_warning.py` | New test `test_excludes_episode_logs_real_fixture` |
| REQ-010-02: episodes prefix added | `.claude/skills/session-end/scripts/rework_warning.py:_REWORK_EXCLUDED_PREFIXES` | Append `.agents/memory/episodes/` |
| REQ-010-02 (mirror): same prefix | `src/copilot-cli/skills/session-end/scripts/rework_warning.py:_REWORK_EXCLUDED_PREFIXES` | Same append, regenerated via `build_all.py` |
| REQ-010-03: self-apply gate | PR description + `build/` invocation | Run M4 before milestone commit; capture output |
| REQ-010-04: real-fixture test | `tests/skills/session-end/fixtures/orphan_ref_validator_git_log.txt` | Captured git log from feat/issue-1939-orphan-ref |

### Canonical file

`.claude/skills/session-end/scripts/rework_warning.py`

Current `_REWORK_EXCLUDED_PREFIXES` (representative; read actual file before editing):

```python
_REWORK_EXCLUDED_PREFIXES = (
    ".agents/sessions/",
    "src/claude/",
    # additional entries...
)
```

After TASK-010-03, the tuple gains `.agents/memory/episodes/` as an additional entry. No other lines in the file change.

### Mirror file

`src/copilot-cli/skills/session-end/scripts/rework_warning.py` is regenerated from the canonical template via `python3 build/scripts/build_all.py` (or equivalent generator). It MUST NOT be hand-edited. TASK-010-04 covers the regeneration step.

### Fixture file

`tests/skills/session-end/fixtures/orphan_ref_validator_git_log.txt` contains the raw output of:

```
git log --follow --name-only --format="" origin/main..feat/issue-1939-orphan-ref | sort | uniq -c | sort -rn
```

(exact command confirmed during TASK-010-01 implementation; the fixture is the captured stdout).

The fixture must contain at minimum two entries: one matching `episode-2026-05-10.json` with count >= 19 and one matching `scan.py` with count >= 14. These values were observed in the live branch; the fixture captures them verbatim.

## Section 3: Test Strategy

### Pattern: real-fixture contract test

The test loads the fixture file using `pathlib.Path`, parses it identically to how `rework_warning.py` parses real git log output, and asserts:

1. `scan.py` appears in the rework warning list (count >= threshold after exclusion pass).
2. No path matching `.agents/memory/episodes/` appears in the rework warning list.

This pattern satisfies testing-007-contract-testing: the mock input structure matches the production input shape because it IS the production input, captured and saved.

### Test file layout

```
tests/skills/session-end/
    fixtures/
        orphan_ref_validator_git_log.txt   # TASK-010-01
    test_rework_warning.py                 # extended in TASK-010-02
```

### Test cases to add

| Test name | Fixture used | Assertion |
|---|---|---|
| `test_excludes_episode_logs_real_fixture` | `orphan_ref_validator_git_log.txt` | episode path absent from output; scan.py present |
| (existing tests) | (unchanged) | continue passing |

### Coverage target

Detection logic (the exclusion filter and the threshold comparison) is treated as a critical path. 100% branch coverage is required per testing-004-coverage-pragmatism.

### Self-apply gate (REQ-010-03)

Before the milestone commit, the implementer runs:

```
python3 .claude/skills/session-end/scripts/rework_warning.py
```

against the working branch and pastes the output into the PR description. At least one warning line must appear. A zero-output result blocks the commit.

## Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Fixture format | Raw git log stdout (text) | Matches production input; no transformation needed |
| Fixture location | `tests/skills/session-end/fixtures/` | Collocated with test; canonical location per project layout |
| Threshold value | Preserve at 6 | Empirically correct; chestertons-fence satisfied with calibration data |
| Mirror update mechanism | `build_all.py` regeneration | Canonical-source-mirror rule; never hand-edit generated file |

## Security Considerations

The rework warning script invokes `git log` via subprocess. Argument vectors are constructed from constants and branch names resolved by the calling shell, not from user-supplied strings. CWE-78 (command injection) risk is low; the argv pattern is already in use. The test suite stubs the subprocess call; no subprocess is invoked during `pytest` runs.

## Open Questions

None blocking. The following are deferred:

- Per-extension thresholds (e.g., lower threshold for `.json` files). Tracked in issue backlog.
- Expanding calibration sample to 10+ branches. Deferred; 4-branch sample is sufficient for the current fix.
- Auto-detection of extension-specific exclusion rules. Deferred.
