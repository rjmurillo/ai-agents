# Retrospective: The obvious fix for "gh is unavailable" was the wrong fix

## Session Info

- **Date**: 2026-09-03
- **Agents**: Claude Code (Opus 5), remote session
- **Task Type**: Bug
- **Outcome**: Success
- **Failure Mode**: None committed. Near miss of #9 Confident-incorrectness recurrence (per `.agents/governance/FAILURE-MODES.md`), caught by a probe before any code was written.

Scope: commits `2e3c1dd` through `bfaa6d6`, removing the repo's hard dependency on a
working `gh` in agent sandboxes. Issue #5508.

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe.** The request was "remove dependency on gh since it is not available in an
environment like this". The repo has 3316 `gh` references, ~60 Python scripts under
`.claude/skills/github/scripts/`, and a `GitHubClient` protocol with exactly one
implementation, `GhCliClient`. The protocol's own docstring names "httpx" as an
anticipated second transport.

**Respond.** That shape makes one design obvious: write a `RestApiClient` over `urllib`
against `api.github.com`, select it when `gh` is missing, and the existing 60 scripts keep
working. The architecture was practically asking for it. Before writing it I ran four
probes.

**Analyze.** Every premise of that design was false:

| Assumption | Probe | Reality |
|------------|-------|---------|
| `gh` is not installed | `which gh` | `/usr/bin/gh`, v2.98.0, present |
| No credential | `env` | `GH_TOKEN` set |
| Direct REST would work | `gh api repos/...` | HTTP 403, refused by the session proxy |
| GraphQL would work | `gh api graphql` | HTTP 403, pinned set only |
| No GitHub access at all | `mcp__github__get_me` | Succeeded, returned real account data |

A `urllib` REST client would have gone through the same proxy with the same missing
authorization and failed identically. The working transport was the MCP tool surface,
which no Python subprocess can call. The whole premise of "swap the transport under the
scripts" was unavailable.

**Apply.** The deliverable changed from a new client to a classification plus a routing
layer: name the condition honestly, and route the agent (not the scripts) to MCP.

### Execution Trace

| # | Event | Evidence |
|---|-------|----------|
| 1 | Surveyed `gh` usage; found `GitHubClient` protocol with one implementation | `scripts/github_core/protocol.py` |
| 2 | Formed the REST-fallback hypothesis from the protocol's shape | Session context |
| 3 | Probed the environment before writing it | `which gh`, `gh auth status` |
| 4 | Found gh present, token set, REST and GraphQL both 403 | HTTP 403 bodies captured |
| 5 | Probed the MCP surface as a control | `mcp__github__get_me` returned real data |
| 6 | Discarded the REST-fallback design | No code written against it |
| 7 | Ran the repo's own classifier against the live failure | Reported `INVALID_CREDENTIALS`, "run gh auth login" |
| 8 | Added `TRANSPORT_BLOCKED` keyed on captured wording | `2e3c1dd` |
| 9 | Mutation-tested the new tests by deleting the branch | 4 failed, confirming they bind |
| 10 | Added preflight, routing table, and command gates | `1daefce`, `9c8a964` |

### Outcome Classification

**Glad.** Four cheap probes killed a design that would have cost a full implementation
across three mirrored trees and shipped something that fails in exactly the environment it
was built for. The probes cost about two minutes.

