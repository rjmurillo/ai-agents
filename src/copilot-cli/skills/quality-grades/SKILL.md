---
name: quality-grades
version: 1.0.0
model: claude-sonnet-4-6
description: Grade each product domain and architectural layer with A-F scoring and gap tracking. Produces markdown or JSON reports showing grades, file counts, gaps, and trends. Use when you ask "grade quality", "audit domain quality", "show quality gaps", "domain quality report", or "run quality grades" across a repo. Use for repo-wide A-F domain grading and trend tracking. Do NOT use for single-file maintainability scoring (use code-qualities-assessment) or a pre-merge review (use review). For the agent form, use quality-auditor.
license: MIT
---

# Quality Grades

Grade each product domain and architectural layer. Track gaps over time.

<!-- vendor-portability: declared. The docs layer of the grader scans the consumer's docs/ and .agents/ for documentation coverage, and the skills layer reads .claude/skills/*/SKILL.md. These are scan targets, not preconditions: a vendored install without .agents/ grades the docs layer on whatever documentation the consumer repo has rather than failing. Issue #2050. -->

## Triggers

- `grade quality`
- `audit domain quality`
- `show quality gaps`
- `run quality grades`
- `domain quality report`

---

## Process

1. **Detect domains**: `grade_domains.py` auto-detects product domains from the repo layout (or use `--domains` to scope).
2. **Grade layers**: each domain is scored A-F across six architectural layers (agents, skills, scripts, tests, docs, workflows), with gaps tagged critical, significant, or minor.
3. **Report**: emit markdown or JSON; with `--output`, the script loads prior JSON to compute per-domain trends (improving, stable, degrading, new).
4. **Act**: address critical gaps first; rerun to track movement.

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

After execution, run the bundled validator and require exit 0:

```bash
python3 .claude/skills/quality-grades/scripts/grade_domains.py --output quality-grades.md
echo "exit=$?"   # must be 0; exit 2 means no domains detected (report is empty)
```

- [ ] `grade_domains.py` exited 0 (non-zero = no domains; the report is not valid)
- [ ] Each domain has grades for all six layers
- [ ] Gaps include actionable descriptions

## Scripts

| Script | Purpose | Exit codes |
|---|---|---|
| `scripts/grade_domains.py` | Grade detected domains across six layers; supports `--domains`, `--format`, `--output`, `--top-n`. | `0` success; `2` no domains detected (report is empty). |
| `scripts/check_grade_changes.py` | Compare current grades against a degradation threshold and open a GitHub issue when domains degrade or hit critical. | `0` no degradation; `1` script error or degradation detected. |

## References

| File | Content |
|------|---------|
| `references/code-qualities.md` | Five foundational qualities (cohesion, coupling, DRY, encapsulation, testability) with diagnostics |
| `references/solid-principles.md` | SOLID overview, violation signs, mapping to code qualities, grading application |
| `references/kiss-principle.md` | Simplicity principles, KISS vs YAGNI, complexity justification criteria |
