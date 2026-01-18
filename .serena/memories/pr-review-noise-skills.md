# PR Review Noise Skills

## Skill-Review-001: CodeRabbit Sparse Checkout Blindness

**Statement**: CodeRabbit sparse checkout blindness causes false positives for .agents/ files

**Context**: When CodeRabbit flags .agents/ files as missing, verify existence with `git ls-tree HEAD .agents/`

**Evidence**: PR #20 had 3 false positives due to sparse checkout pattern `!.agents/**`

**Atomicity**: 95%

**Tag**: helpful for pr-comment-responder agent

---

## Skill-Review-002: Python Implicit String Concat False Positives

**Statement**: Dismiss Python implicit string concat warnings from Copilot as false positives

**Context**: Adjacent string literals are valid Python per PEP 3126

**Evidence**: PR #20 Copilot flagged `r"pattern1" r"pattern2"` as missing comma

**Atomicity**: 92%

**Tag**: helpful for pr-comment-responder agent

---

## PR-20 Review Metrics

- **Total comments**: 19
- **False positive rate**: 47%
- **Signal-to-noise**: 42% actionable
- **Author time on dismissals**: 67%

## Configuration Recommendations

1. Create `.coderabbit.yaml` with path exclusions
2. Add sparse checkout documentation to PR template
3. Consider disabling CodeRabbit for `.agents/` directory

## Related

- [pr-review-001-reviewer-enumeration](pr-review-001-reviewer-enumeration.md)
- [pr-review-002-independent-comment-parsing](pr-review-002-independent-comment-parsing.md)
- [pr-review-003-verification-count](pr-review-003-verification-count.md)
- [pr-review-006-reviewer-signal-quality](pr-review-006-reviewer-signal-quality.md)
- [pr-review-007-ci-verification](pr-review-007-ci-verification.md)
