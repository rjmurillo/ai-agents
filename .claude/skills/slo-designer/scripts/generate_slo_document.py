#!/usr/bin/env python3
"""Generate SLO document from configuration.

This script generates a comprehensive SLO document from a YAML configuration file.

Exit Codes:
    0: Success
    1: Invalid arguments
    2: Configuration error
    3: Generation error
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class SLI:
    """Service Level Indicator definition."""

    name: str
    description: str
    measurement: str
    data_source: str
    good_events: Optional[str] = None
    total_events: Optional[str] = None


@dataclass
class SLO:
    """Service Level Objective definition."""

    sli_name: str
    target: float
    measurement_window: str = "30-day rolling"
    rationale: str = ""


@dataclass
class AlertConfig:
    """Alert configuration for SLO."""

    burn_rate: float
    window: str
    severity: str
    action: str


@dataclass
class SLOConfig:
    """Complete SLO configuration."""

    service_name: str
    owner: str
    description: str
    criticality: str
    user_journeys: list[str]
    slis: list[SLI]
    slos: list[SLO]
    alerts: list[AlertConfig] = field(default_factory=list)


def calculate_error_budget_minutes(target: float, period_days: int = 30) -> float:
    """Calculate error budget in minutes."""
    error_budget_percent = 100 - target
    period_minutes = period_days * 24 * 60
    return (error_budget_percent / 100) * period_minutes


def format_downtime(minutes: float) -> str:
    """Format downtime as human-readable string."""
    if minutes < 1:
        return f"{minutes * 60:.0f}s"
    elif minutes < 60:
        return f"{minutes:.0f}m"
    else:
        hours = int(minutes // 60)
        remaining_minutes = int(minutes % 60)
        return f"{hours}h {remaining_minutes}m"


def parse_yaml_config(config_path: Path) -> SLOConfig:
    """Parse YAML configuration file into SLOConfig."""
    if not YAML_AVAILABLE:
        raise ImportError(
            "PyYAML is required for YAML config files. "
            "Install with: pip install pyyaml"
        )

    with open(config_path) as f:
        data = yaml.safe_load(f)

    slis = [
        SLI(
            name=sli["name"],
            description=sli.get("description", ""),
            measurement=sli.get("measurement", ""),
            data_source=sli.get("data_source", ""),
            good_events=sli.get("good_events"),
            total_events=sli.get("total_events"),
        )
        for sli in data.get("slis", [])
    ]

    slos = [
        SLO(
            sli_name=slo["sli"],
            target=slo["target"],
            measurement_window=slo.get("window", "30-day rolling"),
            rationale=slo.get("rationale", ""),
        )
        for slo in data.get("slos", [])
    ]

    alerts = [
        AlertConfig(
            burn_rate=alert["burn_rate"],
            window=alert["window"],
            severity=alert["severity"],
            action=alert["action"],
        )
        for alert in data.get("alerts", [])
    ]

    return SLOConfig(
        service_name=data["service"]["name"],
        owner=data["service"].get("owner", "TBD"),
        description=data["service"].get("description", ""),
        criticality=data["service"].get("criticality", "Medium"),
        user_journeys=data.get("user_journeys", []),
        slis=slis,
        slos=slos,
        alerts=alerts,
    )


def generate_sli_section(slis: list[SLI]) -> str:
    """Generate SLI documentation section."""
    lines = ["## Service Level Indicators", ""]

    for i, sli in enumerate(slis, 1):
        lines.extend(
            [
                f"### SLI {i}: {sli.name}",
                "",
                f"- **Definition**: {sli.description}",
                f"- **Measurement**: `{sli.measurement}`",
                f"- **Data Source**: {sli.data_source}",
            ]
        )

        if sli.good_events:
            lines.append(f"- **Good Events**: `{sli.good_events}`")
        if sli.total_events:
            lines.append(f"- **Total Events**: `{sli.total_events}`")

        lines.append("")

    return "\n".join(lines)


def generate_slo_section(slos: list[SLO]) -> str:
    """Generate SLO documentation section."""
    lines = [
        "## Service Level Objectives",
        "",
        "| SLI | Target | Measurement Window | Rationale |",
        "|-----|--------|-------------------|-----------|",
    ]

    for slo in slos:
        target_str = f"{slo.target}%"
        lines.append(
            f"| {slo.sli_name} | {target_str} | {slo.measurement_window} | {slo.rationale} |"
        )

    lines.append("")
    return "\n".join(lines)


def generate_error_budget_section(slos: list[SLO]) -> str:
    """Generate error budget documentation section."""
    lines = [
        "## Error Budgets",
        "",
        "| SLO | Error Budget | Monthly Allowance | Weekly Allowance |",
        "|-----|--------------|-------------------|------------------|",
    ]

    for slo in slos:
        error_budget = round(100 - slo.target, 6)
        monthly_minutes = calculate_error_budget_minutes(slo.target, 30)
        weekly_minutes = calculate_error_budget_minutes(slo.target, 7)

        lines.append(
            f"| {slo.sli_name} {slo.target}% | {error_budget}% | "
            f"{format_downtime(monthly_minutes)} | {format_downtime(weekly_minutes)} |"
        )

    lines.append("")
    return "\n".join(lines)


def generate_alerting_section(alerts: list[AlertConfig]) -> str:
    """Generate alerting documentation section."""
    if not alerts:
        return generate_default_alerting_section()

    lines = [
        "## Alerting Strategy",
        "",
        "| Burn Rate | Window | Severity | Action |",
        "|-----------|--------|----------|--------|",
    ]

    for alert in alerts:
        lines.append(
            f"| {alert.burn_rate}x | {alert.window} | {alert.severity} | {alert.action} |"
        )

    lines.append("")
    return "\n".join(lines)


def generate_default_alerting_section() -> str:
    """Generate default alerting section with standard burn rates."""
    return """## Alerting Strategy

