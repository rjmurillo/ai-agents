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
        ".githooks/*", "build/scripts/*"
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

```python
CONFLICT_RESOLUTION = {
    # (agent_a, agent_b) -> winner
    ("security", "implementer"): "security",  # Security concerns win
    ("architect", "implementer"): "architect",  # Design wins
    ("security", "devops"): "security",  # Security wins
    ("critic", "milestone-planner"): "critic",  # Validation wins
}

def resolve_conflicts(conflicts):
    resolutions = []
    for conflict in conflicts:
        agent_a, agent_b = conflict["between"]

        if (agent_a, agent_b) in CONFLICT_RESOLUTION:
            winner = CONFLICT_RESOLUTION[(agent_a, agent_b)]
        elif (agent_b, agent_a) in CONFLICT_RESOLUTION:
            winner = CONFLICT_RESOLUTION[(agent_b, agent_a)]
        else:
            # Escalate to architect
            winner = escalate_to_architect(conflict)

        resolutions.append({
            "conflict": conflict,
            "resolution": winner,
            "recommendation": conflict["positions"][winner]
        })

    return resolutions
```

### Conflict Resolution Priority

| Higher Priority | Lower Priority | Reason |
|-----------------|----------------|--------|
| security | * | Security concerns are non-negotiable |
| architect | implementer | Design decisions guide implementation |
| critic | milestone-planner | Validation catches planning errors |
| qa | implementer | Quality gates must be met |

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
- `.githooks/*`
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

## Validation Against CWE-78 Incident

The CWE-78 shell injection incident in `.githooks/pre-commit` should route correctly:

### Classification

```python
task = "Fix shell injection vulnerability in .githooks/pre-commit"

task_type = "security"  # Contains "injection", "vulnerability"
complexity = "multi_domain"  # Infrastructure + security + code
risk = "critical"  # .githooks/* pattern, shell injection
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
