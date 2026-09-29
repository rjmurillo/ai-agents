"""Invocation DAG for one routing benchmark run (issue #5424).

The runner owns the topology, so the invocation order, session ids, phase ids,
and fresh-context boundaries are defined here and not left to a harness.
Every shape is a list of `InvocationRequest`, each naming what it depends on.

    fan_out          plan -> workers (one per work package) -> integrate [-> review]
    single_agent     one agent invocation, no children
    plan_then_fresh  plan -> implement in a fresh session that reads the artifact

A correction round adds one request that depends on the last request. It
reuses the session of the role that does the work, so it is not a fresh
context.
"""

from __future__ import annotations

from _routing_config import Strategy, Topology
from _routing_result import InvocationRequest
from _routing_scenario import Scenario


def _request(
    invocation_id: str,
    phase_id: str,
    role: str,
    route: tuple[str, str],
    session_id: str,
    depends_on: tuple[str, ...] = (),
    *,
    fresh_context: bool = False,
    work_package: str | None = None,
    difficulty: str | None = None,
    correction_round: int = 0,
) -> InvocationRequest:
    return InvocationRequest(
        invocation_id=invocation_id,
        phase_id=phase_id,
        role=role,
        work_package_id=work_package,
        difficulty=difficulty,
        model=route[0],
        effort=route[1],
        depends_on=depends_on,
        fresh_context=fresh_context,
        session_id=session_id,
        correction_round=correction_round,
    )


def _fan_out(strategy: Strategy, scenario: Scenario) -> list[InvocationRequest]:
    orchestrator = (strategy.orchestrator.model, strategy.orchestrator.effort)
    worker_route = strategy.workers[scenario.difficulty]
    worker = (worker_route.model, worker_route.effort)
    requests = [_request("orchestrator-plan", "plan", "orchestrator", orchestrator, "orchestrator")]
    worker_ids: list[str] = []
    for index in range(1, strategy.work_packages + 1):
        invocation_id = f"worker-wp-{index}"
        worker_ids.append(invocation_id)
        requests.append(
            _request(
                invocation_id,
                "implement",
                "worker",
                worker,
                f"worker-{index}",
                ("orchestrator-plan",),
                fresh_context=True,
                work_package=f"wp-{index}",
                difficulty=scenario.difficulty.value,
            )
        )
    requests.append(
        _request(
            "orchestrator-integrate",
            "integrate",
            "orchestrator",
            orchestrator,
            "orchestrator",
            tuple(worker_ids),
        )
    )
    if strategy.reviewer is not None:
        reviewer = (strategy.reviewer.route.model, strategy.reviewer.route.effort)
        requests.append(
            _request(
                "reviewer-review",
                "review",
                "reviewer",
                reviewer,
                "reviewer",
                ("orchestrator-integrate",),
                fresh_context=strategy.reviewer.isolated,
            )
        )
    return requests


def _plan_then_fresh(strategy: Strategy) -> list[InvocationRequest]:
    implementer = strategy.implementer
    if implementer is None:
        raise ValueError("plan_then_fresh strategy has no implementer")
    planner = (strategy.orchestrator.model, strategy.orchestrator.effort)
    return [
        _request("planner-plan", "plan", "orchestrator", planner, "planner"),
        _request(
            "implementer-implement",
            "implement",
            "implementer",
            (implementer.model, implementer.effort),
            "implementer",
            ("planner-plan",),
            fresh_context=True,
        ),
    ]


def build_requests(strategy: Strategy, scenario: Scenario) -> list[InvocationRequest]:
    """The initial-round invocation DAG for `strategy` on `scenario`."""
    if strategy.topology is Topology.FAN_OUT:
        return _fan_out(strategy, scenario)
    if strategy.topology is Topology.PLAN_THEN_FRESH:
        return _plan_then_fresh(strategy)
    route = (strategy.orchestrator.model, strategy.orchestrator.effort)
    return [_request("agent-implement", "implement", "orchestrator", route, "agent")]


def correction_request(
    strategy: Strategy, scenario: Scenario, round_index: int, previous_id: str
) -> InvocationRequest:
    """One correction invocation, sent to whichever role does the implementation."""
    phase = f"correct-{round_index}"
    if strategy.topology is Topology.FAN_OUT:
        route = strategy.workers[scenario.difficulty]
        role, session, package = "worker", "worker-1", "wp-1"
        difficulty: str | None = scenario.difficulty.value
        model_route = (route.model, route.effort)
    elif strategy.topology is Topology.PLAN_THEN_FRESH and strategy.implementer is not None:
        role, session, package, difficulty = "implementer", "implementer", None, None
        model_route = (strategy.implementer.model, strategy.implementer.effort)
    else:
        role, session, package, difficulty = "orchestrator", "agent", None, None
        model_route = (strategy.orchestrator.model, strategy.orchestrator.effort)
    return _request(
        f"{role}-{phase}",
        phase,
        role,
        model_route,
        session,
        (previous_id,),
        work_package=package,
        difficulty=difficulty,
        correction_round=round_index,
    )
