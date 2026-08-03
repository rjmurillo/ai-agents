---
name: code-qualities-assessment
description: Assess code maintainability through 5 foundational qualities (cohesion, coupling, encapsulation, testability, non-redundancy) with quantifiable scoring rubrics. Works at method/class/module levels across multiple languages. Produces markdown reports with remediation guidance. Use when you ask to "assess maintainability", "score cohesion/coupling/testability" on specific code. Do NOT use for a full pre-merge review (use review) or repo-wide domain grading (use quality-grades).
version: 1.1.0
license: MIT
---

# Code Qualities Assessment

Evaluate code maintainability using 5 timeless design qualities with quantifiable scoring rubrics.

## Triggers

- `assess code quality`
- `evaluate maintainability`
- `check code qualities`
- `testability review`
- `run quality assessment`

---

## Quick Start

```bash
# Assess a single file
python3 scripts/assess.py --target src/services/auth.py

# Assess changed files from the PR base (CI mode)
python3 scripts/assess.py --target . --changed-only --base origin/main --format json

# Full module assessment with HTML report
python3 scripts/assess.py --target src/services/ --format html --output quality-report.html
```

---

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/assess.py` | Scores target code across the five quality axes. | `python3 scripts/assess.py --target <path> --format markdown` |

Use `--changed-only` for diff-scoped checks and `--format json` for automation.

---

## The 5 Code Qualities

| Quality | Question | Score 10 | Score 1-3 |
|---------|----------|----------|-----------|
| **Cohesion** | How related are responsibilities? | Single, well-defined responsibility | Unrelated responsibilities jammed together |
| **Coupling** | How dependent on other code? | Minimal deps, depends on abstractions | Tightly coupled, hard-coded dependencies |
| **Encapsulation** | How well are internals hidden? | All internals private, minimal API | Everything public, no information hiding |
| **Testability** | How easily verified in isolation? | Pure functions, injected dependencies | Hard to test, requires full integration |
| **Non-Redundancy** | How unique is each piece of knowledge? | Zero duplication, appropriate abstractions | Pervasive copy-paste |

---

## When to Use

Use this skill when:

- Reviewing code quality before merge
- Identifying refactoring priorities
- Establishing quality baselines
- Teaching code design principles
- Tracking quality trends over time
- Enforcing quality gates in CI

Use [analyze](../analyze/SKILL.md) instead when:

- Performing broad codebase investigation
- Security assessment is the focus
- Architecture review is needed

---

## Process

The skill runs automated assessment via `scripts/assess.py`:

1. **Symbol Extraction**
   - Detect language
   - Use Serena (if available)
   - Extract classes/methods

2. **Quality Scoring**
   - Run 5 quality assessments
   - Apply context rules (test vs prod)
   - Aggregate symbol -> file -> module

3. **Comparison (if historical data)**
   - Load previous scores
   - Identify regressions/improvements

4. **Report Generation**
   - Format: markdown, JSON, or HTML
   - Include remediation guidance
   - Link to refactoring patterns

5. **Gate Enforcement (CI mode)**
   - Regression mode compares each changed file against its base revision
   - Absolute mode compares every assessed file against configured thresholds
   - Exit code: 0=pass, 10=regressed, 11=below thresholds

---

## Command Reference

### Basic Usage

```bash
python3 scripts/assess.py --target <path> [options]
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--target` | Yes | - | File, directory, or glob pattern |
| `--context` | No | production | production, test, or generated |
| `--changed-only` | No | false | Only assess changed files (git diff) |
| `--base` | No | - | Base revision for `--changed-only`, such as origin/main |
| `--gate-mode` | No | auto | auto, regression, or absolute (see Gate Modes) |
| `--regression-tolerance` | No | 0.5 | Score drop tolerated before a quality counts as regressed |
| `--format` | No | markdown | markdown, json, or html |
| `--config` | No | .qualityrc.json | Path to config file |
| `--output` | No | stdout | Output file path |
| `--use-serena` | No | auto | auto, yes, or no (Serena integration) |

### Gate Modes

The gate answers one of two questions. Pick the one your caller actually asks.

| Mode | Question | Selected when |
|------|----------|---------------|
| `regression` | Did this change make anything worse? | `--gate-mode regression`, or `auto` with both `--changed-only` and `--base` |
| `absolute` | Is this code above the configured thresholds? | `--gate-mode absolute`, or `auto` otherwise |

`--gate-mode regression` requires both `--changed-only` and `--base`, and exits 1
without them. It never silently falls back to absolute thresholds: that fallback
is exactly how a gate advertised as regression-only ends up blocking on inherited
debt.

In regression mode, each changed file is scored twice, once at the merge base of
`--base` and HEAD through `git show` and once at head, using the same scoring
code. The merge base, not the tip of `--base`: file selection is
`git diff base...HEAD`, which git resolves from the merge base, so reading
content at the tip would score the branch against commits that landed on the
base branch after the fork. Qualities are compared
independently and only where both revisions scored them (confidence above 0.0),
so a file whose scored-quality set changed is never compared against a different
set. Aggregate averages are never compared. A quality that goes from scored to
unscored counts as evidence loss and fails, unless the file is now a generated
artifact. A quality that goes from unscored to scored is reported with no delta.
A file absent at the merge base is new, has no delta, and is gated absolutely. A
file the assessor cannot decode as UTF-8 at the merge base (a binary, a
latin-1 source) scores nothing there, so every quality reads as newly scored and
no delta is invented from content it could not read.

Every score is size-derived, so adding one small function moves a quality by a
few tenths with nothing wrong. `--regression-tolerance` defaults to 0.5 for that
reason: measured, one 2-line function added to a 5-function module drops cohesion
8.7 to 8.3, while a real degradation moves whole points. Pass `0.0` to gate on
any drop at all.

Growth costs more than the tolerance absorbs, and cohesion is where it shows.
The score is `10 - LOC/120 - 0.3 * (definitions - 1)` at confidence 0.4, so a
file that gains three functions and 100 lines loses about 1.7 points whether or
not anything got worse. A test module gaining tests hits this every time. Read
the named delta before acting on an exit 10: this heuristic cannot tell growth
from decay, and a file that grew for a good reason is the common case.

The JSON report carries `gate_mode` and a `comparisons` array with per-quality
`base`, `head`, `delta`, and `status`.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Gate passed |
| 10 | Regression mode: a comparable quality regressed, or scored evidence was lost |
| 11 | Below configured thresholds (absolute mode, or a new file in regression mode) |
| 1 | Script error (invalid args, unresolvable base, file not found) |

---

## Configuration

Create `.qualityrc.json` to customize thresholds:

```json
{
  "thresholds": {
    "cohesion": { "min": 7 },
    "coupling": { "min": 7 },
    "encapsulation": { "min": 7 },
    "testability": { "min": 6 },
    "nonRedundancy": { "min": 8 }
  },
  "context": {
    "test": {
      "testability": { "min": 3 }
    }
  },
  "ignore": [
    "**/generated/**",
    "**/*.pb.py",
    "**/migrations/**"
  ]
}
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Running on entire codebase every commit | Slow, noisy | Use --changed-only in CI |
| Using scores for performance reviews | Gaming the system | Focus on trend improvement |
| Blocking merges on absolute scores | Discourages refactoring old code | Run `--gate-mode regression` with `--changed-only --base` |
| Ignoring context (test vs production) | False positives | Use --context flag |
| Not configuring thresholds | One-size-fits-all does not fit | Customize .qualityrc.json |

