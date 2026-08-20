# Orchestrator Routing Algorithm

## Purpose

This document provides the explicit algorithm for routing tasks to appropriate agents. It enables both human decision-making and potential automation of agent selection.

## Algorithm Overview

The routing algorithm proceeds through four phases:

1. **Classify** - Determine task type, complexity, and risk
2. **Select** - Choose primary agent and sequence
3. **Execute** - Run agents with defined strategy
4. **Synthesize** - Combine outputs and resolve conflicts

---

## Phase 1: Classification

### Step 1.1: Identify Task Type

```python
def classify_task_type(task):
    keywords = extract_keywords(task)
    file_patterns = extract_file_patterns(task)

    # Priority order (first match wins)
    if matches_security_indicators(keywords, file_patterns):
        return "security"
    elif matches_infrastructure_indicators(file_patterns):
        return "infrastructure"
    elif matches_research_indicators(keywords):
        return "research"
    elif matches_bug_indicators(keywords):
        return "bug_fix"
    elif matches_feature_indicators(keywords):
        return "feature"
    elif matches_documentation_indicators(keywords, file_patterns):
        return "documentation"
    elif matches_refactoring_indicators(keywords):
        return "refactoring"
    elif matches_strategic_indicators(keywords):
        return "strategic"
    else:
        return "unknown"  # Requires analyst investigation
```

### Step 1.2: Assess Complexity

```python
def assess_complexity(task, task_type):
    domain_count = count_domains_affected(task)
    file_count = estimate_files_affected(task)
    agent_requirements = determine_required_agents(task_type)

    if domain_count > 2 or len(agent_requirements) > 3:
        return "multi_domain"
    elif file_count > 3 or len(agent_requirements) > 1:
        return "multi_step"
    else:
        return "simple"
```

### Step 1.3: Determine Risk Level

```python
def determine_risk(task_type, file_patterns):
    # Critical risk patterns
    critical_patterns = [
        "**/Auth/**", "**/Security/**", "*.env*",
        "lefthook.yml", "scripts/validation/git_hook_policy.py",
        "build/scripts/*"
    ]

    # High risk patterns
    high_patterns = [
        ".github/workflows/*", "Dockerfile",
        "**/Controllers/*", "appsettings*.json"
    ]

    if any(matches(p, file_patterns) for p in critical_patterns):
        return "critical"
    elif task_type in ["security", "infrastructure"]:
        return "high"
    elif any(matches(p, file_patterns) for p in high_patterns):
        return "high"
    elif task_type in ["feature", "bug_fix", "refactoring"]:
        return "medium"
    else:
        return "low"
```

---

## Phase 2: Agent Selection

### Step 2.1: Select Primary Agent

```python
PRIMARY_AGENT_MAP = {
    "security": "security",
    "infrastructure": "devops",
    "research": "analyst",
    "bug_fix": "analyst",
    "feature": "analyst",
    "documentation": "explainer",
    "refactoring": "analyst",
    "strategic": "roadmap",
    "unknown": "analyst"
}

def select_primary_agent(task_type):
    return PRIMARY_AGENT_MAP.get(task_type, "analyst")
```

### Step 2.2: Build Agent Sequence

