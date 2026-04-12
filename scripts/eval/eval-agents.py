#!/usr/bin/env python3
"""Agent Definition Quality Assessment: Measure agent prompt quality against role expectations.

Unlike skill assessments (baseline vs enhanced), agent assessments score how well the agent
definition performs its stated job. Each agent is scored on four dimensions:
  - Role adherence: stays in character, does what the definition says
  - Actionability: outputs are concrete, specific, and usable
  - Quality signals: follows style guide (no filler, data over adjectives)
  - Appropriateness: matches behavior to problem complexity (Cynefin-aware)

Each prompt is tagged with a Cynefin complexity classification that determines the
expected behavior pattern. An "ask first" agent receives high appropriateness for
asking good questions on Complex problems, and low appropriateness for asking
unnecessary questions on Clear problems where direct output is expected.

Complexity classifications:
  - clear: Standard problem, known pattern. Expected: direct output, minimal questions.
  - complicated: Requires expert analysis. Expected: produce with trade-offs and assumptions.
  - complex: Multiple unknowns, no clear right answer. Expected: ask clarifying questions, explore space.
  - chaotic: Crisis/urgent. Expected: stabilize first, then ask, then produce.

Usage:
    python3 scripts/eval/eval-agents.py
    python3 scripts/eval/eval-agents.py --agent analyst
    python3 scripts/eval/eval-agents.py --prompts-file custom-agent-prompts.json
    python3 scripts/eval/eval-agents.py --dry-run
    python3 scripts/eval/eval-agents.py --output results.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# API utilities (shared module)
# ---------------------------------------------------------------------------

from _anthropic_api import call_api as _call_api, load_api_key as _load_api_key, load_custom_prompts


# ---------------------------------------------------------------------------
# Agent context loading
# ---------------------------------------------------------------------------

RATE_LIMIT_SLEEP_SEC = 1.0  # fixed inter-call delay; no 429 backoff (dev tool)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
assert AGENTS_DIR.is_dir(), f"AGENTS_DIR miscomputed: {AGENTS_DIR} (is this script still at scripts/eval/?)"


def list_agents() -> list[str]:
    """List agent names under AGENTS_DIR.

    Only includes markdown files whose content starts with a `---` frontmatter
    block. Index files, READMEs, and CLAUDE.md are skipped automatically.
    """
    agents = []
    for f in sorted(AGENTS_DIR.iterdir()):
        if not (f.is_file() and f.suffix == ".md"):
            continue
        with f.open(encoding="utf-8") as fh:
            if fh.read(3) == "---":
                agents.append(f.stem)
    return agents


def load_agent_context(agent_name: str) -> str:
    """Load full agent definition as system prompt context."""
    agent_file = AGENTS_DIR / f"{agent_name}.md"
    if not agent_file.exists():
        return ""
    return agent_file.read_text(encoding="utf-8")


def extract_agent_meta(agent_name: str) -> dict[str, str]:
    """Extract minimal frontmatter fields (name, description, model).

    Ignores nested keys like ``metadata.tier`` and list-valued fields. Good
    enough for the assessment framework, which only needs the three fields
    above.
    """
    text = load_agent_context(agent_name)
    if not text.startswith("---"):
        return {"name": agent_name}

    end = text.find("---", 3)
    if end == -1:
        return {"name": agent_name}

    frontmatter = text[3:end].strip()
    meta: dict[str, str] = {"name": agent_name}
    for line in frontmatter.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k in ("name", "description", "model"):
                meta[k] = v
    return meta


# ---------------------------------------------------------------------------
# Built-in prompts: 4 prompts per agent, targeting stated capabilities
# ---------------------------------------------------------------------------

PROMPTS: dict[str, list[dict[str, Any]]] = {
    "analyst": [
        {
            "prompt": "A deployment pipeline started failing intermittently 3 days ago. No code changes were deployed. The failure rate is ~15% and only affects the build step. Investigate.",
            "expected": "Structured investigation plan: environment changes (OS patches, dependency updates, runner changes), flaky test identification, timeline correlation, log analysis approach. Should NOT jump to solutions.",
            "complexity": "complicated"
        },
        {
            "prompt": "Product wants to add real-time notifications. We currently use polling. Research the feasibility and trade-offs.",
            "expected": "WebSocket vs SSE vs long-polling comparison with concrete trade-offs (connection limits, proxy compatibility, mobile battery). Infrastructure requirements. Existing code patterns to leverage. Dependencies and risks.",
            "complexity": "complicated"
        },
        {
            "prompt": "We have 3 microservices that each maintain their own user cache. Users report stale data after profile updates. What are we dealing with?",
            "expected": "Cache invalidation analysis: identify cache consistency model (eventual vs strong), propagation delay measurement, event-driven invalidation options. Root cause vs symptom distinction.",
            "complexity": "complicated"
        },
        {
            "prompt": "A feature request asks for 'AI-powered search'. Before anyone writes code, what do I need to know?",
            "expected": "Requirements discovery: what does 'AI-powered' mean specifically? Semantic search vs autocomplete vs RAG. Data volume, latency requirements, cost per query. Build vs buy analysis. Existing search infrastructure.",
            "complexity": "complex"
        },
    ],
    "architect": [
        {
            "prompt": "A team proposes adding a GraphQL layer on top of our existing REST APIs to 'simplify the frontend'. Review this decision.",
            "expected": "Challenge the premise: does GraphQL solve the actual problem? N+1 query risk. Caching complexity increase. Schema governance overhead. Alternative: BFF pattern. Should require ADR."
        },
        {
            "prompt": "We need to share business logic between a web app and a mobile app. The proposal is a shared npm package. Architectural review.",
            "expected": "Coupling analysis: shared package creates deployment coupling. Version drift risk. Platform-specific concerns leaked into shared code. Alternative: API-first with thin clients. Separation of concerns."
        },
        {
            "prompt": "Our monolith has grown to 500K LOC. Three teams work on it. Proposal: split into microservices along team boundaries. Assess.",
            "expected": "Gall's Law warning: don't redesign, evolve. Conway's Law alignment is good but insufficient. Start with modular monolith boundaries. Identify the hot module first. Data ownership before service boundaries."
        },
        {
            "prompt": "Review this design: a service that both reads from and writes to a shared PostgreSQL database, and also publishes events to Kafka for downstream consumers.",
            "expected": "Dual-write problem: DB write + Kafka publish are not atomic. Outbox pattern or CDC needed. Coupling through shared DB is a boundary violation. Event schema governance."
        },
    ],
    "critic": [
        {
            "prompt": "Here is our plan: migrate from MySQL to PostgreSQL over 3 weekends. Step 1: export MySQL data. Step 2: import to PostgreSQL. Step 3: switch connection strings. Step 4: decommission MySQL. Assess.",
            "expected": "Missing rollback plan. No dual-write/read period. No data validation step. Application-level query compatibility not addressed. Performance regression testing absent. What happens if Step 3 fails at 2am Sunday?",
            "complexity": "complicated"
        },
        {
            "prompt": "Plan: Add feature flags to all new features. Use LaunchDarkly. Roll out to 10% of users first, then 50%, then 100%. Is this plan ready?",
            "expected": "Missing: flag cleanup strategy (flag debt), monitoring per cohort, definition of 'success' metrics per rollout stage, kill criteria, data consistency across flag states.",
            "complexity": "complicated"
        },
        {
            "prompt": "We will refactor the auth module by extracting it into a separate service. Timeline: 2 weeks. No tests exist for the current module. Plan review.",
            "expected": "Pre-mortem: extracting without tests means no safety net. 2-week estimate for service extraction is unrealistic. Missing: characterization tests first, API contract definition, auth token handling during migration.",
            "complexity": "complicated"
        },
        {
            "prompt": "Proposal: replace our custom logging with structured logging using Serilog. Scope: all 12 services. Timeline: 1 sprint. Review.",
            "expected": "Scope vs timeline mismatch: 12 services in 1 sprint requires parallel work. Missing: log schema standardization, correlation ID propagation, backward compatibility with existing log consumers, rollback strategy per service.",
            "complexity": "complicated"
        },
    ],
    "implementer": [
        {
            "prompt": "Implement a rate limiter middleware for an ASP.NET Core API. Requirements: 100 requests per minute per IP, sliding window, return 429 with Retry-After header.",
            "expected": "Production-quality implementation: sliding window algorithm, thread-safe storage (ConcurrentDictionary or distributed cache), middleware registration, proper 429 response with Retry-After calculation. Tests for edge cases."
        },
        {
            "prompt": "Add a health check endpoint that verifies database connectivity and returns degraded status if the DB is slow (>500ms).",
            "expected": "IHealthCheck implementation with timed DB query. Degraded vs Unhealthy distinction. Timeout handling. Should not block the health check if DB is down. Integration test."
        },
        {
            "prompt": "The current code uses string concatenation for SQL queries in 3 places. Fix the SQL injection vulnerability.",
            "expected": "Parameterized queries for all 3 locations. Specific file:line references. No ORM migration, just fix the vulnerability. Test with injection payloads."
        },
        {
            "prompt": "Write a retry policy for HTTP calls to an external API. Requirements: exponential backoff, max 3 retries, jitter, circuit breaker after 5 consecutive failures.",
            "expected": "Polly-based implementation (or equivalent). Exponential backoff with jitter formula. Circuit breaker state machine. Logging per retry attempt. Unit tests for retry count and backoff timing."
        },
    ],
    "security": [
        {
            "prompt": "Review this endpoint: POST /api/upload accepts a file path from the request body and reads the file from disk to return its contents.",
            "expected": "CWE-22 path traversal. Attacker can read /etc/passwd or application secrets. Mitigation: allowlist, path canonicalization, chroot. STRIDE: Information Disclosure + Tampering."
        },
        {
            "prompt": "Our CI pipeline uses a GitHub Action that runs `npm install` and then executes a postinstall script from a dependency. Security assessment.",
            "expected": "Supply chain attack vector. Postinstall scripts execute arbitrary code. Mitigations: --ignore-scripts, lockfile integrity, dependency pinning, SLSA provenance. CWE-506 (embedded malicious code)."
        },
        {
            "prompt": "API returns user objects including email, phone, and hashed_password in the response. The frontend only needs name and avatar. Assess.",
            "expected": "Excessive data exposure (OWASP API3). hashed_password should never leave the server. DTOs/projections needed. Principle of least privilege on data. CWE-200."
        },
        {
            "prompt": "Authentication uses JWT stored in localStorage. Tokens expire after 24 hours. No refresh token mechanism. Security review.",
            "expected": "XSS can steal tokens from localStorage. Use httpOnly cookies instead. 24h expiry is too long. Missing: token revocation, refresh rotation, CSRF protection if switching to cookies."
        },
    ],
    "devops": [
        {
            "prompt": "Design a GitHub Actions CI pipeline for a Python monorepo with 3 packages. Requirements: lint, test, build Docker images, deploy to staging on merge to main.",
            "expected": "Matrix strategy for 3 packages. Path-based triggers. Caching (pip, Docker layers). Parallel lint+test, sequential deploy. Environment protection rules. Secrets management."
        },
        {
            "prompt": "Our Docker build takes 8 minutes. The Dockerfile installs dependencies, copies source, and builds. How to speed it up?",
            "expected": "Layer ordering: dependencies before source (cache deps layer). Multi-stage build. .dockerignore. BuildKit cache mounts. Specific base image (not latest). Concrete time savings estimates."
        },
        {
            "prompt": "We need to deploy the same app to 3 environments (dev, staging, prod) with different configs. Design the approach.",
            "expected": "Environment-specific config via env vars or mounted secrets. Same artifact across environments (build once, deploy many). GitHub environments with approval gates for prod. No config in Docker image."
        },
        {
            "prompt": "A developer accidentally pushed a secret (API key) to the repository. What's the remediation plan?",
            "expected": "Immediate: rotate the key. Git: BFG repo cleaner or filter-branch (historical removal). Prevention: pre-commit hooks (detect-secrets), GitHub secret scanning. Audit: check key usage logs."
        },
    ],
    "qa": [
        {
            "prompt": "A signup form was just implemented. Design the test strategy covering happy path and edge cases.",
            "expected": "Happy path: valid email, strong password, successful redirect. Edge cases: duplicate email, weak password, SQL injection in fields, XSS in name field, empty fields, max length, unicode characters. Accessibility checks."
        },
        {
            "prompt": "After deploying a cart feature, users report items disappearing. How do you test this?",
            "expected": "Reproduce: add items, navigate away, return. Check: session persistence, concurrent tab behavior, cache invalidation, race conditions on quantity update. User-focused scenarios, not unit tests."
        },
        {
            "prompt": "The test suite has 200 tests, all passing, but users keep finding bugs. What's wrong?",
            "expected": "Tests verify implementation, not user behavior. Missing: integration tests, E2E flows, edge cases, error paths, concurrent usage, real data shapes. Coverage number is misleading without scenario coverage."
        },
        {
            "prompt": "We added dark mode. What should QA verify beyond 'colors changed'?",
            "expected": "Contrast ratios (WCAG AA 4.5:1). Image/icon visibility. Input field borders. Disabled state visibility. Chart/graph readability. Transition between modes (no flash). OS preference respect. Persistence across sessions."
        },
    ],
    "explainer": [
        {
            "prompt": "Write a PRD for adding two-factor authentication to an existing login system. Target audience: junior developers.",
            "expected": "Clear problem statement. User stories with INVEST criteria. Acceptance criteria (testable, pass/fail). No jargon without definition. Concrete examples of user flow. Out of scope section.",
            "complexity": "clear"
        },
        {
            "prompt": "Explain the difference between authentication and authorization to someone who has never heard either term.",
            "expected": "Concrete analogy (building access: badge = authentication, floor access = authorization). No assumed knowledge. Examples before definitions. Progressive complexity.",
            "complexity": "clear"
        },
        {
            "prompt": "Document how our API rate limiting works for new team members.",
            "expected": "What it does (plain English), why it exists, how to test against it, what happens when limits are hit, how to request increases. Code examples. No unexplained acronyms.",
            "complexity": "clear"
        },
        {
            "prompt": "Write acceptance criteria for a 'forgot password' feature.",
            "expected": "Numbered, independently testable criteria. Each one pass/fail verifiable. Covers: email validation, token expiry, password requirements, rate limiting, success/failure UX. No ambiguous language.",
            "complexity": "clear"
        },
    ],
    "milestone-planner": [
        {
            "prompt": "Break down 'migrate from REST to gRPC for inter-service communication' into milestones. We have 4 services.",
            "expected": "Sequential milestones with exit criteria. M1: protobuf schema + code gen. M2: one service (lowest risk) dual-protocol. M3: remaining services. M4: decommission REST. Each independently shippable. Parallel opportunities identified.",
            "complexity": "complicated"
        },
        {
            "prompt": "Plan milestones for adding multi-tenancy to a single-tenant SaaS application.",
            "expected": "Data isolation strategy first (schema-per-tenant vs row-level). M1: tenant context middleware. M2: data layer isolation. M3: auth/authz per tenant. M4: tenant provisioning. Risk: data leakage between tenants.",
            "complexity": "complicated"
        },
        {
            "prompt": "Epic: 'Improve API response times by 50%'. Create implementation milestones.",
            "expected": "M1: baseline measurement + profiling (exit: bottlenecks identified with data). M2: quick wins (caching, query optimization). M3: architectural changes (async, connection pooling). Each with measurable exit criteria.",
            "complexity": "complicated"
        },
        {
            "prompt": "We need to upgrade from .NET 6 to .NET 9. 15 projects in the solution. Plan it.",
            "expected": "Dependency graph analysis first. Leaf projects before root. M1: shared libraries. M2: test projects. M3: application projects. M4: deployment pipeline updates. Breaking change assessment per milestone.",
            "complexity": "complicated"
        },
    ],
    "task-decomposer": [
        {
            "prompt": "Decompose 'Add CSV export to the reports page' into atomic tasks.",
            "expected": "Tasks sized S/M/L. Each independently verifiable. T1: CSV serialization utility (S). T2: export endpoint with streaming (M). T3: UI button + download trigger (S). T4: large dataset pagination/chunking (M). Acceptance criteria per task."
        },
        {
            "prompt": "Break down 'Implement email notifications for order status changes' into work items.",
            "expected": "T1: email template system (M). T2: order status change event (S). T3: notification preferences model (S). T4: email sending service integration (M). T5: unsubscribe mechanism (S). Done definition per item."
        },
        {
            "prompt": "Decompose: 'Add audit logging for all admin actions'.",
            "expected": "T1: audit log schema/model (S). T2: middleware/interceptor for admin routes (M). T3: structured log format with actor/action/target (S). T4: audit log query/search API (M). T5: retention policy (S). Dependency ordering."
        },
        {
            "prompt": "Break down 'Add dark mode support' for a React application.",
            "expected": "T1: theme token system (colors, shadows) (M). T2: CSS custom properties integration (S). T3: theme toggle component + persistence (S). T4: component audit for hardcoded colors (M). T5: image/icon variants (S). Sequenced by dependency."
        },
    ],
    "orchestrator": [
        {
            "prompt": "A user reports: 'The checkout page is broken after the latest deploy. Orders are failing with a 500 error.' Coordinate the response.",
            "expected": "Classify severity (P0, revenue impact). Route: analyst for root cause, devops for rollback assessment, qa for reproduction. Sequence: investigate first, don't fix blind. Synthesize findings before action.",
            "complexity": "chaotic"
        },
        {
            "prompt": "User asks: 'Plan and implement a new webhook system for our API.' Coordinate the multi-step task.",
            "expected": "Route: spec-generator for requirements, architect for design review, milestone-planner for breakdown, implementer for code, qa for testing. Sequence respects dependencies. Handoff context preserved between agents.",
            "complexity": "complicated"
        },
        {
            "prompt": "Three PRs are open: a security fix (P0), a feature (P2), and a refactor (P3). Coordinate review and merge.",
            "expected": "Priority ordering: security first. Route security to security agent + implementer. Feature to architect + qa. Refactor to critic. Merge order matters: security, then feature (check conflicts), then refactor.",
            "complexity": "complicated"
        },
        {
            "prompt": "User says: 'Our API is slow. Fix it.' Classify complexity and coordinate.",
            "expected": "Classify as Complex (Cynefin). Don't jump to implementation. Route to analyst for profiling/investigation first. Then architect for systemic issues. Then implementer for targeted fixes. Report back with evidence.",
            "complexity": "complex"
        },
    ],
    "roadmap": [
        {
            "prompt": "We have 5 feature requests, 3 tech debt items, and a security vulnerability. Prioritize for next quarter.",
            "expected": "Security vulnerability is P0 (non-negotiable). Then RICE/KANO scoring for features vs debt. Outcome-focused: which features drive retention/revenue? Tech debt scored by blast radius. Clear sequencing with rationale.",
            "complexity": "complicated"
        },
        {
            "prompt": "A stakeholder wants us to build a custom CRM. We currently use spreadsheets. Should we build, buy, or partner?",
            "expected": "Challenge the build instinct. Consider Salesforce/HubSpot fit. What is unique about our needs? TCO comparison. Build only if core differentiator. Start with the smallest thing that could work.",
            "complexity": "complex"
        },
        {
            "prompt": "We shipped 3 features last quarter but NPS dropped 5 points. What is the strategic response?",
            "expected": "Features without user value is vanity work. Investigate: which features drove the drop? User feedback data. Reliability/performance regression? Strategic drift: building what was asked vs what was needed.",
            "complexity": "complex"
        },
        {
            "prompt": "Engineering wants to spend a full sprint on tech debt. Product says we need 2 features for a conference demo. Resolve.",
            "expected": "False dichotomy. Which tech debt blocks feature velocity? Interleave: debt that enables features ships first. Conference demo scope: what is the minimum that impresses? Challenge both sides.",
            "complexity": "complex"
        },
    ],
    "high-level-advisor": [
        {
            "prompt": "We have been discussing our architecture for 3 weeks. No code has been written. We have 4 competing proposals. What do we do?",
            "expected": "Decision paralysis. Pick the most reversible option and ship it. Analysis paralysis costs more than a wrong choice you can undo. Set a 48-hour deadline. If no consensus, the tech lead decides."
        },
        {
            "prompt": "Our team of 5 is maintaining 12 microservices. Performance is fine but developer velocity is low. Advice.",
            "expected": "Too many services for team size. Consolidate. 2-3 services per engineer is unsustainable for on-call, context switching, and deployment overhead. Merge low-traffic services. Monolith is not a dirty word."
        },
        {
            "prompt": "We are 80% done with a rewrite but the original system still works. Should we finish or cut losses?",
            "expected": "Sunk cost fallacy check. 80% done means the hardest 20% remains. Is the rewrite solving a real problem or just 'cleaner code'? If original works, consider strangler fig instead of big-bang switch."
        },
        {
            "prompt": "Three senior engineers disagree on the right database. PostgreSQL, MongoDB, DynamoDB. They each have strong opinions. Break the tie.",
            "expected": "What are the actual data access patterns? Don't pick the database, pick the one that fits the workload. If ACID matters, PostgreSQL. If schema flexibility, MongoDB. If scale-to-zero, DynamoDB. No 'it depends' without specifics."
        },
    ],
    "independent-thinker": [
        {
            "prompt": "Everyone on the team agrees we should use Kubernetes. Challenge this.",
            "expected": "Challenge: do you have the ops team to run it? ECS/Cloud Run are simpler for most workloads. K8s operational cost is hidden (upgrades, networking, RBAC). Unless you need multi-cloud or custom schedulers, you are adding complexity."
        },
        {
            "prompt": "The industry consensus is that microservices are better than monoliths. Present the counter-argument.",
            "expected": "Monoliths are better for most teams. Distributed systems add latency, debugging complexity, deployment coordination, and data consistency problems. Amazon, Shopify, and Basecamp run successful monoliths. Start monolithic, extract when proven necessary."
        },
        {
            "prompt": "Our CTO says 'we should rewrite in Rust for performance'. Provide a contrarian view.",
            "expected": "Profile first. Where is the bottleneck? If it is I/O bound, Rust will not help. If it is algorithmic, fix the algorithm in any language. Rust has a steep learning curve and smaller hiring pool. Consider: optimize the hot path only."
        },
        {
            "prompt": "The team wants 100% test coverage. Is this always the right goal?",
            "expected": "100% coverage incentivizes trivial tests. Coverage measures lines executed, not behavior verified. Better metric: mutation testing score. Focus coverage on business logic and error paths. Some code (UI layout, config) is not worth testing."
        },
    ],
    "spec-generator": [
        {
            "prompt": "We need a password reset feature. Generate the spec.",
            "expected": "Clarifying questions first (email or SMS? token expiry? rate limiting?). EARS format requirements. Testable acceptance criteria. Security considerations (token entropy, brute force protection). Out of scope section.",
            "complexity": "complicated"
        },
        {
            "prompt": "Feature idea: 'users should be able to share reports with external people'. Spec it.",
            "expected": "Questions: what access level? Expiry? Revocation? Auth required for viewers? Then: requirements with SHALL/SHOULD/MAY. Acceptance criteria (each independently testable). Privacy/compliance considerations.",
            "complexity": "complex"
        },
        {
            "prompt": "Vibe-level description: 'make the dashboard faster'. Transform into a spec.",
            "expected": "Push back on vague requirement. Define measurable targets (LCP < 2.5s, TTI < 3.8s). Identify which dashboard components are slow. Requirements tied to specific performance metrics, not subjective 'fast'.",
            "complexity": "complex"
        },
        {
            "prompt": "We want to add webhooks so customers can subscribe to events. Spec this feature.",
            "expected": "Event catalog (which events?). Delivery guarantees (at-least-once). Retry policy. Payload format (schema versioning). Authentication (HMAC signing). Rate limiting. Self-service management UI vs API-only.",
            "complexity": "complex"
        },
    ],
    "backlog-generator": [
        {
            "prompt": "The project has 3 open PRs (2 bug fixes, 1 feature), 5 open issues (3 bugs, 1 feature request, 1 improvement), and the CI is green. Generate backlog items.",
            "expected": "3-5 actionable items. Sized (S/M/L). Prioritized by impact. Should address: unresolved bugs, blocked PRs, improvement opportunities from code health. Each item is pick-up-and-go ready."
        },
        {
            "prompt": "All PRs are merged, no open issues, CI is green, but test coverage is at 45%. Generate work.",
            "expected": "Coverage improvement tasks: identify uncovered critical paths, not just line coverage. Technical debt items from recent commits. Documentation gaps. Performance baseline establishment."
        },
        {
            "prompt": "We have 10 open issues, 5 are stale (>30 days). Agent slots are idle. What should we work on?",
            "expected": "Triage stale issues (close or re-prioritize). Generate fresh items from: code health analysis, dependency updates, security audit findings. Don't just restate the open issues."
        },
        {
            "prompt": "The last 3 PRs all touched the same 2 files. No issues mention this area. Generate backlog items.",
            "expected": "Hotspot analysis: high churn files likely need refactoring. Generate: extract shared logic, add tests for the hot area, consider architectural review of that module. Proactive, not reactive."
        },
    ],
    "retrospective": [
        {
            "prompt": "Last sprint: shipped 2 features, missed 1 deadline, had 1 production incident (30 min downtime), resolved 5 bugs. Run the retro.",
            "expected": "Structured framework (Start/Stop/Continue or similar). Root cause the missed deadline (scope creep? dependency?). Incident timeline and prevention. Pattern analysis across the 5 bugs. Actionable improvements, not platitudes."
        },
        {
            "prompt": "The team has been using AI agents for 2 months. Run a retrospective on agent performance.",
            "expected": "What worked (speed, consistency). What did not (hallucinations, context loss). Error pattern analysis. Agent routing accuracy. Specific improvement recommendations. Learning matrix: capture for future sessions."
        },
        {
            "prompt": "We ran 3 sprints without a retro. Run a combined retrospective covering the full period.",
            "expected": "Timeline analysis across sprints. Trend identification (getting better or worse?). Five Whys on recurring issues. Consolidate learnings. Flag patterns that would have been caught earlier with regular retros."
        },
        {
            "prompt": "A project took 3x the estimated time. Run a post-project retrospective.",
            "expected": "Estimate vs actual breakdown by milestone. Where did the 3x come from? Scope creep, unknown unknowns, dependency delays? Atomicity scoring of original plan. Calibration recommendations for future estimates."
        },
    ],
    "skillbook": [
        {
            "prompt": "During this sprint, we learned: (1) our retry policy needs jitter, (2) structured logging caught a bug faster than unstructured, (3) the auth middleware has undocumented rate limiting. Encode these.",
            "expected": "Three atomic skill updates. Each has: rule, why, how to apply. Deduplication check against existing skills. Scored for atomicity (one concept per update). Reject if too vague."
        },
        {
            "prompt": "A developer said 'mocking the database in tests is fine'. Later, a production migration failed that tests did not catch. Capture the learning.",
            "expected": "Atomic skill: integration tests should hit real DB for migration safety. Why: mock/prod divergence masks schema issues. How to apply: migration tests always use real DB. Confidence: HIGH (production incident)."
        },
        {
            "prompt": "We have been using the same deployment script for 6 months without issues. Should we capture anything?",
            "expected": "Capture success pattern: what makes this script reliable? Immutability, idempotency, rollback steps? Don't create noise for 'it just works'. Only encode if there is a transferable principle."
        },
        {
            "prompt": "Three different developers independently chose the Strategy pattern for similar problems this month. Encode the pattern.",
            "expected": "Meta-pattern: when the team reaches for Strategy, what is the trigger? Document the recognition heuristic (multiple conditional branches on type). Link to existing CVA/design skills. Avoid duplicating GoF docs."
        },
    ],
    "adr-generator": [
        {
            "prompt": "We decided to use PostgreSQL over MongoDB for our new service because we need ACID transactions and complex joins. Write the ADR.",
            "expected": "ADR format: title, status, context, decision, consequences. Alternatives considered (MongoDB, DynamoDB). Trade-offs documented. Consequences (schema migration overhead, horizontal scaling limits). Reviewers identified."
        },
        {
            "prompt": "We are adopting Python for new scripts instead of Bash. Document this decision.",
            "expected": "Context: Bash is error-prone for complex logic, not testable, not cross-platform. Decision: Python for all new scripts. Alternatives: PowerShell, Node.js. Consequences: Python dependency required, but testable and maintainable."
        },
        {
            "prompt": "The team decided to use feature flags (LaunchDarkly) instead of long-lived feature branches. ADR this.",
            "expected": "Context: feature branches cause merge conflicts and integration delays. Decision: trunk-based development with feature flags. Alternatives: GitFlow, release branches. Consequences: flag cleanup discipline required, runtime complexity."
        },
        {
            "prompt": "We are moving from REST to gRPC for internal service communication. Write the ADR.",
            "expected": "Context: REST overhead for high-frequency internal calls, schema drift. Decision: gRPC with protobuf. Alternatives: REST with OpenAPI, GraphQL. Consequences: protobuf schema management, learning curve, debugging tooling."
        },
    ],
    "memory": [
        {
            "prompt": "It is a new session. The user is working on a payment refund feature. What context should you retrieve?",
            "expected": "Search for: payment-related memories, refund-related decisions, previous session context on this branch, architectural constraints for payment systems, relevant ADRs. Synthesize into actionable briefing."
        },
        {
            "prompt": "During the session, the architect agent decided to use the Outbox pattern for event publishing. Should this be persisted?",
            "expected": "Yes. Architectural decision with cross-session value. Store with: decision, rationale, context (which service), related ADR if exists. Tag for future retrieval by architect and implementer agents."
        },
        {
            "prompt": "A memory from 3 months ago says 'the user table has 50K rows'. The table now has 2M rows. How do you handle this?",
            "expected": "Staleness detection. Verify against current state before acting on the memory. Update or mark obsolete. Memories are claims about a point in time, not facts about now."
        },
        {
            "prompt": "The user asks 'what did we decide about caching last month?' Search and synthesize.",
            "expected": "Multi-tier search: Serena memories, session logs, ADRs, git history. Present findings with source attribution and dates. Flag if multiple conflicting decisions exist. Don't fabricate if nothing found."
        },
    ],
    "quality-auditor": [
        {
            "prompt": "Audit the test infrastructure domain: test configuration, fixtures, mocking patterns, and CI integration.",
            "expected": "Graded report (A-F) per layer. File counts and coverage. Specific gaps: missing integration tests, fixture sprawl, mock overuse. Trend vs previous audit if available. Actionable improvement items."
        },
        {
            "prompt": "The documentation domain has README.md, CLAUDE.md, and AGENTS.md. Grade it.",
            "expected": "Grade per file: accuracy, completeness, freshness. Cross-reference: do docs match current code? Gap tracking: undocumented modules, stale references. Concrete improvement recommendations."
        },
        {
            "prompt": "Run a quality audit on the agent definitions in .claude/agents/.",
            "expected": "Audit axes: prompt clarity, role overlap between agents, style guide compliance, tool access consistency, model assignment appropriateness. Grade A-F per agent. Surface redundancy and gaps."
        },
        {
            "prompt": "Scan the CI/CD configuration for quality issues.",
            "expected": "Check: pinned action versions, secret handling, cache strategy, matrix efficiency, job dependencies, timeout configuration, artifact management. Grade with specific file:line references."
        },
    ],
    "issue-feature-review": [
        {
            "prompt": "Feature request: 'Add dark mode to the admin dashboard'. 15 upvotes. Assess.",
            "expected": "Summarize the ask. User impact: cosmetic vs accessibility need? Implementation cost: theme system needed? Effort vs value. Recommendation with actionable next steps. Constructive skepticism: is this the right priority?"
        },
        {
            "prompt": "Issue: 'Support SAML SSO for enterprise customers'. 3 enterprise prospects requesting it. Assess.",
            "expected": "Revenue impact assessment. Implementation complexity (SAML is non-trivial). Build vs buy (Auth0, Okta). Competitive analysis: do competitors offer it? Recommendation tied to business outcomes."
        },
        {
            "prompt": "Feature request: 'Add AI-powered code review comments'. No upvotes. From internal team member. Assess.",
            "expected": "Low signal (no external validation). Clarify: what specific problem does this solve? Existing tools (CodeRabbit, Copilot)? Build vs integrate. Flag: internal requests without user demand are dangerous."
        },
        {
            "prompt": "Bug report: 'App crashes when uploading files > 100MB'. 2 reports. Assess severity and priority.",
            "expected": "Severity: crash = high. But frequency: only 2 reports. Check: what is the expected max file size? Is 100MB a valid use case? If yes, P1 with size limit increase or chunked upload. If no, better error message."
        },
    ],
    "context-retrieval": [
        {
            "prompt": "About to plan implementation of a caching layer. What context should be gathered?",
            "expected": "Search: caching decisions (ADRs), performance benchmarks, existing cache usage, framework docs (Context7 for cache library). Read linked artifacts. Surface constraints and prior decisions."
        },
        {
            "prompt": "Starting work on a branch that was abandoned 2 weeks ago. Retrieve context.",
            "expected": "Git log for branch history. Session logs from 2 weeks ago. Memory search for branch-related decisions. HANDOFF.md contents. Synthesize: what was done, what remains, why it was paused."
        },
        {
            "prompt": "Need to understand how the authentication system works before modifying it. Gather context.",
            "expected": "Serena symbol analysis for auth modules. Memory search for auth decisions. ADR search. Framework docs for auth library. Code pattern analysis. Dependency mapping."
        },
        {
            "prompt": "User mentions they discussed API versioning in a previous session. Find that context.",
            "expected": "Search across: Serena memories (API versioning), session logs (grep for 'version'), ADRs, git commit messages. Return with timestamps and source attribution. Flag if nothing found."
        },
    ],
}


# ---------------------------------------------------------------------------
# Anthropic API interaction (uses shared module with agent-specific max_tokens)
# ---------------------------------------------------------------------------

# Agent assessments use 2048 max_tokens for longer responses
_AGENT_MAX_TOKENS = 2048


def _call_api_for_agents(api_key: str, messages: list[dict], system: str = "", model: str = "claude-sonnet-4-20250514") -> str:
    """Call the Anthropic API with agent-specific max_tokens."""
    return _call_api(api_key, messages, system=system, model=model, max_tokens=_AGENT_MAX_TOKENS)


COMPLEXITY_BEHAVIOR = {
    "clear": (
        "Direct output. The problem is standard with a known pattern. "
        "Producing the requested artifact directly is the correct behavior. "
        "Asking clarifying questions for basic context is OVER-ENGINEERING and scores low on appropriateness."
    ),
    "complicated": (
        "Expert analysis. The problem requires domain expertise but has defensible answers. "
        "The agent should produce output while flagging key assumptions and trade-offs. "
        "Asking questions is appropriate ONLY if essential information is missing. "
        "Jumping to implementation without considering alternatives scores low."
    ),
    "complex": (
        "Explore the space. The problem has multiple stakeholders or unknowns with no clear right answer. "
        "The agent SHOULD ask clarifying questions before committing to a direction. "
        "Producing direct output without surfacing unknowns is INAPPROPRIATE and scores low. "
        "Good questions target high-leverage unknowns."
    ),
    "chaotic": (
        "Stabilize first. The problem is urgent or involves a crisis. "
        "The agent should acknowledge urgency, prioritize immediate stabilization steps, "
        "then ask focused questions, then produce output. Deep analysis without action is inappropriate."
    ),
}


def score_agent_response(
    api_key: str,
    prompt: str,
    response: str,
    expected: str,
    agent_name: str,
    complexity: str = "complicated",
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Score an agent response on 4 dimensions: role, actionability, quality, appropriateness."""
    behavior_guidance = COMPLEXITY_BEHAVIOR.get(complexity, COMPLEXITY_BEHAVIOR["complicated"])

    scoring_prompt = f"""Score the following agent response on four dimensions (1-5 each).

**Agent role**: {agent_name}

**Task given to agent**: {prompt}

**Problem complexity**: {complexity}
**Expected behavior pattern for this complexity**: {behavior_guidance}

**Expected output description**: {expected}

**Actual response**: {response}

Score each dimension:
- **Role adherence** (1-5): Does the response stay in character for the {agent_name} role? Does it do what the role says it should do, not what other roles do?
- **Actionability** (1-5): Are the outputs concrete, specific, and immediately usable? File names, line numbers, specific recommendations vs vague advice?
- **Quality** (1-5): Does the response follow style standards (no AI filler, no hedging, data over adjectives, active voice, short sentences)?
- **Appropriateness** (1-5): Does the response match the behavior pattern for this complexity level? For '{complexity}' problems, {behavior_guidance.split('.')[0]}. Score 5 if the agent correctly matched behavior to complexity, 1 if it went the wrong direction (e.g., asked 10 questions on a clear problem, or produced direct output on a complex problem without surfacing unknowns).

Respond in JSON only, no other text:
{{"role_adherence": <int>, "actionability": <int>, "quality": <int>, "appropriateness": <int>, "reasoning": "<brief explanation>"}}"""

    raw = _call_api_for_agents(api_key, [{"role": "user", "content": scoring_prompt}], model=model)

    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    try:
        scores = json.loads(text)
        # Note: if appropriateness is missing, we leave it out and _avg_scores will exclude it
    except json.JSONDecodeError:
        scores = {
            "role_adherence": 0,
            "actionability": 0,
            "quality": 0,
            "appropriateness": 0,
            "reasoning": f"Failed to parse: {text[:200]}",
        }

    return scores


