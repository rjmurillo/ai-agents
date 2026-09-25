---
name: autoplan
version: 0.1.0
description: Route any request to the right skill, command, or agent chain with
  defaults, so nobody hand-picks from the full catalog. Use when you say
  `/autoplan`, `do it`, `handle it`, `figure this out`, or when a concrete
  request names no skill. Do NOT use when the user names a specific skill or
  lifecycle command; invoke that directly.
license: MIT
metadata:
  capability:
    kind: orchestrator
    status: active
  inspiration: gstack /autoplan (garrytan/gstack autoplan/SKILL.md.tmpl)
  routing:
    role: front-door
    invoker: harness
    trigger: the harness selects autoplan for a concrete request that names no skill
    user-facing: true
---

# Autoplan

One lazy entry point for the whole catalog. Classify the request, route it,
apply defaults, and only stop for decisions that are genuinely the user's.
Models and people do not hand-route across dozens of skills; this skill does.

## Identity

This router's stable identity is `project-toolkit:autoplan`. `/autoplan`
stays the local alias inside this repository; nothing is renamed
(REQ-039 criterion 10, DESIGN-037).

| Context | Name the model sees | Contract selected |
|---|---|---|
| This repository, `.claude/skills` | `autoplan` | this router |
| Packaged plugin | `project-toolkit:autoplan` | this router |
| Mixed catalog with gstack | `project-toolkit:autoplan` and `gstack:autoplan` | router by qualified name; gstack's own review pipeline only by its qualified name |

gstack ships an unrelated skill also named `autoplan` (a four-phase
CEO/design/engineering/DX review pipeline). Never invoke a bare `autoplan` in
a mixed catalog expecting this router; use the qualified name. This router
never selects the gstack pipeline by an unqualified request, because that
skill carries no `intents` for this router's long-tail resolver to match.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `/autoplan` followed by the request text | Classify and route the request |
| `do it` | Classify and route the current request |
| `handle it` | Classify and route the current request |
| `figure this out` | Classify, then report the route before running |
| `your call` | Classify, then report the route before running |

The router also fires implicitly. Any concrete request that names no skill
routes through the table below instead of defaulting to a bare answer, for
example "why is CI failing", "investigate the flaky test", or "redo #1723
properly".

These phrases are grounded in this repo's own Copilot and Claude session
history. The dominant real openers are continue, proceed, investigate, fix
the X, do it, and handle it, not ceremonial delegation phrases. Continue and
proceed are deliberately excluded as hard triggers: they mean resume the
in-flight work, so they route to whatever is already running rather than
re-classifying from scratch.

## Precedence

Apply in this order (REQ-039):

1. An explicitly named, installed skill wins, with no rerouting.
2. A high-traffic table row wins next.
3. A single-domain miss goes to the long-tail resolver.
4. A feature, bug, or shipping request with no specialist uses the lifecycle
   chain.
5. Only multi-domain, cross-cutting, or multi-agent work goes to the
   orchestrator.
6. The router never routes to itself. The orchestrator never invokes the
   router.

## Process

### Phase 0: Recon the target

Before you classify, establish the target repository's stack. Do not assume the
stack of the repo this skill ships from (Python-first). The target may be C#,
TypeScript, Go, Rust, or anything else.

