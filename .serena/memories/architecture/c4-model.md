# C4 Model (Simon Brown)

**Category**: Architecture Documentation
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`

## Core Concept

Document systems at four levels of abstraction, each for different audiences.

## The Four Levels

| Level | Name | Description | Audience |
|-------|------|-------------|----------|
| 1 | Context | System in its environment | Everyone |
| 2 | Container | High-level technology choices | Technical staff |
| 3 | Component | Key abstractions within containers | Developers |
| 4 | Code | UML or actual code | Developers (optional) |

## Level Descriptions

**Context**: System as a box with users and external systems. "What are we building?"

**Container**: Applications, databases, file systems. "What are the technology pieces?"

**Component**: Components within containers. "How is responsibility divided?"

**Code**: Optional, usually auto-generated UML.

## Benefits

- Common vocabulary across teams
- Right detail level for each audience
- Maps to code structure

## Tool Support

Structurizr, PlantUML, Mermaid diagrams

## Related

- [design-diagrams](design-diagrams.md) - Visual documentation
- [architecture-adr-compliance-documentation](architecture-adr-compliance-documentation.md) - Decision records