```python
AGENT_SEQUENCES = {
    # (task_type, complexity, risk) -> agent_sequence
    ("security", "multi_domain", "critical"): [
        "analyst", "security", "architect", "critic",
        "implementer", "qa"
    ],
    ("security", "multi_step", "high"): [
        "security", "implementer", "qa"
    ],
    ("infrastructure", "multi_domain", "critical"): [
        "analyst", "devops", "security", "critic", "qa"
    ],
    ("infrastructure", "multi_step", "high"): [
        "devops", "security", "qa"
    ],
    ("feature", "multi_domain", "*"): [
        "analyst", "architect", "milestone-planner", "critic",
        "implementer", "qa"
    ],
    ("feature", "multi_step", "*"): [
        "analyst", "milestone-planner", "implementer", "qa"
    ],
    ("bug_fix", "multi_step", "*"): [
        "analyst", "implementer", "qa"
    ],
    ("bug_fix", "simple", "*"): [
        "implementer", "qa"
    ],
    ("research", "*", "*"): [
        "analyst"
    ],
    ("documentation", "*", "*"): [
        "explainer", "critic"
    ],
    ("strategic", "*", "*"): [
        "roadmap", "architect", "milestone-planner", "critic"
    ]
}

def build_agent_sequence(task_type, complexity, risk):
    # Try exact match first
    key = (task_type, complexity, risk)
    if key in AGENT_SEQUENCES:
        return AGENT_SEQUENCES[key]

    # Try with wildcard risk
    key = (task_type, complexity, "*")
    if key in AGENT_SEQUENCES:
        sequence = AGENT_SEQUENCES[key].copy()
        # Insert security for high/critical risk
        if risk in ["high", "critical"] and "security" not in sequence:
            sequence.insert(1, "security")
        return sequence

    # Try with wildcard complexity
    key = (task_type, "*", "*")
    if key in AGENT_SEQUENCES:
        return AGENT_SEQUENCES[key]

    # Default fallback
    return ["analyst"]
```

### Step 2.3: Add Mandatory Agents

```python
def add_mandatory_agents(sequence, task_type, risk, file_patterns):
    result = sequence.copy()

    # Security is mandatory for critical risk
    if risk == "critical" and "security" not in result:
        # Insert after analyst if present, else at start
        insert_pos = result.index("analyst") + 1 if "analyst" in result else 0
        result.insert(insert_pos, "security")

    # QA is mandatory for any implementation
    if "implementer" in result and "qa" not in result:
        result.append("qa")

    # Critic recommended for multi-domain
    if len(result) > 3 and "critic" not in result:
        # Insert before implementer if present
        if "implementer" in result:
            result.insert(result.index("implementer"), "critic")

    return result
```

---

## Phase 2.5: Detect Conflicts and Escalate

After the selected agents return, check their results for disagreement. There
is no agent ranking to validate a sequence against: ADR-009 routes a hard
conflict to `high-level-advisor`, so escalation is a single hop rather than a
climb up a hierarchy.

Quoted verbatim from
`.agents/architecture/ADR-009-parallel-safe-multi-agent-design.md`:

| Strategy | Use Case | Behavior |
|----------|----------|----------|
| **merge** | Non-conflicting outputs | Combine all outputs |
| **vote** | Redundant execution | Select majority |
| **escalate** | Conflicts detected | Route to high-level-advisor |

