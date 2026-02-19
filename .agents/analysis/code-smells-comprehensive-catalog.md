# Code Smells: Comprehensive Catalog and Integration Guide

**Date**: 2026-02-08
**Category**: Code Quality, Refactoring
**Sources**: SonarSource, Martin Fowler, Refactoring.Guru, Marcel Jerzyk, Mäntylä Taxonomy

## Executive Summary

Code smells are surface indicators of deeper design problems. They are not bugs, the code still works, but they signal refactoring opportunities that prevent future maintenance burden. Kent Beck coined the term during collaboration with Martin Fowler on the Refactoring book (1999). This document provides a comprehensive catalog for AI agent integration, including detection heuristics, remediation mappings, and tooling recommendations.

## Core Concept

A code smell is "a surface indication that usually corresponds to a deeper problem in the system" (Fowler). Key characteristics:

1. **Detectable**: Smells are intentionally easy to spot quickly ("sniffable")
2. **Not inherently problematic**: They serve as indicators, not definitive proof of issues
3. **Context-dependent**: Some instances are acceptable based on design intent
4. **Refactoring triggers**: They act as starting points for improvement efforts

## The Mäntylä Taxonomy (Five Categories)

The academic standard taxonomy, proposed by Mäntylä (2003), organizes smells into five groups based on their nature and impact.

### Category 1: Bloaters

**Definition**: Code elements that have grown so large they cannot be effectively handled. These accumulate incrementally rather than by design.

| Smell | Signs | Threshold | Treatment |
|-------|-------|-----------|-----------|
| **Long Method** | Method exceeds readable length | >10-15 lines (Java), >20 lines (Python) | Extract Method, Replace Temp with Query, Decompose Conditional |
| **Large Class** | Class has too many responsibilities | >200-300 lines, >5 fields, >10 methods | Extract Class, Extract Subclass, Extract Interface |
| **Primitive Obsession** | Using strings/ints instead of domain types | Type codes, string-formatted data | Replace Data Value with Object, Introduce Parameter Object |
| **Long Parameter List** | Too many method parameters | >3-4 parameters | Introduce Parameter Object, Preserve Whole Object, Replace Parameter with Method |
| **Data Clumps** | Groups of data that appear together repeatedly | Same 3+ fields in multiple places | Extract Class, Introduce Parameter Object |

**Detection Heuristic**: Count lines, parameters, fields. Look for repeated field groupings across classes.

### Category 2: Object-Orientation Abusers

**Definition**: Solutions failing to fully exploit object-oriented design possibilities. These often emerge from procedural thinking.

| Smell | Signs | Treatment |
|-------|-------|-----------|
| **Switch Statements** | Type-checking switch/case for behavior | Replace Type Code with Subclasses, Replace Conditional with Polymorphism |
| **Temporary Field** | Object field only set in certain conditions | Extract Class, Introduce Null Object |
| **Refused Bequest** | Subclass doesn't use inherited methods/data | Replace Inheritance with Delegation, Push Down Method |
| **Alternative Classes with Different Interfaces** | Two classes do the same thing with different signatures | Rename Method, Extract Superclass |

**Detection Heuristic**: Look for switch statements on type codes, unused inherited members, duplicate functionality with different method names.

### Category 3: Change Preventers

**Definition**: Smells that hinder changing or further developing the software. They violate the principle that classes and changes should have one-to-one relationships.

| Smell | Signs | Treatment |
|-------|-------|-----------|
| **Divergent Change** | One class changed for multiple unrelated reasons | Extract Class (split by change reason) |
| **Shotgun Surgery** | One change requires changes in many places | Move Method, Move Field, Inline Class |
| **Parallel Inheritance Hierarchies** | Creating subclass in one hierarchy requires subclass in another | Move Method, Move Field (to collapse one hierarchy) |

**Detection Heuristic**: Track which files change together. Divergent change = many changes to one file. Shotgun surgery = one logical change touches many files.

### Category 4: Dispensables

**Definition**: Something unnecessary whose absence would make the code cleaner, more efficient, and easier to understand.

| Smell | Signs | Treatment |
|-------|-------|-----------|
| **Comments** | Comments that explain "what" instead of "why" | Extract Method, Rename Method, Introduce Assertion |
| **Duplicate Code** | Same code structure in multiple places | Extract Method, Extract Class, Pull Up Method |
| **Lazy Class** | Class that doesn't do enough to justify its existence | Inline Class, Collapse Hierarchy |
| **Data Class** | Class with only getters/setters and no behavior | Move Method (move behavior to data), Encapsulate Field |
| **Dead Code** | Variables, parameters, fields, methods never used | Delete |
| **Speculative Generality** | Code written for future needs that never materialized | Collapse Hierarchy, Inline Class, Remove Parameter |

