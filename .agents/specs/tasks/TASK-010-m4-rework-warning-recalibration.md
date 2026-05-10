---
type: task
id: TASK-010
title: M4 rework warning recalibration
status: todo
priority: P1
complexity: XS
estimate: 1.25h
related:
  - DESIGN-010
  - REQ-010
blocked_by: []
blocks: []
assignee: ""
created: 2026-05-10
updated: 2026-05-10
---

# TASK-010: M4 Rework Warning Recalibration

## Objective

Fix the M4 rework detector's exclusion list and pin its contract with a real-fixture test. Four atomic commits, each within the 5-file budget, totalling approximately 75 minutes.

## In Scope

- Capturing the orphan-ref-validator branch git log as a test fixture
- Writing a contract test that loads the real fixture
- Adding `.agents/memory/episodes/` to `_REWORK_EXCLUDED_PREFIXES` in the canonical script
- Running the self-apply gate and regenerating the mirror

## Out of Scope

- Changing `REWORK_THRESHOLD` (calibration shows it is correct at 6)
- Per-extension thresholds
- Mirror deduplication
- Expanding the calibration sample beyond the 4 sampled branches

## Acceptance Criteria

- [ ] All four REQ-010 acceptance criteria pass
- [ ] pytest reports 0 failures on `tests/skills/session-end/test_rework_warning.py`
- [ ] At least one warning line appears when M4 runs against the working branch before the milestone commit
- [ ] The mirror file `src/copilot-cli/skills/session-end/scripts/rework_warning.py` is regenerated (not hand-edited) to include the new prefix

---

## TASK-010-01: Capture real-branch git log fixture

**Complexity**: S | **Estimate**: ~15 min | **AC**: REQ-010-04

### Objective

Run git log against the `feat/issue-1939-orphan-ref` branch, capture the per-file edit-count output, and save it as a text fixture.

### Files Affected

| File | Action | Description |
|---|---|---|
| `tests/skills/session-end/fixtures/orphan_ref_validator_git_log.txt` | Create | Raw git log output from orphan-ref-validator branch |

### Implementation Notes

Run the following command (or the exact equivalent used in `rework_warning.py` to enumerate file counts) against the `feat/issue-1939-orphan-ref` branch:

```
git log --follow --name-only --format="" origin/main..feat/issue-1939-orphan-ref | grep -v '^$' | sort | uniq -c | sort -rn
```

Save stdout verbatim to the fixture file. Verify the file contains at minimum:
- A line with count >= 19 referencing an `episode-*.json` path
- A line with count >= 14 referencing `scan.py`

If the branch has been rebased or deleted, reconstruct from PR #1989 diff data or any surviving ref. The fixture must contain the two sentinel values above; the exact line format must match what `rework_warning.py` actually parses.

Commit message: `test(session-end): capture orphan-ref-validator git log fixture`

### Testing Requirements

No automated test covers this task directly. Manual verification: open the saved file and confirm the two sentinel lines are present.

---

## TASK-010-02: TDD - write failing contract test

**Complexity**: S | **Estimate**: ~30 min | **AC**: REQ-010-01, REQ-010-04 | **Blocked by**: TASK-010-01

### Objective

Add `test_excludes_episode_logs_real_fixture` to the existing test file. The test MUST fail before TASK-010-03 lands (the exclusion prefix is not yet present).

### Files Affected

| File | Action | Description |
|---|---|---|
| `tests/skills/session-end/test_rework_warning.py` | Modify | Add one test case using the fixture from TASK-010-01 |

### Implementation Notes

The test structure:

```python
def test_excludes_episode_logs_real_fixture(monkeypatch):
    fixture_path = Path(__file__).parent / "fixtures" / "orphan_ref_validator_git_log.txt"
    raw_output = fixture_path.read_text()

    # Stub subprocess to return the captured fixture
    monkeypatch.setattr(
        "skills.session_end.scripts.rework_warning.subprocess.check_output",
        lambda *args, **kwargs: raw_output.encode(),
    )

    warnings = collect_rework_warnings()  # or equivalent public entry point

    warned_paths = [w.path for w in warnings]
    assert any("scan.py" in p for p in warned_paths), "scan.py must appear in rework warnings"
    assert not any("episodes" in p for p in warned_paths), "episode logs must be excluded"
```

Adjust import paths and function names to match the actual module structure. Run `pytest tests/skills/session-end/test_rework_warning.py -k test_excludes_episode_logs_real_fixture` and confirm the test fails with an assertion error on the `episodes` check (because the prefix is not yet excluded).

