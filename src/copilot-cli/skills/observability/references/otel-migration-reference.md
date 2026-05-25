---
source: wiki/concepts/Observability/OpenTelemetry Migration.md
created: 2026-04-11
review-by: 2026-07-11
---

# OpenTelemetry Migration Reference

Migrate from legacy telemetry to OpenTelemetry (OTel) before legacy SDK retirement.

## Migration Phases

| Phase | Activities |
|-------|-----------|
| 1. Dual Ingestion | Run legacy and OTel side-by-side, validate metrics consistency, use feature flags |
| 2. Validation | Compare legacy vs OTel metrics, duplicate dashboards, break down by `host.arch` |
| 3. Cutover | Gradual legacy disable + OTel enable using deployment rings, update collector configs |
| 4. Cleanup | Remove legacy code and config, finalize docs, update monitoring standards |

## Instrumentation Best Practices

- Prefer automatic instrumentation (ASP.NET Core, HttpClient, SQL, gRPC)
- Custom instrumentation only for business-critical operations
- Use `ActivitySource` and `Meter` with stable, descriptive names
- Follow OTel Semantic Conventions v1.39

## Metric Instrument Types

| Type | Use Case | Example |
|------|----------|---------|
| Counter | Monotonically increasing | Request count, errors |
| Histogram | Distributions | Latency, payload size |
| UpDownCounter | Up/down values | Active connections, queue depth |
| ObservableGauge | Point-in-time readings | CPU temp, memory usage |

## Cardinality Control

- Avoid unbounded attributes (user IDs, full URLs, request bodies)
- Use Views to drop unwanted attributes or customize histogram buckets
- Set meaningful histogram bucket boundaries aligned to SLOs

## Tracing Practices

- Propagate W3C Trace Context (`traceparent`/`tracestate`) end-to-end
- Head-based sampling in SDK for high-throughput; tail-based in Collector for errors
- Keep span names low-cardinality: use route templates not actual URLs
- Set span status on errors: `Activity.SetStatus(ActivityStatusCode.Error, description)`

## Resource Configuration

Required service attributes: `service.name`, `service.version`, `service.namespace`, `deployment.environment.name`

Kubernetes enrichment: Use `k8sattributesprocessor` + `resourcedetection` for `k8s.cluster.name`, `k8s.namespace.name`, `host.arch`

## Recommended Standard Metrics

**Service Metrics**:

- `http.server.request.duration` (Histogram): RPS, latency, errors by route, status, `host.arch`
- `http.server.active_requests` (UpDownCounter): Active requests by method
- `process.runtime.dotnet.exceptions.count` (Counter): Exception count by type
- `process.runtime.dotnet.gc.collections.count` (Counter): GC by generation
- `process.cpu.time` (Counter): CPU time by mode

**Infrastructure Metrics** (Prometheus):

- CPU utilization: `node_cpu_seconds_total`, `container_cpu_usage_seconds_total`
- Memory: `container_memory_usage_bytes`
- Throttling: `container_cpu_cfs_throttled_periods_total`
- Disk I/O: `node_disk_read_time_seconds_total`, `node_disk_written_bytes_total`
- Network: `node_netstat_Tcp_RetransSegs`, `node_netstat_Tcp_CurrEstab`

## Dimensionality Regression Risk

Legacy telemetry SDKs may surface dimensions that OTel does not automatically provide. Hard-coding dimensions into OTel instrumentation is an anti-pattern.

**Resolution**: Use OTel Collector processors to inject `pod_name`, `service_name`, and infrastructure dimensions automatically. Deploy Collector as sidecar or gateway.

## Reliability Practices

- OTel SDKs are non-blocking; avoid synchronous I/O in custom instrumentation
- Monitor `otel.dotnet.sdk` events for dropped spans and export failures
- Use `ConfigureAwait(false)` in library code
- Test telemetry in CI using in-memory exporter
