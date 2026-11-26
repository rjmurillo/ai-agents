#!/usr/bin/env python3
"""LLM Council script route: multi-model deliberation via Copilot CLI and GitHub Models.

Three-stage flow (Karpathy-inspired, via thevgavini/ghcp-llm-council):
  1. N councillors answer in parallel
  2. Each surviving councillor ranks all responses anonymously (Borda count)
  3. Chairman synthesizes a final answer

Default councils are task-shaped and use the current Copilot frontier catalog:
  - ambiguous judgment/design: GPT-6 Astra + Claude Opus 5.5 + GPT-6 Sol + Claude Sonnet 5
  - implementation plans: GPT-6 Astra + GPT-6 Sol + Claude Sonnet 5 + Claude Opus 5.5
  - research/review: GPT-6 Sol + Claude Opus 5.5 + Claude Sonnet 5 + GPT-6 Astra
Default chairman: GPT-6 Astra, except research/review use Claude Opus 5.5.

Usage:
  council.py "Question text" [--mode general|design|plan|research|review]
                              [--chairman MODEL_ID]
                              [--out PATH]
                              [--quiet]
                              [--models m1,m2,m3]  (override defaults)
                              [--cheap]            (free-tier only, no credits)

Exit codes: 0 synthesis written, 1 no gh token for a GitHub Models member,
2 fewer councillors answered than --min-responses.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import subprocess
import sys
import time
from collections.abc import Callable
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_BOOTSTRAP = Path(__file__).resolve().parents[3] / "lib" / "bootstrap.py"
if not _BOOTSTRAP.is_file():
    raise ImportError(f"Cannot load skill bootstrap from {_BOOTSTRAP}")
_spec = spec_from_file_location("_skill_bootstrap", _BOOTSTRAP)
assert _spec is not None and _spec.loader is not None
_bootstrap = module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
paths = _bootstrap.load_skill_paths(_BOOTSTRAP.parent, __file__)

from council_backends import backend_for, call_model, gh_token  # noqa: E402
from council_core import (  # noqa: E402
    CHEAP_CHAIRMAN,
    DEFAULT_CHAIRMAN,
    DEFAULT_MIN_RESPONSES,
    MODES,
    borda,
    chairman_prompt,
    labels_for,
    members_error,
    min_responses_error,
    parse_ranking,
    ranker_prompt,
    render_artifact,
    resolve_members,
    stage1_prompt,
)

ARTIFACT_SUBDIR = "council/runs"
Log = Callable[..., None]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("question", help="The question for the council")
    ap.add_argument("--mode", default="general", choices=list(MODES))
    ap.add_argument(
        "--chairman",
        help=f"Chairman model id (default: {DEFAULT_CHAIRMAN}; with --cheap: {CHEAP_CHAIRMAN})",
    )
    ap.add_argument("--models", help="Comma-separated councillor model ids (overrides defaults)")
    ap.add_argument(
        "--cheap", action="store_true", help="Use free-tier council only (no Copilot AI Credits)"
    )
    ap.add_argument("--out", help="Output file (default: <artifact root>/council/runs/<ts>.md)")
    ap.add_argument("--quiet", action="store_true", help="Suppress stage progress to stderr")
    ap.add_argument(
        "--min-responses",
        type=int,
        default=DEFAULT_MIN_RESPONSES,
        help=f"Minimum successful councillors to proceed (default {DEFAULT_MIN_RESPONSES})",
    )
    return ap


def _fetch_token(council: list[str], chairman: str, log: Log) -> str | None:
    """Fetch a gh token only when a member routes through GitHub Models REST.

    A Copilot-only council must not fail for users who never ran `gh auth login`.
    """
    if all(backend_for(m) != "github-models" for m in [*council, chairman]):
        return None
    try:
        return gh_token()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log("[error] At least one councillor or the chairman routes through")
        log("        GitHub Models, which requires `gh auth login`. Either")
        log("        install/authenticate the GitHub CLI, or pass a council")
        log("        consisting only of Copilot-backed models.")
        log(f"        ({e})")
        sys.exit(1)


def _fan_out(
    token: str | None, models: list[str], prompt: str, **kw
) -> dict[str, tuple[str | None, str]]:
    """Call every model in parallel. Returns {model: (text or None, error)}."""
    results: dict[str, tuple[str | None, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as ex:
        futures = {ex.submit(call_model, token, m, prompt, **kw): m for m in models}
        for fut in concurrent.futures.as_completed(futures):
            model = futures[fut]
            try:
                results[model] = (fut.result(), "")
            # One councillor's failure, of any kind, must not abort the others;
            # the error text is kept and reported in the artifact.
            except Exception as e:
                results[model] = (None, str(e)[:200])
    return results


def run_stage1(token: str | None, council: list[str], question: str, log: Log):
    log("[stage 1] dispatching councillors in parallel...")
    t0 = time.time()
    responses: dict[str, str] = {}
    errors: dict[str, str] = {}
    for model, (text, error) in _fan_out(token, council, stage1_prompt(question)).items():
        if text and text.strip():
            responses[model] = text.strip()
            log(f"  ok {model} ({len(text)} chars)")
        else:
            errors[model] = error or "empty response"
            log(f"  FAIL {model}: {errors[model]}")
    log(f"[stage 1] {len(responses)}/{len(council)} succeeded in {time.time() - t0:.1f}s")
    return responses, errors


def run_stage2(
    token: str | None, question: str, survivors: list[str], responses: dict[str, str], log: Log
):
    labels = labels_for(len(survivors))
    label_map = dict(zip(labels, survivors, strict=True))
    log(f"[stage 2] {len(survivors)} rankers")
    t0 = time.time()
    rankings_raw: dict[str, str] = {}
    rankings_parsed: dict[str, list[str]] = {}
    # Rankers review every response before the FINAL RANKING block, so lift the
    # output cap to 4096; 2048 cut verbose rankers off before the block.
    prompt = ranker_prompt(question, survivors, responses)
    for model, (text, error) in _fan_out(token, survivors, prompt, max_tokens=4096).items():
        if text is None:
            log(f"  FAIL ranker {model}: {error}")
            continue
        rankings_raw[model] = text
        parsed = parse_ranking(text, labels)
        if parsed:
            rankings_parsed[model] = parsed
            log(f"  ok ranker {model}: {[label_map[lbl].split('/')[-1] for lbl in parsed]}")
        else:
            log(f"  WARN ranker {model}: could not parse FINAL RANKING block")
    aggregate = borda(rankings_parsed, labels) if rankings_parsed else []
    if aggregate:
        log("[stage 2] Borda (lower=better):")
        for lbl, score in aggregate:
            log(f"          {round(score, 2)}  {label_map[lbl]}")
    log(f"[stage 2] {time.time() - t0:.1f}s")
    return rankings_raw, aggregate, label_map


def run_stage3(token: str | None, chairman: str, prompt: str, log: Log) -> str:
    log(f"[stage 3] chairman {chairman} synthesizing...")
    t0 = time.time()
    try:
        synthesis = call_model(token, chairman, prompt, max_tokens=4096).strip()
        log(f"[stage 3] {len(synthesis)} chars in {time.time() - t0:.1f}s")
    # A failed chairman still leaves Stage 1 and Stage 2 worth writing out.
    except Exception as e:
        log(f"[stage 3] FAILED: {e}")
        synthesis = f"[Chairman synthesis failed: {e}]"
    return synthesis


def _out_path(out: str | None) -> Path:
    if out:
        return Path(out)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return paths.artifact_dir(ARTIFACT_SUBDIR) / f"{stamp}.md"


def _announce(council: list[str], chairman: str, mode: str, out_path: Path, log: Log) -> None:
    log(f"[council] {len(council)} councillors:")
    for model in council:
        log(f"          - {model}  ({backend_for(model)})")
    log(f"[council] chairman: {chairman}  ({backend_for(chairman)})")
    log(f"[council] mode: {mode}    artifact: {out_path}")


def _quiet_log(*_args: object, **_kwargs: object) -> None:
    return None


def _stderr_log(*args: object, **kwargs: object) -> None:
    print(*args, **kwargs, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_error = min_responses_error(args.min_responses)
    council, chairman = resolve_members(args.mode, args.models, args.cheap, args.chairman)
    config_error = config_error or members_error(council)
    if config_error:
        print(f"council: {config_error}", file=sys.stderr)
        return 2
    log: Log = _quiet_log if args.quiet else _stderr_log
    token = _fetch_token(council, chairman, log)
    out_path = _out_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _announce(council, chairman, args.mode, out_path, log)

    # Clamp --min-responses to the council size, or a two-member custom council
    # would abort even when both answer.
    min_required = min(args.min_responses, len(council))
    if min_required < args.min_responses:
        log(
            f"[council] --min-responses={args.min_responses} clamped to {min_required} ({len(council)} councillors)"
        )

    responses, errors = run_stage1(token, council, args.question, log)
    if len(responses) < min_required:
        log(f"[abort] only {len(responses)} succeeded, need {min_required}")
        return 2
    survivors = list(responses)
    rankings_raw, aggregate, label_map = run_stage2(token, args.question, survivors, responses, log)
    prompt = chairman_prompt(args.mode, args.question, survivors, responses, rankings_raw)
    synthesis = run_stage3(token, chairman, prompt, log)
    run = {
        "mode": args.mode,
        "chairman": chairman,
        "council": council,
        "errors": errors,
        "question": args.question,
        "synthesis": synthesis,
        "survivors": survivors,
        "responses": responses,
        "aggregate": aggregate,
        "label_map": label_map,
        "rankings_raw": rankings_raw,
    }
    out_path.write_text(render_artifact(run), encoding="utf-8")
    log(f"[done] artifact written to {out_path}")
    print(synthesis)
    return 0


if __name__ == "__main__":
    sys.exit(main())
