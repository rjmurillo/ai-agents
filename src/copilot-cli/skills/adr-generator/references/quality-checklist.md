# ADR Quality Checklist

Self-validation checklist for Phase G4. All items must pass before saving the ADR.

## Structural Completeness

- [ ] All required sections present (based on template detected in Phase G2)
- [ ] ADR number is unique (no collision with existing files in the destination directory)
- [ ] Title is descriptive and kebab-slug matches filename
- [ ] File follows naming convention detected in Phase G2 (e.g., `ADR-NNN-title-slug.md` or `0NNN-title-slug.md`)
- [ ] Status is `Proposed` (not `Accepted` — that requires `adr-review`)
- [ ] Date is in YYYY-MM-DD format

## Content Quality

- [ ] Context explains the problem, not the solution
- [ ] Decision is stated unambiguously in active voice
- [ ] At least 2 alternatives considered with pros/cons table
- [ ] Consequences include at least 1 positive and 1 negative (honest trade-off)
- [ ] Implementation notes provide actionable guidance
- [ ] References include related ADRs using relative paths

## Conditional Sections

- [ ] Prior Art Investigation included if changing an existing system
- [ ] Impact on Dependent Components included if changing canonical source files
- [ ] Agent-Specific Fields included if this is an agent ADR (overlap analysis, entry criteria, limitations, success metrics)

## Governance

- [ ] No duplication with existing ADRs (checked via scan in Phase G2)
- [ ] File saved to destination directory determined in Phase G2
- [ ] Language is precise, avoids ambiguity, uses active voice
- [ ] No sycophancy, AI filler phrases, or hedging language
