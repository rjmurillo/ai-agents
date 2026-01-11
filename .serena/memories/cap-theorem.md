# CAP Theorem

**Category**: Distributed Systems
**Source**: `.agents/analysis/advanced-engineering-knowledge.md`

## Core Principle

In a distributed data store, you can only have two of three guarantees:

- **Consistency**: Every read receives the most recent write
- **Availability**: Every request receives a response
- **Partition Tolerance**: System operates despite network failures

## The Trade-off

Network partitions are inevitable. During partitions, choose between consistency and availability.

## Classifications

| Type | Description | Examples |
|------|-------------|----------|
| CP | Consistent during partitions, may refuse requests | MongoDB, HBase, Redis |
| AP | Available during partitions, may return stale data | Cassandra, CouchDB, DynamoDB |
| CA | Impossible in distributed systems | Single-node only |

## PACELC Extension

During Partition: choose A or C
Else: choose Latency or Consistency

## Application

1. Identify consistency requirements per data type
2. Choose storage appropriate to requirements
3. Design for partition scenarios
4. Consider eventual consistency patterns

## Related

- `resilience-patterns` - Handling failures
- `idempotency-pattern` - Safe retries