---

## Verification

After running assessment, run the bundled validator and require exit 0:

```bash
python3 .claude/skills/code-qualities-assessment/scripts/assess.py --target "$TARGET_PATH"
echo "exit=$?"   # must be 0; 10 = regressed, 11 = thresholds not met, 1 = script error
```

- [ ] `assess.py` exited 0 (10 = regressed; 11 = thresholds not met; 1 = script error; none is a pass)
- [ ] All 5 qualities scored for each symbol
- [ ] Scores are 1-10 (not null or out of range)
- [ ] Remediation links provided for low scores
- [ ] Report format is valid (markdown/JSON/HTML)
- [ ] Historical data saved to .quality-cache/

---

<details>
<summary><strong>Deep Dive: Scoring Rubrics</strong></summary>

### Cohesion

How strongly related are responsibilities within a boundary?

High cohesion = focused, understandable code. Low cohesion = "god objects" doing too much.

| Score | Description |
|-------|-------------|
| 10 | Single, well-defined responsibility |
| 7-9 | Primary responsibility clear, minor supporting concerns |
| 4-6 | Multiple loosely related responsibilities |
| 1-3 | Unrelated responsibilities jammed together |

### Coupling

How dependent is this code on other code?

Loose coupling = independent evolution, easy testing. Tight coupling = fragile, hard to test.

| Score | Description |
|-------|-------------|
| 10 | Minimal dependencies, depends on abstractions |
| 7-9 | Few dependencies, all explicit |
| 4-6 | Moderate dependencies, some global state |
| 1-3 | Tightly coupled, hard-coded dependencies |

### Encapsulation

How well are implementation details hidden?

Good encapsulation = freedom to change internals. Poor encapsulation = brittle API.

| Score | Description |
|-------|-------------|
| 10 | All internals private, minimal public API |
| 7-9 | Mostly private, well-defined API |
| 4-6 | Some internals exposed |
| 1-3 | Everything public, no information hiding |

### Testability

How easily can behavior be verified in isolation?

Testable code = fast feedback, confidence to refactor. Untestable code = fear of change.

