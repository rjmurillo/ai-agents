# Golden Principles

Mechanically enforced invariants for the ai-agents repository.
Each principle has a unique ID, rationale, enforcement mechanism, and exception process.

Inspired by [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/):

> "We started encoding what we call 'golden principles' directly into the repository
> and built a recurring cleanup process."

## How to Use

1. Reference by ID (e.g., GP-001) in PRs, ADRs, and commit messages.
2. Run `python3 .claude/skills/golden-principles/scripts/scan_principles.py` to check compliance.
3. Violations include remediation instructions agents can act on directly.

## Principles

### GP-001: Python for New Scripts

New automation scripts MUST use Python. No new `.sh` or `.bash` files.
PowerShell is grandfathered for existing scripts only.

- **Rationale**: ADR-042 standardized on Python for cross-platform consistency and testability.
- **Enforcement**: `scan_principles.py` rule `script-language`
- **Exception**: Add `# golden-principle: ignore script-language` in file header with justification.

### GP-002: Atomic Commits

Each commit addresses a single logical change with 5 or fewer files.

- **Rationale**: Small commits are easier to review, revert, and bisect. Issue #934 retrospective.
- **Enforcement**: Pre-push hook, PR review checklist.
- **Exception**: Large renames or generated files may exceed 5 files with reviewer approval.

### GP-003: Skill Frontmatter Required

Every SKILL.md MUST have valid YAML frontmatter with `name`, `version`, `model`, `description`, and `license`.

- **Rationale**: Consistent metadata enables tooling, discovery, and validation.
- **Enforcement**: `scan_principles.py` rule `skill-frontmatter`
- **Exception**: None. All skills must comply.

### GP-004: Agent Design Compliance

Agent definitions MUST follow the six principles in `agent-design-principles.md`:
non-overlapping specialization, clear entry criteria, explicit limitations,
composability, verifiable success, and consistent interface.

- **Rationale**: Prevents agent sprawl and ensures agents work together.
- **Enforcement**: `scan_principles.py` rule `agent-definition`
- **Exception**: Requires ADR with architect review.

### GP-005: No Logic in YAML

GitHub Actions workflows MUST NOT contain inline logic. Logic belongs in scripts
referenced by workflow steps.

- **Rationale**: ADR-006. YAML logic is untestable, hard to debug, and brittle.
- **Enforcement**: `scan_principles.py` rule `yaml-logic`
- **Exception**: Simple conditionals (`if: github.event_name == 'push'`) are permitted.

### GP-006: Pin Actions to SHA

GitHub Actions MUST reference actions by full SHA, not tags or branches.

- **Rationale**: Tags are mutable. SHA pinning prevents supply-chain attacks.
- **Enforcement**: `scan_principles.py` rule `actions-pinned`
- **Exception**: First-party actions (`actions/checkout`) may use version tags with Dependabot.

### GP-007: Structured Naming

Files follow language-specific naming conventions:
Python = `snake_case`, Skills/YAML = `kebab-case`, PowerShell = `PascalCase`.

- **Rationale**: Consistent naming reduces cognitive load and enables automated tooling.
- **Enforcement**: `taste-lints` skill (rule: `naming`).
- **Exception**: Add `# taste-lint: ignore naming` with justification.

### GP-008: File Size Limits

Source files MUST NOT exceed 500 lines. Warning at 300 lines.

- **Rationale**: Large files indicate poor cohesion. Smaller files are easier to navigate and test.
- **Enforcement**: `taste-lints` skill (rule: `file-size`).
- **Exception**: Add `# taste-lint: ignore file-size` with justification.

## Garbage Collection Cadence

| Frequency | Scan | Action |
|-----------|------|--------|
| Per-commit | Taste lints on staged files | Block commit on errors |
| Per-PR | Full principle scan | Block merge on violations |
| Weekly | Deep scan across all files | Open fix-up issues |

## Adding a New Principle

1. Assign the next GP-NNN ID.
2. Write the principle with rationale, enforcement, and exception process.
3. Add a corresponding rule in `scan_principles.py`.
4. Update this document.
5. Announce in PR description with `golden-principle: new` label.

## Cross-References

- [PROJECT-CONSTRAINTS.md](PROJECT-CONSTRAINTS.md): Operational constraints (superset).
- [agent-design-principles.md](agent-design-principles.md): Agent-specific design rules.
- [taste-lints SKILL.md](../../.claude/skills/taste-lints/SKILL.md): Code-level linting.
- [quality-grades SKILL.md](../../.claude/skills/quality-grades/SKILL.md): Domain grading.
