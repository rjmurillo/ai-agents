"""Pre-registered constants and interpretation notes for the routing verdict scorer.

Values come from `evals/routing-benchmark/PREDICTIONS.md` (`predictions-v1`, Amendments
1 and 2); the comment on each threshold names the line it reads.
"""

from __future__ import annotations

from fractions import Fraction

PREDICTIONS_VERSION = "predictions-v1"
CLASS_ORDINARY = "ordinary_bounded"
CLASS_FALLBACK = "fallback_reasoning"
POOLED = "pooled_all_six"
SUPPORTED = "SUPPORTED"
SUPPORTED_FOR_FALLBACK = "SUPPORTED_FOR:fallback_reasoning"
FALSIFIED = "FALSIFIED"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
SUPERSEDED_DIR = "results-2026-10-03"
CODEX = "codex"
DECISION_RULE = "predictions-v1 amendment 2"
DECISION_KEEP = "KEEP_CURRENT_POLICY"
DECISION_SOL_FANOUT = "ADOPT_SOL_FANOUT"
DECISION_ORIGINAL_ROUTING = "ADOPT_ORIGINAL_SOL_LUNA_TERRA_ROUTING"
DECISION_SOL_WITH_LUNA = "ADOPT_SOL_PARENT_WITH_LUNA_WORKERS"
DECISION_HETEROGENEOUS = "ADOPT_HETEROGENEOUS_ROUTING"
DECISION_CONDITIONAL = "ADOPT_CONDITIONALLY"
EDGE_TERRA = "Terra high for fallback_reasoning"
EDGE_SOL_SINGLE = "single-agent Sol for fallback_reasoning"

NOT_RUN = "NOT_RUN"
ACCEPTED = "ACCEPTED"
HARNESS_FAILED = "HARNESS_FAILED"
CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
KNOWN_STATUSES = frozenset({ACCEPTED, "TASK_FAILED", HARNESS_FAILED, CONTRACT_VIOLATION, NOT_RUN})

QUALITY_MARGIN = Fraction(1, 6)  # PREDICTIONS.md line 47
DEFECT_MARGIN = Fraction(1, 2)  # line 48
ECONOMICS_FACTOR = Fraction(3, 4)  # line 50: at least 25 percent lower
HARNESS_FAILURE_LIMIT = Fraction(1, 5)  # line 66
EVIDENCE_FLOOR = 8  # line 58
FALLBACK_MIN_REPS = 2  # line 63
REPETITIONS = (1, 2, 3)  # line 29
COMPARED_ARMS = ("A", "B", "C", "D", "E")  # H1 to H4
FALLBACK_COMPARED_ARMS = ("A", "C", "D", "E")  # H2 and H4
DECISION_ORDINARY_SCORED_FLOOR = 12  # Amendment 2 item 1

