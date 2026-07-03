"""Data model and aggregation for the eval-run rollup (issue #2787).

The per-run write path (`_run_persistence.RunPersistence`) appends one record per
`(fixture_id, variant, run_index)` to
`evals/<agent>-spike/runs/<RUN_ID>/runs.jsonl`, carrying `latency_ms`,
`tokens_in`, and `tokens_out`. This module rolls those rows up *across* runs:
per-agent totals plus a drift flag for any run beyond N standard deviations of
its agent's mean cost or latency. Rendering and the CLI live in
`eval_run_rollup`; this module is pure model and computation.

Design note (why no schema change): issue #2787 AC1 reads "every agent run
appends a tally record (agent, cost, latency_ms, tokens)". The agent name is
recoverable from the run-directory path and per-run cost is a pure function of
`(model_id, tokens_in, tokens_out)` via the shared pricing table, so the per-run
tally already exists on disk. Adding `agent`/`cost` columns to `RunRecord` would
bump `schemaVersion` across the whole write path and its tests for data we can
derive. The rollup is the missing consumer, not a new column.

The module degrades gracefully (release-it.md): a malformed line, an unparseable
file, or an unpriced model is counted and skipped, never fatal.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from _eval_common import (
    MODEL_PRICING_RATES_USD_PER_1K_TOKENS,
    PRICING_RATE_AS_OF,
)

DEFAULT_GLOB = "*/runs/*/runs.jsonl"
DEFAULT_SIGMA = 3.0
_SPIKE_SUFFIX = "-spike"


def cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float | None:
    """USD cost for one run, or None when the model has no published rate.

    Mirrors `_report_aggregator._cost_estimate` but returns None instead of
    raising on an unpriced model: a rollup over historical logs must tolerate a
    model whose price was never recorded rather than abort the whole report.
    """
    rates = MODEL_PRICING_RATES_USD_PER_1K_TOKENS.get(model_id)
    if rates is None:
        return None
    return float(
        tokens_in * rates["input"] + tokens_out * rates["output"]
    ) / 1000.0


@dataclass(frozen=True)
class RunTally:
    """One run's derived tally row. The unit the rollup aggregates over."""

    agent: str
    variant: str
    fixture_id: str
    run_id: str
    model_id: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    outcome: str
    cost: float | None

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass
class AgentRollup:
    """Per-agent aggregate over its run tallies."""

    agent: str
    runs: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    cost_priced_runs: int = 0
    errors: int = 0
    _latencies: list[float] = field(default_factory=list)
    _costs: list[float] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def mean_latency_ms(self) -> float:
        return statistics.fmean(self._latencies) if self._latencies else 0.0

    @property
    def stdev_latency_ms(self) -> float:
        return statistics.stdev(self._latencies) if len(self._latencies) >= 2 else 0.0

    @property
    def mean_cost(self) -> float:
        return statistics.fmean(self._costs) if self._costs else 0.0

    @property
    def stdev_cost(self) -> float:
        return statistics.stdev(self._costs) if len(self._costs) >= 2 else 0.0


@dataclass
class DriftFlag:
    """One run that exceeded mean + sigma*stdev on a metric."""

    agent: str
    fixture_id: str
    variant: str
    run_id: str
    metric: str  # "latency_ms" or "cost"
    value: float
    threshold: float


@dataclass
class RollupResult:
    """The full rollup: per-agent aggregates, drift flags, and skip counts."""

    agents: list[AgentRollup]
    drift: list[DriftFlag]
    sigma: float
    files_scanned: int
    runs_counted: int
    lines_skipped: int
    files_skipped: int
    unpriced_runs: int
    pricing_rate_as_of: str = PRICING_RATE_AS_OF

    @property
    def total_cost(self) -> float:
        return sum(a.cost for a in self.agents)

    @property
    def total_tokens(self) -> int:
        return sum(a.tokens for a in self.agents)


def agent_from_path(jsonl_path: Path, root: Path) -> str:
    """Derive the agent name from a `runs.jsonl` path.

    Layout: `<root>/<agent>-spike/runs/<RUN_ID>/runs.jsonl`. The `-spike`
    suffix is stripped so the agent reads as `devops`, not `devops-spike`. A
    path that does not match the layout falls back to the first component under
    root, or the parent directory name, so an off-convention log still rolls up
    under a stable, non-empty key instead of silently merging into one bucket.
    """
    try:
        rel = jsonl_path.resolve().relative_to(root.resolve())
        head = rel.parts[0]
    except (ValueError, IndexError):
        head = jsonl_path.parent.name
    if head.endswith(_SPIKE_SUFFIX):
        head = head[: -len(_SPIKE_SUFFIX)]
    return head or jsonl_path.parent.name


def run_id_from_path(jsonl_path: Path) -> str:
    """The `<RUN_ID>` directory that holds the `runs.jsonl`."""
    return jsonl_path.parent.name


@dataclass(frozen=True)
class _CoercedRecord:
    """The typed subset of a JSONL row the rollup meters on."""

    model_id: str
    variant: str
    fixture_id: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    outcome: str


