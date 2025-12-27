# Skill-Labeler-006: Negation Pattern Isolation

**Statement**: Separate negation patterns into dedicated `all-globs-to-all-files` matcher within `all:` block.

**Evidence**: Working pattern from PR #229 (dae9db1):

- Positive patterns: `any-glob-to-any-file: ["**/*.md"]`
- Negative patterns: `all-globs-to-all-files: ["!.agents/**/*.md", "!.serena/**/*.md"]`
- Combined with `all:` block for AND logic

**Atomicity**: 92%

**Anti-Pattern**: Mixing negation and inclusion in same matcher block