**Detection Heuristic**: Static analysis for unused code. Manual review for comment quality and premature abstractions.

### Category 5: Couplers

**Definition**: Smells representing excessive coupling between classes or problematic attempts to reduce it through over-delegation.

| Smell | Signs | Treatment |
|-------|-------|-----------|
| **Feature Envy** | Method uses another class's data more than its own | Move Method, Extract Method |
| **Inappropriate Intimacy** | Classes spend too much time in each other's private parts | Move Method, Move Field, Change Bidirectional Association |
| **Message Chains** | Client asks object A for object B, then asks B for C, etc. | Hide Delegate, Extract Method, Move Method |
| **Middle Man** | Class delegates all its work to another | Remove Middle Man, Inline Method |
| **Incomplete Library Class** | Library class missing needed functionality | Introduce Foreign Method, Introduce Local Extension |

**Detection Heuristic**: Count references to external class members versus internal members. Analyze call chain depth.

## Extended Smell Catalog (60+ Smells)

Beyond the classic taxonomy, modern catalogs (Marcel Jerzyk, QualInsight) identify additional smells:

### Additional Bloaters

| Smell | Definition | Severity |
|-------|------------|----------|
| **Combinatorial Explosion** | Many methods exist due to parameter combinations | HIGH |
| **Oddball Solution** | Same problem solved in multiple ways | CRITICAL |

### Obfuscators (Clarity Issues)

| Smell | Definition | Severity |
|-------|------------|----------|
| **Clever Code** | Unnecessarily complex for showing off | MAJOR |
| **Obscured Intent** | Code purpose not clear from reading | MAJOR |
| **Complicated Boolean Expression** | Hard-to-understand conditionals | MAJOR |
| **Complicated Regex Expression** | Incomprehensible regular expressions | MAJOR |
| **Status Variable** | Flags controlling flow instead of state machines | MAJOR |
| **Inconsistent Style** | Mixed coding conventions | MINOR |
| **Vertical Separation** | Related code separated by unrelated code | MINOR |

### Lexical Abusers (Naming Issues)

| Smell | Definition | Severity |
|-------|------------|----------|
| **Magic Number** | Unexplained literal values | MAJOR |
| **Uncommunicative Name** | Name doesn't convey purpose | CRITICAL |
| **Inconsistent Names** | Same concept with different names | MAJOR |
| **Abbreviations Usage** | Confusing abbreviations | MAJOR |
| **Binary Operator in Name** | Method name includes "And"/"Or" | MAJOR |
| **Type Embedded in Name** | Hungarian notation, type prefixes | MINOR |

### Data Dealers (Data Flow Issues)

| Smell | Definition | Severity |
|-------|------------|----------|
| **Global Data** | Mutable global state | CRITICAL |
| **Hidden Dependencies** | Implicit dependencies not in signature | CRITICAL |
| **Tramp Data** | Data passed through methods that don't use it | MAJOR |
| **Insider Trading** | Classes sharing too much internal knowledge | CRITICAL |

### Functional Abusers

| Smell | Definition | Severity |
|-------|------------|----------|
| **Mutable Data** | Data changed in place instead of immutable | CRITICAL |
| **Side Effects** | Functions with hidden state changes | CRITICAL |
| **Imperative Loops** | For/while when map/filter/reduce would be cleaner | MINOR |

### Documentation Issues

| Smell | Definition | Severity |
|-------|------------|----------|
| **How Comment** | Comment describes implementation, not intent | MAJOR |
| **Meaningless Comment** | Comment adds no information | MAJOR |
| **Missing Documentation** | Critical documentation absent | CRITICAL |
| **What Comment** | Comment restates the code | MINOR |

### Logic Issues

| Smell | Definition | Severity |
|-------|------------|----------|
| **Callback Hell** | Deeply nested callbacks | MAJOR |
| **Flag Argument** | Boolean parameter changing behavior | MAJOR |
| **Null Check** | Excessive null/undefined checking | MAJOR |
| **Non-Exception** | Exceptions for normal control flow | MAJOR |
| **Wrong Logic** | Incorrect business logic | BLOCKER |

### Design Issues

