#!/usr/bin/env python3
"""Skill-Router Eval: measure whether SKIP-clause descriptions improve sibling disambiguation.

Issue #2127 rewrote skill/agent `description` fields to add verbatim trigger
phrases and reciprocal SKIP clauses ("Do NOT use for X; use <sibling> instead.").
A description-matching router picks a skill from its frontmatter description alone.
This eval measures whether the rewritten descriptions let a router pick the correct
sibling more often than the old ones did.

For each fixture (a verbatim user request plus 2-4 candidate sibling skills) and
each VARIANT in {before, after}, the scorer:
  1. Resolves every candidate's description text:
       - before : `git show origin/main:<path>` (the pre-#2127 description)
       - after  : the working-tree file (the rewritten description)
  2. Builds a router prompt that lists ONLY the candidate descriptions plus the
     user query, and instructs the model to reply with EXACTLY one candidate name.
  3. Calls the Anthropic Messages API (model claude-sonnet-4-6, temperature 0).
  4. Parses the chosen skill and scores it against the fixture's `correct` field.

A candidate name resolves to a skill file `.claude/skills/<name>/SKILL.md` or, if
that does not exist, an agent file `.claude/agents/<name>.md`. Both shapes carry a
YAML `description` in their frontmatter (skills use folded scalars, agents plain).

Output is a single JSON summary on stdout:
    {
      "accuracy_before": <float>,
      "accuracy_after":  <float>,
      "n": <int>,
      "per_fixture": [
        {"id","before_pick","after_pick","correct","before_ok","after_ok"}, ...
      ]
    }

Usage:
    # Live eval (calls the API; spends tokens)
    python3 scripts/eval/eval_skill_router.py \
        --fixtures /path/to/fixtures.json

    # Dry run: build prompts, validate fixtures, resolve every candidate's
    # before+after description. No API calls, no spend.
    python3 scripts/eval/eval_skill_router.py \
        --fixtures /path/to/fixtures.json --dry-run

    # Limit to the first N fixtures
    python3 scripts/eval/eval_skill_router.py \
        --fixtures /path/to/fixtures.json --limit 5 --dry-run

Exit codes:
    0 ok
    2 config (fixtures file invalid, or a candidate's description failed to load)
    3 external (API failure)
    4 auth   (missing ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _anthropic_api import load_api_key, call_api

MODEL = "claude-sonnet-4-6"
BEFORE_REF = "origin/main"
MAX_TOKENS = 64

REQUIRED_FIXTURE_FIELDS = {"id", "query", "candidates", "correct"}


# ---------------------------------------------------------------------------
# Fixture loading and validation
# ---------------------------------------------------------------------------

def load_fixtures(path: str) -> list[dict[str, Any]]:
    """Load and validate the fixtures file.

    The file is a JSON array of disambiguation cases. Each case has:
        id        : stable identifier
        query     : a verbatim user request
        candidates: 2-4 sibling skill/agent names from one family
        correct   : the one candidate that should handle the query

    Raises RuntimeError with an actionable message on any structural error.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Fixtures file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in fixtures file {path}: {exc.msg} at line {exc.lineno}."
        ) from exc

    if not isinstance(data, list):
        raise RuntimeError(
            f"Invalid fixtures file {path}: expected a top-level JSON array."
        )
    if not data:
        raise RuntimeError(f"Fixtures file {path} has 0 cases; need at least 1.")

    seen_ids: set[str] = set()
    for i, fx in enumerate(data):
        _validate_fixture(fx, i, path, seen_ids)
    return data


