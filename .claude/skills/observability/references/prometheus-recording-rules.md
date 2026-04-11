---
source: wiki/concepts/Observability/Prometheus Recording Rules.md
created: 2026-04-11
review-by: 2026-07-11
---

# Prometheus Recording Rules

Precomputed PromQL expressions that emit new time series. Move expensive aggregations from query time to write time. Dashboards stay fast, calculations stay consistent.

## Core Pattern

Recording rule = PromQL query that runs periodically and stores the result as a new metric.

**Purpose**: Reduce dashboard load, standardize calculations, enable cross-architecture comparisons.

## Infrastructure Dimensions

Add at scrape time via relabeling to enable architecture-aware dashboards:

- `machine_sku`: Instance type (from node label)
- `dk8s_arch`: CPU architecture (from node label)

Group by these dimensions in recording rules for comparative analysis (x64 vs ARM64).

## Key Recording Rules

### CPU Throttling Ratio

```prometheus
- record: container:cpu_throttle_ratio
  expr: |
    sum(increase(container_cpu_cfs_throttled_periods_total{container!=""}[5m]))
      by (container, pod, namespace, dk8s_arch, machine_sku)
    /
    sum(increase(container_cpu_cfs_periods_total{}[5m]))
      by (container, pod, namespace, dk8s_arch, machine_sku)
```

Alert thresholds: WARN >0.15 (10m), CRIT >0.30 (10m), gated by sustained CPU >80%.

### Disk I/O Latency

```prometheus
- record: node:disk_read_latency_seconds
  expr: |
    rate(node_disk_read_time_seconds_total[5m])
    / rate(node_disk_reads_completed_total[5m])

- record: node:disk_write_latency_seconds
  expr: |
    rate(node_disk_write_time_seconds_total[5m])
    / rate(node_disk_writes_completed_total[5m])
```

### Normalized Load Average

```prometheus
- record: node:load_average_scaled
  expr: |
    sum(node_load5) by (instance)
    / count by (instance) (sum by (instance, cpu) (node_cpu_seconds_total))
```

Sustained >2.0 may need investigation.

### Pressure Stall (PSI) Rates

```prometheus
- record: node:cpu_stall_rate
  expr: avg(rate(node_pressure_cpu_waiting_seconds_total[5m])) by (dk8s_arch, machine_sku) * 300

- record: node:memory_stall_rate
  expr: avg(rate(node_pressure_memory_waiting_seconds_total[5m])) by (dk8s_arch, machine_sku) * 300

- record: node:io_stall_rate
  expr: avg(rate(node_pressure_io_waiting_seconds_total[5m])) by (dk8s_arch, machine_sku) * 300
```

The `*300` converts 5m rate to stalled seconds.

### TCP Retransmission Ratio

```prometheus
- record: node:tcp_retransmissions_scaled
  expr: |
    rate(node_netstat_Tcp_RetransSegs[5m])
    / rate(node_netstat_Tcp_OutSegs[5m])
```

Sustained >0.02 warrants inspection.

## Range Vector Window: Why 5m?

- Prometheus default scrape interval = 1 minute
- Range window >= 4x scrape interval (avoids counter reset artifacts, scrape jitter)
- 5m = 5 samples at 1m scrape, sufficient for stable rates
- Rule: `window = max(5m, 4 * scrape_interval)`
- For coarser scrape: consider 7-10m for disk latency and retransmissions

## Troubleshooting

| Symptom | Investigation |
|---------|---------------|
| High throttling + low CPU | Increase CPU requests |
| High disk latency + normal throughput | Investigate storage class or device |
| Elevated PSI memory + normal usage | Examine reclaim or GC behavior |
| Retransmissions spike (no CPU/disk issue) | Inspect network path or kernel params |

## Onboarding Checklist

1. Enable metadata enrichment (non-prod first)
2. Validate labels in cardinality report
3. Deploy recording rules
4. Add architecture and SKU filters to dashboards
