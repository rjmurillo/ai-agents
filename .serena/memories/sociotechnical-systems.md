# Sociotechnical Systems

**Category**: Engineering Culture, Organization Design
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`
**Origin**: Tavistock Institute, 1950s

## Core Principle

Technical and social systems are intertwined. You cannot optimize one without considering the other.

## Key Insights

1. **Joint optimization**: Optimize social and technical together
2. **Minimal critical specification**: Only specify what must be controlled
3. **Boundary management**: Define clear interfaces between groups
4. **Multi-functional teams**: Teams should complete work without external dependencies

## Implications for Software

- Microservices architecture requires autonomous teams
- Shared databases create social dependencies
- Platform teams must provide high-quality developer experience
- Communication overhead limits distributed team effectiveness

## Relationship to Conway's Law

Conway's Law is a manifestation of sociotechnical systems. Team structure directly affects system structure.

## Application

When designing architecture, consider:
- Who will build and maintain this?
- What team boundaries exist?
- How will communication flow?
- What dependencies are we creating?

## Related

- `conways-law` - Teams mirror architecture
- `paved-roads-innovation` - Platform team patterns