```python
# Soft-conflict weights. ADR-009:90 grants exactly one ordering, quoted
# verbatim: "Soft conflicts -> weighted vote (architect > implementer)".
# That is the whole of the canonical source; ADR-009 defines no weight table
# and names no other agent. This dict is the minimal encoding of that one
# ordering, and an agent absent from it carries weight 1.
#
# An earlier revision also carried "security": 2 under this same "per ADR-009"
# comment. ADR-009 does not grant it (`grep -c -i security` on the ADR returns
# 0), so it was an invented authority grant wearing a canonical citation: a
# security/qa disagreement would have resolved 2-1 for security instead of
# escalating. Removed rather than renamed, per
# `.claude/rules/canonical-source-mirror.md` ("a wrong citation is worse than
# no citation; it weaponizes the next reader's trust"). Weighting any further
# agent is an ADR-009 amendment, not a docs edit. Refs #5130 adr-review
# (architect, critic).
CONFLICT_VOTE_WEIGHTS = {
    "architect": 2,
    "implementer": 1,
}


def resolve_disagreement(results):
    """
    Apply ADR-009's aggregation strategies to a set of agent results.

    ADR-009 defines three outcomes, and disagreement alone does not mean
    escalate. A soft conflict is settled by weighted vote; only a hard
    conflict, one the vote cannot settle, routes onward. Escalating every
    disagreement would skip the vote strategy entirely and contradict the
    protocol quoted above.

    Returns one of:
      {"strategy": "merge",    ...}  no disagreement
      {"strategy": "vote",     ...}  soft conflict, decided by weight
      {"strategy": "escalate", ...}  hard conflict, routed to high-level-advisor

    **The hard-conflict trigger below is this document's, not ADR-009's.**
    ADR-009:88-91 grants the three strategies and the one vote ordering, and
    stops there; it never says what makes a conflict hard. Some rule has to
    decide, or "escalate" has no entry condition and the vote strategy is
    unreachable. This document supplies one and labels it, rather than
    attributing an invented contract to the ADR. If the semantics below are
    ever relied on as governance rather than as this router's behavior, they
    belong in ADR-009 by amendment. Refs #5177 review (Copilot).

    A conflict is hard when the top weight is tied, so the vote has no winner,
    or when any dissenting agent marked its position non-negotiable. The
    orchestrator routes a hard conflict; it does not arbitrate it.
    """
    recommendations = {
        agent: result.get("recommendation")
        for agent, result in results.items()
        if result.get("recommendation") is not None
    }

    if len(recommendations) < 2 or len(set(recommendations.values())) == 1:
        return {"strategy": "merge", "recommendation": next(iter(recommendations.values()), None)}

    tallies = {}
    for agent, recommendation in recommendations.items():
        weight = CONFLICT_VOTE_WEIGHTS.get(agent, 1)
        tallies[recommendation] = tallies.get(recommendation, 0) + weight

    ranked = sorted(tallies.items(), key=lambda item: item[1], reverse=True)
    tied = len(ranked) > 1 and ranked[0][1] == ranked[1][1]

    # Only a *dissenting* non-negotiable makes the conflict hard, which is what
    # the docstring says and what an earlier revision of this code did not do.
    # Checking every voter escalated when the winner itself marked its position
    # non-negotiable: architect=A/non-negotiable against implementer=B is an
    # untied 2-1 for A, and the vote settled it. Holding firm on the position
    # that won is agreement with the vote, not a block on it. Refs #5177 review
    # (Copilot).
    winner = None if tied else ranked[0][0]
    blocking = any(
        results[agent].get("non_negotiable")
        for agent, recommendation in recommendations.items()
        if recommendation != winner
    )

    if tied or blocking:
        return {
            "strategy": "escalate",
            "escalate_to": "high-level-advisor",
            "reason": "Tied weighted vote" if tied else "Dissenting non-negotiable position",
            "agents": sorted(recommendations),
            "conflict": sorted(tallies),
        }

    return {
        "strategy": "vote",
        "recommendation": ranked[0][0],
        "tallies": tallies,
        "agents": sorted(recommendations),
    }
```

---

## Phase 3: Execution Strategy

### Step 3.1: Determine Execution Mode

```python
def determine_execution_mode(sequence, dependencies):
    """
    Agents can run in parallel if they don't have data dependencies.
    """
    parallel_compatible = {
        ("analyst", "security"),  # Both can analyze independently
        ("architect", "security"),  # Design + security can parallel
    }

    # Check if any adjacent pairs can parallelize
    parallel_groups = []
    i = 0
    while i < len(sequence):
        if i + 1 < len(sequence):
            pair = (sequence[i], sequence[i+1])
            if pair in parallel_compatible or tuple(reversed(pair)) in parallel_compatible:
                parallel_groups.append([sequence[i], sequence[i+1]])
                i += 2
                continue
        parallel_groups.append([sequence[i]])
        i += 1

    return parallel_groups
```

### Step 3.2: Execute Agent Sequence

```python
def execute_sequence(task, sequence, parallel_groups):
    results = {}

    for group in parallel_groups:
        if len(group) == 1:
            # Serial execution
            agent = group[0]
            results[agent] = execute_agent(agent, task, results)
        else:
            # Parallel execution
            group_results = execute_agents_parallel(group, task, results)
            results.update(group_results)

        # Check for blocking issues after each group
        if has_blocking_issues(results):
            handle_blocking_issues(results)

    return results
```

