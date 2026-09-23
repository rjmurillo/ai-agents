# Advanced Engineering Knowledge: Architectural Patterns, Security, and Software Craft

**Created**: 2026-01-10
**Category**: Engineering Practices, Patterns, and Mental Models
**Status**: Reference Document
**Prerequisite**: [Foundational Engineering Knowledge](./foundational-engineering-knowledge.md)

## Executive Summary

This document expands on foundational engineering knowledge with advanced architectural models, design patterns, security principles, and software craft. It continues the transition from "How to code" to "How to think as an engineer."

---

## Part 1: Architectural Models

### 1.1 Martin Fowler's Definition of Architecture

**Definition**: "Architecture is the stuff that's hard to change."

**Core Insight**: Architecture is not defined by diagrams or documentation. It is defined by the cost of change. The architectural decisions are those where changing your mind is expensive.

**Implications**:

1. **Identify what's hard to change early**: Database schema, API contracts, deployment topology, programming language choice
2. **Invest in flexibility for uncertain areas**: Use abstraction layers, interfaces, and configuration
3. **Accept constraints for stable areas**: Not everything needs to be flexible

**Application**:

| Decision | Hard to Change? | Strategy |
|----------|-----------------|----------|
| Database choice | Yes | Evaluate thoroughly, use repository pattern |
| API contracts | Yes | Design carefully, version from start |
| Internal algorithms | No | Optimize when needed |
| UI component library | Medium | Abstract if uncertain |

**Anti-Pattern**: Over-architecting everything. Not all decisions need the same investment. Focus flexibility on genuinely uncertain areas.

### 1.2 C4 Model (Simon Brown)

**Origin**: Simon Brown, 2011

**Core Concept**: Document systems at four levels of abstraction, each serving different audiences and purposes.

**The Four Levels**:

| Level | Name | Description | Audience |
|-------|------|-------------|----------|
| 1 | Context | System in its environment | Everyone |
| 2 | Container | High-level technology choices | Technical staff |
| 3 | Component | Key abstractions within containers | Developers |
| 4 | Code | UML or actual code | Developers (optional) |

**Level 1 (Context)**: Shows the system as a box in relation to users and external systems. Answers: "What are we building and who uses it?"

**Level 2 (Container)**: Shows containers (applications, databases, file systems) that make up the system. Answers: "What are the major technology pieces?"

**Level 3 (Component)**: Shows components within each container. Answers: "How is responsibility divided?"

**Level 4 (Code)**: Optional UML or code-level diagrams. Usually auto-generated.

**Benefits**:

- Common vocabulary across teams
- Right level of detail for each audience
- Maps to code structure

**Tool Support**: Structurizr, PlantUML, Mermaid diagrams

### 1.3 Paved Roads vs Innovation Paths

**Origin**: Netflix engineering culture

**Core Concept**: Provide well-supported default technology choices ("paved roads") while allowing deviation with justification ("innovation paths").

**Paved Roads**:

- Pre-approved, well-documented technology stacks
- Supported by platform teams
- Include templates, examples, and training
- Optimized for the 80% of common use cases

**Innovation Paths**:

- Deviation from paved roads with explicit justification
- Team takes ownership of support and maintenance
- Requires documentation of why standard path is insufficient
- Successful innovations may become new paved roads

**Benefits**:

- Standardization without stifling innovation
- Reduced cognitive load for teams
- Clear ownership and support expectations
- Learning opportunities from deviations

**Implementation**:

1. Identify common technology needs
2. Evaluate and select default options
3. Document the paved roads
4. Define the process for deviation
5. Review innovations for potential standardization

### 1.4 Sociotechnical Systems

**Origin**: Tavistock Institute, 1950s (coal mining studies)

**Core Principle**: Technical and social systems are intertwined. You cannot optimize one without considering the other.

**Software Application**: Team structure, communication patterns, and organizational culture directly affect technical outcomes. Conway's Law is a manifestation of this.

**Key Insights**:

1. **Joint optimization**: Optimize social and technical together
2. **Minimal critical specification**: Only specify what must be controlled
3. **Boundary management**: Define clear interfaces between groups
4. **Multi-functional teams**: Teams should be able to complete work without external dependencies

**Implications for Software**:

- Microservices architecture requires autonomous teams
- Shared databases create social dependencies
- Platform teams must provide high-quality developer experience
- Communication overhead limits distributed team effectiveness

### 1.5 CAP Theorem

**Origin**: Eric Brewer, 2000 (Berkeley)

**Core Principle**: In a distributed data store, you can only have two of three guarantees: Consistency, Availability, and Partition Tolerance.

