# Implementation: Proactive Linting During File Creation 92

## Skill-Implementation-003: Proactive Linting During File Creation (92%)

**Statement**: Run linters during file creation, not after implementation, to catch formatting issues early

**Context**: File creation workflow in multi-file implementations

**Trigger**: After creating or modifying markdown, YAML, or other lintable files

**Evidence**: Session 03 (2025-12-18): 7 MD040 errors caught post-implementation; all could have been prevented with immediate linting after file creation. Retrospective explicitly recommended this as process improvement.

**Atomicity**: 92%

- Specific action (run linters) ✓
- Single concept (timing of linting) ✓
- Actionable (trigger after Write) ✓
- Measurable (verify linter ran after each file) ✓
- Minor vagueness on "formatting issues" (-8%)

**Impact**: 7/10 - Prevents cosmetic fix commits

**Category**: Quality Workflow

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (AI Workflow Implementation session)

**Pattern**:

```bash
# After creating markdown file
npx markdownlint-cli2 path/to/file.md --fix

# After creating YAML workflow
actionlint .github/workflows/new-workflow.yml
```

---

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-001-preimplementation-test-discovery-95](implementation-001-preimplementation-test-discovery-95.md)
- [implementation-001-preimplementation-test-discovery](implementation-001-preimplementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
