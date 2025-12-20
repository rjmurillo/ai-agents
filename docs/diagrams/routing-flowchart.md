# Orchestrator Routing Flowchart

## Overview

This document provides a visual representation of the orchestrator routing algorithm.

---

## Main Routing Flow

```mermaid
flowchart TB
    subgraph Phase1["PHASE 1: CLASSIFY"]
        RECEIVE[RECEIVE TASK]
        CLASSIFY[PHASE 1: CLASSIFY]
        RECEIVE --> CLASSIFY
        CLASSIFY --> IDENTIFY & ASSESS & DETERMINE
        IDENTIFY[Identify<br/>Task Type]
        ASSESS[Assess<br/>Complexity]
        DETERMINE[Determine<br/>Risk Level]
    end

    subgraph Phase2["PHASE 2: SELECT"]
        SELECT[PHASE 2: SELECT]
        IDENTIFY & ASSESS & DETERMINE --> SELECT
        SELECT --> PRIMARY & SEQUENCE & MANDATORY
        PRIMARY[Select<br/>Primary]
        SEQUENCE[Build Agent<br/>Sequence]
        MANDATORY[Add Mandatory<br/>Agents]
    end

    subgraph Phase3["PHASE 3: EXECUTE"]
        EXECUTE[PHASE 3: EXECUTE]
        SEQUENCE --> EXECUTE
        EXECUTE --> SERIAL_PARALLEL[Determine Serial vs<br/>Parallel Execution]
        SERIAL_PARALLEL --> SERIAL & PARALLEL
        SERIAL[SERIAL GROUP<br/>Execute one by<br/>one, passing<br/>outputs forward]
        PARALLEL[PARALLEL GROUP<br/>Execute agents<br/>concurrently]
    end

    subgraph Phase4["PHASE 4: SYNTHESIZE"]
        SYNTHESIZE[PHASE 4: SYNTHESIZE]
        SERIAL & PARALLEL --> SYNTHESIZE
        SYNTHESIZE --> COLLECT & DETECT & RESOLVE
        COLLECT[Collect<br/>Outputs]
        DETECT[Detect<br/>Conflicts]
        RESOLVE[Resolve<br/>Conflicts]
        DETECT --> DELIVER
        DELIVER[DELIVER RESULT]
    end
```

---

## Task Type Classification Flow

```mermaid
flowchart TB
    ANALYZE[ANALYZE TASK]
    ANALYZE --> SECURITY_CHECK{Contains security<br/>keywords or file patterns?}

    SECURITY_CHECK -->|YES| SECURITY[SECURITY]
    SECURITY_CHECK -->|NO| INFRA_CHECK{Contains infrastructure<br/>file patterns?}

    INFRA_CHECK -->|YES| INFRASTRUCTURE[INFRASTRUCTURE]
    INFRA_CHECK -->|NO| QUESTION_CHECK{Question format?<br/>Why/How does X...?}

    QUESTION_CHECK -->|YES| RESEARCH[RESEARCH]
    QUESTION_CHECK -->|NO| BUG_CHECK{Contains bug indicators?}

    BUG_CHECK -->|YES| BUG_FIX[BUG_FIX]
    BUG_CHECK -->|NO| FEATURE_CHECK{Contains feature<br/>indicators?}

    FEATURE_CHECK -->|YES| FEATURE[FEATURE]
    FEATURE_CHECK -->|NO| UNKNOWN[UNKNOWN]
```

---

## Complexity Assessment Flow

```mermaid
flowchart TB
    COUNT[COUNT DOMAINS]
    COUNT --> DOMAINS_CHECK{Domains affected > 2?}

    DOMAINS_CHECK -->|YES| MULTI_DOMAIN[MULTI_DOMAIN]
    DOMAINS_CHECK -->|NO| FILES_CHECK{Files affected > 3?}

    FILES_CHECK -->|YES| MULTI_STEP1[MULTI_STEP]
    FILES_CHECK -->|NO| AGENTS_CHECK{Agents required > 1?}

    AGENTS_CHECK -->|YES| MULTI_STEP2[MULTI_STEP]
    AGENTS_CHECK -->|NO| SIMPLE[SIMPLE]
```

---

## Risk Level Flow

```mermaid
flowchart TB
    CHECK[CHECK PATTERNS]
    CHECK --> CRITICAL_CHECK{Matches critical patterns?<br/>**/Auth/**, .githooks/*, etc}

    CRITICAL_CHECK -->|YES| CRITICAL[CRITICAL]
    CRITICAL_CHECK -->|NO| TYPE_CHECK{Task type security or infra?}

    TYPE_CHECK -->|YES| HIGH1[HIGH]
    TYPE_CHECK -->|NO| HIGH_RISK_CHECK{Matches high-risk patterns?}

    HIGH_RISK_CHECK -->|YES| HIGH2[HIGH]
    HIGH_RISK_CHECK -->|NO| MEDIUM_LOW[MEDIUM/LOW]
```

---

## Agent Selection Flow

