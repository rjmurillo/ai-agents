# Orchestrator Routing Flowchart

## Overview

This document provides a visual representation of the orchestrator routing algorithm.

---

## Main Routing Flow

```text
                              +-------------------+
                              |   RECEIVE TASK    |
                              +-------------------+
                                       |
                                       v
                          +------------------------+
                          |  PHASE 1: CLASSIFY     |
                          +------------------------+
                                       |
           +---------------------------+---------------------------+
           |                           |                           |
           v                           v                           v
   +--------------+           +--------------+            +--------------+
   | Identify     |           | Assess       |            | Determine    |
   | Task Type    |           | Complexity   |            | Risk Level   |
   +--------------+           +--------------+            +--------------+
           |                           |                           |
           +---------------------------+---------------------------+
                                       |
                                       v
                          +------------------------+
                          |  PHASE 2: SELECT       |
                          +------------------------+
                                       |
           +---------------------------+---------------------------+
           |                           |                           |
           v                           v                           v
   +--------------+           +--------------+            +--------------+
   | Select       |           | Build Agent  |            | Add Mandatory|
   | Primary      |           | Sequence     |            | Agents       |
   +--------------+           +--------------+            +--------------+
                                       |
                                       v
                          +------------------------+
                          |  PHASE 3: EXECUTE      |
                          +------------------------+
                                       |
                                       v
                          +------------------------+
                          | Determine Serial vs    |
                          | Parallel Execution     |
                          +------------------------+
                                       |
              +------------------------+------------------------+
              |                                                 |
              v                                                 v
    +------------------+                              +------------------+
    | SERIAL GROUP     |                              | PARALLEL GROUP   |
    | Execute one by   |                              | Execute agents   |
    | one, passing     |                              | concurrently     |
    | outputs forward  |                              +------------------+
    +------------------+                                        |
              |                                                 |
              +------------------------+------------------------+
                                       |
                                       v
                          +------------------------+
                          |  PHASE 4: SYNTHESIZE   |
                          +------------------------+
                                       |
           +---------------------------+---------------------------+
           |                           |                           |
           v                           v                           v
   +--------------+           +--------------+            +--------------+
   | Collect      |           | Detect       |            | Resolve      |
   | Outputs      |           | Conflicts    |            | Conflicts    |
   +--------------+           +--------------+            +--------------+
                                       |
                                       v
                              +----------------+
                              | DELIVER RESULT |
                              +----------------+
```

---

## Task Type Classification Flow

```text
                         +------------------+
                         |  ANALYZE TASK    |
                         +------------------+
                                  |
                                  v
                    +---------------------------+
                    | Contains security         |
                    | keywords or file patterns?|
                    +---------------------------+
                           |           |
                          YES          NO
                           |           |
                           v           v
                    +----------+  +---------------------------+
                    | SECURITY |  | Contains infrastructure   |
                    +----------+  | file patterns?            |
                                  +---------------------------+
                                       |           |
                                      YES          NO
                                       |           |
                                       v           v
                            +----------------+  +---------------------------+
                            | INFRASTRUCTURE |  | Question format?          |
                            +----------------+  | ("Why/How does X...?")    |
                                                +---------------------------+
                                                     |           |
                                                    YES          NO
                                                     |           |
                                                     v           v
                                            +----------+  +---------------------------+
                                            | RESEARCH |  | Contains bug indicators?  |
                                            +----------+  +---------------------------+
                                                               |           |
                                                              YES          NO
                                                               |           |
                                                               v           v
                                                        +----------+  +---------------------------+
                                                        | BUG_FIX  |  | Contains feature          |
                                                        +----------+  | indicators?               |
                                                                      +---------------------------+
                                                                           |           |
                                                                          YES          NO
                                                                           |           |
                                                                           v           v
                                                                    +----------+  +----------+
                                                                    | FEATURE  |  | UNKNOWN  |
                                                                    +----------+  +----------+
```

---

## Complexity Assessment Flow

```text
                      +-------------------+
                      |   COUNT DOMAINS   |
                      +-------------------+
                               |
                               v
              +--------------------------------+
              | Domains affected > 2?          |
              +--------------------------------+
                     |                |
                    YES               NO
                     |                |
                     v                v
            +--------------+  +--------------------------------+
            | MULTI_DOMAIN |  | Files affected > 3?            |
            +--------------+  +--------------------------------+
                                     |                |
                                    YES               NO
                                     |                |
                                     v                v
                            +--------------+  +--------------------------------+
                            | MULTI_STEP   |  | Agents required > 1?           |
                            +--------------+  +--------------------------------+
                                                     |                |
                                                    YES               NO
                                                     |                |
                                                     v                v
                                            +--------------+  +--------------+
                                            | MULTI_STEP   |  | SIMPLE       |
                                            +--------------+  +--------------+
```

---

## Risk Level Flow

```text
                      +-------------------+
                      |  CHECK PATTERNS   |
                      +-------------------+
                               |
                               v
              +--------------------------------+
              | Matches critical patterns?     |
              | (**/Auth/**, .githooks/*, etc)|
              +--------------------------------+
                     |                |
                    YES               NO
                     |                |
                     v                v
            +--------------+  +--------------------------------+
            | CRITICAL     |  | Task type security or infra?   |
            +--------------+  +--------------------------------+
                                     |                |
                                    YES               NO
                                     |                |
                                     v                v
                            +--------------+  +--------------------------------+
                            | HIGH         |  | Matches high-risk patterns?    |
                            +--------------+  +--------------------------------+
                                                     |                |
                                                    YES               NO
                                                     |                |
                                                     v                v
                                            +--------------+  +--------------+
                                            | HIGH         |  | MEDIUM/LOW   |
                                            +--------------+  +--------------+
```

