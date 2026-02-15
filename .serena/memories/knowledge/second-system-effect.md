# Second-System Effect

**Category**: Project Management
**Source**: Fred Brooks, The Mythical Man-Month (1975)

## Core Concept

The tendency of small, elegant, and successful systems to be succeeded by over-engineered, bloated systems due to inflated expectations and overconfidence.

## Key Insight

Designers of second systems are tempted to include all features omitted from the first. The result is often a system that collapses under its own weight.

## Warning Signs

- "This time we'll do everything right"
- Scope expanding during design phase
- Multiple stakeholders adding requirements
- No clear success criteria from original system

## Application

- Maintain humility when replacing successful systems
- Set explicit scope boundaries for rewrites
- Preserve the simplicity that made the original successful
- Assign experienced architects who resist feature creep

## Prevention

1. Document why original succeeded
2. Limit scope to 80% of original feature set initially
3. Require explicit justification for new features
4. Measure against original's simplicity

## Related

- [lindy-effect](lindy-effect.md): Systems that survive longer tend to keep surviving
- `sacrificial-architecture`: Plan for replacement at 10x growth
- [yagni-principle](yagni-principle.md): Build only what's needed now
