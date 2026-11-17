#!/usr/bin/env python3
"""LLM Council delegate route: the steps around T3 or harness subagent calls.

The agent starts one delegate per council member (T3 ``delegate_task``, or the
harness's own subagent tool). This script writes the prompts each stage sends
and assembles the result, using the same members, prompts, and Borda count
as the script route (``council.py``), through one run directory:

    <run-dir>/plan.json            members, chairman, mode, unavailable members
    <run-dir>/question.md          the question
    <run-dir>/stage1-prompt.md     prompt for every councillor
    <run-dir>/stage1/<model>.md    each councillor's reply (agent writes)
    <run-dir>/stage2-prompt.md     anonymised ranking prompt
    <run-dir>/stage2/<model>.md    each ranker's reply (agent writes)
    <run-dir>/stage3-prompt.md     chairman prompt
    <run-dir>/chairman.md          chairman's reply (agent writes)
    <run-dir>/council.md           the artifact

Subcommands: ``init``, ``rank``, ``chair``, ``finish``. Each prints JSON.

Exit codes: 0 step done, 1 fewer councillors answered than the minimum,
2 config error (bad run directory, missing file, unknown member).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).absolute().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from council_core import (  # noqa: E402
    DEFAULT_MIN_RESPONSES,
    MODES,
    borda,
    chairman_prompt,
    labels_for,
    member_slug,
    members_error,
    min_responses_error,
    parse_ranking,
    ranker_prompt,
    render_artifact,
    resolve_members,
    stage1_prompt,
)

EXIT_OK, EXIT_TOO_FEW, EXIT_CONFIG = 0, 1, 2


class StepError(ValueError):
    """A run directory is missing something this step needs."""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StepError(f"cannot read {path}: {exc}") from exc


def _plan(run_dir: Path) -> dict:
    try:
        return json.loads(_read(run_dir / "plan.json"))
    except json.JSONDecodeError as exc:
        raise StepError(f"plan.json is not JSON: {exc}") from exc


def _replies(run_dir: Path, stage: str, members: list[str]) -> dict[str, str]:
    """Non-empty replies in ``stage`` for ``members``, in member order."""
    out = {}
    for model in members:
        path = run_dir / stage / f"{member_slug(model)}.md"
        if path.is_file():
            text = _read(path).strip()
            if text:
                out[model] = text
    return out


def _emit(payload: dict) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    """Resolve members, record unavailable ones, and write the Stage 1 prompt."""
    council, chairman = resolve_members(args.mode, args.models, args.cheap, args.chairman)
    config_error = min_responses_error(args.min_responses) or members_error(council)
    if config_error:
        raise StepError(config_error)
    bad = [item for item in args.unavailable if "=" not in item]
    if bad:
        raise StepError(f"--unavailable takes MODEL=REASON, got: {', '.join(bad)}")
    unavailable = dict(item.split("=", 1) for item in args.unavailable)
    unknown = sorted(set(unavailable) - {*council, chairman})
    if unknown:
        raise StepError(f"--unavailable names a model that is not a member: {', '.join(unknown)}")
    question = _read(Path(args.question_file)).strip()
    if not question:
        raise StepError("question file is empty")
    run_dir = Path(args.run_dir)
    if (run_dir / "plan.json").exists():
        raise StepError(f"{run_dir} already holds a council run; use a new --run-dir")
    (run_dir / "stage1").mkdir(parents=True, exist_ok=True)
    (run_dir / "stage2").mkdir(parents=True, exist_ok=True)
    plan = {
        "mode": args.mode,
        "council": council,
        "chairman": chairman,
        "unavailable": unavailable,
        "min_responses": min(args.min_responses, len(council)),
    }
    (run_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    (run_dir / "question.md").write_text(question + "\n", encoding="utf-8")
    (run_dir / "stage1-prompt.md").write_text(stage1_prompt(question), encoding="utf-8")
    start = [m for m in council if m not in unavailable]
    replies = {m: str(run_dir / "stage1" / f"{member_slug(m)}.md") for m in start}
    return _emit(
        {
            "start": start,
            "unavailable": unavailable,
            "prompt": str(run_dir / "stage1-prompt.md"),
            "replies": replies,
        }
    )


def cmd_rank(args: argparse.Namespace) -> int:
    """Check Stage 1 survivors and write the anonymised Stage 2 prompt."""
    run_dir = Path(args.run_dir)
    plan = _plan(run_dir)
    if "survivors" in plan:
        raise StepError("rank already ran for this run; the survivors are frozen")
    responses = _replies(run_dir, "stage1", plan["council"])
    if len(responses) < plan["min_responses"]:
        print(
            f"council_steps: only {len(responses)} councillors answered, need {plan['min_responses']}",
            file=sys.stderr,
        )
        return EXIT_TOO_FEW
    survivors = list(responses)
    # Freeze the survivors: a Stage 1 reply that lands after this point would
    # shift the anonymous labels and break every ranking.
    plan["survivors"] = survivors
    (run_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    question = _read(run_dir / "question.md").strip()
    (run_dir / "stage2-prompt.md").write_text(
        ranker_prompt(question, survivors, responses), encoding="utf-8"
    )
    replies = {m: str(run_dir / "stage2" / f"{member_slug(m)}.md") for m in survivors}
    return _emit(
        {"rankers": survivors, "prompt": str(run_dir / "stage2-prompt.md"), "replies": replies}
    )


def _stage2(run_dir: Path, survivors: list[str]):
    labels = labels_for(len(survivors))
    rankings_raw = _replies(run_dir, "stage2", survivors)
    parsed = {
        m: order for m, text in rankings_raw.items() if (order := parse_ranking(text, labels))
    }
    aggregate = borda(parsed, labels) if parsed else []
    return rankings_raw, parsed, aggregate, dict(zip(labels, survivors, strict=True))


def _ranked(run_dir: Path) -> tuple[dict, list[str], dict[str, str]]:
    """Return (plan, frozen survivors, their Stage 1 replies). Needs ``rank`` first."""
    plan = _plan(run_dir)
    if "survivors" not in plan:
        raise StepError("run `rank` before `chair` or `finish`")
    survivors = plan["survivors"]
    responses = _replies(run_dir, "stage1", survivors)
    missing = [m for m in survivors if m not in responses]
    if missing:
        raise StepError(f"Stage 1 replies vanished after rank: {', '.join(missing)}")
    return plan, survivors, responses


def cmd_chair(args: argparse.Namespace) -> int:
    """Run the Borda count and write the Stage 3 chairman prompt."""
    run_dir = Path(args.run_dir)
    plan, survivors, responses = _ranked(run_dir)
    rankings_raw, parsed, aggregate, label_map = _stage2(run_dir, survivors)
    question = _read(run_dir / "question.md").strip()
    prompt = chairman_prompt(plan["mode"], question, survivors, responses, rankings_raw)
    (run_dir / "stage3-prompt.md").write_text(prompt, encoding="utf-8")
    return _emit(
        {
            "chairman": plan["chairman"],
            "chairman_unavailable": plan["unavailable"].get(plan["chairman"], ""),
            "prompt": str(run_dir / "stage3-prompt.md"),
            "reply": str(run_dir / "chairman.md"),
            "borda": [[label_map[lbl], round(score, 2)] for lbl, score in aggregate],
            "unparsed_rankers": sorted(set(rankings_raw) - set(parsed)),
            "missing_rankers": [m for m in survivors if m not in rankings_raw],
        }
    )


def cmd_finish(args: argparse.Namespace) -> int:
    """Write the council artifact from the run directory."""
    run_dir = Path(args.run_dir)
    plan, survivors, responses = _ranked(run_dir)
    rankings_raw, _, aggregate, label_map = _stage2(run_dir, survivors)
    chair = run_dir / "chairman.md"
    synthesis = _read(chair).strip() if chair.is_file() else ""
    errors = dict(plan["unavailable"])
    late = set(_replies(run_dir, "stage1", plan["council"])) - set(survivors)
    for model in plan["council"]:
        if model not in responses and model not in errors:
            errors[model] = "replied after ranking started" if model in late else "no reply"
    for model in survivors:
        if model not in rankings_raw:
            errors[model] = "no Stage 2 ranking"
    if not synthesis:
        reason = plan["unavailable"].get(plan["chairman"])
        synthesis = (
            f"[Chairman unavailable: {reason}]"
            if reason
            else "[Chairman synthesis failed: no reply]"
        )
    run = {
        "mode": plan["mode"],
        "chairman": plan["chairman"],
        "council": plan["council"],
        "errors": errors,
        "question": _read(run_dir / "question.md").strip(),
        "synthesis": synthesis,
        "survivors": survivors,
        "responses": responses,
        "aggregate": aggregate,
        "label_map": label_map,
        "rankings_raw": rankings_raw,
    }
    artifact = run_dir / "council.md"
    artifact.write_text(render_artifact(run), encoding="utf-8")
    return _emit({"artifact": str(artifact), "errors": errors, "synthesis": synthesis})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM Council delegate-route steps.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="resolve members and write the Stage 1 prompt")
    init.add_argument("--run-dir", required=True)
    init.add_argument("--question-file", required=True)
    init.add_argument("--mode", default="general", choices=list(MODES))
    init.add_argument("--models", help="Comma-separated councillor model ids (overrides defaults)")
    init.add_argument("--chairman", help="Chairman model id")
    init.add_argument("--cheap", action="store_true", help="Use the free-tier council")
    init.add_argument(
        "--unavailable",
        action="append",
        default=[],
        metavar="MODEL=REASON",
        help="member the harness cannot reach",
    )
    init.add_argument("--min-responses", type=int, default=DEFAULT_MIN_RESPONSES)
    for name, helptext in (
        ("rank", "write the Stage 2 ranking prompt"),
        ("chair", "run Borda and write the chairman prompt"),
        ("finish", "write the council artifact"),
    ):
        sub.add_parser(name, help=helptext).add_argument("--run-dir", required=True)
    return parser


COMMANDS = {"init": cmd_init, "rank": cmd_rank, "chair": cmd_chair, "finish": cmd_finish}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (StepError, KeyError, OSError, ValueError) as exc:
        print(f"council_steps: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
