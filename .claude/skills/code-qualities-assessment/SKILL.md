---
name: code-qualities-assessment
version: 1.0.0
model: claude-sonnet-4-5
description: Assess code maintainability through 5 foundational qualities (cohesion, coupling, encapsulation, testability, non-redundancy) with quantifiable scoring rubrics. Works at method/class/module levels across multiple languages. Produces markdown reports with remediation guidance.
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

```python
# Assess a single file
python3 scripts/assess.py --target src/services/auth.py

# Assess changed files only (CI mode)
python3 scripts/assess.py --target . --changed-only --format json

# Full module assessment with HTML report
python3 scripts/assess.py --target src/services/ --format html --output quality-report.html
```text

---

## The 5 Code Qualities

### 1. Cohesion

#### How strongly related are responsibilities within a boundary?

High cohesion = focused, understandable code. Low cohesion = "god objects" doing too much.

- **10**: Single, well-defined responsibility
- **7-9**: Primary responsibility clear, minor supporting concerns
- **4-6**: Multiple loosely related responsibilities
- **1-3**: Unrelated responsibilities jammed together

### 2. Coupling

#### How dependent is this code on other code?

Loose coupling = independent evolution, easy testing. Tight coupling = fragile, hard to test.

- **10**: Minimal dependencies, depends on abstractions
- **7-9**: Few dependencies, all explicit
- **4-6**: Moderate dependencies, some global state
- **1-3**: Tightly coupled, hard-coded dependencies

### 3. Encapsulation

#### How well are implementation details hidden?

Good encapsulation = freedom to change internals. Poor encapsulation = brittle API.

- **10**: All internals private, minimal public API
- **7-9**: Mostly private, well-defined API
- **4-6**: Some internals exposed
- **1-3**: Everything public, no information hiding

### 4. Testability

#### How easily can behavior be verified in isolation?

Testable code = fast feedback, confidence to refactor. Untestable code = fear of change.

- **10**: Pure functions, injected dependencies
- **7-9**: Mostly testable, straightforward to mock
- **4-6**: Moderately testable, requires setup
- **1-3**: Hard to test, requires full integration

### 5. Non-Redundancy

#### How unique is each piece of knowledge?

DRY code = fix once, single source of truth. Duplication = fix N times, maintenance burden.

- **10**: Zero duplication, appropriate abstractions
- **7-9**: Minimal duplication (intentional)
- **4-6**: Moderate duplication, missed abstractions
- **1-3**: Pervasive copy-paste

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

```text
┌─────────────────────────────────────────┐
│ 1. Symbol Extraction                    │
│    • Detect language                    │
│    • Use Serena (if available)          │
│    • Extract classes/methods            │
├─────────────────────────────────────────┤
│ 2. Quality Scoring                      │
│    • Run 5 quality assessments          │
│    • Apply context rules (test vs prod) │
│    • Aggregate symbol → file → module   │
├─────────────────────────────────────────┤
│ 3. Comparison (if historical data)      │
│    • Load previous scores               │
│    • Identify regressions/improvements  │
├─────────────────────────────────────────┤
│ 4. Report Generation                    │
│    • Format: markdown, JSON, or HTML    │
│    • Include remediation guidance       │
│    • Link to refactoring patterns       │
├─────────────────────────────────────────┤
│ 5. Gate Enforcement (CI mode)           │
│    • Check thresholds                   │
│    • Exit code: 0=pass, 10=degraded     │
└─────────────────────────────────────────┘
```text

---

## Command Reference

### Basic Usage

