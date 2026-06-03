---
source: wiki/concepts/Architectural Patterns/8 Fallacies of Distributed Computing.md
created: 2026-06-01
review-by: 2026-09-01
---

# 8 Fallacies of Distributed Computing

## Principle

Eight false assumptions developers make about distributed systems. Originally
stated by Peter Deutsch and James Gosling (Sun Microsystems, 1994). Violating any
of them leads to fragile, unreliable systems. This reference serves both the
architect axis (system structure across process boundaries) and the reliability
axis (how a change behaves when its dependencies misbehave); it sits beside the
observability references because the failure modes here are exactly the ones an
operator must be able to see.

## The Fallacies

| # | Fallacy | Reality | Key consequence |
|---|---------|---------|-----------------|
| 1 | The network is reliable | Networks fail unpredictably | Cannot distinguish "request lost" from "response lost"; failure is non-deterministic |
| 2 | Latency is zero | Total time equals latency plus size over bandwidth; bounded by physics | Many small requests cost far more than one combined request |
| 3 | Bandwidth is infinite | Demand grows faster than capacity | Always optimizing, never satisfied |
| 4 | The network is secure | Only a disconnected, buried machine is secure | Defense in depth, proportional paranoia |
| 5 | Topology does not change | Slow creep of chaos; servers added, IPs reassigned | Static assumptions break under real-world infra drift |
| 6 | There is one administrator | Bus factor of 1 is dangerous | Knowledge must be distributed and documented |
| 7 | Transport cost is zero | Bandwidth costs money; cloud shifts CapEx to OpEx but does not eliminate | Factor cost into architecture decisions |
| 8 | The network is homogeneous | Stacks do not interoperate cleanly | Expect more divergence, not less |

## Mitigations

For fallacy 1 (network unreliable):

- Store-and-forward messaging (a durable queue or service bus).
- Fire-and-forget with automatic retry.
- Message IDs for server-side deduplication.
- Abandon request/response for async messaging where it fits. This requires
  real redesign, not a queue bolted on.

For fallacy 2 (latency is not zero):

- Minimize geography (same availability zone).
- Batch data; eliminate cross-network chit-chat.
- In-memory caching, with care for invalidation.
- Publish events on data change so subscribers cache locally for fast reads.

## Why This Matters

These are the root cause of microservice call storms, cascading failures, silent
data loss, "it works on my machine" in distributed contexts, and over-reliance
on synchronous RPC where messaging would fit better.

## Why This Lens Applies In PR Review

When a diff adds or changes a call across a process boundary (an HTTP call, an
MCP request, a child process, a queue read or write, an agent orchestration
step), check it against the fallacies it most often violates. Does a new
synchronous call assume the network is reliable and zero-latency (1 and 2)? Does
a retry assume the request, not the response, was lost (1)? Does a config assume
a fixed topology or a single operator (5 and 6)? Does a chatty loop ignore
transport cost (2 and 7)? Each fallacy maps to a concrete reliability or
architecture finding: name the number, name the call site, name the failure it
invites.

## Related

- `.claude/rules/release-it.md`: the stability-patterns rule (timeouts, retries,
  circuit breakers, bounded queues) that turns these fallacies into review
  checks.
- OTel semantic conventions: the failure modes here are only actionable if the
  call emits the telemetry an operator needs to see them.

## Source

Peter Deutsch and James Gosling, Fallacies of Distributed Computing (Sun
Microsystems, 1994).