INTERPRETATIONS: tuple[dict[str, object], ...] = (
    {
        "id": "I1",
        "predictions_lines": "45-46",
        "reading": (
            "Residual defects per run = scope violations + missing expected files from the "
            "stored validation, plus 1 when validation is FAIL with neither itemized (a failed "
            "follow-up check exists but rows do not list it). A run with no validation counts 0. "
            "Counts are lower bounds."
        ),
    },
    {
        "id": "I2",
        "predictions_lines": "47-49",
        "reading": (
            "Non-inferior is one-sided: comparator rate minus candidate rate <= 1/6 and "
            "candidate mean residual defects minus comparator's <= 0.5. Rates are pooled over the "
            "class (not paired per scenario) and use only non-harness-failed runs."
        ),
    },
    {
        "id": "I3",
        "predictions_lines": "50-52",
        "reading": (
            "Per accepted task = total over the arm's non-harness-failed runs in the class "
            "divided by the accepted count. Wall-clock of a run = latest invocation window end "
            "minus earliest start, so parallel fan-out is not double counted. Uncached tokens = "
            "sum over invocations of input_tokens + output_tokens. Row input_tokens is already "
            "Codex input minus cached_input_tokens (_durable_codex.py:45-46,197, the cached part "
            "is cache_read_tokens). The routing live path writes rows through that parser: "
            "_routing_live.py:325 parse_codex_run, :329 facts.input_tokens into the observation, "
            "_routing_result.py:193 into the row. "
            "'At least 25 percent lower' = candidate <= 0.75 x comparator on both measures. "
            "Zero accepted: economics undefined, never 'materially better'. A run with unknown "
            "time or tokens makes the arm's economics unmeasured and any verdict needing it "
            f"{INSUFFICIENT}."
        ),
    },
    {
        "id": "I4",
        "predictions_lines": "58-59",
        "reading": (
            "'Runs per arm' for the evidence floor of 8 counts non-harness-failed, non-NOT_RUN "
            "runs, because harness failures are excluded from rates (line 65)."
        ),
    },
    {
        "id": "I5",
        "predictions_lines": "60-64",
        "reading": (
            "Fallback evidence rule. Per scenario and repetition, direction = accepted(x) minus "
            "accepted(comparator) for the same repetition; a repetition with a missing or "
            "harness-failed side has no direction. 'Advantage' needs direction > 0 on at least "
            "2 of 3 repetitions in each fallback scenario and a class acceptance gap >= 1/6. "
            "'No advantage' (FALSIFIED legs) needs direction <= 0 on at least 2 of 3 repetitions "
            "in each fallback scenario and a class gap < 1/6. The H4 FALSIFIED economics leg is "
            "evaluated on the class aggregate, not per repetition."
        ),
    },
    {
        "id": "I6",
        "predictions_lines": "65-67",
        "reading": (
            "Harness-failure share of a cell = HARNESS_FAILED / (all rows except NOT_RUN). "
            "'More than 20 percent' is strictly greater than 1/5. CONTRACT_VIOLATION rows are "
            "counted as non-accepted task outcomes, not excluded."
        ),
    },
    {
        "id": "I7",
        "predictions_lines": "90-93",
        "reading": (
            "H2 SUPPORTED_FOR also needs the ordinary cells for D, A, and C to clear the "
            "harness-failure limit and the floor of 8, and ordinary D must not beat both A and "
            "C by >= 1/6. Ordinary data that cannot be judged gives INSUFFICIENT_EVIDENCE."
        ),
    },
    {
        "id": "I8",
        "predictions_lines": "106-109",
        "reading": (
            "H3 'B is not materially worse than A on both latency and tokens' is read as: it is "
            "not true that A is materially better than B on both measures. If A has zero "
            "accepted runs, A's economics is undefined, so B is not shown worse and the gap "
            "survives."
        ),
    },
    {
        "id": "I9",
        "predictions_lines": "Amendment 2 items 1 and 2 (replaces 143-145)",
        "reading": (
            "Amendment 2 sets the decision floor per compared arm: each of A, B, C, D, E needs "
            "12 scored ordinary_bounded runs (not HARNESS_FAILED, not NOT_RUN), and A, C, D, E "
            "also need the fallback rule: at least 2 scored runs in each fallback scenario and a "
            "fallback harness-failure share of at most 1/5. Any arm short gives "
            "INSUFFICIENT_EVIDENCE. The decision value is the first matching mapping rule, "
            "wrapped as ADOPT_CONDITIONALLY when H2 or H4 is SUPPORTED_FOR:fallback_reasoning "
            "and the base decision is not INSUFFICIENT_EVIDENCE."
        ),
    },
    {
        "id": "I10",
        "predictions_lines": "163-170",
        "reading": (
            "Amendment 1: inputs under a results-2026-10-03 directory are pre-amendment. They "
            "may be scored alone, but every verdict is then INSUFFICIENT_EVIDENCE because they "
            "do not count toward the evidence floor. Mixing them with other files is refused."
        ),
    },
    {
        "id": "I11",
        "predictions_lines": "126-130",
        "reading": (
            "Only Codex rows are scorable. Any other harness name is refused, because H1 to H4 "
            "name Codex model families."
        ),
    },
)