**Definitions**:

- **Consistency**: Every read receives the most recent write
- **Availability**: Every request receives a response (success or failure)
- **Partition Tolerance**: System continues operating despite network failures

**The Trade-off**: Network partitions are inevitable in distributed systems. You must choose between consistency and availability during partitions.

**Classifications**:

| Type | Description | Examples |
|------|-------------|----------|
| CP | Consistent during partitions, may refuse requests | MongoDB, HBase, Redis (default) |
| AP | Available during partitions, may return stale data | Cassandra, CouchDB, DynamoDB |
| CA | Impossible in distributed systems | Single-node databases |

**PACELC Extension**: During partition (P), choose A or C. Else (E), choose Latency (L) or Consistency (C). Captures the latency trade-off in normal operation.

**Practical Application**:

1. Identify consistency requirements for each data type
2. Choose storage appropriate to requirements
3. Design for partition scenarios
4. Consider eventual consistency patterns

### 1.6 Resilience Patterns

**Origin**: Michael Nygard's "Release It!" (2007, updated 2018)

**Core Concept**: Patterns for building fault-tolerant systems that survive partial failures.

**Pattern 1: Circuit Breaker**

Stops calling a failing service to prevent cascade failures.

States:
- **Closed**: Requests pass through normally
- **Open**: Requests fail immediately (after threshold breached)
- **Half-Open**: Limited requests test if service recovered

Implementation: Polly (.NET), Resilience4j (Java), Hystrix (deprecated)

**Pattern 2: Bulkheads**

Isolate components so failure in one doesn't affect others. Like watertight compartments in ships.

Types:
- Thread pool isolation
- Connection pool isolation
- Process isolation
- Service isolation

**Pattern 3: Retries with Backoff**

Retry transient failures with increasing delays.

Strategy:
- Exponential backoff: 100ms, 200ms, 400ms, 800ms...
- Jitter: Add randomness to prevent thundering herd
- Max retries: Limit total attempts
- Retry budgets: Limit retries per time window

**Pattern 4: Timeouts**

Every external call needs a timeout. No exceptions.

Guidelines:
- p99 latency + buffer
- Separate connect and read timeouts
- Consider retry budget impact

### 1.7 Backpressure

**Core Concept**: Throttle upstream producers when downstream consumers are overwhelmed.

**Problem Without Backpressure**: Unbounded queues grow until memory exhaustion. System crashes.

**Strategies**:

| Strategy | Description | Trade-off |
|----------|-------------|-----------|
| Blocking | Producer waits | High latency |
| Dropping | Discard excess messages | Data loss |
| Buffering | Bounded queue | Memory limit |
| Signaling | Tell producer to slow down | Requires protocol support |

**Implementation Patterns**:

- Reactive Streams: Publisher/Subscriber with demand signaling
- Rate limiting: Token bucket, leaky bucket algorithms
- Load shedding: Reject requests above capacity
- Throttling: Queue depth triggers slowing

### 1.8 Idempotency

**Core Principle**: An operation can be applied multiple times without changing the result beyond the initial application.

**Importance**: Enables safe retries. If a request times out, the client can retry without worrying about duplicate effects.

**Examples**:

| Idempotent | Not Idempotent |
|------------|----------------|
| PUT /user/123 {name: "John"} | POST /users {name: "John"} |
| DELETE /user/123 | POST /orders (creates new order) |
| Setting absolute value | Incrementing a counter |

**Implementation Techniques**:

1. **Idempotency keys**: Client provides unique ID, server deduplicates
2. **Version numbers**: Reject if version doesn't match
3. **State machines**: Operations only valid in certain states
4. **Natural idempotency**: Design operations to be naturally idempotent

**Database Pattern**:

```sql
INSERT INTO operations (idempotency_key, result)
VALUES (@key, @result)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING result;
```

### 1.9 Poka-Yoke

**Origin**: Shigeo Shingo, Toyota Production System

**Core Principle**: Design systems so errors are impossible or immediately obvious.

**Software Application**:

| Technique | Example |
|-----------|---------|
| Compile-time checks | Strong typing, exhaustive pattern matching |
| Constructor validation | Invalid objects cannot exist |
| Configuration validation | Fail fast on startup |
| API design | Required parameters, sensible defaults |
| UI design | Disable invalid actions, confirmation dialogs |

**Design for Inevitable Mistakes**:

1. Make invalid states unrepresentable
2. Validate at the boundary
3. Fail fast, fail loud
4. Prefer correctness over convenience

---

## Part 2: Design Patterns (Usage Guide)