### Execution Rules

| Pattern | Execution | Reason |
|---------|-----------|--------|
| analyst -> implementer | Serial | Implementation needs analysis |
| architect -> implementer | Serial | Implementation needs design |
| architect + security | Parallel | Independent concerns |
| critic -> implementer | Serial | Implementation needs validation |
| implementer -> qa | Serial | QA needs code to test |
| security + devops | Parallel | Can review independently |

---

## Phase 4: Result Synthesis

### Step 4.1: Collect Outputs

```python
def collect_outputs(results):
    outputs = {
        "findings": [],
        "recommendations": [],
        "code_changes": [],
        "test_cases": [],
        "documentation": [],
        "conflicts": []
    }

    for agent, result in results.items():
        categorize_output(agent, result, outputs)

    return outputs
```

### Step 4.2: Resolve Conflicts

One conflict algorithm, not two. An earlier revision of this document kept a
pairwise `CONFLICT_RESOLUTION` table here alongside Phase 2.5's weighted vote,
and a "Conflict Resolution Priority" table below it. Both disagreed with the
weighted vote: `security` against `implementer` ties 1-1 under ADR-009's weights
and escalates, while the pairwise table awarded it to `security` outright. The
same inputs produced different outcomes depending on which phase read them.
Copilot found the contradiction on PR #5177, and the `adr-review` debate found
the same shape in `CONFLICT_VOTE_WEIGHTS`.

The table is deleted rather than reconciled, for the same reason a `security: 2`
weight was deleted from `CONFLICT_VOTE_WEIGHTS` one section above: ADR-009 grants
exactly one weighting, `architect > implementer`. Every other precedence pair in
that table (`security > implementer`, `security > devops`,
`critic > milestone-planner`) was local invention with no ADR behind it, which is
the same unenforced-hierarchy problem issue #5130 exists to remove. Adding a
precedence rule is an ADR-009 amendment, not a docs edit.

```python
def resolve_conflicts(conflicts):
    """Route every conflict through the single ADR-009 aggregation above.

    `resolve_disagreement` returns one of three strategies: `merge` when the
    agents agree, `vote` when a weighted tally has an outright winner, and
    `escalate` when the vote ties or a dissenting agent marked its position
    non-negotiable. Escalation names `high-level-advisor` as the arbiter, not
    `architect`, because architect is a participant in these disputes and cannot
    arbitrate one it is party to.

    `conflict["positions"]` maps an agent to the position it took, which is the
    shape `resolve_disagreement` consumes once wrapped as results.
    """
    resolutions = []
    for conflict in conflicts:
        positions = conflict["positions"]
        outcome = resolve_disagreement(
            {agent: {"recommendation": position} for agent, position in positions.items()}
        )

        if outcome["strategy"] == "escalate":
            # Escalation is not a pairwise winner. high-level-advisor is not a
            # party to the dispute, so it has no entry in `positions`, and the
            # arbiter decides rather than carrying a participant's position
            # forward.
            resolutions.append({
                "conflict": conflict,
                "resolution": "escalate",
                "arbiter": outcome["escalate_to"],
                "reason": outcome["reason"],
                "recommendation": None,
            })
            continue

        resolutions.append({
            "conflict": conflict,
            "resolution": outcome["strategy"],
            "recommendation": outcome["recommendation"],
        })

    return resolutions
```

### Conflict Resolution Priority

ADR-009 grants exactly one ordering, quoted verbatim from
`.agents/architecture/ADR-009-parallel-safe-multi-agent-design.md:90`:

> Soft conflicts -> weighted vote (architect > implementer)

That is the whole of it. Every other conflict goes to a weighted vote in which
the agents ADR-009 does not name carry equal weight, and a vote the weights
cannot settle escalates to `high-level-advisor`.