def _validate_fixture(
    fx: Any, index: int, path: str, seen_ids: set[str]
) -> None:
    """Validate one fixture's shape. Raises RuntimeError on any violation."""
    if not isinstance(fx, dict):
        raise RuntimeError(
            f"Fixture at index {index} in {path} is not an object "
            f"(got {type(fx).__name__})."
        )
    missing = REQUIRED_FIXTURE_FIELDS - set(fx.keys())
    if missing:
        raise RuntimeError(
            f"Fixture {index} in {path} missing required fields: {sorted(missing)}. "
            f"Required: {sorted(REQUIRED_FIXTURE_FIELDS)}."
        )

    fid = fx["id"]
    if not isinstance(fid, str) or not fid.strip():
        raise RuntimeError(f"Fixture {index} in {path}: 'id' must be a non-empty string.")
    if fid in seen_ids:
        raise RuntimeError(f"Fixture {index} in {path}: duplicate id {fid!r}.")
    seen_ids.add(fid)

    if not isinstance(fx["query"], str) or not fx["query"].strip():
        raise RuntimeError(f"Fixture {fid} in {path}: 'query' must be a non-empty string.")

    candidates = fx["candidates"]
    if not isinstance(candidates, list) or not (2 <= len(candidates) <= 4):
        raise RuntimeError(
            f"Fixture {fid} in {path}: 'candidates' must be a list of 2-4 names "
            f"(got {len(candidates) if isinstance(candidates, list) else type(candidates).__name__})."
        )
    if len(set(candidates)) != len(candidates):
        raise RuntimeError(f"Fixture {fid} in {path}: 'candidates' contains duplicates.")
    for c in candidates:
        if not isinstance(c, str) or not c.strip():
            raise RuntimeError(
                f"Fixture {fid} in {path}: every candidate must be a non-empty string."
            )

    if fx["correct"] not in candidates:
        raise RuntimeError(
            f"Fixture {fid} in {path}: 'correct' value {fx['correct']!r} is not among "
            f"its candidates {candidates}."
        )


# ---------------------------------------------------------------------------
# Candidate resolution: name -> repo-relative path
# ---------------------------------------------------------------------------

def resolve_candidate_path(name: str, repo_root: Path) -> str:
    """Resolve a candidate name to its repo-relative description-bearing file.

    A name is a skill if `.claude/skills/<name>/SKILL.md` exists in the working
    tree, otherwise an agent at `.claude/agents/<name>.md`. The returned path is
    POSIX-relative so it can be passed straight to `git show <ref>:<path>`.

    Raises RuntimeError if neither file exists.
    """
    skill_rel = f".claude/skills/{name}/SKILL.md"
    agent_rel = f".claude/agents/{name}.md"
    if (repo_root / skill_rel).is_file():
        return skill_rel
    if (repo_root / agent_rel).is_file():
        return agent_rel
    raise RuntimeError(
        f"Candidate {name!r} resolves to neither a skill ({skill_rel}) nor an "
        f"agent ({agent_rel}) in the working tree."
    )


# ---------------------------------------------------------------------------
# Description extraction
# ---------------------------------------------------------------------------

def extract_description(markdown: str, source_label: str) -> str:
    """Extract the YAML frontmatter `description` field from a SKILL/agent file.

    Parses the leading `---` ... `---` frontmatter block with PyYAML so folded
    scalars (skills) and plain scalars (agents) both collapse to one line.

    Raises RuntimeError if there is no frontmatter, no `description` key, or an
    empty description. `source_label` names the origin (e.g. "before .claude/...")
    for actionable errors.
    """
    match = re.search(r"(?s)\A﻿?---\r?\n(.*?)\r?\n---", markdown)
    if not match:
        raise RuntimeError(f"No YAML frontmatter found in {source_label}.")

    try:
        import yaml  # lazy: only the description path needs it
    except ModuleNotFoundError as exc:  # pragma: no cover - env guard
        raise RuntimeError(
            "PyYAML is required to parse frontmatter but is not installed."
        ) from exc

    try:
        front = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Invalid YAML frontmatter in {source_label}: {exc}.") from exc

    if not isinstance(front, dict) or "description" not in front:
        raise RuntimeError(f"No 'description' field in frontmatter of {source_label}.")

    desc = front["description"]
    if not isinstance(desc, str) or not desc.strip():
        raise RuntimeError(f"Empty 'description' field in {source_label}.")
    return " ".join(desc.split())