Design patterns are reusable solutions to common problems. However, misapplied patterns create complexity without benefit.

### Pattern Usage Matrix

| Pattern | Use When | Risk if Misused |
|---------|----------|-----------------|
| Strategy | Vary behavior at runtime (e.g., payment methods) | Overengineering if only 1 implementation |
| Factory | Encapsulate complex object creation | Obfuscation if creation is simple |
| Decorator | Add behavior dynamically (e.g., logging, caching) | Hard to trace/debug with many layers |
| Adapter | Integrating incompatible interfaces | Unnecessary indirection if you control both sides |
| Null Object | Avoid null-checking everywhere (e.g., EmptyCart) | May silently ignore real problems |
| Composite | Represent part-whole hierarchies (e.g., UI trees) | Overly complex tree structures |
| Observer/Event | Pub/sub decoupling (e.g., domain events) | Temporal coupling, hard to trace |
| Specification | Encapsulate business rules as objects | Overkill for simple predicates |

### Decision Checklist

Before applying a pattern, ask:

1. **Do I have the problem this pattern solves?** (Not the problem I might have)
2. **Is there a simpler solution?** (Inline code, configuration, etc.)
3. **Will future maintainers understand this?**
4. **Can I remove this pattern later if wrong?**

### Pattern Anti-Patterns

- **Speculative generalization**: Patterns for imagined requirements
- **Golden hammer**: Using favorite pattern everywhere
- **Pattern mania**: Using patterns for resume building
- **Cargo cult**: Copying patterns without understanding intent

---

## Part 3: Code Smells

Code smells are surface indicators of deeper design problems. They are not bugs but suggest refactoring opportunities.

### Smell Catalog

| Smell | Signal | Suggested Fix |
|-------|--------|---------------|
| God Class | Class does too much | Break into smaller SRP classes |
| Feature Envy | Method uses another class's data excessively | Move behavior to where the data is |
| Primitive Obsession | Using strings/ints instead of domain types | Introduce Value Objects |
| Shotgun Surgery | One change requires changes in many places | Centralize related behavior |
| Lava Flow | Dead but scary-to-remove code | Understand intent, test, remove |
| Magic Numbers/Strings | Literal values with unclear meaning | Replace with constants or enums |
| Switch Statements | Used for behavior control | Replace with polymorphism (Strategy) |

### Detection Approach

1. **Review**: Does this code explain itself?
2. **Change**: Is change isolated or scattered?
3. **Test**: Is this easy to test?
4. **Extend**: Can I add features without modification?

---

## Part 4: Security Principles

Security is not a feature. It is a quality that must be designed in from the start.

### Core Principles

| Principle | Summary |
|-----------|---------|
| OWASP Top 10 | Standard for most common web vulnerabilities |
| Principle of Least Privilege | Code and users should have only the access they need |
| Never Trust User Input | Always validate and sanitize at the boundary |
| Never Log Secrets | Exposing sensitive data in logs is a breach risk |
| Secure by Default | Default settings should be safe (HTTPS, deny all) |
| Authentication vs Authorization | AuthN proves identity; AuthZ grants permissions |

### OWASP Top 10 (2021)

1. Broken Access Control
2. Cryptographic Failures
3. Injection
4. Insecure Design
5. Security Misconfiguration
6. Vulnerable Components
7. Authentication Failures
8. Data Integrity Failures
9. Logging/Monitoring Failures
10. Server-Side Request Forgery

### Secure Development Practices

- **Input validation**: Whitelist, not blacklist
- **Output encoding**: Context-appropriate escaping
- **Parameterized queries**: Never concatenate SQL
- **Secret management**: Use vaults, not environment variables in code
- **Dependency scanning**: Automated vulnerability detection
- **Security testing**: SAST, DAST, penetration testing

---

## Part 5: Domain-Driven Design (Expanded)

### Core Concepts

| Concept | Definition |
|---------|------------|
| Ubiquitous Language | Domain experts and developers use the same terms |
| Bounded Context | Each domain model lives in a clear boundary |
| Aggregate | Cluster of objects treated as a unit for data changes |
| Entity | Object with identity that persists across changes |
| Value Object | Object defined by its attributes, interchangeable |
| Domain Event | Something that happened that domain experts care about |
| Anti-Corruption Layer | Translation layer protecting your domain from external models |

### Event Storming

Visual modeling technique for discovering domain events and boundaries.

**Process**:

1. Gather domain experts and developers
2. Write domain events on orange sticky notes
3. Sequence events on timeline
4. Identify commands that trigger events (blue)
5. Identify aggregates that handle commands (yellow)
6. Draw context boundaries

