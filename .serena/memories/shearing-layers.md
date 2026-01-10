# Shearing Layers

**Category**: Architecture
**Source**: Stewart Brand, How Buildings Learn

## Core Concept

Different components of a system change at different rates. Design to allow independent evolution of layers.

## Building Layers (Brand)

| Layer | Change Rate |
|-------|-------------|
| Site | Permanent |
| Structure | 30-300 years |
| Skin | 20 years |
| Services | 7-15 years |
| Space Plan | 3-30 years |
| Stuff | Daily |

## Software Layers

| Layer | Change Rate | Examples |
|-------|-------------|----------|
| Core Data Model | Years | Database schema, entity relationships |
| Business Logic | Months | Rules, workflows, calculations |
| API Contracts | Months-Years | Public interfaces, protocols |
| Services | Weeks-Months | Internal implementations |
| UI/UX | Weeks | Visual design, user flows |
| Configuration | Daily | Feature flags, settings |

## Application

- Design boundaries between fast-changing and slow-changing components
- Use interfaces to isolate change rates
- Don't couple fast layers to slow layers tightly
- Accept that some layers will be replaced more often

## Key Insight

If you mix layers with different change rates, the slow layer becomes a bottleneck for change.

## Related

- `strangler-fig-pattern`: Isolate and replace incrementally
- `hexagonal-architecture`: Isolate core from infrastructure
- `sacrificial-architecture`: Plan for replacement