def _coerce_record(payload: dict[str, Any]) -> _CoercedRecord | None:
    """Return the typed subset of fields the rollup needs, or None when incomplete.

    A record missing any required metering field is treated as un-meterable and
    skipped. This is the graceful-degradation boundary: do not raise.
    """
    required = (
        "model_id",
        "variant",
        "fixture_id",
        "latency_ms",
        "tokens_in",
        "tokens_out",
    )
    if any(payload.get(name) is None for name in required):
        return None
    if (
        isinstance(payload["latency_ms"], bool)
        or isinstance(payload["tokens_in"], bool)
        or isinstance(payload["tokens_out"], bool)
    ):
        return None
    try:
        latency_ms = float(payload["latency_ms"])
        tokens_in = int(payload["tokens_in"])
        tokens_out = int(payload["tokens_out"])
    except (TypeError, ValueError):
        return None
    if (
        not math.isfinite(latency_ms)
        or latency_ms < 0
        or tokens_in < 0
        or tokens_out < 0
    ):
        return None
    return _CoercedRecord(
        model_id=str(payload["model_id"]),
        variant=str(payload["variant"]),
        fixture_id=str(payload["fixture_id"]),
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        outcome=str(payload.get("outcome", "unknown")),
    )


def iter_tallies(jsonl_path: Path, root: Path) -> tuple[list[RunTally], int]:
    """Parse one `runs.jsonl` into tallies. Returns (tallies, lines_skipped).

    Raises `OSError` only if the file cannot be read; the caller decides
    whether a read failure skips the file. Malformed lines are skipped and
    counted, never raised.
    """
    agent = agent_from_path(jsonl_path, root)
    run_id = run_id_from_path(jsonl_path)
    tallies: list[RunTally] = []
    skipped = 0
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(payload, dict):
                skipped += 1
                continue
            record = _coerce_record(payload)
            if record is None:
                skipped += 1
                continue
            tallies.append(
                RunTally(
                    agent=agent,
                    variant=record.variant,
                    fixture_id=record.fixture_id,
                    run_id=run_id,
                    model_id=record.model_id,
                    latency_ms=record.latency_ms,
                    tokens_in=record.tokens_in,
                    tokens_out=record.tokens_out,
                    outcome=record.outcome,
                    cost=cost_usd(
                        record.model_id, record.tokens_in, record.tokens_out
                    ),
                )
            )
    return tallies, skipped


def _build_agent_rollups(tallies: Iterable[RunTally]) -> dict[str, AgentRollup]:
    rollups: dict[str, AgentRollup] = {}
    for tally in tallies:
        rollup = rollups.setdefault(tally.agent, AgentRollup(agent=tally.agent))
        rollup.runs += 1
        rollup.tokens_in += tally.tokens_in
        rollup.tokens_out += tally.tokens_out
        rollup._latencies.append(tally.latency_ms)
        if tally.outcome != "success":
            rollup.errors += 1
        if tally.cost is not None:
            rollup.cost += tally.cost
            rollup.cost_priced_runs += 1
            rollup._costs.append(tally.cost)
    return rollups


def _drift_flags(
    tallies: list[RunTally], rollups: dict[str, AgentRollup], sigma: float
) -> list[DriftFlag]:
    """Flag every run whose latency or cost exceeds its agent's mean + sigma*stdev.

    A group with fewer than two samples has an undefined spread, so it cannot
    drift: no flags. A zero standard deviation (identical samples) means any
    strictly larger value is impossible, so a tie never flags.
    """
    flags: list[DriftFlag] = []
    for tally in tallies:
        rollup = rollups[tally.agent]
        lat_std = rollup.stdev_latency_ms
        if lat_std > 0.0:
            threshold = rollup.mean_latency_ms + sigma * lat_std
            if tally.latency_ms > threshold:
                flags.append(
                    DriftFlag(
                        agent=tally.agent,
                        fixture_id=tally.fixture_id,
                        variant=tally.variant,
                        run_id=tally.run_id,
                        metric="latency_ms",
                        value=tally.latency_ms,
                        threshold=threshold,
                    )
                )
        cost_std = rollup.stdev_cost
        if tally.cost is not None and cost_std > 0.0:
            threshold = rollup.mean_cost + sigma * cost_std
            if tally.cost > threshold:
                flags.append(
                    DriftFlag(
                        agent=tally.agent,
                        fixture_id=tally.fixture_id,
                        variant=tally.variant,
                        run_id=tally.run_id,
                        metric="cost",
                        value=tally.cost,
                        threshold=threshold,
                    )
                )
    return flags


def rollup(
    root: Path,
    *,
    glob: str = DEFAULT_GLOB,
    sigma: float = DEFAULT_SIGMA,
    agent_filter: str | None = None,
) -> RollupResult:
    """Walk `root` for run logs and build the cross-run rollup.

    `sigma` must be non-negative. `agent_filter`, when set, keeps only runs
    whose derived agent name matches exactly.
    """
    if sigma < 0:
        raise ValueError(f"sigma must be non-negative, got {sigma}")

    files = sorted(root.glob(glob))
    all_tallies: list[RunTally] = []
    files_scanned = 0
    lines_skipped = 0
    files_skipped = 0
    for jsonl_path in files:
        files_scanned += 1
        try:
            tallies, skipped = iter_tallies(jsonl_path, root)
        except OSError:
            files_skipped += 1
            continue
        lines_skipped += skipped
        if agent_filter is not None:
            tallies = [t for t in tallies if t.agent == agent_filter]
        all_tallies.extend(tallies)

    rollups = _build_agent_rollups(all_tallies)
    drift = _drift_flags(all_tallies, rollups, sigma)
    unpriced = sum(1 for t in all_tallies if t.cost is None)
    agents = sorted(rollups.values(), key=lambda r: r.agent)
    return RollupResult(
        agents=agents,
        drift=sorted(drift, key=lambda d: (d.agent, d.metric, -d.value)),
        sigma=sigma,
        files_scanned=files_scanned,
        runs_counted=len(all_tallies),
        lines_skipped=lines_skipped,
        files_skipped=files_skipped,
        unpriced_runs=unpriced,
    )
