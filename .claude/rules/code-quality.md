---
description: Baseline code quality rules merging Clean Code and Code Complete fundamentals. Apply on every code edit.
alwaysApply: true
---

# Code Quality

This rule sets the baseline quality standard for all code you write or change. It merges the everyday fundamentals from Robert Martin's _Clean Code_ and Steve McConnell's _Code Complete_. Apply these rules on every edit. They override stylistic preferences but defer to project conventions found in `AGENTS.md`, `.editorconfig`, and `.markdownlint-cli2.yaml`.

## Naming

Names are documentation. A reader who knows nothing about the change should understand the code from the names alone.

- Choose intention-revealing names. `daysSinceLastLogin` beats `d` or `delta`. `isExpired` beats `flag`.
- Use pronounceable, searchable names. `customerCount` beats `cc`.
- Drop abbreviations and Hungarian prefixes. `userList` beats `usrLst` or `lstUsr`.
- Use one word per concept across the whole codebase. Pick `fetch`, `get`, or `retrieve` and stay with it.
- Names track scope. Short names fit short scopes. Long names fit long-lived classes and public APIs.
- Class names are nouns. Method names are verbs. Boolean methods read as predicates: `isReady`, `hasChildren`, `canCommit`.
- Avoid disinformation. Do not call something `accountList` if it is a `Set`. Do not name a `boolean` `status`.
- Mirror the domain. If the team says "tenant," do not write `customer` in code. Ubiquitous language reduces translation cost.

When you find yourself writing a comment to explain a name, rename instead.

## Functions

Functions are the core unit of design. Keep them small, single-purpose, and easy to test.

- Functions should do one thing. If you can describe the function as "X and Y," split it.
- Prefer 20 lines or fewer. The project ceiling is 60. Past that, extract.
- Aim for cyclomatic complexity of 10 or lower. Past that, extract or use table-driven logic.
- Limit parameters to three. Prefer two. Zero is best. Bundle related parameters into a parameter object.
- Avoid flag arguments. A `boolean` argument means the function does two things. Split it into `renderTextual()` and `renderHtml()`.
- Output parameters are confusing. Return a value, a tuple, or a small record.
- One level of abstraction per function. A high-level orchestrator should not parse strings; a parser should not log analytics.
- Apply the Stepdown Rule. Read top to bottom: each function calls the next level of detail.
- No side effects beyond the function's name. `validatePassword(user)` should not also log the user in.

If a function is hard to name, it does too much. Split it.

## Guard Clauses Over Deep Nesting

Deep `if`/`else` trees hide intent. Use early returns to flatten control flow.

```python
# Avoid
def charge(order):
    if order is not None:
        if order.is_valid():
            if order.total > 0:
                process(order)
            else:
                raise ValueError("non-positive total")
        else:
            raise ValueError("invalid order")
    else:
        raise ValueError("missing order")

# Prefer
def charge(order):
    if order is None:
        raise ValueError("missing order")
    if not order.is_valid():
        raise ValueError("invalid order")
    if order.total <= 0:
        raise ValueError("non-positive total")
    process(order)
```

Bail on the unhappy path first. Keep the happy path on the leftmost indent level. This pattern also localizes preconditions next to the inputs they check.

## Delete Dead Code

Commented-out code rots. Remove it. The version control history is the archive.

- Delete unreachable branches, unused imports, and stale parameters.
- Delete TODOs that have outlived their context. Open an issue if the work still matters.
- Delete commented-out blocks. If you are unsure, run a search across the repo first; then delete.
- Delete unused public APIs once you confirm no internal callers exist. External consumers belong behind a deprecation notice.

A reader trusts the code in front of them. Dead code teaches readers to distrust everything they read.

## Code Smell Detection

Treat smells as evidence, not verdicts. They flag places worth a closer look.

- **Long Method**: extract until each method fits one screen.
- **Large Class**: split by responsibility. A `User` class that handles auth, billing, and email is three classes.
- **Long Parameter List**: introduce a parameter object or builder.
- **Duplicate Code**: extract a function or use a shared helper. The Rule of Three: duplicate twice, refactor on the third occurrence.
- **Feature Envy**: a method that uses another class's data more than its own belongs on that other class.
- **Data Clumps**: the same group of fields traveling together (`startDate`, `endDate`, `timezone`) usually wants to be a type.
- **Primitive Obsession**: replace `string customerId` with a `CustomerId` type when the value carries rules.
- **Switch Statements on Type**: replace with polymorphism or a strategy table.
- **Shotgun Surgery**: one logical change touching many files signals weak cohesion. Consolidate the responsibility.
- **Comments Explaining What**: rename or extract until the comment becomes redundant. Reserve comments for _why_.

When you smell something, name it explicitly in the PR description so reviewers can see your reasoning.

## SOLID

SOLID protects code from change-driven decay. Apply at the unit boundary.

- **Single Responsibility**: a class has one reason to change. Auth rules and rendering rules change for different reasons; do not house them together.
- **Open/Closed**: open to extension, closed to modification. Add a new strategy by writing a new class, not by editing the existing one.
- **Liskov Substitution**: subtypes must be usable wherever the parent is used. A `ReadOnlyList` that throws on `add()` violates LSP. Prefer composition.
- **Interface Segregation**: clients should not depend on methods they do not use. Split a fat `IRepository` into `IReader`, `IWriter`, `IBatchWriter`.
- **Dependency Inversion**: depend on abstractions, not concretes. High-level policy should not import a database driver directly.