```text
python3 scripts/assess.py --target <path> [options]
```text

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--target` | Yes | - | File, directory, or glob pattern |
| `--context` | No | production | production\|test\|generated |
| `--changed-only` | No | false | Only assess changed files (git diff) |
| `--format` | No | markdown | markdown\|json\|html |
| `--config` | No | .qualityrc.json | Path to config file |
| `--output` | No | stdout | Output file path |
| `--use-serena` | No | auto | auto\|yes\|no (Serena integration) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Assessment complete, all thresholds met |
| 10 | Quality degraded vs previous run |
| 11 | Quality below configured thresholds |
| 1 | Script error (invalid args, file not found) |

---

## Configuration

Create `.qualityrc.json` to customize thresholds:

```json
{
  "thresholds": {
    "cohesion": { "min": 7, "warn": 5 },
    "coupling": { "max": 3, "warn": 5 },
    "encapsulation": { "min": 7, "warn": 5 },
    "testability": { "min": 6, "warn": 4 },
    "nonRedundancy": { "min": 8, "warn": 6 }
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
```text

---

## Examples

### Example 1: Single File Assessment

```text
python3 scripts/assess.py --target src/models/user.py
```text

#### Output:

```python
# Code Quality Assessment: src/models/user.py

## Summary
- **Cohesion**: 8/10 ✅
- **Coupling**: 4/10 ⚠️
- **Encapsulation**: 9/10 ✅
- **Testability**: 7/10 ✅
- **Non-Redundancy**: 9/10 ✅

## Issues Found

### Coupling: 4/10 (Warning)
**Problem**: Direct instantiation of DatabaseConnection in constructor

**Impact**: Hard to test, tightly coupled to database layer

**Remediation**: Use dependency injection
- See: [references/patterns/dependency-injection.md](references/patterns/dependency-injection.md)
- Related ADR: ADR-023 (Dependency Management)

**Example Fix**:
\`\`\`python
# Before
class User:
    def __init__(self):
        self.db = DatabaseConnection()  # Hard-coded dependency

# After
class User:
    def __init__(self, db: DatabaseInterface):
        self.db = db  # Injected dependency
\`\`\`
```text

### Example 2: CI Integration

```python
# In CI pipeline
python3 scripts/assess.py --target . --changed-only --format json --output quality.json

# Exit code 10 = quality degraded → fail PR
# Exit code 0 = quality maintained → pass
```text

### Example 3: Full Codebase Report

```text
python3 scripts/assess.py --target src/ --format html --output reports/quality.html
```text

Opens dashboard showing:

- Quality trends over time
- Hot spots (lowest scoring files)
- Improvement opportunities
- Top refactoring priorities

---

## Integration with Other Skills

### With `planner`

```python
# Identify refactoring targets
python3 scripts/assess.py --target src/ --format json | \
  jq '.files | sort_by(.overall) | .[0:5]' > low-quality-files.json

# Feed to planner
planner --input low-quality-files.json --goal "Refactor lowest quality files"
```text

### With `adr-review`

When reviewing ADRs, include quality impact:

```python
# Before implementing ADR
python3 scripts/assess.py --target affected-files.txt > baseline.md

# After implementing ADR
python3 scripts/assess.py --target affected-files.txt > post-implementation.md

# Compare
diff baseline.md post-implementation.md
```text

### With `analyze`

Combine broad analysis with focused quality metrics:

```python
# First: broad exploration
analyze --target src/

# Then: quality deep dive on problem areas
python3 scripts/assess.py --target src/services/auth.py
```text

---

## Deep Dives

For detailed scoring methodology and examples:

- [Cohesion Scoring](references/cohesion-scoring.md)
- [Coupling Scoring](references/coupling-scoring.md)
- [Encapsulation Scoring](references/encapsulation-scoring.md)
- [Testability Scoring](references/testability-scoring.md)
- [Non-Redundancy Scoring](references/nonredundancy-scoring.md)
- [Calibration Examples](references/calibration-examples.md)
- [Refactoring Patterns](references/refactoring-patterns.md)

---

## Language Support

### Fully Supported

- Python (.py)
- TypeScript/JavaScript (.ts, .js, .tsx, .jsx)
- C# (.cs)
- Java (.java)
- Go (.go)

### Partial Support (heuristic-based)

- Ruby (.rb)
- Rust (.rs)
- PHP (.php)
- Kotlin (.kt)

Serena integration improves accuracy when available.

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Running on entire codebase every commit | Slow, noisy | Use --changed-only in CI |
| Using scores for performance reviews | Gaming the system | Focus on trend improvement |
| Blocking merges on absolute scores | Discourages refactoring old code | Block on regression only |
| Ignoring context (test vs production) | False positives | Use --context flag |
| Not configuring thresholds | One-size-fits-all doesn't fit | Customize .qualityrc.json |

---

## Verification

After running assessment:

- [ ] All 5 qualities scored for each symbol
- [ ] Scores are 1-10 (not null or out of range)
- [ ] Remediation links provided for low scores
- [ ] Report format is valid (markdown/JSON/HTML)
- [ ] Exit code matches assessment result
- [ ] Historical data saved to .quality-cache/

---

## Programming by Intention

This skill embodies the "sergeant methods directing privates" pattern:

**Sergeant (assess.py)**: Orchestrates workflow, delegates to specialists
**Privates (score_*.py)**: Focus on one quality each, report back

Each quality scorer is cohesive (single responsibility), loosely coupled (independent), and testable (pure calculation).

---

## Timelessness: 9/10

These 5 qualities are computer science fundamentals:

- Cohesion and coupling: 1970s (Parnas, Stevens)
- Encapsulation: Core OOP principle (1960s)
- Testability: TDD movement (1990s-2000s)
- DRY: Pragmatic Programmer (1999)

Language-agnostic design ensures longevity across technology shifts.
