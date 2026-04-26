---
description: Production survivability patterns from Michael Nygard's _Release It!_. Apply when designing or changing agent orchestration, lifecycle hooks, inter-agent communication, or any code that calls external APIs, message queues, or long-running services. Skip for purely internal utility or pure-function helpers.
alwaysApply: false
---

# Release It! Production Survivability

This rule encodes the patterns from Michael Nygard's _Release It!_ that matter for ai-agents. It applies to agent orchestration, lifecycle hooks, skill execution that crosses a process boundary, and any code that talks to an external API, message queue, file watcher, or other service that can fail independently.

The goal is to keep the system useful when its dependencies misbehave. A failed external call should not stall an orchestrator turn, take down a sibling agent, or wedge a worker pool. Most outages do not start with the code under your fingers; they propagate from one component to another because the boundaries between them are too forgiving.

When the change is purely internal (in-process pure functions, formatting helpers, local data transforms), this rule does not apply. Do not bolt on circuit breakers or retry policies for code that has no remote dependency.

## Core Vocabulary

Use these terms consistently in code, comments, and PR descriptions.

- **Stability pattern**: a structural choice that keeps a system running when something it depends on does not.
- **Stability anti-pattern**: a shape that turns a localized failure into a systemic one.
- **Integration point**: any call that crosses a process, host, or trust boundary. Treat every integration point as a known source of failure.
- **Blast radius**: the set of components a single failure can affect. Smaller is better.
- **Fail fast**: detect that a request cannot succeed and return early, before consuming more resources.
- **Graceful degradation**: keep a reduced version of the feature working when the full version cannot.

## Integration Points Are Suspect

Every integration point is a place where the system can fail in ways the caller did not anticipate.

Apply when:

- The call goes to a different process: HTTP service, database, message broker, file watcher, MCP server, child process.
- The call goes to a managed service or API (OpenAI, Anthropic, GitHub, telemetry sinks).
- The call reads from or writes to a queue, stream, or shared file the caller does not own.

Rules:

- Wrap integration points in a small adapter. The adapter owns timeouts, retries, error translation, and logging. Domain code calls the adapter, not the raw client.
- Translate remote errors into domain errors at the boundary. Do not leak transport-shaped exceptions into business logic.
- Assume the integration point can hang, return malformed data, or return success-shaped failure responses. Validate the response before trusting it.
- Log enough at the boundary to reconstruct the call without touching the remote service: method, target, attempt number, latency, outcome.

Smell: HTTP clients, MCP calls, or queue producers used directly inside orchestration logic, with try/except as the only safety net.

## Timeouts on Every Outbound Call

Use bounded timeouts on every call that crosses a process boundary.

Apply when:

- You issue any network call, MCP request, subprocess invocation, queue read, or file system call against a path that may be remote, mounted, or blocked.
- You compose multiple integration points into a single user-facing operation.

Rules:

- Every outbound call sets an explicit timeout. No "default" timeouts; libraries default to "infinite" too often. Pass the value at the call site or at adapter construction.
- Choose connect and read timeouts independently. A slow DNS or TLS handshake should not consume the read budget.
- The total time budget for a request is the sum of its parts. If a service-level operation must answer in 30 seconds and it makes three downstream calls, no single call may have a 30-second timeout.
- Treat a timeout as a definitive failure. Do not silently extend or retry without going through the retry policy.
- Surface timeouts in structured logs. They are the leading indicator of capacity and dependency problems.

Smell: a downstream call with no timeout, or a generic `requests.get(url)` / `subprocess.run(cmd)` without `timeout=`. In an agent orchestrator, a single hung call ties up a worker, then the queue, then the run.

## Circuit Breaker

Use a circuit breaker to stop sending requests to a failing dependency until it recovers.

Apply when:

- The dependency has a meaningful failure mode that recurs (it goes down, returns 5xx, throttles).
- Repeated calls during the failure cost real resources (threads, connections, agent worker slots, money).
- A cached or degraded response is acceptable while the dependency is unhealthy.

Rules:

- The breaker has three states: closed (calls flow), open (calls fail fast), half-open (a limited probe checks recovery). Make all three observable.
- Trip the breaker on a measurable signal: error rate over a window, consecutive timeouts, or both. Do not trip on a single failure unless the cost of one bad call is high.
- While open, return a defined fallback: cached value, default response, or a typed error the caller can handle. Never return success-shaped data without marking it as fallback.
- Recover via half-open probe traffic, not by clock alone. Move back to closed only after probes succeed; reopen immediately on a probe failure.
- Each integration point gets its own breaker. Do not share a breaker across unrelated dependencies.
- Keep state per-process unless you have a tested distributed implementation. A naive shared store of breaker state is worse than per-process.

