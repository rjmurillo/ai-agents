---
source: wiki/concepts/Design Principles/SOLID Principles.md
created: 2026-04-11
review-by: 2026-07-11
---

# SOLID Principles

Five principles for object-oriented design that promote maintainability and flexibility.

## Overview

| Principle | One-liner |
|-----------|-----------|
| Single Responsibility (SRP) | A class should have one reason to change |
| Open-Closed (OCP) | Open for extension, closed for modification |
| Liskov Substitution (LSP) | Subtypes must be substitutable for base types |
| Interface Segregation (ISP) | Many specific interfaces over one general interface |
| Dependency Inversion (DIP) | Depend on abstractions, not concretions |

## Violation Signs

**SRP**: Class does multiple things. Difficult to name without "And" or "Manager".

**OCP**: Adding behavior requires changing existing code. No extension points.

**LSP**: Subclass throws exceptions for inherited methods. Type checking in client code.

**ISP**: "Fat" interfaces with many methods. Implementers throw NotImplementedException.

**DIP**: High-level modules import low-level modules directly. Hard to swap implementations.

## SOLID Maps to Code Qualities

| Principle | Supports |
|-----------|----------|
| SRP | Cohesion |
| OCP | Encapsulation, Low Coupling |
| LSP | Encapsulation, Testability |
| ISP | Cohesion |
| DIP | Low Coupling, Encapsulation |

## Grading Application

When grading a domain, check SOLID adherence as evidence for quality scores:

- **A (90-100)**: All five principles consistently applied
- **B (75-89)**: Minor violations, non-blocking
- **C (60-74)**: Noticeable violations in 1-2 principles
- **D (40-59)**: Significant violations across multiple principles
- **F (0-39)**: SOLID principles largely ignored
