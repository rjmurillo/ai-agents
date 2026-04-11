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

## Single Responsibility (SRP)

Signs of violation: class does multiple things, many reasons to modify, hard to name without "And" or "Manager." Achieve through Commonality Variability Analysis and Programming by Intention.

## Open-Closed (OCP)

Add new behavior without changing existing code. Use abstractions (interfaces, abstract classes), Strategy or Bridge patterns, and encapsulate what varies.

```csharp
// Adding Encryption256 doesn't modify existing classes
public abstract class Encryption { }
public class Encryption64 : Encryption { }
public class Encryption128 : Encryption { }
```

## Liskov Substitution (LSP)

Signs of violation: subclass throws exceptions for inherited methods, returns null where parent returns object, client code checks types with `if (x is DerivedType)`.

Classic example: a Square inheriting Rectangle violates LSP if setting width also sets height.

## Interface Segregation (ISP)

Signs of violation: "fat" interfaces, implementers throw `NotImplementedException`, clients use only a subset.

```csharp
// Split large interfaces into focused ones
interface IWorkable { void Work(); }
interface IFeedable { void Eat(); }
```

## Dependency Inversion (DIP)

High-level modules depend on abstractions, not low-level modules.

Traditional: `BusinessLogic -> Database`
Inverted: `BusinessLogic -> IRepository <- Database`

Achieve through interface definitions, constructor injection, and DI containers.

## SOLID and Code Qualities

| Principle | Supports |
|-----------|----------|
| SRP | Cohesion |
| OCP | Encapsulation, Low Coupling |
| LSP | Encapsulation, Testability |
| ISP | Cohesion |
| DIP | Low Coupling, Encapsulation |

## Reference

- Martin, 2000. Design Principles and Design Patterns