| Smell | Definition | Severity |
|-------|------------|----------|
| **Anti-Pattern** | Known anti-pattern implemented | BLOCKER |
| **Bad Design** | Fundamental design flaws | BLOCKER |
| **Bad Framework Usage** | Framework used incorrectly | BLOCKER |
| **Indecent Exposure** | Class exposes internals unnecessarily | CRITICAL |
| **Multiple Responsibilities** | Violates Single Responsibility Principle | BLOCKER |
| **Reinvented Wheel** | Custom solution when library exists | BLOCKER |
| **Solution Sprawl** | Too many classes to do anything useful | CRITICAL |

### Testing Issues

| Smell | Definition | Severity |
|-------|------------|----------|
| **Missing Test** | Critical test coverage absent | BLOCKER |
| **Useless Test** | Test that doesn't verify anything | MAJOR |

## Smell-to-Refactoring Mapping

Critical for remediation: knowing which refactoring addresses which smell.

### Extract Method Addresses

- Long Method
- Duplicate Code
- Feature Envy
- Comments (replace with well-named method)
- Message Chains
- Switch Statements
- Data Class

### Move Method Addresses

- Feature Envy (primary)
- Shotgun Surgery
- Switch Statements
- Parallel Inheritance Hierarchies
- Message Chains
- Inappropriate Intimacy

### Extract Class Addresses

- Large Class
- Data Clumps
- Divergent Change
- Temporary Field

### Replace Conditional with Polymorphism Addresses

- Switch Statements
- Conditional Complexity
- Type Code patterns

### Inline Class/Method Addresses

- Lazy Class
- Middle Man
- Speculative Generality

## Detection Tools and Automation

### Static Analysis Tools (2024-2026)

| Tool | Languages | Strengths |
|------|-----------|-----------|
| **SonarQube** | 35+ languages | Industry standard, 1000s of rules, CI/CD integration |
| **ESLint** | JavaScript/TypeScript | Excellent autofix, plugin ecosystem |
| **PMD** | Java, JavaScript, Apex | Fast, focus on common issues |
| **Pylint** | Python | Comprehensive Python analysis |
| **RuboCop** | Ruby | Community-driven style enforcement |
| **CodeClimate** | Multiple | Aggregation across languages |
| **DeepSource** | Multiple | AI-enhanced, autofix capabilities |

### AI-Enhanced Detection (2025-2026)

Modern tools use machine learning for context-sensitive detection:

- **CodeAnt.AI**: Pattern learning from codebase history
- **Panto AI**: Smart static analysis at scale
- **GitHub Copilot Code Review**: Contextual smell detection
- **Amazon CodeGuru**: AWS-integrated ML analysis

### Metrics Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Cyclomatic Complexity | >10 | >20 |
| Method Lines | >15 | >30 |
| Class Lines | >200 | >500 |
| Parameters | >4 | >7 |
| Coupling Between Objects | >10 | >20 |
| Lack of Cohesion | >0.5 | >0.8 |

## Clean as You Code Methodology

SonarSource's approach to smell prevention:

### Principles

1. **Focus on New Code**: Enforce standards on additions/changes, not entire codebase
2. **Personal Responsibility**: Developers own their contributions
3. **Incremental Improvement**: Quality improves through consistent enforcement

### Quality Gate (New Code)

1. No new bugs introduced
2. No new vulnerabilities introduced
3. All security hotspots reviewed
4. Limited technical debt ratio (<5%)
5. Limited duplication (<3%)
6. Adequate test coverage (>80%)

## Project Integration Points

### Agent Applications

| Agent | Smell Detection Role |
|-------|---------------------|
| **implementer** | Follow smell-aware coding patterns |
| **critic** | Validate plans against smell introduction |
| **qa** | Test for smell regression |
| **architect** | Design reviews for structural smells |
| **retrospective** | Extract smell patterns from PR feedback |

### Protocol Integration

1. **Pre-commit**: Run static analysis, block on critical smells
2. **PR Review**: Check for new smells in changed code
3. **Definition of Done**: No critical/blocker smells introduced

### Memory Integration

- Store smell patterns in project memory for consistent detection
- Link smells to refactoring techniques for automated suggestions
- Track smell density trends for quality metrics

## Failure Modes and Anti-Patterns

### Detection Anti-Patterns

| Anti-Pattern | Problem | Correction |
|--------------|---------|------------|
| **Smell Blindness** | Ignoring tool warnings | Set quality gates that block merges |
| **False Positive Fatigue** | Too many low-value warnings | Configure rules for project context |
| **Over-Refactoring** | Changing working code for purity | Use smell severity to prioritize |
| **Analysis Paralysis** | Can't decide which smell to fix first | Apply Clean as You Code: focus on new |

### Remediation Anti-Patterns