**Sad.** The repo's own diagnostics were the thing pointing the wrong way. `check_gh_auth`
reported `INVALID_CREDENTIALS` and `describe_gh_auth_failure` said "GitHub CLI (gh) is not
installed or not authenticated", both clauses false. An agent trusting that message would
conclude the token was broken and go fix a token. The module's docstrings already record
two prior rounds of this exact bug (#3139, #4344), so the pattern recurred a third time
for a third cause.

**Mad.** Nothing. No wrong artifact shipped.

## Phase 1: Insights Generated

### Five Whys

1. **Why was the obvious design wrong?** Because it assumed the constraint was "gh is
   missing" when the constraint was "GitHub is refused for this session".
2. **Why was that assumption available?** The request said "not available", and a missing
   binary is the ordinary meaning of unavailable.
3. **Why did the codebase reinforce it?** `GitHubClient` exists precisely to swap
   transports, and its docstring names httpx. The architecture answered a question nobody
   had checked was the right question.
4. **Why did the wrong answer look confirmable?** Every gh call did fail. The symptom
   matched the wrong diagnosis perfectly, and no gh-side evidence could distinguish them.
5. **Why was a probe needed rather than reading?** Because only the negative control
   separated the two: `gh` failing proves nothing about whether GitHub is reachable. The
   MCP call was the control, and it inverted the conclusion.

### Patterns and Shifts

- A failing tool is evidence about that tool, not about the resource behind it. Distinguishing
  "the client is broken" from "the resource is refused" requires a second, independent client.
- An extension point is not evidence that extending it solves your problem. `GitHubClient`
  made the wrong fix cheap to build, which is a reason to check the premise harder, not less.
- The repo's failure archaeology carried two prior instances of this misdiagnosis shape in
  the same module. Reading the docstrings first framed the third correctly.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

- Probing before building. The four commands that killed the design are in the trace above.
- Using an independent transport as a negative control rather than re-running the failing one.
- Capturing the 403 bodies verbatim off the running proxy instead of guessing the wording,
  so the classifier's signature cannot encode an assumption about text nobody observed.
- Mutation-testing the new tests by deleting the classification branch, confirming 4 of them
  fail without it rather than asserting coverage.

### Failures (Tag: harmful)

- None that shipped. The initial design direction was wrong for roughly four tool calls.

### Near Misses

- Nearly wrote a `RestApiClient` because the protocol invited it. Would have failed in the
  target environment and been discovered only after touching three mirrored trees.
- Nearly reformatted `api.py` and the test file when `ruff format --check` flagged them.
  Checking `origin/main` first showed both already failed that check, so it is not an
  enforced gate and reformatting would have buried an 18-file change in noise.

## Phase 3: Decisions

### Action Classification

| Action | Type | Status |
|--------|------|--------|
| Classify the refusal as its own condition | Code | Done, `2e3c1dd` |
| Return exit 2 and name MCP, not exit 3 or 4 | Code | Done, `2e3c1dd` |
| Keep both retry ladders off it | Code | Done, `2e3c1dd` |
| Expose the verdict as a preflight | Code | Done, `1daefce` |
| Route `/pr-autofix` and `/pr-review` | Prose | Done, `9c8a964` |
| Name the operations with no MCP equivalent | Prose | Done, `9c8a964` |

### Action Sequence

Classification first, because the preflight and both commands read its verdict. Prose last,
because the routing table can only be honest once the tool coverage is known.

### Remediation (open, with owners)

`.claude/rules/retros.md` MUST 4 wants follow-ups with owners or issues, not a
list of commits already made. The table above is the completed work. These are
the actions still open, all surfaced by review on PR #5509 after this retro was
first written.

| Action | Type | Owner / tracking |
|--------|------|------------------|
| Wire `check_skill_md_exec_portability.py` and `validate-slash-commands` into `pre_pr.py` | Governance | Issue #5515. CI-only today, so a bare-path invocation and a rejected tool grant are both undiscoverable locally; between them they cost two review cycles on PR #5509. |
| Decide MCP-mode write policy for `/pr-autofix` | Instruction | Repo owner. MCP mode is triage-only because no lease can be held; either implement the marker-comment lease over MCP operations or narrow the command's documented scope. |
| Correct the `issue #2223` citation in `tests/validation/test_check_git_hook_health.py:60,166` | Docs | Issue #5516. That issue is about splitting oversized modules; it was copied into new code from there before being caught. |
| Split `tests/test_github_auth_classification.py` | Tech debt | Issue #5517. Past the advisory taste-lint file-size threshold; natural seams are classification, remedy, retry, preflight. |

The first row is one governance gap in two places: a gate that runs only in CI
teaches contributors nothing until after they push. Both are cheap.

## Phase 4: Extracted Learnings

### Learning 1

**Statement**: A failing client proves nothing about the reachability of the resource
behind it. Use a second, independent client as the control.

**Context**: Diagnosing any "X is unavailable" report where one tool is the only evidence.

**Evidence**: `gh` REST and GraphQL both returned 403 in this session while
`mcp__github__get_me` returned real account data. Had the second probe not run, the
conclusion would have been "no GitHub access", and the fix built for it would have failed.

### Learning 2

**Statement**: An existing extension point is a reason to check the premise harder, not
evidence that extending it is the fix.

**Context**: Any task where the codebase already has an abstraction shaped like the change.

**Evidence**: `scripts/github_core/protocol.py` defines `GitHubClient` and names httpx as
an anticipated transport. Implementing it would have produced a client that fails in the
one environment the work targets, because the refusal is upstream of the client.

### Learning 3

**Statement**: When a diagnostic message has been wrong twice for two causes, expect a
third and check the message against the live failure before trusting it.

**Context**: Reading any classifier whose docstrings cite prior misdiagnosis incidents.

**Evidence**: `scripts/github_core/api.py` records #3139 (a 5xx read as invalid
credentials) and #4344 (a quota refusal read as missing gh). Running the classifier
against this session's failure produced a third false answer, and the fix is the same
shape as the first two: give the condition its own member and its own remedy.