**Output**: Shared understanding, bounded context map, event catalog

### Context Mapping Patterns

| Pattern | Description |
|---------|-------------|
| Shared Kernel | Two contexts share a subset of domain model |
| Customer-Supplier | Upstream context serves downstream |
| Conformist | Downstream conforms to upstream model |
| Anti-Corruption Layer | Downstream translates from upstream |
| Open Host Service | Upstream provides protocol for integration |
| Published Language | Shared language for integration (e.g., XML schema) |

---

## Part 6: Code Quality Techniques

### Measurement and Analysis

| Technique | Application |
|-----------|-------------|
| Cyclomatic Complexity | Keep below 10; refactor complex methods |
| Mutation Testing | Test quality by introducing changes (Stryker) |
| Static Analysis | Roslyn Analyzers, SonarQube |
| Property-Based Testing | Generate inputs to test invariants (FsCheck) |
| Benchmarking | Measure performance objectively (BenchmarkDotNet) |
| Profiling | Find hot paths and memory leaks (dotTrace, dotMemory) |

### Quality Metrics

- **Cyclomatic Complexity**: Number of independent paths through code. High values indicate untestable, hard-to-understand code.
- **Cognitive Complexity**: Measures how hard code is to understand (better than cyclomatic for readability).
- **Test Coverage**: Percentage of code exercised by tests. Aim for 80%+ on critical paths.
- **Mutation Score**: Percentage of mutations killed by tests. Higher indicates stronger tests.

---

## Part 7: Recommended Resources

| Resource | Type | Key Lesson |
|----------|------|------------|
| Designing Data-Intensive Applications (Kleppmann) | Book | Gold standard for modern data systems |
| Building Microservices (Newman) | Book | Pragmatic view of when/how to slice services |
| The Pragmatic Programmer (Hunt & Thomas) | Book | Foundational career-long guidance |
| Thinking in Systems (Meadows) | Book | Feedback loops, emergence, unintended consequences |
| The Goal (Goldratt) | Book | Throughput, constraints, lean thinking |
| The Art of Monitoring (Turnbull) | Book | Designing operable systems |
| Release It! (Nygard) | Book | Resilience patterns for production systems |

---

## Part 8: Additional Mental Models

### Development Workflow Models

| Model | Use it for |
|-------|------------|
| Inversion of Control | Let dependencies call you (DI containers, event systems) |
| Pessimistic vs Optimistic Concurrency | Choose the right strategy in data coordination |
| Trunk-Based vs Gitflow | Pick based on team size, deployment model |
| Tradeoff Triangle (Fast, Good, Cheap) | Use when prioritizing. You only get two. |
| Domain/Application/Infrastructure Layering | Clean separation of concerns |
| Default to Simplicity, Escalate to Abstraction | Only abstract when real differences emerge |

### Concurrency Strategies

**Optimistic Concurrency**: Assume conflicts are rare. Check for conflicts at commit time.

- Best for: Low contention scenarios, read-heavy workloads
- Implementation: Version numbers, ETags

**Pessimistic Concurrency**: Lock resources before modification.

- Best for: High contention, critical sections
- Risk: Deadlocks, reduced throughput

### The Tradeoff Triangle

You can optimize for at most two:

```
        Fast
       /    \
      /      \
   Good ---- Cheap
```

- Fast + Good = Expensive
- Fast + Cheap = Low quality
- Good + Cheap = Slow

---

## Conclusion

These advanced concepts build on foundational knowledge to create thinking engineers who:

1. **Design for change**: Identify what's hard to change, invest flexibility there
2. **Build for failure**: Assume components fail, design resilience
3. **Secure by default**: Treat security as a quality, not a feature
4. **Model the domain**: Use DDD to align code with business concepts
5. **Measure quality**: Use objective metrics to guide improvement
6. **Apply patterns wisely**: Solve real problems, avoid speculative generalization

Master these concepts. Apply them with judgment. Build systems that endure.

---

## References

- [C4 Model](https://c4model.com/)
- [CAP Theorem (Wikipedia)](https://en.wikipedia.org/wiki/CAP_theorem)
- [Release It! (Michael Nygard)](https://pragprog.com/titles/mnee2/release-it-second-edition/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Domain-Driven Design (Eric Evans)](https://www.domainlanguage.com/ddd/)
- [Event Storming (Alberto Brandolini)](https://www.eventstorming.com/)
- [Poka-Yoke (Wikipedia)](https://en.wikipedia.org/wiki/Poka-yoke)
- [Designing Data-Intensive Applications (Martin Kleppmann)](https://dataintensive.net/)
