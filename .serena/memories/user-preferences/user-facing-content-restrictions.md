<!-- placement: evidence; reason: the PR #212 review finding that produced the internal-reference rule, kept as the incident rather than the rule -->

# Evidence: Internal References Reached User-Facing Files in PR #212

Authoritative owners: `.claude/rules/claude-agents.md` MUST-5 forbids internal
references under `src/claude/`, `AGENTS.md` carries the always-on "Never:
internal refs" line, and the vendor portability scan enforces it.

## Observation (2025-12-20, PR #212 review)

Agent-facing tables shipped to downstream installers carried repository-local
context a reader outside the repository cannot resolve: pull request numbers,
issue numbers, session identifiers, and `.agents/` or `.serena/` paths.

The reviewed line:

```markdown
| **Security** | ... | Security issues can cause critical damage; CWE-20/CWE-78 introduced in PR #60 went undetected until PR #211 quality gate |
```

and the accepted replacement:

```markdown
| **Security** | ... | Security issues can cause critical damage if missed during review |
```

The claim survives the rewrite. Only the unresolvable citation goes.

## The distinction that mattered

A public standard identifier such as CWE-20 or CWE-78 stayed, because a reader
outside the repository can resolve it. The test is resolvability by the
downstream reader, not whether the reference is a number.

## Related

- [decision-plugin-descriptions-carry-no-counts](../decision-plugin-descriptions-carry-no-counts.md)
- [validation/validation-portability-scan-contract](../validation/validation-portability-scan-contract.md)