Commit message: `test(session-end): add real-fixture contract test for episode exclusion [RED]`

### Testing Requirements

- Test must fail before TASK-010-03 (TDD red phase)
- Test must pass after TASK-010-03 (TDD green phase)
- No other tests in the file may regress

---

## TASK-010-03: Add episodes prefix to exclusion list (canonical)

**Complexity**: S | **Estimate**: ~15 min | **AC**: REQ-010-02 | **Blocked by**: TASK-010-02

### Objective

Add `.agents/memory/episodes/` to `_REWORK_EXCLUDED_PREFIXES` in the canonical script. The test from TASK-010-02 turns green.

### Files Affected

| File | Action | Description |
|---|---|---|
| `.claude/skills/session-end/scripts/rework_warning.py` | Modify | Append `.agents/memory/episodes/` to `_REWORK_EXCLUDED_PREFIXES` |

### Implementation Notes

Read the file first. Locate `_REWORK_EXCLUDED_PREFIXES`. Append the new string to the tuple. Preserve trailing comma and existing formatting. Do not change any other lines.

Before:
```python
_REWORK_EXCLUDED_PREFIXES = (
    ".agents/sessions/",
    "src/claude/",
    # ... existing entries ...
)
```

After:
```python
_REWORK_EXCLUDED_PREFIXES = (
    ".agents/sessions/",
    "src/claude/",
    # ... existing entries ...
    ".agents/memory/episodes/",
)
```

Run `pytest tests/skills/session-end/test_rework_warning.py` and confirm all tests pass, including the test added in TASK-010-02.

Canonical-source-mirror rule: this edit goes to the canonical file only. TASK-010-04 regenerates the mirror.

Commit message: `fix(session-end): add .agents/memory/episodes/ to rework exclusion list`

### Testing Requirements

- `test_excludes_episode_logs_real_fixture` must pass (TDD green)
- Full test file must pass with 0 failures

---

## TASK-010-04: Self-apply gate and mirror regeneration

**Complexity**: S | **Estimate**: ~15 min | **AC**: REQ-010-03 | **Blocked by**: TASK-010-03

### Objective

Run M4 against the current branch to confirm at least one warning fires. Regenerate the mirror via `build_all.py`. Paste the self-apply output into the PR description.

### Files Affected

| File | Action | Description |
|---|---|---|
| `src/copilot-cli/skills/session-end/scripts/rework_warning.py` | Modify (generated) | Regenerated by `build_all.py`; gains the episodes prefix |

### Implementation Notes

Step 1: Run the self-apply gate.

```
python3 .claude/skills/session-end/scripts/rework_warning.py
```

If the output is empty (zero warnings), STOP. The gate has failed. Investigate before proceeding.

If at least one warning line appears, capture the output. It will be pasted verbatim into the PR description under a "Self-apply gate output" heading.

Step 2: Regenerate the mirror.

```
python3 build/scripts/build_all.py
```

(or the equivalent generator script; confirm the correct invocation by checking `build/` contents).

Step 3: Run `git status` and confirm only the mirror file changed under `src/copilot-cli/`. If the generator touched unrelated files, inspect and revert those before staging. (This is the generator-isolation memory constraint.)

Step 4: Commit only the mirror file.

Commit message: `feat(session-end): regen mirror with episodes exclusion + self-apply gate evidence`

### Testing Requirements

- Self-apply gate must emit at least one warning line (binary gate: pass or stop)
- Mirror file must diff only at the `_REWORK_EXCLUDED_PREFIXES` addition
- Full test suite must continue to pass after regeneration

---

## Traceability

| Task | Implements | Acceptance Criterion |
|---|---|---|
| TASK-010-01 | DESIGN-010 Section 2 (fixture path) | REQ-010-04 |
| TASK-010-02 | DESIGN-010 Section 3 (test strategy) | REQ-010-01, REQ-010-04 |
| TASK-010-03 | DESIGN-010 Section 2 (canonical file) | REQ-010-02 |
| TASK-010-04 | DESIGN-010 Section 2 (mirror + self-apply) | REQ-010-03 |

## Effort Summary

| Task | Complexity | Estimate |
|---|---|---|
| TASK-010-01 | S | ~15 min |
| TASK-010-02 | S | ~30 min |
| TASK-010-03 | S | ~15 min |
| TASK-010-04 | S | ~15 min |
| **Total** | **4 x S** | **~75 min** |