def load_description_before(rel_path: str, repo_root: Path) -> str:
    """Load a candidate's description from the BEFORE git ref (origin/main)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{BEFORE_REF}:{rel_path}"],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Cannot load {rel_path} from ref {BEFORE_REF!r}: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Timed out loading {rel_path} from ref {BEFORE_REF!r} after {exc.timeout}s."
        ) from exc
    return extract_description(result.stdout, f"before {BEFORE_REF}:{rel_path}")


def load_description_after(rel_path: str, repo_root: Path) -> str:
    """Load a candidate's description from the AFTER working-tree file."""
    p = repo_root / rel_path
    if not p.is_file():
        raise RuntimeError(f"Working-tree file not found for after: {rel_path}")
    return extract_description(p.read_text(encoding="utf-8"), f"after (working tree) {rel_path}")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_router_prompt(
    query: str, candidates: list[str], descriptions: dict[str, str]
) -> str:
    """Build the router user message for one fixture/variant.

    Lists ONLY the candidate skills and their descriptions, then the user query,
    and instructs the model to reply with EXACTLY one candidate name.
    """
    lines = [
        "You are a skill router. Given a user request and a closed set of candidate",
        "skills (each with its description), pick the ONE skill that should handle the",
        "request. Use only the descriptions below; do not invent skills.",
        "",
        "Candidate skills:",
    ]
    for name in candidates:
        lines.append(f"- {name}: {descriptions[name]}")
    lines.extend([
        "",
        f"User request: {query}",
        "",
        "Reply with EXACTLY one skill name from the candidate list above and nothing",
        "else. No punctuation, no explanation, no code fences.",
    ])
    return "\n".join(lines)


def resolve_variant_descriptions(
    candidates: list[str], paths: dict[str, str], repo_root: Path, variant: str
) -> dict[str, str]:
    """Load the description for each candidate for a single variant."""
    loader = load_description_before if variant == "before" else load_description_after
    return {name: loader(paths[name], repo_root) for name in candidates}


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_pick(raw: str, candidates: list[str]) -> str:
    """Parse the model's chosen skill from its raw reply.

    The router prompt instructs the model to reply with EXACTLY one candidate
    name and nothing else, so the whole reply must be a single candidate (modulo
    surrounding quotes, markdown emphasis, whitespace, or trailing punctuation).
    Replies that name several candidates or wrap the pick in prose are scored as
    "PARSE_ERROR" rather than counted as correct, so accuracy is not inflated by
    loose substring matches. Longest names are checked first so a substring name
    cannot shadow a longer sibling.
    """
    text = raw.strip()
    for name in sorted(candidates, key=len, reverse=True):
        if re.fullmatch(
            rf"[\"'`*\s]*{re.escape(name)}[\"'`*.,!?;:\s-]*",
            text,
            re.IGNORECASE,
        ):
            return name
    return "PARSE_ERROR"


# ---------------------------------------------------------------------------
# API call (live path only; lazily imports the SDK)
# ---------------------------------------------------------------------------

