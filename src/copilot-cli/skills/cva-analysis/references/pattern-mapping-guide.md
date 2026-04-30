# CVA Matrix Pattern Mapping Guide

This guide explains how to read a CVA matrix and translate its structure to design patterns.

## Core Principle

**Patterns should EMERGE from the matrix, not be imposed before analysis.**

The CVA matrix is a 2D structure:

- **Rows** = Commonalities (what's constant across all use cases)
- **Columns** = Variabilities (what differs between use cases)

Reading the matrix from different perspectives reveals different pattern opportunities.

---

## Reading Strategies

### Row Perspective: Strategy Pattern

**When to apply**: Each row (commonality) has different implementations across columns.

**Matrix signature**:

```
| Commonality   | Variation A | Variation B | Variation C |
|---------------|-------------|-------------|-------------|
| Operation X   | Impl A.X    | Impl B.X    | Impl C.X    |  ← Different across columns
| Operation Y   | Impl A.Y    | Impl B.Y    | Impl C.Y    |  ← Different across columns
```

**Pattern**: Strategy pattern - vary algorithm for same operation.

**Implementation**:

```
// Define strategy interface
public interface IOperationXStrategy {
    void Execute();
}

// Concrete strategies from each column
public class VariationAOperationX : IOperationXStrategy { }
public class VariationBOperationX : IOperationXStrategy { }
public class VariationCOperationX : IOperationXStrategy { }

// Context uses strategy
public class Context {
    private readonly IOperationXStrategy _strategy;
    public Context(IOperationXStrategy strategy) => _strategy = strategy;
    public void PerformOperation() => _strategy.Execute();
}
```

---

### Column Perspective: Abstract Factory Pattern

**When to apply**: Each column (variation) represents a coherent family of related implementations.

**Matrix signature**:

```
| Commonality   | Family A    | Family B    | Family C    |
|---------------|-------------|-------------|-------------|
| Operation X   | Impl A.X    | Impl B.X    | Impl C.X    |
| Operation Y   | Impl A.Y    | Impl B.Y    | Impl C.Y    |
| Operation Z   | Impl A.Z    | Impl B.Z    | Impl C.Z    |
       ↑             ↑             ↑             ↑
    Coherent      Coherent      Coherent      Coherent
    families      families      families      families
```

**Pattern**: Abstract Factory - vary implementations across product families.

**Implementation**:

```
// Define abstract factory
public interface IProductFactory {
    IOperationX CreateOperationX();
    IOperationY CreateOperationY();
    IOperationZ CreateOperationZ();
}

// Concrete factory per column
public class FamilyAFactory : IProductFactory {
    public IOperationX CreateOperationX() => new ImplAX();
    public IOperationY CreateOperationY() => new ImplAY();
    public IOperationZ CreateOperationZ() => new ImplAZ();
}

public class FamilyBFactory : IProductFactory {
    public IOperationX CreateOperationX() => new ImplBX();
    public IOperationY CreateOperationY() => new ImplBY();
    public IOperationZ CreateOperationZ() => new ImplBZ();
}

// Client uses factory
public class Client {
    private readonly IProductFactory _factory;
    public Client(IProductFactory factory) => _factory = factory;
    public void Execute() {
        var opX = _factory.CreateOperationX();
        var opY = _factory.CreateOperationY();
        // Use products...
    }
}
```

---

### Cell Perspective: Template Method Pattern

**When to apply**: Matrix cells show common structure with localized variation.

**Matrix signature**:

```
| Commonality   | Variation A        | Variation B        | Variation C        |
|---------------|--------------------|--------------------|-------------------|
| Workflow      | Step1→VarA→Step3   | Step1→VarB→Step3   | Step1→VarC→Step3  |
                  ↑     ↑      ↑       ↑     ↑      ↑       ↑     ↑      ↑
              Common  Varies  Common  Common Varies Common  Common Varies Common
```

**Pattern**: Template Method - common algorithm skeleton, varying steps.

**Implementation**:

```
public abstract class WorkflowTemplate {
    // Template method (common structure)
    public void Execute() {
        Step1();
        VariableStep();  // Hook method (varies per subclass)
        Step3();
    }

    protected void Step1() { /* Common implementation */ }
    protected abstract void VariableStep();  // Subclasses provide implementation
    protected void Step3() { /* Common implementation */ }
}

public class VariationAWorkflow : WorkflowTemplate {
    protected override void VariableStep() { /* Variation A logic */ }
}

public class VariationBWorkflow : WorkflowTemplate {
    protected override void VariableStep() { /* Variation B logic */ }
}
```

---

## Combination Patterns

### Strategy + Abstract Factory

**When to apply**: BOTH rows and columns vary independently (multidimensional variability).

**Matrix signature**:

```
| Commonality   | Platform A   | Platform B   | Platform C   |
|---------------|--------------|--------------|--------------|
| Auth          | A.Auth1      | B.Auth1      | C.Auth1      |  ← Row varies
|               | A.Auth2      | B.Auth2      | C.Auth2      |  ← Row varies
| Storage       | A.Storage1   | B.Storage1   | C.Storage1   |  ← Row varies
|               | A.Storage2   | B.Storage2   | C.Storage2   |  ← Row varies
                    ↑              ↑              ↑
                Column varies  Column varies  Column varies
```

**Pattern**: Abstract Factory per platform (column), Strategy per operation (row).

**Implementation**:

```
// Strategy for authentication
public interface IAuthStrategy { void Authenticate(); }
public class AuthStrategy1 : IAuthStrategy { }
public class AuthStrategy2 : IAuthStrategy { }

// Abstract Factory per platform
public interface IPlatformFactory {
    IAuthStrategy CreateAuthStrategy();
    IStorageStrategy CreateStorageStrategy();
}

public class PlatformAFactory : IPlatformFactory {
    public IAuthStrategy CreateAuthStrategy() => new AuthStrategy1();  // Platform A uses Auth1
    public IStorageStrategy CreateStorageStrategy() => new Storage1();
}

public class PlatformBFactory : IPlatformFactory {
    public IAuthStrategy CreateAuthStrategy() => new AuthStrategy2();  // Platform B uses Auth2
    public IStorageStrategy CreateStorageStrategy() => new Storage2();
}
```

---

## Decision Tree

Use this tree to determine which pattern(s) to apply:

```
1. Is there variability?
   No → Don't abstract (YAGNI)
   Yes → Continue to step 2

2. Are operations independent (rows vary independently)?
   Yes → Strategy pattern (one per operation)
   No → Continue to step 3

3. Do variations form coherent families (columns)?
   Yes → Abstract Factory pattern
   No → Continue to step 4

4. Is there common algorithm structure with localized variation?
   Yes → Template Method pattern
   No → Continue to step 5

5. Multiple dimensions of variability?
   Yes → Combination patterns (Strategy + Factory, etc.)
   No → Reconsider scope or use case grouping
```

---

## Pattern Selection Criteria

| Criterion | Strategy | Abstract Factory | Template Method | Combination |
|-----------|----------|------------------|-----------------|-------------|
| Row variability | High | Medium | Medium | High |
| Column variability | Medium | High | Low | High |
| Operations independent | Yes | No (family) | No (workflow) | Varies |
| Complexity | Low | Medium | Low | High |
| Extensibility (new rows) | Easy | Medium | Hard | Medium |
| Extensibility (new columns) | Medium | Easy | Hard | Medium |

---

## Anti-Patterns

### Pattern Forcing

**Bad**: Deciding on Strategy pattern before analyzing matrix.

**Example**: "We need a Strategy pattern for payment processing" (before CVA).

**Fix**: Build matrix first, let pattern emerge from structure.

---

### Ignoring Coherence

**Bad**: Using Strategy when column families are coherent.

**Example**: Payment methods (Credit Card, PayPal, Bank Transfer) have 4 operations each. Using 4 separate Strategy patterns loses cohesion.

**Matrix**:

```
| Operation | Credit Card | PayPal | Bank |
|-----------|-------------|--------|------|
| Validate  | CC validate | PP val | Bank val |
| Authorize | CC auth     | PP auth| Bank auth|
| Record    | CC record   | PP rec | Bank rec |
| Handle    | CC handle   | PP hdl | Bank hdl |
```

**Fix**: Abstract Factory per payment method (columns are coherent families).

---

### Over-Abstraction

**Bad**: Creating abstractions when matrix shows no variability.

**Matrix**:

```
| Operation | Use Case 1 | Use Case 2 | Use Case 3 |
|-----------|------------|------------|------------|
| Step A    | Same       | Same       | Same       |
| Step B    | Same       | Same       | Same       |
```

**Fix**: Don't abstract. Concrete implementation is correct. Document in ADR.

---

## .NET-Specific Patterns

### ASP.NET Middleware Pipeline

**CVA Matrix**:

```
| Middleware     | Development | Staging | Production |
|----------------|-------------|---------|------------|
| Error Handling | DetailedErr | LogOnly | GenericErr |
| Auth           | DevAuth     | StagAuth| ProdAuth   |
| Logging        | Verbose     | Moderate| Minimal    |
```

**Pattern**: Abstract Factory per environment (columns are coherent families).

---

### Dependency Injection Providers

**CVA Matrix**:

```
| Operation    | Transient | Scoped | Singleton |
|--------------|-----------|--------|-----------|
| Create       | New each  | New/scope| Once     |
| Dispose      | Immediate | End scope| Never    |
| Resolve deps | Fresh     | Cached   | Cached   |
```

**Pattern**: Strategy per lifetime scope (rows vary independently).

---

## Further Reading

- **GOF Design Patterns** (1994): Original pattern catalog
- **Coplien Multi-Paradigm Design** (1999): CVA foundation
- **Fowler Refactoring** (2018): When to extract abstractions
- **Martin Clean Architecture** (2017): Dependency inversion and abstractions

---

## Validation Checklist

Before committing to a pattern:

- [ ] Matrix constructed with ≥2 rows, ≥2 columns
- [ ] Pattern recommendation cites matrix structure as evidence
- [ ] Alternative patterns considered and rejected (document WHY)
- [ ] Edge cases addressed (single use case, all variability)
- [ ] Reviewed with decision-critic or independent-thinker agent
- [ ] ADR created documenting rationale