# ---------------------------------------------------------------------------
# Assessment runner
# ---------------------------------------------------------------------------

DIMENSIONS = ["role_adherence", "actionability", "quality", "appropriateness"]


def _avg_scores(score_list: list[dict]) -> dict[str, float]:
    """Average role_adherence, actionability, quality, appropriateness across score dicts.
    
    Missing dimensions are excluded from averaging rather than treated as 0,
    to avoid corrupting scores when a dimension is not evaluated.
    """
    if not score_list:
        return {dim: 0.0 for dim in DIMENSIONS}

    result = {}
    for dim in DIMENSIONS:
        values = [s[dim] for s in score_list if dim in s and s[dim] is not None]
        if values:
            result[dim] = round(sum(values) / len(values), 2)
        else:
            result[dim] = 0.0
    return result


def run_assessment(
    api_key: str,
    agents: list[str],
    prompts: dict[str, list[dict[str, str]]],
    model: str = "claude-sonnet-4-20250514",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the agent assessment: load agent definition as system prompt, score responses."""
    results: dict[str, Any] = {}
    total = sum(len(prompts.get(a, [])) for a in agents)
    current = 0

    for agent_name in agents:
        agent_prompts = prompts.get(agent_name, [])
        if not agent_prompts:
            print(f"  SKIP {agent_name}: no prompts", file=sys.stderr)
            continue

        agent_context = load_agent_context(agent_name)
        context_size = len(agent_context)

        if not agent_context:
            print(f"  SKIP {agent_name}: agent definition not found", file=sys.stderr)
            continue

        meta = extract_agent_meta(agent_name)
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Agent: {agent_name} (model: {meta.get('model', 'unspecified')}, "
              f"{len(agent_prompts)} prompts, context: {context_size} chars)", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        scores: list[dict] = []

        for i, item in enumerate(agent_prompts):
            current += 1
            prompt_text = item["prompt"]
            expected = item["expected"]
            complexity = item.get("complexity", "complicated")
            print(f"  [{current}/{total}] ({complexity}) {prompt_text[:60]}...", file=sys.stderr)

            if dry_run:
                scores.append({
                    "role_adherence": 0,
                    "actionability": 0,
                    "quality": 0,
                    "appropriateness": 0,
                    "reasoning": "dry-run",
                    "complexity": complexity,
                })
                continue

            # Run prompt with agent definition as system context
            system_ctx = (
                f"You are the {agent_name} agent. Follow your agent definition exactly.\n\n"
                f"{agent_context}"
            )
            response = _call_api_for_agents(api_key, [{"role": "user", "content": prompt_text}],
                                 system=system_ctx, model=model)

            # Score the response with complexity context
            score = score_agent_response(
                api_key, prompt_text, response, expected, agent_name,
                complexity=complexity, model=model
            )
            score["complexity"] = complexity
            scores.append(score)

            r = score.get("role_adherence", 0)
            a = score.get("actionability", 0)
            q = score.get("quality", 0)
            ap = score.get("appropriateness", 0)
            print(f"    R={r} A={a} Q={q} Ap={ap}", file=sys.stderr)

            time.sleep(RATE_LIMIT_SLEEP_SEC)

        results[agent_name] = {
            "scores": scores,
            "context_chars": context_size,
            "model": meta.get("model", "unspecified"),
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Assess agent definition quality")
    parser.add_argument("--agent", type=str, help="Assess a single agent instead of all")
    parser.add_argument("--prompts-file", type=str, help="Load custom prompts from JSON")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-20250514",
                        help="Model to use for assessment")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompts without calling the API")
    parser.add_argument("--output", type=str, help="Write results to file")
    args = parser.parse_args()

    if args.dry_run:
        api_key = ""
    else:
        try:
            api_key = _load_api_key()
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    # Determine which agents to assess
    if args.agent:
        agent_file = AGENTS_DIR / f"{args.agent}.md"
        if not agent_file.exists():
            print(f"ERROR: Agent definition not found: {agent_file}", file=sys.stderr)
            sys.exit(1)
        agents = [args.agent]
    else:
        # Only assess agents that have prompts defined
        agents = [a for a in list_agents() if a in PROMPTS]

    # Load prompts
    if args.prompts_file:
        prompts = load_custom_prompts(args.prompts_file)
        print(f"Loaded custom prompts from {args.prompts_file}", file=sys.stderr)
        if not args.agent:
            agents = list(prompts.keys())
    else:
        prompts = PROMPTS

    prompt_count = sum(len(prompts.get(a, [])) for a in agents)
    api_calls = prompt_count * 2 if not args.dry_run else 0  # 1 run + 1 score per prompt
    print(f"Agents: {agents}", file=sys.stderr)
    print(f"Prompts: {prompt_count}, API calls: {api_calls}", file=sys.stderr)

    if not args.dry_run:
        print(f"Starting assessment (est. {api_calls * 3}s with rate limiting)...",
              file=sys.stderr)

    try:
        results = run_assessment(api_key, agents, prompts, model=args.model, dry_run=args.dry_run)
    except RuntimeError as exc:
        print(f"Error: assessment failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Build output
    output: dict[str, Any] = {
        "assessment_type": "agent-definitions",
        "model": args.model,
        "agents_assessed": agents,
        "total_prompts": prompt_count,
        "dimensions": DIMENSIONS,
        "results": {},
    }

    for agent_name in agents:
        if agent_name in results:
            avg = _avg_scores(results[agent_name]["scores"])
            non_zero_values = [v for v in avg.values() if v > 0]
            overall = round(sum(non_zero_values) / len(non_zero_values), 2) if non_zero_values else 0.0
            output["results"][agent_name] = {
                "context_chars": results[agent_name]["context_chars"],
                "model": results[agent_name]["model"],
                "avg_scores": avg,
                "overall": overall,
                "detail": results[agent_name]["scores"],
            }

    json_output = json.dumps(output, indent=2)

    if args.output:
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

    # Print summary table
    print(f"\n{'='*92}", file=sys.stderr)
    print(f"  AGENT QUALITY RESULTS (4-dimensional, Cynefin-aware)", file=sys.stderr)
    print(f"{'='*92}", file=sys.stderr)
    print(f"  {'Agent':<22} {'Model':<8} {'Role':>6} {'Action':>7} {'Qual':>6} {'Approp':>7} {'Overall':>8}",
          file=sys.stderr)
    print(f"  {'-'*80}", file=sys.stderr)

    sorted_agents = sorted(
        output["results"].items(),
        key=lambda x: x[1].get("overall", 0),
        reverse=True,
    )
    for agent_name, data in sorted_agents:
        avg = data["avg_scores"]
        overall = data["overall"]
        model = data.get("model", "?")[:6]
        print(
            f"  {agent_name:<22} {model:<8} "
            f"{avg.get('role_adherence', 0):>6.2f} "
            f"{avg.get('actionability', 0):>7.2f} "
            f"{avg.get('quality', 0):>6.2f} "
            f"{avg.get('appropriateness', 0):>7.2f} "
            f"{overall:>8.2f}",
            file=sys.stderr,
        )

    print(f"{'='*92}", file=sys.stderr)

    # Highlight weak spots
    weak = [
        (name, data)
        for name, data in sorted_agents
        if data["overall"] < 3.5
    ]
    if weak:
        print(f"\n  BELOW THRESHOLD (<3.5):", file=sys.stderr)
        for name, data in weak:
            print(f"    {name}: {data['overall']:.2f}", file=sys.stderr)

    sys.exit(1 if weak else 0)


if __name__ == "__main__":
    main()