Smell: a retry loop that keeps hammering a service that is clearly down, or a single global "is the world okay" flag.

## Bulkheads

Use bulkheads to prevent a failure in one component from consuming resources another component needs.

Apply when:

- Multiple flows share a thread pool, connection pool, agent worker pool, queue, or rate-limit budget.
- One slow dependency could starve unrelated traffic on the same resource.
- A subset of work is more important (user-facing, latency-sensitive) than the rest (background, batch).

Rules:

- Partition shared resources by concern. Give critical traffic its own pool and its own quota.
- Size each partition for its own load, not the worst case across all of them. Idle headroom in one partition is a feature, not waste.
- Make partitioning explicit in the code. Named pools, named queues, named worker groups. Do not encode bulkheads as magic numbers.
- Monitor each partition independently. The aggregate metric will hide saturation in a single partition until it spreads.

Smell: one global thread pool, one global queue, one global agent worker pool serving everything. A single noisy dependency degrades the whole system.

## Retries: Bounded, Idempotent, Backed Off

Retries are useful only when they cost less than the value they recover.

Apply when:

- The operation is genuinely idempotent at the level you are retrying. If the remote side may double-process the request, retries are unsafe.
- The expected failure mode is transient: a packet loss, a 503 from a load balancer, a connection reset.
- You can detect the difference between transient and permanent failures and only retry the transient ones.

Rules:

- Bound the retry count. Two or three attempts is usually enough; more rarely helps.
- Use exponential backoff with jitter. A fixed-interval retry storm synchronizes clients and amplifies the outage.
- Do not retry on 4xx responses. Most are not retryable, and retrying them masks bugs.
- Pair retries with a circuit breaker. Otherwise the retry loop keeps a dying dependency on its knees.
- Include an idempotency key on every retried mutating call. Without it, "exactly once" is wishful thinking.
- Surface retry counts and outcomes in structured logs and metrics. Hidden retries hide capacity problems.

Smell: an unbounded `while True` retry, retries on POST without an idempotency key, retries on a 400-class error, or "let's just retry it" without naming the failure mode you are catching.

## Health Check Integrity

A health check that lies is worse than no health check at all.

Apply when:

- A load balancer, orchestrator, supervisor, or other agent uses a health signal to decide whether to send work to your component.
- You expose a `/health`, `ready`, or status probe.

Rules:

- The health check exercises the actual dependencies the component needs to do its job. It is not a static "200 OK" handler.
- Distinguish liveness from readiness. Liveness is "the process is not wedged"; readiness is "the process can serve requests right now". Restart on liveness failure; remove from rotation on readiness failure.
- A failed dependency makes the health check fail with a useful reason. Returning green while the database is unreachable will route traffic into a crash.
- Cache health results briefly to avoid hammering dependencies, but never longer than the worst tolerable detection delay.
- Keep secrets and internal topology out of health responses. They are read by anyone who reaches the endpoint.

Smell: a health check that always returns 200 because "we restart fast." A health check whose only failure path is the process being completely dead.

## Bound Every Queue and Buffer

Unbounded queues turn slow consumers into outages.

Apply when:

- Producers and consumers run at different rates.
- The system uses an in-process channel, a database-backed work table, a message broker topic, an agent run queue, or a memory write buffer.

Rules:

- Every queue has an explicit maximum depth and a documented overflow policy. Choose one of: drop new, drop old, reject producer, divert to an overflow store. Do not let it grow without bound.
- Reject early, with a typed error the producer can act on, rather than letting backpressure show up as out-of-memory errors.
- Track depth, age of oldest item, and overflow rate. The metric to alert on is "depth approaching the bound", not "depth nonzero".
- For agent orchestration, a queue full of work the agent cannot finish is not progress. Bound it, and signal the orchestrator to slow down upstream.

Smell: in-memory lists used as queues, broker topics with default unlimited retention, agent run tables that never compact. The crash is not OOM; the crash is days later when retention bites.

## Slow Responses Are Failures

A slow response can be worse than a fast failure. It holds resources on both sides.