| Score | Description |
|-------|-------------|
| 10 | Pure functions, injected dependencies |
| 7-9 | Mostly testable, straightforward to mock |
| 4-6 | Moderately testable, requires setup |
| 1-3 | Hard to test, requires full integration |

### Non-Redundancy

How unique is each piece of knowledge?

DRY code = fix once, single source of truth. Duplication = fix N times, maintenance burden.

| Score | Description |
|-------|-------------|
| 10 | Zero duplication, appropriate abstractions |
| 7-9 | Minimal duplication (intentional) |
| 4-6 | Moderate duplication, missed abstractions |
| 1-3 | Pervasive copy-paste |

</details>

<details>
<summary><strong>Deep Dive: Examples</strong></summary>

### Example 1: Single File Assessment

```bash
python3 scripts/assess.py --target src/models/user.py
```

Output:

```markdown
# Code Quality Assessment: src/models/user.py

## Summary
- **Cohesion**: 8/10
- **Coupling**: 4/10
- **Encapsulation**: 9/10
- **Testability**: 7/10
- **Non-Redundancy**: 9/10

## Issues Found

### Coupling: 4/10 (Warning)
**Problem**: Direct instantiation of DatabaseConnection in constructor

**Impact**: Hard to test, tightly coupled to database layer

**Remediation**: Use dependency injection
- See: [Refactoring Patterns](references/refactoring-patterns.md)
- Related ADR: ADR-023 (Dependency Management)
```

**Example Fix:**

```python
# Before
class User:
    def __init__(self):
        self.db = DatabaseConnection()  # Hard-coded dependency

# After
class User:
    def __init__(self, db: DatabaseInterface):
        self.db = db  # Injected dependency
```

### Example 2: CI Integration

```bash
# In CI pipeline. --changed-only with --base selects regression mode.
python3 scripts/assess.py --target . --changed-only --base origin/main \
  --format json --output quality.json

# Exit code 0  = nothing this change touched got worse, pass
# Exit code 10 = a comparable quality regressed, fail PR
# Exit code 11 = a file added by this change is below thresholds, fail PR
```

### Example 3: Full Codebase Report

```bash
python3 scripts/assess.py --target src/ --format html --output reports/quality.html
```

Opens dashboard showing:

- Quality trends over time
- Hot spots (lowest scoring files)
- Improvement opportunities
- Top refactoring priorities

</details>

<details>
<summary><strong>Deep Dive: Integration with Other Skills</strong></summary>

### With planner

```bash
# Identify refactoring targets
python3 scripts/assess.py --target src/ --format json | \
  jq '.files | sort_by(.overall) | .[0:5]' > low-quality-files.json

# Feed to planner
planner --input low-quality-files.json --goal "Refactor lowest quality files"
```

### With adr-review

When reviewing ADRs, include quality impact:

```bash
# Before implementing ADR
python3 scripts/assess.py --target affected-files.txt > baseline.md

# After implementing ADR
python3 scripts/assess.py --target affected-files.txt > post-implementation.md

# Compare
diff baseline.md post-implementation.md
```

### With analyze

Combine broad analysis with focused quality metrics:

```bash
# First: broad exploration
analyze --target src/

# Then: quality deep dive on problem areas
python3 scripts/assess.py --target src/services/auth.py
```

</details>

<details>
<summary><strong>Deep Dive: Scoring References</strong></summary>

For detailed methodology and examples:

- [Calibration Examples](references/calibration-examples.md)
- [Refactoring Patterns](references/refactoring-patterns.md)
- [Dotnet Performance Patterns](references/dotnet-performance-patterns.md)

</details>

---

## References

| File | Content |
|------|---------|
| [dotnet-performance-patterns.md](references/dotnet-performance-patterns.md) | Allocation-free .NET patterns with quality scoring calibration |

---

## Language Support

| Support Level | Languages |
|---------------|-----------|
| Full | Python (.py), TypeScript/JavaScript (.ts, .js, .tsx, .jsx), C# (.cs), Java (.java), Go (.go) |
| Partial (heuristic) | Ruby (.rb), Rust (.rs), PHP (.php), Kotlin (.kt) |

Serena integration improves accuracy when available.

---

## Design Philosophy

This skill embodies "sergeant methods directing privates":

- **Sergeant (assess.py)**: Orchestrates workflow, delegates to specialists
- **Privates (score_*.py)**: Focus on one quality each, report back

Each quality scorer is cohesive (single responsibility), loosely coupled (independent), and testable (pure calculation).

### Timelessness: 9/10

These 5 qualities are computer science fundamentals:

- Cohesion and coupling: 1970s (Parnas, Stevens)
- Encapsulation: Core OOP principle (1960s)
- Testability: TDD movement (1990s-2000s)
- DRY: Pragmatic Programmer (1999)

Language-agnostic design ensures longevity across technology shifts.