Apply SOLID where change is likely. Premature abstraction is its own smell.

## Test Readability

Tests are first-class code. They document behavior. Treat them with the same care.

- Use the Arrange/Act/Assert structure. One blank line between sections.
- One behavior per test. A failing test should localize the bug.
- Names describe the behavior, not the method. `creditsAccountWhenBalanceIsPositive` beats `testCredit1`.
- Prefer Given/When/Then phrasing for integration tests.
- Build inputs with named factories or builders. `aValidOrder().withTotal(100).build()` reads better than a 12-argument constructor.
- Assert on outcomes, not internals. Avoid asserting on private state when a public observation works.
- Keep test data minimal. Each value in the setup should matter to the assertion. Hide irrelevant defaults inside the builder.
- Tests should fail for one reason. If the assertion message cannot tell you what broke, add a clearer assertion.

If you cannot write a test, the design is wrong. Fix the design first.

## Defensive Programming

Assume bad input can reach your function. Decide where to catch it, then catch it once.

- Validate inputs at the boundary. Internal functions trust their callers; public APIs do not.
- Use assertions for conditions that should be impossible. Use exceptions for conditions that are merely invalid.
- Fail fast. A function with a contract violation should raise on the first detection, not log and continue.
- Check pre-conditions, then post-conditions. Document both in the function header.
- Treat all external data as hostile until validated: HTTP request bodies, environment variables, file contents, database rows from older schemas.
- Never trust user-supplied identifiers as authorization. Re-check ownership inside the function.
- Choose one error-handling strategy per layer: exceptions, result types, or sentinel values. Mixing them inside one layer creates ambiguity.
- Log enough context to reconstruct the failure: input identifiers, user, request id. Never log secrets, tokens, or full PII.

Defensive code should not become paranoid code. If two callers already validated the input, a third check is noise.

## Table-Driven Logic

When branching grows past three or four cases, replace conditional code with a table.

- Map known inputs to outputs in a dictionary or array.
- Add a default case for unknown inputs. Decide explicitly: raise, log, or fall back.
- Tables make changes localized. Adding a new case is a one-line edit, not a new branch.
- Tables make tests parametrize cleanly. Each row becomes one test case.

Use table-driven logic for command dispatch, status transitions, validation rules, and feature flags. Avoid it when the cases differ in structure, not just data; polymorphism fits better there.

```python
HTTP_STATUS_TEXT = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
}

def status_text(code: int) -> str:
    return HTTP_STATUS_TEXT.get(code, "Unknown")
```

A table replaces five `if`/`elif` branches with one lookup and one default.

## Variable Scope and Lifetime

Minimize the distance between a variable's declaration and its last use.

- Declare variables at the smallest scope that satisfies their use.
- Initialize at the point of declaration. Avoid declared-then-assigned-later patterns.
- Prefer immutability. Reassignment is a smell unless the loop variable is the point.
- Reduce live variables: a function with twelve locals is harder to read than three small functions with three locals each.
- Avoid global mutable state. Where you cannot, document the invariants and guard the writers.
- Pull constants out of methods only when they are reused. A constant used in one method belongs in that method.

A short scope is easier to reason about. A short scope makes refactoring safe.

## Comments

Code explains _what_. Comments explain _why_.

- Write comments when the rationale would surprise a peer reader: a hidden invariant, a workaround for a vendor bug, a non-obvious performance choice.
- Do not narrate the code. `// increment counter` next to `counter += 1` is noise.
- Do not date-stamp or sign comments. Git already records that.
- Reference issues and ADRs when the rationale lives elsewhere: `# See ADR-007 (memory-first architecture)`.
- Update or delete comments when the code under them changes. A wrong comment is worse than no comment.

If you must comment to explain a function, the function probably wants a better name or a smaller body.

## Error Handling

Errors are part of the contract. Handle them with the same care as the happy path.

- Define what each function does on failure: returns, raises, or both.
- Do not swallow exceptions. If you catch one, you have a reason; record the reason in code or in a log.
- Wrap low-level errors with domain-meaningful types at the boundary so callers do not depend on infrastructure details.
- Use `try`/`finally` (or its language equivalent) for resource cleanup. Prefer language constructs (`with`, `using`, `defer`) when available.
- Never use exceptions for normal control flow. They are slow and hide intent.
- Re-raise with `raise` (Python) or `throw;` (C#) to preserve the stack. A new exception with no `cause` loses the trail.

A function that fails predictably is easier to operate than one that succeeds unpredictably.

## Quick Self-Review

Before you mark work complete, walk this list:

- [ ] Names tell the reader what the code does without comments.
- [ ] Each function does one thing. Cyclomatic complexity is 10 or lower. Length is 60 lines or fewer.
- [ ] No commented-out code. No dead branches.
- [ ] Guard clauses are at the top. The happy path is on the leftmost column.
- [ ] Inputs are validated at the boundary, not at every layer.
- [ ] Long branching uses tables when shapes match; polymorphism when they do not.
- [ ] Tests describe behavior, follow Arrange/Act/Assert, and would catch a regression.
- [ ] Variables live in the narrowest scope that satisfies their use.
- [ ] Comments explain _why_; the code explains _what_.
- [ ] Errors are typed, traced, and logged without secrets.

If you cannot check a box, fix it before requesting review. The cost of a fix grows after the merge.