Apply when:

- Latency objectives exist for the operation (explicit SLO, agent-turn budget, user wait time).
- Resources held during the call are scarce (connections, worker slots, large model contexts).

Rules:

- Define a deadline at the entry point of the operation and propagate it down. Do not let downstream calls exceed the deadline.
- Cancel work that exceeds its deadline. Release the resources, mark the request as failed, log the timeout.
- Prefer a fast, typed timeout error to a slow success that breaks the caller's own deadline.
- Measure the tail (p95, p99), not just the median. Stability problems live in the tail.

Smell: code that waits "as long as it takes," or a deadline parameter that is parsed but never enforced.

## Graceful Degradation Over Hard Failure

Prefer to deliver less than to deliver nothing, when "less" is still useful.

Apply when:

- The full feature depends on multiple services, only some of which are essential.
- A reduced version of the response is meaningful to the caller.
- The user-visible contract documents (or can document) the degraded mode.

Rules:

- Identify the minimum useful response. Decide which inputs are essential and which are enrichments.
- When an enrichment dependency is unavailable, return the minimum response and mark the missing data explicitly. Never silently substitute defaults that look like real data.
- Keep degraded paths exercised. Fallbacks that are never run rot. Run them in tests, in canaries, and occasionally in production via fault injection.
- Document the degraded contract. The caller needs to know what fields are optional and how to detect that they were dropped.

Smell: a single bad downstream call propagates as a 500 to the user when half the response was already computed. Cached or partial answers thrown away because the code path could not represent "partial".

## Stability Anti-Patterns to Reject in Review

These shapes recur in greenfield code. Push back on them.

- **Cascading failure**: one component's failure brings down its callers, then their callers, with no breaker between them.
- **Chain reaction**: a slow node makes its peers absorb its load, the peers slow down, and the chain consumes the cluster.
- **Shared resource exhaustion**: one tenant or one bad request consumes a pool everyone depends on; no bulkhead.
- **Unbalanced capacities**: a downstream service sized for a fraction of upstream traffic with no rate limit between them.
- **Capacity by hope**: assumed limits with no enforcement (queue depth, connection count, retry count).
- **Blocking I/O on a hot path**: synchronous network calls inside a request loop that should answer in milliseconds.
- **Self-inflicted denial of service**: retry storms, thundering herds, or cron jobs that all start at minute 0.
- **Cookie-monster logging**: writing every request body to the log; later, the disk is full and every write blocks.

## Boundaries with the Existing Codebase

ai-agents already has the seams these patterns belong on. Reuse them; do not duplicate.

- The agent orchestrator is the natural home for timeouts, deadlines, breakers, and bulkheads around per-agent work. New use cases that cross a process boundary go through orchestrator-owned adapters, not from skills or hooks directly.
- Lifecycle hooks (SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop) run in line with user-facing work. They MUST be fast, MUST timeout external calls, and MUST never block the agent on an unbounded retry. Hooks that do real work belong behind a circuit-broken adapter, not a raw network call.
- Skills are entry points. Keep them thin: parse, call a service or adapter, format. Do not embed timeouts, retries, or breakers inside skill bodies; lift those into the adapter the skill uses.
- MCP servers and external tooling (gh CLI, search APIs, model providers) are integration points. Treat them with the rules above, even when they are convenient.
- Memory systems (Serena, Forgetful) are integration points too. A failed memory call must degrade to a documented fallback, not silently swallow context loss.

When you find code that deviates from this rule, prefer a small focused refactor on the path you are already touching over a sweeping cleanup. Note the deviation in the PR description so future readers see your reasoning.

## Quick Self-Review

Before opening a PR that touches orchestration, hooks, or any external integration, walk this list.

- Does every outbound call have an explicit timeout (connect and read)?
- Is the operation retried? If yes, is it idempotent, bounded, backed off with jitter, and protected by a circuit breaker?
- Does the failure of any single dependency trip a breaker rather than blocking the caller indefinitely?
- Are queues, buffers, and worker pools bounded with a defined overflow policy?
- Are critical and non-critical flows isolated (different pools, queues, or agent workers)?
- Does the health check fail when the component cannot do its job, and pass when it can?
- Does a downstream failure produce a graceful degradation or a typed error, never a silent success-shaped lie?
- Is the deadline propagated, enforced, and observable in logs and metrics?

If any answer is "no" or "not sure," fix the design before review.
