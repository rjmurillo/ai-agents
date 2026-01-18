# Review: Python Implicit String Concat

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