```mermaid
flowchart TB
    INPUT[TASK TYPE +<br/>COMPLEXITY +<br/>RISK LEVEL]
    INPUT --> LOOKUP[LOOKUP IN SEQUENCE MAP]

    LOOKUP --> EXACT[EXACT MATCH<br/>Use sequence]
    LOOKUP --> NO_MATCH[NO MATCH<br/>Use fallback]

    EXACT --> RISK_CHECK
    NO_MATCH --> RISK_CHECK

    RISK_CHECK{Risk = Critical or High?}
    RISK_CHECK -->|YES| INSERT_SECURITY[Insert SECURITY agent<br/>if not present]
    RISK_CHECK -->|NO| IMPL_CHECK
    INSERT_SECURITY --> IMPL_CHECK

    IMPL_CHECK{IMPLEMENTER in sequence?}
    IMPL_CHECK -->|YES| ENSURE_QA[Ensure QA follows<br/>implementer]
    IMPL_CHECK -->|NO| FINAL
    ENSURE_QA --> FINAL

    FINAL[FINAL SEQUENCE]
```

---

## Execution Strategy Flow

```mermaid
flowchart TB
    AGENT_SEQ[AGENT SEQUENCE]
    AGENT_SEQ --> FOR_EACH[For each pair of agents]
    FOR_EACH --> COMPATIBLE{Are they parallel-<br/>compatible?}

    COMPATIBLE -->|YES| PARALLEL_GROUP[Add to<br/>PARALLEL<br/>group]
    COMPATIBLE -->|NO| SERIAL_QUEUE[Add to<br/>SERIAL<br/>queue]

    PARALLEL_GROUP --> EXECUTE_GROUPS
    SERIAL_QUEUE --> EXECUTE_GROUPS

    EXECUTE_GROUPS[Execute groups in order]
    EXECUTE_GROUPS --> PARALLEL_EXEC & SERIAL_EXEC

    PARALLEL_EXEC[PARALLEL<br/>Run all<br/>concurrently]
    SERIAL_EXEC[SERIAL<br/>Run one<br/>at a time]

    PARALLEL_EXEC --> MERGE
    SERIAL_EXEC --> MERGE
    MERGE[Merge results and proceed]
```

---

## Conflict Resolution Flow

```mermaid
flowchart TB
    CONFLICT[CONFLICT<br/>DETECTED]
    CONFLICT --> SECURITY_Q{Is one agent SECURITY?}

    SECURITY_Q -->|YES| SECURITY_WINS[SECURITY<br/>WINS]
    SECURITY_Q -->|NO| ARCHITECT_Q{Is one agent ARCHITECT?}

    ARCHITECT_Q -->|YES| ARCHITECT_WINS[ARCHITECT<br/>WINS]
    ARCHITECT_Q -->|NO| CRITIC_Q{Is one agent CRITIC?}

    CRITIC_Q -->|YES| CRITIC_WINS[CRITIC<br/>WINS]
    CRITIC_Q -->|NO| ESCALATE[ESCALATE<br/>to ARCH]
```

---

## Example: CWE-78 Routing

```mermaid
flowchart TB
    subgraph Task["TASK"]
        TASK_DESC["Fix shell injection vulnerability in .githooks/pre-commit"]
    end

    subgraph Phase1["PHASE 1: CLASSIFY"]
        TYPE[Type:<br/>SECURITY<br/>injection,<br/>vulnerability]
        COMPLEXITY[Complexity:<br/>MULTI_DOMAIN<br/>security +<br/>infra + code]
        RISK[Risk:<br/>CRITICAL<br/>.githooks/*<br/>pattern]
    end

    subgraph Phase2["PHASE 2: SELECT"]
        BASE["Base Sequence: analyst, security, devops, critic, impl, qa"]
        ADDITIONS["Mandatory Additions: Security already present"]
        FINAL["Final Sequence: analyst, security, devops, critic, impl, qa"]
    end

    subgraph Phase3["PHASE 3: EXECUTE"]
        ANALYST[analyst<br/>Research<br/>CWE-78] --> SECURITY_AGENT[security<br/>Assess<br/>severity]
        SECURITY_AGENT --> DEVOPS[devops<br/>Validate<br/>hook context]
        DEVOPS --> CRITIC[critic<br/>Verify<br/>approach]
        CRITIC --> IMPLEMENTER[implementer<br/>Apply fix]
        IMPLEMENTER --> QA[qa<br/>Test fix<br/>completeness]
    end

    subgraph Phase4["PHASE 4: SYNTHESIZE"]
        COLLECT_P4["Collect: Security report, code changes, test results"]
        CONFLICTS["Conflicts: None expected (clear remediation path)"]
        RESULT["Result: Vulnerability fixed with quoted expansion"]
    end

    Task --> Phase1
    Phase1 --> Phase2
    Phase2 --> Phase3
    Phase3 --> Phase4
```

---

## Related Documents

- [Orchestrator Routing Algorithm](./orchestrator-routing-algorithm.md)
- [Task Classification Guide](./task-classification-guide.md)
- [Agent Interview Protocol](../.agents/governance/agent-interview-protocol.md)

---

*Diagram Version: 1.1*
*Created: 2025-12-13*
*Updated: 2025-12-18 - Converted ASCII diagrams to Mermaid*
*GitHub Issue: #5*