A table here previously granted standing precedence to four more pairs
(`security` over everything, `critic` over `milestone-planner`, `qa` over
`implementer`). No ADR grants those. It is recorded rather than silently
dropped because the rankings are not unreasonable on their face, which is
exactly what made them durable: a reader could not tell which line was
canonical and which was invented. If any of them should bind, the route is an
ADR-009 amendment, not a table in a routing document. Refs #5130 adr-review.

---

## Indicator Patterns

### Security Indicators

**Keywords**: vulnerability, CVE, authentication, authorization, credential, secret, token, injection, XSS, CSRF, encryption, password, session

**File Patterns**:

- `**/Auth/**`
- `**/Security/**`
- `**/*[Aa]uth*`
- `**/*[Ss]ecret*`
- `**/*[Cc]redential*`
- `*.env*`

### Infrastructure Indicators

**Keywords**: CI, CD, pipeline, deploy, docker, kubernetes, build, workflow, hook

**File Patterns**:

- `.github/workflows/*`
- `lefthook.yml` (Git hook manager configuration)
- `scripts/validation/git_hook_policy.py`
- `build/**`
- `Dockerfile*`
- `docker-compose*.yml`
- `*.yml` (in .github)

### Research Indicators

**Keywords**: why, how, investigate, analyze, understand, explore, research

**Patterns**:

- Question format ("Why does X...?")
- No clear action requested
- Exploratory language

### Feature Indicators

**Keywords**: add, create, implement, new, feature, enable, support

**Patterns**:

- "Add X to Y"
- "Implement X"
- "Enable X functionality"

### Bug Indicators

**Keywords**: fix, broken, error, bug, issue, not working, crash, fail

**Patterns**:

- Error messages in request
- "X stopped working"
- Stack traces mentioned

---

## Validation Against Historical CWE-78 Incident

The deleted custom payload path is preserved below because it identifies where
the historical incident occurred. Current Git hook authority lives in
`lefthook.yml`.

### Classification

```python
task = "Historical: fix shell injection vulnerability in .githooks/pre-commit"

task_type = "security"  # Contains "injection", "vulnerability"
complexity = "multi_domain"  # Infrastructure + security + code
risk = "critical"  # Shell injection vulnerability
```

### Agent Sequence

```python
sequence = [
    "analyst",      # Investigate vulnerability scope
    "security",     # Assess security implications
    "devops",       # Infrastructure expertise for hooks
    "critic",       # Validate fix approach
    "implementer",  # Apply the fix
    "qa"            # Verify fix effectiveness
]
```

### Expected Behavior

1. **analyst**: Research CWE-78 patterns, identify all vulnerable lines
2. **security**: Confirm vulnerability severity, recommend bash array approach
3. **devops**: Validate hook execution context, review fix compatibility
4. **critic**: Verify fix is complete, no other injection vectors
5. **implementer**: Apply quoted expansion fix
6. **qa**: Test with malicious filenames to confirm fix

**Result**: Vulnerability would be caught and fixed proactively.

---

## Quick Reference

### When to Use Orchestrator

| Complexity | Risk | Use Orchestrator? |
|------------|------|-------------------|
| Simple | Low | No - Direct agent |
| Simple | High+ | Yes - Need validation |
| Multi-Step | Any | Yes - Coordination needed |
| Multi-Domain | Any | Yes - REQUIRED |

### Emergency Overrides

| Scenario | Action |
|----------|--------|
| Production incident | Skip milestone-planner, direct to implementer with security |
| Security breach | Security agent first, regardless of task type |
| Revert needed | DevOps direct, no validation chain |

---

## Related Documents

- [Task Classification Guide](./task-classification-guide.md)
- [Routing Flowchart](./diagrams/routing-flowchart.md)
- [Agent Interview Protocol](../.agents/governance/agent-interview-protocol.md)

---

*Algorithm Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #5*
