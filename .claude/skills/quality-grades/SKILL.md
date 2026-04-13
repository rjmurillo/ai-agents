---
name: quality-grades
version: 1.0.0
model: claude-sonnet-4-6
description: Grade quality per product domain and architectural layer with gap tracking. Produces markdown or JSON reports showing grades (A-F), file counts, gaps, and trends over time. Use when auditing repo quality, tracking improvement, or identifying domains that need attention.
license: MIT
---

# Quality Grades

Grade each product domain and architectural layer. Track gaps over time.

## Triggers

- `grade quality`
- `audit domain quality`
- `show quality gaps`
- `run quality grades`
- `domain quality report`

---

## Quick Start

```python
# Grade all auto-detected domains
python3 .claude/skills/quality-grades/scripts/grade_domains.py

# Grade specific domains as JSON
python3 .claude/skills/quality-grades/scripts/grade_domains.py --domains security memory --format json

# Write report to file (enables trend tracking)
python3 .claude/skills/quality-grades/scripts/grade_domains.py --output quality-grades.md

# Show top 10 domains by gap count
python3 .claude/skills/quality-grades/scripts/grade_domains.py --top-n 10
```

---

## Grading Criteria

| Grade | Score | Meaning |
|-------|-------|---------|
| A | 90-100 | Full coverage, no known gaps |
| B | 75-89 | Minor gaps, non-blocking |
| C | 60-74 | Gaps present, should address |
| D | 40-59 | Significant gaps, blocking quality |
| F | 0-39 | Broken or missing |

## Architectural Layers

Each domain is graded across six layers:

| Layer | What it checks |
|-------|---------------|
| agents | Agent definition file completeness |
| skills | SKILL.md presence and structure |
| scripts | Automation scripts with docstrings |
| tests | Test file coverage for the domain |
| docs | Documentation in docs/ and .agents/ |
| workflows | GitHub Actions workflow coverage |

## Gap Severity

| Severity | Meaning |
|----------|---------|
| critical | Missing required artifact (blocks quality) |
| significant | Important gap (should address soon) |
| minor | Nice-to-have improvement |

## Trend Tracking

When `--output` is used, the script loads previous JSON results to compute trends:

| Trend | Meaning |
|-------|---------|
| improving | Score increased by 5+ points |
| stable | Score changed less than 5 points |
| degrading | Score decreased by 5+ points |
| new | No previous data |

---

## When to Use

Use this skill when:

- Starting a quality improvement initiative across multiple domains
- Reporting on repo health to stakeholders
- Identifying which domains need the most attention
- Tracking quality trends over time via repeated runs

Use `code-qualities-assessment` instead when:

- Assessing code-level qualities (cohesion, coupling) for specific files
- Reviewing a single PR or module

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Grading without context | Scores depend on repo structure | Run from repo root |
| Ignoring trends | Single snapshots miss trajectory | Use --output for persistence |
| Treating all F grades equally | Some domains are optional | Focus on domains with critical gaps |

---

## Verification

After execution:

- [ ] Report contains at least one domain
- [ ] Each domain has grades for all six layers
- [ ] Gaps include actionable descriptions
- [ ] Output format matches --format flag

## References

| File | Content |
|------|---------|
| `references/code-qualities.md` | Five foundational qualities (cohesion, coupling, DRY, encapsulation, testability) with diagnostics |
| `references/solid-principles.md` | SOLID overview, violation signs, mapping to code qualities, grading application |
| `references/kiss-principle.md` | Simplicity principles, KISS vs YAGNI, complexity justification criteria |