### Learning 4

**Statement**: An absence claim about a tool surface needs the schema read, not
an inference from a repository search.

**Context**: Writing that an operation is unavailable, in any routing table,
capability matrix, or fallback document.

**Evidence**: Review on PR #5509 found five absence claims made without
checking: an ADR path, an import closure asserted out of scope twice, and two
routing rows saying no reactions or milestone tool exists. All five were false.
`add_issue_comment` takes a `reaction`, `issue_write` takes a `milestone`, and
the ADR paragraph said exactly what the citation claimed. A repository grep
cannot see an MCP surface, because that surface is not defined in the
repository. The instrument has to match the claim: read the tool schema, or
scan the import closure, rather than searching a tree that never held the
answer. A false "unavailable" is worse than silence, because it disables a
path that works.

## Skillbook Updates

### ADD

```json
{
  "skill_id": "diagnose-unavailable-with-an-independent-control",
  "statement": "Before concluding a resource is unreachable, probe it through a second, independent client.",
  "context": "Any 'X is not available' report where one tool's failure is the only evidence.",
  "evidence": "2026-09-03: gh REST and GraphQL both returned HTTP 403 while mcp__github__get_me returned real data, inverting the diagnosis and the fix.",
  "atomicity": 80
}
```

```json
{
  "skill_id": "absence-claims-need-the-matching-instrument",
  "statement": "Verify an absence with the instrument that can see the thing: read the tool schema for a tool, scan the import closure for an import, open the file for a path.",
  "context": "Writing that an operation, module, file, or rule does not exist.",
  "evidence": "2026-09-03 PR #5509: five absence claims, all false. Two routing rows said no reactions or milestone tool exists while add_issue_comment takes a reaction and issue_write takes a milestone; a repo grep cannot see an MCP surface.",
  "atomicity": 85
}
```

```json
{
  "skill_id": "extension-point-is-not-a-premise-check",
  "statement": "An abstraction shaped like the proposed change makes the wrong fix cheap; verify the constraint before filling it in.",
  "context": "Starting work where the codebase already has a protocol, interface, or plugin seam matching the task description.",
  "evidence": "2026-09-03: GitHubClient invited a REST transport that would have hit the same proxy refusal as gh; four probes killed it before any code was written.",
  "atomicity": 75
}
```