---

## Agent Selection Flow

```text
                      +-------------------+
                      |   TASK TYPE +     |
                      |   COMPLEXITY +    |
                      |   RISK LEVEL      |
                      +-------------------+
                               |
                               v
              +--------------------------------+
              |   LOOKUP IN SEQUENCE MAP       |
              +--------------------------------+
                               |
              +----------------+----------------+
              |                                 |
              v                                 v
      +---------------+                 +---------------+
      | EXACT MATCH   |                 | NO MATCH      |
      | Use sequence  |                 | Use fallback  |
      +---------------+                 +---------------+
              |                                 |
              +----------------+----------------+
                               |
                               v
              +--------------------------------+
              | Risk = Critical or High?       |
              +--------------------------------+
                     |                |
                    YES               NO
                     |                |
                     v                |
      +----------------------------+  |
      | Insert SECURITY agent      |  |
      | if not present             |  |
      +----------------------------+  |
              |                       |
              +----------+------------+
                         |
                         v
              +--------------------------------+
              | IMPLEMENTER in sequence?       |
              +--------------------------------+
                     |                |
                    YES               NO
                     |                |
                     v                |
      +----------------------------+  |
      | Ensure QA follows          |  |
      | implementer                |  |
      +----------------------------+  |
              |                       |
              +----------+------------+
                         |
                         v
              +-------------------+
              |  FINAL SEQUENCE   |
              +-------------------+
```

---

## Execution Strategy Flow

```text
              +-------------------+
              |   AGENT SEQUENCE  |
              +-------------------+
                       |
                       v
         +---------------------------+
         | For each pair of agents   |
         +---------------------------+
                       |
                       v
         +---------------------------+
         | Are they parallel-        |
         | compatible?               |
         +---------------------------+
                |           |
               YES          NO
                |           |
                v           v
         +------------+ +------------+
         | Add to     | | Add to     |
         | PARALLEL   | | SERIAL     |
         | group      | | queue      |
         +------------+ +------------+
                |           |
                +-----+-----+
                      |
                      v
         +---------------------------+
         | Execute groups in order   |
         +---------------------------+
                      |
         +------------+------------+
         |                         |
         v                         v
  +-------------+           +-------------+
  | PARALLEL    |           | SERIAL      |
  | Run all     |           | Run one     |
  | concurrently|           | at a time   |
  +-------------+           +-------------+
         |                         |
         +------------+------------+
                      |
                      v
         +---------------------------+
         | Merge results and proceed |
         +---------------------------+
```

---

## Conflict Resolution Flow

```text
              +-------------------+
              |   CONFLICT        |
              |   DETECTED        |
              +-------------------+
                       |
                       v
         +---------------------------+
         | Is one agent SECURITY?    |
         +---------------------------+
                |           |
               YES          NO
                |           |
                v           v
         +------------+ +---------------------------+
         | SECURITY   | | Is one agent ARCHITECT?   |
         | WINS       | +---------------------------+
         +------------+          |           |
                                YES          NO
                                 |           |
                                 v           v
                         +------------+ +---------------------------+
                         | ARCHITECT  | | Is one agent CRITIC?      |
                         | WINS       | +---------------------------+
                         +------------+          |           |
                                                YES          NO
                                                 |           |
                                                 v           v
                                         +------------+ +------------+
                                         | CRITIC     | | ESCALATE   |
                                         | WINS       | | to ARCH    |
                                         +------------+ +------------+
```

---

## Example: CWE-78 Routing

```text
TASK: "Fix shell injection vulnerability in .githooks/pre-commit"

PHASE 1: CLASSIFY
+----------------+     +----------------+     +----------------+
| Type:          |     | Complexity:    |     | Risk:          |
| SECURITY       |     | MULTI_DOMAIN   |     | CRITICAL       |
| (injection,    |     | (security +    |     | (.githooks/*   |
|  vulnerability)|     |  infra + code) |     |  pattern)      |
+----------------+     +----------------+     +----------------+

PHASE 2: SELECT
+---------------------------------------------------------------+
| Base Sequence: [analyst, security, devops, critic, impl, qa]  |
| Mandatory Additions: Security already present                  |
| Final Sequence: [analyst, security, devops, critic, impl, qa] |
+---------------------------------------------------------------+

PHASE 3: EXECUTE
+-------------+     +-------------+     +-------------+
| analyst     | --> | security    | --> | devops      | -->
| Research    |     | Assess      |     | Validate    |
| CWE-78      |     | severity    |     | hook context|
+-------------+     +-------------+     +-------------+
                                               |
                                               v
+-------------+     +-------------+     +-------------+
| qa          | <-- | implementer | <-- | critic      |
| Test fix    |     | Apply fix   |     | Verify      |
| completeness|     |             |     | approach    |
+-------------+     +-------------+     +-------------+

PHASE 4: SYNTHESIZE
+---------------------------------------------------------------+
| Collect: Security report, code changes, test results          |
| Conflicts: None expected (clear remediation path)              |
| Result: Vulnerability fixed with quoted expansion              |
+---------------------------------------------------------------+
```

---

## Related Documents

- [Orchestrator Routing Algorithm](./orchestrator-routing-algorithm.md)
- [Task Classification Guide](./task-classification-guide.md)
- [Agent Interview Protocol](../.agents/governance/agent-interview-protocol.md)

---

*Diagram Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #5*