Read the target's own signals: `CONTRIBUTING*`, `AGENTS.md`/`CLAUDE.md`,
`README*`, build manifests (`*.csproj`/`*.sln`, `pyproject.toml`,
`package.json`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`,
`build.gradle.kts`, `settings.gradle`, `settings.gradle.kts`), and the
`src/`, `lib/`, `test/`/`tests/` layout. Derive language, build command, test
command, and conventions; carry them into every route. A plan, path, or test
command that does not match the detected stack is a recon failure. For large
governed repos (SDK, runtime, framework), detect contribution gates (API
review, ref-assembly updates, changelog, breaking-change policy) and route
public-API work through those gates: land an API proposal and maintainer
review before writing the implementation.

**Issue already has an in-flight blocking PR.** Check for one before routing an
`autoplan <issue-url>` request into a fresh implementation. If an open PR
already carries a closing keyword for the issue, do not treat "avoid
duplicating that work" and "resolve the issue" as the same goal; they diverge
whenever the PR bundles the requested scope with unrelated scope that has not
cleared review. Do not infer that divergence from an advisory scope- or
size-related label alone (a `needs-split`-style tag): such a label is
routinely assigned purely from commit count or file count, unrelated to
whether the PR's content is actually separable, and a long, cohesive PR can
carry it too. Before trusting one, check what actually assigns it in the
target repository (its CI workflow or label-automation config), not what its
name suggests. Forking a PR on the label's presence alone risks creating a
duplicate implementation instead of extracting anything, so treat any such
label only as a prompt to open the diff and review state, never as evidence
on its own. Confirm from the actual diff and review comments that the
issue's scope sits in its own reviewed, extractable commits before acting;
when it does, extract that slice into its own minimal, mergeable PR rather
than filing a follow-up issue and reporting the parent issue as handled
while it stays open with no merged artifact. (Learned from the
`rjmurillo/ai-agents` repository's issue #5198, 2026-08-25, where
`needs-split` was assigned purely from commit count and proves nothing about
scope; an earlier version of this rule hardcoded that repository's label
semantics and pointed plugin consumers at a test file that does not ship
with this skill. Also from the same issue: two independently-extracted
slices of the same blocking PR can race each other and one PR merging first
does not retroactively make the other's extraction wrong, only redundant
for the scope both cover; check what the winner actually shipped before
re-deriving or discarding the loser's independent findings.)

### Phase 1: Classify

Answer two questions before you route. The Phase 0 recon reads come first;
this step selects the pipeline, it does not forbid those reads.

**Intent family.** Match the request against the routing table below. When two
families match, prefer the more specific row (a failing CI check on a PR is
`Session-protocol CI failure`, not `PR ops`).

**Size.** Pick the smallest honest tier:

| Tier | Signal | Pipeline depth |
|------|--------|----------------|
| Trivial | One known file, no new capability, no contract change | Fix, test, commit |
| Standard | Bounded change, existing capability surface | /build then /test then /review then /ship |
| Feature | New capability, new module, or ambiguous requirements | /spec then /plan then the Standard chain |

When unsure between tiers, start one tier down and escalate on contact with
evidence (failing tests, widening diff), not on speculation.

### Phase 2: Route

| Intent | Route |
|--------|-------|
| Build a feature, "add X" | Lifecycle chain per size tier above |
| New capability (Context, module, scanner, validator, pipeline component) | Skill: programming-advisor prior-art discovery BEFORE /spec; add buy-vs-build-framework only for a strategic build, buy, partner, or defer decision, then the Feature chain |
| Bug, error, "why is this broken" | Skill: analyze, then /build for the fix |
| PR, issue, label, milestone ops | Skill: github |
| Respond to PR review threads | Skill: pr-comment-responder |
| Merge conflicts | Agent: merge-resolver |
| Push, ship, "open a PR" | /ship (or /push-pr for push-only) |
| "what do we know about X" | Skill: memory-search |
| Research an unfamiliar topic | Skill: context-gather, then command: /research |
| Ask about Claude Code or Copilot CLI hook contracts | Skill: agent-harness-reference |
| Port, implement, or change cross-harness hooks | Skill: ai-agents-portability-campaign |
| Software design depth, architecture boundaries, domain modeling, refactoring, legacy code, low coverage, old files, external APIs, queues, retries, transactions, event ordering, schema evolution, resilience | Skill: software-engineering-library, then the routed reference |
| Code quality, health check | Skill: quality-grades (repo-wide) or review (pre-merge) |
| "Did I touch security-critical files?" | Skill: security-detection |
| Review a diff or snippet for vulnerabilities | Skill: security-review; injection scan via security-scan |
| Correction received, lesson learned | Skill: reflect |
| Document a decision | Skill: adr-generator |
| New skill wanted | Skill: skillforge |
| Multi-domain, cross-cutting, or requires multiple agents | `agent_type: "project-toolkit:orchestrator"` |

The user naming a skill or command bypasses this table entirely. User
Sovereignty wins over any row.

**Router boundary (ADR-078).** Autoplan is the outer front-door router at the
skill layer. It classifies any request that names no skill and routes it to one
destination: a skill, a lifecycle command, or an agent chain. When a request is
multi-domain or multi-agent execution, autoplan hands off to `orchestrator`
(last row above). Orchestrator is one of the destinations autoplan routes to,
not a peer: it owns multi-agent coordination, handoff management, and synthesis,
and it never routes back to autoplan. Rule: autoplan routes; orchestrator
coordinates specialists.

### Phase 2b: Single-domain miss -> long-tail resolver

When the request names no skill or command, matches no row above, and is not
multi-domain (Precedence step 3), run the resolver before falling back to the
orchestrator. In a repository checkout, resolve
`RESOLVER="$(git rev-parse --show-toplevel)/.claude/skills/autoplan/scripts/resolve_route.py"`.
From an installed skill copy, use the local skill path:
`RESOLVER="$PWD/scripts/resolve_route.py"` when your shell is in the
`autoplan` skill directory. Then run:

```bash
python3 "$RESOLVER" --request "<the user's request text>"
```

Read `kind` from the JSON result and act:

| `kind` | Action |
|--------|--------|
| `explicit` | Invoke `route` directly; the request already named it. |
| `orchestrator` | `agent_type: "project-toolkit:orchestrator"`; a multi-domain marker fired. |
| `specialist` | Invoke `route`, the one eligible skill whose intents matched. |
| `ambiguous` | Ask the user to pick from `candidates` (Sovereignty; do not guess). |
| `none` | No specialist matched. Fall through to the lifecycle chain by size tier, or `agent_type: "project-toolkit:orchestrator"` when nothing else fits. |

A missing PyYAML module or a missing skills root exits 2 with a named
reason on stderr; when that happens, read skill descriptions directly
instead of retrying the resolver. The resolver never returns this router
itself (Precedence step 6): a request naming `/autoplan` drops that
self-reference and resolves the rest of the request instead.

Example specialists this step reaches that carry no table row above:
`business-strategy` (a founder problem, a business model, or a competitive
strategy question), `book-to-skill` (turn a named book into a reusable
skill), `world-model-diagnostic` (why an agent's assumptions or model are
failing), and `dx-review` (audit a CLI, API, or onboarding workflow for
developer friction).

### Phase 2c: Resolver ambiguity from a home-repo run

When you cannot invoke a subprocess (a constrained sandbox, no `python3`),
fall back to reading each candidate skill's `description` frontmatter field
directly and picking the closest match. Report which path you took
(resolver output vs. description fallback) in the Phase 4 final gate.

### Phase 3: Execute with defaults

Apply these without asking. Log each application for the final gate.

1. **Completeness.** Fix every case the bug applies to, not only the reported
   one. Tests cover positive, negative, and edge in the same change.
2. **Run the checks.** Tests, lint, and type checks always run before a commit
   claims completion. Never ask "should I run the tests?".
3. **DRY at the knowledge level.** Reuse the existing helper, skill, or script
   before writing a sibling.
4. **Bias to action.** Internal and reversible: act. Flag what you assumed in
   the final gate instead of pausing mid-run.
5. **Mirrors and gates.** Honor repo obligations without prompting: sync
   generated mirrors, update the per-issue handoff when needed, and keep commits
   atomic. Session log creation is discontinued.

Classify every decision the run surfaces; never promote silently.

| Class | Definition | Handling |
|-------|------------|----------|
| Mechanical | One defensible answer (run tests, fix lint, sync a mirror) | Decide silently |
| Taste | Viable trade-offs, low reversal cost (naming, small refactor shape) | Decide, surface at the final gate |
| Sovereignty | Architecture, new ADRs, breaking changes, security posture, anything external or irreversible | Stop and ask. Never auto-decide |

The Sovereignty row is the AGENTS.md Ask First list plus the Autonomy
Guardrail. When a Sovereignty decision blocks the whole run, present 2 to 3
options with trade-offs per the Confusion Protocol and wait. See
`references/writing-style-and-confusion-protocol.md` for the full protocol,
completeness scoring, and writing-style mechanics. Read
`references/decision-procedure.md` before Phase 1: it is the six-step walk
(scope constraint, search, lake or ocean, build, present and ask, stop at
terminal) that used to live in the always-on builder-ethos rule.

### Phase 4: Final gate

Every /autoplan run ends with one summary block, not a narration stream:

1. **Route taken** and why (one line).
2. **Auto-decided items**, Mechanical count plus each Taste decision with its
   one-line rationale.
3. **Open Sovereignty questions**, if any, with options.
4. **Evidence**: tests run and their counts, gates passed, artifacts produced.

## Scripts

`resolve_route.py` is the deterministic long-tail resolver Phase 2b runs on
a single-domain table miss (DESIGN-037). It reads local `SKILL.md`
frontmatter and prints one JSON line to stdout; it opens no network
connection and runs no subprocess. Resolve its path the same way Phase 2b
does (`$RESOLVER` below), never as a bare relative invocation:

```bash
RESOLVER="$(git rev-parse --show-toplevel)/.claude/skills/autoplan/scripts/resolve_route.py"
python3 "$RESOLVER" --request "audit our CLI for developer friction"
```

Exit codes: `0` on any resolution, including `kind: "none"`. `2` for a
missing skills root, a missing PyYAML module (named on stderr), or a bad
argument. See Phase 2b above for the `kind` values and how to act on each.

## Verification

A routed run is complete when every box checks:

- [ ] The request was classified (intent family and size tier named).
- [ ] The route was one table row, a lifecycle chain, or the orchestrator
      fallback, and it was stated in the final gate.
- [ ] Every Mechanical default that fired is counted in the final gate.
- [ ] Every Taste decision appears in the final gate with a rationale.
- [ ] No Sovereignty decision was auto-decided.
- [ ] Evidence (test counts, gate results) is present in the final gate.

## Anti-Patterns

- **Routing everything to the orchestrator.** The fallback row is for the long
  tail, not a substitute for classification. Two orchestrator fallbacks in a
  row on classifiable requests means the table needs a row, not more fallback.
- **Asking mechanical questions.** "Should I run the tests?" is never a
  question. If one defensible answer exists, act.
- **Silent sovereignty.** Auto-deciding architecture, ADRs, breaking changes,
  or security posture because the run had momentum. Stop and ask.
- **Narration instead of a gate.** Streaming every micro-decision as chat
  defeats the point; batch them into the Phase 4 summary.

## Extension Points

- **New routing row.** When a new skill lands and requests start missing the
  table, add one row (intent, route) here and mirror the change in the
  CLAUDE.md Skill routing section until that section delegates here.
- **Tier signals.** Size-tier signals may grow project-specific entries (for
  example, a change that touches the shared agent templates implies Standard or
  above because of mirror obligations).
- **Escape hatches.** Route fails mid-run: fall back to
  `agent_type: "project-toolkit:orchestrator"` with the failure context rather than
  retrying the same route blind. Two consecutive routing misses on one
  request: stop, ask which route the user wanted, and log the miss with the
  reflect skill.