| Anti-Pattern | Problem | Correction |
|--------------|---------|------------|
| **Wrong Refactoring** | Applying technique that doesn't fit | Learn smell-to-refactoring mappings |
| **Incomplete Refactoring** | Partial fix leaves worse state | Complete the refactoring or don't start |
| **Big Bang Refactoring** | Changing everything at once | Incremental, tested changes |

## Questions for Code Review

Apply during any code review:

1. **Readability**: Does this code explain itself?
2. **Change Impact**: Is change isolated or scattered?
3. **Testability**: Is this easy to test?
4. **Extensibility**: Can I add features without modification?
5. **Simplicity**: Is there a simpler solution?

## Detailed Smell Examples

### Example 1: Long Method (Bloater)

**Before (smell present):**

```python
def process_order(order):
    # Validate order
    if not order.items:
        raise ValueError("Empty order")
    if not order.customer:
        raise ValueError("No customer")
    if order.total < 0:
        raise ValueError("Invalid total")

    # Calculate discounts
    discount = 0
    if order.customer.is_vip:
        discount += order.total * 0.1
    if len(order.items) > 10:
        discount += order.total * 0.05
    if order.total > 1000:
        discount += order.total * 0.03

    # Apply tax
    tax_rate = 0.08
    if order.shipping_state == "OR":
        tax_rate = 0
    elif order.shipping_state == "CA":
        tax_rate = 0.0725
    tax = (order.total - discount) * tax_rate

    # ... 50 more lines of processing
    return final_order
```

**After (refactored):**

```python
def process_order(order):
    validate_order(order)
    discount = calculate_discount(order)
    tax = calculate_tax(order, discount)
    return finalize_order(order, discount, tax)

def validate_order(order):
    if not order.items:
        raise ValueError("Empty order")
    # Each validation is clear and testable
```

**Why this matters:** The original method has multiple responsibilities (validation, discount calculation, tax calculation, finalization). Each extracted method is now independently testable and modifiable.

### Example 2: Feature Envy (Coupler)

**Before (smell present):**

```python
class OrderProcessor:
    def calculate_shipping(self, customer):
        # This method "envies" Customer's data
        base_rate = 5.99
        if customer.address.country != "US":
            base_rate *= 2
        if customer.loyalty_points > 1000:
            base_rate *= 0.8
        if customer.order_history_count > 10:
            base_rate *= 0.9
        return base_rate
```

**After (refactored):**

```python
class Customer:
    def calculate_shipping_rate(self, base_rate):
        rate = base_rate
        if self.address.country != "US":
            rate *= 2
        if self.loyalty_points > 1000:
            rate *= 0.8
        if self.order_history_count > 10:
            rate *= 0.9
        return rate

class OrderProcessor:
    def calculate_shipping(self, customer):
        return customer.calculate_shipping_rate(5.99)
```

**Why this matters:** The behavior now lives with the data it operates on, following the "Tell, Don't Ask" principle and improving encapsulation.

### Example 3: Shotgun Surgery (Change Preventer)

**Before (smell present):**

When adding a new payment type, you must change:

- `PaymentProcessor.process()`
- `PaymentValidator.validate()`
- `PaymentReporter.report()`
- `PaymentAuditor.audit()`
- `PaymentUI.display()`
- Database schema
- API endpoints

**After (refactored using Strategy pattern):**

```python
class PaymentStrategy(ABC):
    @abstractmethod
    def process(self, amount): pass

    @abstractmethod
    def validate(self): pass

    @abstractmethod
    def get_display_name(self): pass

class CreditCardPayment(PaymentStrategy):
    # All credit card logic in one place
    pass

class PayPalPayment(PaymentStrategy):
    # All PayPal logic in one place
    pass
```

**Why this matters:** Adding a new payment type now requires creating one new class that implements the strategy interface. The change is localized rather than scattered.

### Example 4: Primitive Obsession (Bloater)

**Before (smell present):**

```python
def create_user(email: str, phone: str, postal_code: str):
    # Email validation scattered throughout codebase
    if "@" not in email or "." not in email:
        raise ValueError("Invalid email")

    # Phone validation duplicated in multiple places
    phone = phone.replace("-", "").replace(" ", "")
    if len(phone) != 10:
        raise ValueError("Invalid phone")

    # Postal code validation repeated
    if len(postal_code) != 5 or not postal_code.isdigit():
        raise ValueError("Invalid postal code")
```

**After (refactored with Value Objects):**

