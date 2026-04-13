# Critical Path Method (CPM)

**Created**: 2026-01-10
**Category**: Project Management

## Overview

Algorithm for scheduling project activities by identifying the longest sequence of dependent tasks (critical path).

## Key Concepts

| Term | Definition |
|------|------------|
| **Critical Path** | Longest sequence of dependent tasks |
| **Critical Activities** | Zero float, any delay affects project |
| **Float/Slack** | Time a task can be delayed without impact |
| **Free Float** | Delay without impacting subsequent task |
| **Total Float** | Delay without impacting project completion |

## Calculation

### Forward Pass

Calculate Early Start (ES) and Early Finish (EF):

- ES = EF of predecessor
- EF = ES + duration

### Backward Pass

Calculate Late Start (LS) and Late Finish (LF):

- Start from last activity
- LF for last activity = EF of critical path

### Slack

- Slack = LF - EF
- Or: Slack = LS - ES
- Critical path activities have zero slack

## Application

- Prioritize zero-float (critical path) activities
- Use high-float activities for resource reallocation
- Identify project timeline risks

## Related

- [planning-task-descriptions](planning-task-descriptions.md): Task breakdown
- [foundational-knowledge-index](foundational-knowledge-index.md): Master index
