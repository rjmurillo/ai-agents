#!/usr/bin/env python3
"""Shared core for the moq.analyzers cross-provider eval (see
docs/eval/moq-analyzers-provider-comparison.md). One rubric, two CLI transports
(codex, claude), token + score + latency capture. All experiment drivers import
from here so the rubric and parsing are identical across every table in the doc.

Config via environment:
  MOQ_REPO   path to a checkout of rjmurillo/moq.analyzers (required for runs)
  EVAL_OUT   output directory for reports + per-cell message files (default: ./out)

Prerequisites: `pip install tiktoken openai`, plus the `codex` and `claude` CLIs
logged in (subscription auth; bypasses metered API budgets).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")
except Exception:  # noqa: BLE001 - tiktoken optional for non-cost runs
    _ENC = None

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA = str(SCRIPT_DIR / "codex_eval_schema.json")
FILES_DEFAULT = str(SCRIPT_DIR / "eval_files24.json")

KEYS = ["cohesion", "coupling", "encapsulation", "testability", "non_redundancy", "overall"]

# The single rubric used for every table in the comparison doc. Keep byte-for-byte
# stable: changing it re-baselines every score.
RUBRIC = """You are the code-qualities-assessment skill. Assess code maintainability
using these 5 timeless design qualities, each scored 1-10 against the rubric:
- cohesion: 10 = single well-defined responsibility; 1-3 = unrelated jammed together.
- coupling: 10 = minimal deps on abstractions (LOOSEST); 1-3 = tightly coupled.
- encapsulation: 10 = internals private, minimal API; 1-3 = everything public.
- testability: 10 = pure functions, injected deps; 1-3 = needs full integration.
- non_redundancy: 10 = zero duplication; 1-3 = pervasive copy-paste.
Assess ONLY the single C# source file provided. Do not read other files. Return
JSON ONLY: the 5 quality scores, overall (rounded mean of the 5), and 2-4
concrete, file-specific findings."""

RUBRIC_TOKENS = len(_ENC.encode(RUBRIC)) if _ENC else 0


def moq_repo() -> str:
    repo = os.environ.get("MOQ_REPO")
    if not repo or not Path(repo).is_dir():
        raise SystemExit(
            "Set MOQ_REPO to a checkout of rjmurillo/moq.analyzers. "
            "e.g. export MOQ_REPO=~/src/moq.analyzers"
        )
    return repo


def out_dir() -> Path:
    d = Path(os.environ.get("EVAL_OUT", SCRIPT_DIR / "out"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_files(path: str = FILES_DEFAULT) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def input_tokens(code: str) -> int:
    """Clean model-input tokens (rubric + file), what you would send via API.
    The CLIs add ~16-18k tokens of harness context on top; see the doc."""
    if _ENC is None:
        raise SystemExit("pip install tiktoken to compute input tokens")
    return len(_ENC.encode(code)) + RUBRIC_TOKENS


def parse_scores(text: str):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        o = json.loads(text[a:b + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(o, dict):
        return None
    scores = {}
    for key in KEYS:
        value = o.get(key)
        if type(value) is not int:
            return None
        scores[key] = value
    return scores


def run_codex(model: str, effort: str, code: str, msgfile: str):
    """codex exec, JSON output schema forces the shape; --json stream carries
    token usage (output + reasoning). Returns (scores|None, usage dict)."""
    proc = subprocess.run(
        ["codex", "exec", "-m", model, "-c", f"model_reasoning_effort={effort}",
         "-s", "read-only", "--ephemeral", "-C", moq_repo(), "--json",
         "--output-schema", SCHEMA, "-o", msgfile, RUBRIC],
        input=code, capture_output=True, text=True, timeout=1800)
    usage = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(o, dict) and o.get("type") == "turn.completed":
            usage = o.get("usage", {})
    if os.path.exists(msgfile):
        with open(msgfile, encoding="utf-8") as handle:
            msg = handle.read()
    else:
        msg = ""
    out_total = int(usage.get("output_tokens", 0)) + int(usage.get("reasoning_output_tokens", 0))
    return parse_scores(msg), {
        "out_total": out_total, "out_answer": usage.get("output_tokens"),
        "out_reasoning": usage.get("reasoning_output_tokens"),
        "in_harness": usage.get("input_tokens")}


def run_claude(model: str, effort: str, code: str):
    """claude -p, JSON output. usage.output_tokens includes thinking tokens.
    Unsets inherited CLAUDE_EFFORT so --effort is authoritative.
    Returns (scores|None, usage dict)."""
    env = dict(os.environ)
    env.pop("CLAUDE_EFFORT", None)
    proc = subprocess.run(
        ["claude", "-p", "--output-format", "json", "--effort", effort,
         "--append-system-prompt", RUBRIC, "--model", model],
        input=code, capture_output=True, text=True, timeout=900, cwd=moq_repo(), env=env)
    o = json.loads(proc.stdout)
    u = o.get("usage", {})
    res = str(o.get("result", "") or "")
    return parse_scores(res), {
        "out_total": u.get("output_tokens"), "out_answer": u.get("output_tokens"),
        "out_reasoning": None, "in_harness": u.get("input_tokens"),
        "cache_read": u.get("cache_read_input_tokens")}


def run_cell(transport: str, model: str, effort: str, rel: str, msg_prefix: str = "cell"):
    """One (model, file) cell with a single retry on the flaky empty-result.
    Returns a record dict with scores, token usage, in_clean, ms (or error)."""
    with open(os.path.join(moq_repo(), rel), encoding="utf-8") as handle:
        code = handle.read()
    in_clean = input_tokens(code) if _ENC else None
    safe = (msg_prefix + "_" + rel).replace("/", "_")
    last = None
    for _ in range(2):
        t = time.monotonic()
        try:
            if transport == "codex":
                scores, usage = run_codex(model, effort, code, str(out_dir() / f"{safe}.json"))
            elif transport == "claude":
                scores, usage = run_claude(model, effort, code)
            else:
                raise ValueError(f"unknown transport {transport}")
            dur = int((time.monotonic() - t) * 1000)
            if scores is not None and (usage.get("out_total") or 0) > 50:
                return {"scores": scores, **usage, "in_clean": in_clean, "ms": dur}
            last = {"error": "parse_or_empty", "out_total": usage.get("out_total"), "ms": dur}
        except Exception as exc:  # noqa: BLE001
            last = {"error": str(exc)[:160], "ms": int((time.monotonic() - t) * 1000)}
    return {**(last or {"error": "unknown"}), "in_clean": in_clean}