### Page-worthy Alerts (Critical)

- **Condition**: Burn rate > 14.4x for 1 hour AND > 6x for 6 hours
- **Action**: Immediate response required
- **Escalation**: Page on-call engineer

### Ticket-worthy Alerts (Warning)

- **Condition**: Burn rate > 2x for 24 hours
- **Action**: Investigate within 1 business day
- **Escalation**: Create ticket for engineering team

### Multi-window Alert Logic

```
Alert if:
  burn_rate_1h > 14.4 AND burn_rate_6h > 6
  OR
  burn_rate_6h > 6 AND burn_rate_24h > 2
```

"""


def generate_slo_document(config: SLOConfig) -> str:
    """Generate complete SLO document from configuration."""
    timestamp = datetime.now().strftime("%Y-%m-%d")

    journeys_list = "\n".join(
        f"{i}. {journey}" for i, journey in enumerate(config.user_journeys, 1)
    )

    document = f"""# SLO Document: {config.service_name}

> Generated: {timestamp}

## Service Overview

- **Name**: {config.service_name}
- **Owner**: {config.owner}
- **Description**: {config.description}
- **Business Criticality**: {config.criticality}

## Critical User Journeys

{journeys_list}

{generate_sli_section(config.slis)}
{generate_slo_section(config.slos)}
{generate_error_budget_section(config.slos)}
{generate_alerting_section(config.alerts)}
## Error Budget Policy

### When Error Budget is Exhausted

1. Freeze non-critical feature work
2. Prioritize reliability improvements
3. Conduct incident reviews
4. Address technical debt contributing to failures

### When Error Budget is Healthy (>50%)

1. Invest in new features
2. Accept more risk for velocity
3. Run experiments and tests

### Error Budget Governance

- Review error budget status in weekly SRE sync
- Monthly report to engineering leadership
- Quarterly SLO target review

## Implementation Checklist

- [ ] Metrics collection configured
- [ ] SLO dashboard created in monitoring system
- [ ] Alerts configured per strategy above
- [ ] Runbook documented for each alert
- [ ] Team trained on error budget policy
- [ ] Stakeholders informed of SLO targets

## Appendix: Metric Queries

"""

    for sli in config.slis:
        document += f"""### {sli.name}

```promql
{sli.measurement}
```

"""

    document += """## References

- [Google SRE Book - Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [SLO Engineering Guide](https://sre.google/workbook/slo-engineering/)
"""

    return document


def create_sample_config() -> str:
    """Create a sample configuration file."""
    return """# SLO Configuration Example
# Use this as a template for your service

service:
  name: User API
  owner: Platform Team
  description: Core user management API for authentication and profile operations
  criticality: High

user_journeys:
  - User can log in within 2 seconds
  - User can view their profile without errors
  - User can update their settings and see changes immediately

slis:
  - name: Availability
    description: Percentage of successful HTTP requests (non-5xx)
    measurement: |
      sum(rate(http_requests_total{service="user-api",status!~"5.."}[5m]))
      /
      sum(rate(http_requests_total{service="user-api"}[5m]))
    data_source: Prometheus
    good_events: http_requests_total{status!~"5.."}
    total_events: http_requests_total

  - name: Latency (p99)
    description: 99th percentile response time
    measurement: |
      histogram_quantile(0.99,
        sum(rate(http_request_duration_seconds_bucket{service="user-api"}[5m]))
        by (le)
      )
    data_source: Prometheus

slos:
  - sli: Availability
    target: 99.9
    window: 30-day rolling
    rationale: Industry standard for user-facing APIs; balances reliability with velocity

  - sli: Latency (p99)
    target: 99.0
    window: 30-day rolling
    rationale: User research shows frustration above 500ms; 99% of requests under threshold

alerts:
  - burn_rate: 14.4
    window: 1h
    severity: Critical
    action: Page on-call immediately

  - burn_rate: 6
    window: 6h
    severity: Warning
    action: Investigate within 2 hours

  - burn_rate: 2
    window: 24h
    severity: Info
    action: Create ticket for next sprint
"""


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate SLO document from configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --config slo-config.yaml --output docs/slo-user-api.md
  %(prog)s --sample-config > slo-config.yaml

Note: Requires PyYAML for YAML config files (pip install pyyaml)
        """,
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for generated document (default: stdout)",
    )

    parser.add_argument(
        "--sample-config",
        action="store_true",
        help="Print sample configuration file and exit",
    )

    args = parser.parse_args()

    if args.sample_config:
        print(create_sample_config())
        return 0

    if not args.config:
        parser.error("--config is required (or use --sample-config)")

    if not args.config.exists():
        print(f"Error: Configuration file not found: {args.config}", file=sys.stderr)
        return 1

    try:
        config = parse_yaml_config(args.config)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    try:
        document = generate_slo_document(config)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(document)
            print(f"Generated: {args.output}")
        else:
            print(document)

        return 0

    except Exception as e:
        print(f"Generation error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