def call_router(api_key: str, prompt: str) -> str:
    """Call the Anthropic Messages API and return the assistant's text.

    Uses the repo's own urllib-based transport (`_anthropic_api.call_api`), the
    same one the agent-vs-baseline harness uses, so no third-party SDK is
    required. temperature=0 for determinism.

    Raises RuntimeError on any transport error so main() can map it to the
    external-failure exit code.
    """
    try:
        return call_api(
            api_key,
            [{"role": "user", "content": prompt}],
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001 - normalize all transport errors to one type
        raise RuntimeError(f"Anthropic API call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Eval execution
# ---------------------------------------------------------------------------

def build_plan(
    fixtures: list[dict[str, Any]], repo_root: Path
) -> list[dict[str, Any]]:
    """Resolve paths and both-variant descriptions/prompts for every fixture.

    This is the shared work for dry-run and live runs: it touches `git show` and
    the working tree for every candidate, so a clean return proves every
    candidate's before+after description loaded without error.

    Raises RuntimeError on the first unresolvable candidate or description.
    """
    plan: list[dict[str, Any]] = []
    for fx in fixtures:
        candidates = fx["candidates"]
        paths = {name: resolve_candidate_path(name, repo_root) for name in candidates}
        before_desc = resolve_variant_descriptions(candidates, paths, repo_root, "before")
        after_desc = resolve_variant_descriptions(candidates, paths, repo_root, "after")
        plan.append({
            "fixture": fx,
            "paths": paths,
            "prompts": {
                "before": build_router_prompt(fx["query"], candidates, before_desc),
                "after": build_router_prompt(fx["query"], candidates, after_desc),
            },
        })
    return plan


def run_eval(plan: list[dict[str, Any]], api_key: str) -> dict[str, Any]:
    """Run both variants for every planned fixture and aggregate accuracy."""
    per_fixture: list[dict[str, Any]] = []
    before_ok_count = 0
    after_ok_count = 0

    total = len(plan)
    for i, item in enumerate(plan):
        fx = item["fixture"]
        candidates = fx["candidates"]
        correct = fx["correct"]
        print(f"  [{i + 1}/{total}] {fx['id']}", file=sys.stderr)

        before_pick = parse_pick(call_router(api_key, item["prompts"]["before"]), candidates)
        after_pick = parse_pick(call_router(api_key, item["prompts"]["after"]), candidates)

        before_ok = before_pick == correct
        after_ok = after_pick == correct
        before_ok_count += int(before_ok)
        after_ok_count += int(after_ok)

        per_fixture.append({
            "id": fx["id"],
            "before_pick": before_pick,
            "after_pick": after_pick,
            "correct": correct,
            "before_ok": before_ok,
            "after_ok": after_ok,
        })

    return {
        "accuracy_before": round(before_ok_count / total, 4),
        "accuracy_after": round(after_ok_count / total, 4),
        "n": total,
        "per_fixture": per_fixture,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Skill-router eval: before/after SKIP-clause disambiguation accuracy."
    )
    parser.add_argument(
        "--fixtures", type=str, required=True,
        help="Path to the fixtures JSON array."
    )
    parser.add_argument(
        "--repo-root", type=str, default=".",
        help="Repository root holding .claude/ and origin/main (default: cwd)."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Evaluate only the first N fixtures."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build prompts and resolve all before+after descriptions; no API calls."
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer.")
    return args


def main() -> int:
    """Entry point. Returns a process exit code (see module docstring)."""
    args = _parse_args()
    repo_root = Path(args.repo_root).resolve()

    try:
        fixtures = load_fixtures(args.fixtures)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.limit is not None:
        fixtures = fixtures[: args.limit]

    print(f"  Fixtures: {len(fixtures)} (from {args.fixtures})", file=sys.stderr)
    print(f"  Repo root: {repo_root}", file=sys.stderr)
    print(f"  Before ref: {BEFORE_REF}  Model: {MODEL}", file=sys.stderr)

    # Resolving the plan touches git show + working tree for every candidate's
    # before and after description. A clean return proves all of them loaded.
    try:
        plan = build_plan(fixtures, repo_root)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        planned_calls = len(plan) * 2  # one before + one after per fixture
        print("\n  DRY RUN: prompts built, descriptions resolved, no API calls made.",
              file=sys.stderr)
        print(json.dumps({
            "dry_run": True,
            "fixtures": len(plan),
            "variants": ["before", "after"],
            "planned_api_calls": planned_calls,
            "model": MODEL,
            "before_ref": BEFORE_REF,
        }, indent=2))
        return 0

    try:
        api_key = load_api_key()
    except RuntimeError as exc:
        # A missing ANTHROPIC_API_KEY is an absent environment variable, which
        # ADR-035 classifies as a configuration/environment error (exit 2), not
        # an auth failure (exit 4, reserved for a credential that exists but is
        # rejected: token expired, permission denied, rate limited).
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        summary = run_eval(plan, api_key)
    except RuntimeError as exc:
        print(f"ERROR: eval failed: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
