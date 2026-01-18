# PR Review: Known False Positives

## Skill-Review-001: CodeRabbit Sparse Checkout Blindness

**Statement**: CodeRabbit flags .agents/ files as missing due to sparse checkout pattern.

**Atomicity**: 95%

**Verify**: `git ls-tree HEAD .agents/`

## Skill-Review-002: Python Implicit String Concat

**Statement**: Dismiss Python implicit string concat warnings as false positives.

**Atomicity**: 92%

Adjacent string literals `r"pattern1" r"pattern2"` are valid Python per PEP 3126.

## Copilot False Positive Patterns

| Pattern | Frequency | Actionability |
|---------|-----------|---------------|
| Unused variable | ~30% | ~20% (often intentional) |
| Style suggestions | ~25% | ~10% (noise) |
| Syntax issues | ~10% | ~90% (usually valid) |

## gemini-code-assist False Positives

| Pattern | Frequency | Actionability |
|---------|-----------|---------------|
| Documentation-as-code | ~40% | 0% (misunderstands docs) |
| Style suggestions | ~30% | ~20% |

## Related

- [pr-review-001-reviewer-enumeration](pr-review-001-reviewer-enumeration.md)
- [pr-review-002-independent-comment-parsing](pr-review-002-independent-comment-parsing.md)
- [pr-review-003-verification-count](pr-review-003-verification-count.md)
- [pr-review-006-reviewer-signal-quality](pr-review-006-reviewer-signal-quality.md)
- [pr-review-007-ci-verification](pr-review-007-ci-verification.md)
