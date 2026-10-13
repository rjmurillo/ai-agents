"""Coverage ledger check for the requirements-interview audit mode.

Validates a ledger of audit candidates against the source document, records the
ones the document or codebase already answers, and composes the rest into
batched decision questions through the decision-question engine.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from audit_source import AnchorError, Section, normalize, parse_sections, resolve_anchor

CATEGORIES = frozenset(
    {
        "edge_case",
        "undefined_state",
        "permissions",
        "error_behavior",
        "data_constraint",
        "concurrency",
        "contradiction",
        "terminology",
    }
)
DISPOSITIONS = frozenset({"ask", "answered_in_document", "answered_in_codebase"})
NO_GAPS_VERDICT = "NO MATERIAL GAPS"
OWNER_DECISION_NOTE = "Owner decision, no evidence-backed recommendation"
_DQ_RELATIVE = Path("..", "..", "decision-question", "scripts", "decision_question.py")


def load_decision_question() -> Any:
    """Import the decision-question engine (#5408) from the sibling skill."""

    path = (Path(__file__).resolve().parent / _DQ_RELATIVE).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"decision-question engine not found at {path}")
    spec = importlib.util.spec_from_file_location("decision_question", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("decision_question", module)
    spec.loader.exec_module(module)
    return module


def _anchor_problems(
    candidate: dict[str, Any], lines: list[str], sections: list[Section]
) -> list[str]:
    anchors = candidate.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        return ["anchors: at least one source anchor is required"]
    problems: list[str] = []
    headings: set[str] = set()
    for index, anchor in enumerate(anchors):
        try:
            section, _ = resolve_anchor(anchor, lines, sections)
            headings.add(section.heading)
        except AnchorError as exc:
            problems.append(f"anchors[{index}]: {exc}")
    if candidate.get("category") == "contradiction" and not problems and len(headings) < 2:
        problems.append("anchors: a contradiction needs anchors in two different sections")
    return problems


def _evidence_problems(
    candidate: dict[str, Any], lines: list[str], sections: list[Section], repo_root: Path
) -> list[str]:
    disposition = candidate["disposition"]
    if disposition == "ask":
        return []
    problems: list[str] = []
    if not str(candidate.get("answer", "")).strip():
        problems.append("answer: record what the evidence answers")
    evidence = candidate.get("evidence")
    try:
        if disposition == "answered_in_document":
            resolve_anchor(evidence, lines, sections)
        else:
            _codebase_evidence(evidence, repo_root)
    except AnchorError as exc:
        problems.append(f"evidence: {exc}")
    return problems


def _codebase_evidence(evidence: Any, repo_root: Path) -> None:
    if not isinstance(evidence, dict) or not str(evidence.get("path", "")).strip():
        raise AnchorError("codebase evidence needs a path")
    target = (repo_root / str(evidence["path"])).resolve()
    if not target.is_relative_to(repo_root.resolve()) or not target.is_file():
        raise AnchorError(f"path {evidence['path']!r} is not a file under the repo root")
    total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
    span = evidence.get("lines")
    ok = isinstance(span, list) and len(span) == 2 and all(type(n) is int for n in span)
    if not ok or not 1 <= span[0] <= span[1] <= total:
        raise AnchorError(f"lines must be [start, end] within 1-{total}")


def _ask_problems(candidate: dict[str, Any]) -> list[str]:
    if candidate["disposition"] != "ask":
        return []
    problems: list[str] = []
    for option in candidate.get("options") or []:
        if normalize(str(option.get("label", ""))).lower().startswith("other"):
            problems.append("options: 'Other' is added by the harness; do not list it")
    if (
        candidate.get("recommendation")
        and not str(candidate.get("recommendation_evidence", "")).strip()
    ):
        problems.append(
            "recommendation: needs recommendation_evidence (repo evidence or an "
            "existing contract); otherwise omit it for an owner decision"
        )
    return problems


def candidate_problems(
    candidate: dict[str, Any], lines: list[str], sections: list[Section], repo_root: Path
) -> list[str]:
    """Return every reason one ledger candidate is not usable. Empty means valid."""

    problems: list[str] = []
    if candidate.get("category") not in CATEGORIES:
        problems.append(f"category: must be one of {sorted(CATEGORIES)}")
    if candidate.get("disposition") not in DISPOSITIONS:
        problems.append(f"disposition: must be one of {sorted(DISPOSITIONS)}")
        return problems
    problems.extend(_anchor_problems(candidate, lines, sections))
    problems.extend(_evidence_problems(candidate, lines, sections, repo_root))
    problems.extend(_ask_problems(candidate))
    return problems


def _normalized(candidate: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(candidate)
    prepared.setdefault("disposition", "ask")
    return prepared


def ledger_problems(
    ledger: dict[str, Any], lines: list[str], repo_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Validate the whole ledger. Returns (candidates, problems)."""

    sections = parse_sections(lines)
    candidates = [_normalized(c) for c in ledger.get("candidates") or []]
    problems: list[dict[str, str]] = []
    missing = sorted(CATEGORIES - set(ledger.get("coverage_reviewed") or []))
    if missing:
        problems.append({"id": "ledger", "problem": f"coverage_reviewed is missing {missing}"})
    seen: set[str] = set()
    for candidate in candidates:
        cid = str(candidate.get("id", "")).strip()
        if not cid or cid in seen:
            problems.append({"id": cid or "?", "problem": "id: required and unique"})
        seen.add(cid)
        for text in candidate_problems(candidate, lines, sections, repo_root):
            problems.append({"id": cid or "?", "problem": text})
    return candidates, problems


def _decision_dict(candidate: dict[str, Any]) -> dict[str, Any]:
    decision = {
        key: candidate[key]
        for key in (
            "id",
            "statement",
            "why_now",
            "options",
            "recommendation",
            "recommendation_reason",
            "allow_hold",
            "hold_reopen_condition",
            "requires",
        )
        if key in candidate
    }
    if not candidate.get("recommendation"):
        decision["no_recommendation"] = True
    return decision


def _batch_entry(
    dq: Any, decision: Any, candidate: dict[str, Any], paging: dict[str, int], cap: int
) -> dict[str, Any]:
    pages = dq.plan_prompt_pages(decision.options, cap, hold=decision.allow_hold)
    index = paging.get(decision.id, 0)
    if index >= len(pages):
        raise ValueError(f"paging for {decision.id} is {index} but it has {len(pages)} page(s)")
    ids = [[o.id for o in page] for page in pages]
    entry = {
        "id": decision.id,
        "category": candidate["category"],
        "anchors": candidate["anchors"],
        "statement": decision.statement,
        "pages": ids,
        "page_index": index,
        "page": ids[index],
        "split": len(pages) > 1,
    }
    if decision.no_recommendation:
        entry["recommendation_note"] = OWNER_DECISION_NOTE
    return entry


def _recorded(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": c["id"],
            "disposition": c["disposition"],
            "answer": c["answer"],
            "evidence": c["evidence"],
        }
        for c in candidates
        if c["disposition"] != "ask"
    ]


def plan_questions(
    candidates: list[dict[str, Any]], ledger: dict[str, Any], max_options: int, max_questions: int
) -> dict[str, Any]:
    """Compose ask candidates into the next batch of independent questions."""

    dq = load_decision_question()
    asks = {c["id"]: c for c in candidates if c["disposition"] == "ask"}
    result: dict[str, Any] = {"recorded": _recorded(candidates)}
    if not asks:
        return {**result, "status": "no_material_gaps", "verdict": NO_GAPS_VERDICT}
    brief = {
        "context": {"material_decision": True},
        "decisions": [_decision_dict(c) for c in asks.values()],
        "answers": ledger.get("answers") or {},
        "paging": ledger.get("paging") or {},
    }
    # evaluate() validates answers and paging and reports deferred, pruned, held.
    base = dq.evaluate(brief, max_options)
    decisions = [dq.Decision.from_dict(d) for d in brief["decisions"]]
    answers = {str(k): str(v) for k, v in brief["answers"].items()}
    paging = {str(k): v for k, v in brief["paging"].items()}
    result.update({k: base[k] for k in ("deferred", "pruned", "held") if k in base})
    live = [d for d in dq.prune_chain(decisions, answers) if d.id not in answers]
    return _finish(dq, live, asks, answers, paging, result, (max_options, max_questions))


def _finish(
    dq: Any,
    live: list[Any],
    asks: dict[str, dict[str, Any]],
    answers: dict[str, str],
    paging: dict[str, int],
    result: dict[str, Any],
    caps: tuple[int, int],
) -> dict[str, Any]:
    max_options, max_questions = caps
    batch = live[:max_questions]
    stale = {
        d.id: asks[d.id]["recommendation"]
        for d in batch
        if asks[d.id].get("recommendation")
        and asks[d.id]["recommendation"] not in {o.id for o in d.options}
    }
    if stale:
        return {**result, "status": "revise_recommendation", "stale_recommendations": stale}
    gaps = {d.id: dq.missing_brief_fields(d) for d in batch if dq.missing_brief_fields(d)}
    if gaps:
        return {**result, "status": "incomplete", "incomplete": gaps}
    if not batch:
        held = bool(result.get("held"))
        return {**result, "status": "held" if held else "resolved"}
    entries = [_batch_entry(dq, d, asks[d.id], paging, max_options) for d in batch]
    return {
        **result,
        "status": "ask",
        "batch": entries,
        "max_questions_per_call": max_questions,
        "max_presented_options": max_options,
        "harness_limit_observed": dq.HARNESS_LIMIT_OBSERVED,
    }