```python
@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        if "@" not in self.value or "." not in self.value:
            raise ValueError("Invalid email format")

@dataclass(frozen=True)
class PhoneNumber:
    value: str

    def __post_init__(self):
        cleaned = self.value.replace("-", "").replace(" ", "")
        if len(cleaned) != 10:
            raise ValueError("Invalid phone number")
        object.__setattr__(self, 'value', cleaned)

def create_user(email: Email, phone: PhoneNumber, postal_code: PostalCode):
    # Validation is guaranteed by the type system
    pass
```

**Why this matters:** The validation logic is now centralized in the value objects. Invalid data cannot exist because the constructor enforces invariants. This eliminates duplicate validation scattered across the codebase.

## Related Concepts

| Concept | Relationship |
|---------|--------------|
| **Technical Debt** | Smells are indicators of accrued debt |
| **Refactoring** | Smells trigger refactoring decisions |
| **Design Patterns** | Patterns often emerge from smell removal |
| **SOLID Principles** | Smells frequently indicate SOLID violations |
| **Law of Demeter** | Message Chains violate Demeter |
| **Cyclomatic Complexity** | Metric correlates with multiple smells |

## Project Applicability

### Integration Opportunities

| Integration Point | Opportunity | Effort | Priority |
|-------------------|-------------|--------|----------|
| **analyze skill** | Already triggers on "find code smells"; enhance with taxonomy | LOW | HIGH |
| **code-qualities-assessment skill** | Map qualities to smells (cohesion→Large Class, coupling→Feature Envy) | MEDIUM | HIGH |
| **critic agent** | Add smell-aware plan validation | LOW | MEDIUM |
| **implementer agent** | Embed smell avoidance in coding patterns | LOW | HIGH |
| **qa agent** | Add smell regression testing to verification | MEDIUM | MEDIUM |
| **retrospective agent** | Extract smell patterns from PR feedback | LOW | LOW |

### Skill Enhancement Recommendations

1. **analyze skill (HIGH priority)**
   - Current: Triggers on "find code smells" but lacks taxonomy reference
   - Enhancement: Add smell catalog as reference material for analysis steps
   - File: `.claude/skills/analyze/references/code-smells-catalog.md`

2. **code-qualities-assessment skill (HIGH priority)**
   - Current: Assesses 5 qualities (cohesion, coupling, encapsulation, testability, non-redundancy)
   - Enhancement: Map qualities to specific smells for actionable remediation
   - Example: Low cohesion score → check for Large Class, Long Method

3. **New skill opportunity: smell-detection**
   - Purpose: Quick smell scan with severity classification
   - Input: File or directory path
   - Output: Prioritized smell list with refactoring suggestions
   - Integrates: SonarQube rules, cyclomatic complexity metrics

### Agent Enhancement Recommendations

1. **implementer agent**
   - Add smell-aware coding checklist to prompt
   - Before writing: "Will this introduce Long Method, Feature Envy, or Primitive Obsession?"
   - During writing: Keep methods <15 lines, parameters <4

2. **critic agent**
   - Add smell risk assessment to plan validation
   - Flag plans that create Large Classes or Shotgun Surgery potential

3. **qa agent**
   - Add smell regression check to verification
   - Compare smell count before/after implementation

### Memory System Integration

1. **Serena project memory**: Update `code-smells-catalog` with comprehensive taxonomy
2. **Forgetful memories**: Create atomic memories for each smell category and key mappings
3. **Link to existing**: Connect to `law-of-demeter`, `refactoring-001-delete-over-extract`

### Quality Gate Integration

Add to PR quality gates:
- No critical/blocker smells introduced (SonarQube integration)
- Smell density does not increase (Clean as You Code)
- New code coverage maintains threshold

## Sources

- [SonarSource Code Smells](https://www.sonarsource.com/resources/library/code-smells/)
- [Martin Fowler: Code Smell](https://martinfowler.com/bliki/CodeSmell.html)
- [Refactoring.Guru Smells](https://refactoring.guru/refactoring/smells)
- [Marcel Jerzyk Code Smells Catalog](https://luzkan.github.io/smells/)
- [Mäntylä Taxonomy](https://mmantyla.github.io/BadCodeSmellsTaxonomy)
- [SourceMaking Smells](https://sourcemaking.com/refactoring/smells)
- [Clean as You Code](https://docs.sonarsource.com/sonarqube-server/9.9/user-guide/clean-as-you-code)
- [QualInsight SonarQube Plugin](https://github.com/QualInsight/qualinsight-plugins-sonarqube-smell/wiki/Code-Smells-Types/)
- [Refactoring Catalog](https://refactoring.com/catalog/)
