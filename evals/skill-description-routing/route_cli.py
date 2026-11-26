"""Organic skill routing through the real Claude Code CLI, one arm per catalog.

Each run starts `claude --print` in a fresh sandbox that holds every skill as a
stub: the real frontmatter of one arm, and a one-line body. `Skill` is the only
tool. The record keeps the first skill the model invoked, if any.

Usage (from a checkout that holds scripts/eval):
  uv run python route_cli.py --arms arms.json --queries queries.json \
      --out results.jsonl --models claude-sonnet-5-5 [--workers 2] [--limit N]

Resumable: a (model, arm, query id) already in --out is skipped unless it errored.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts" / "eval"))

from _claude_cli import PROVIDER_LABEL, _ClaudeCLIProvider
from _claude_skill_harness import ambient_instruction_paths
from _cli_transport import run_cli

STUB_BODY = "\nRouting stub. Reply with the single word OK and stop.\n"
_LOCK = threading.Lock()


def argv(model: str) -> list[str]:
    return [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--setting-sources",
        "project",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--tools",
        "Skill",
        "--no-session-persistence",
    ]


def installer(catalog: dict[str, dict[str, str]]):
    def _install(workspace: Path) -> None:
        for name, entry in catalog.items():
            target = workspace / ".claude" / "skills" / name
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text(f"---\n{entry['frontmatter']}\n---\n{STUB_BODY}")

    return _install


USAGE_KEYS = (
    "input_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "output_tokens",
)


def stream_events(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def skill_calls(event: dict) -> list[str]:
    """Return the skill named by each Skill tool call in one assistant event."""
    names = []
    for block in (event.get("message") or {}).get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == "Skill":
            args = block.get("input") or {}
            names.append(str(args.get("skill") or args.get("command") or ""))
    return names


def result_usage(event: dict) -> dict[str, int]:
    raw = event.get("usage") or {}
    usage = {key: raw[key] for key in USAGE_KEYS if isinstance(raw.get(key), int)}
    if isinstance(event.get("num_turns"), int):
        usage["num_turns"] = event["num_turns"]
    return usage


def read_stream(stdout: str) -> dict[str, object]:
    picked: list[str] = []
    listed = None
    usage: dict[str, int] = {}
    completed = False
    error = None
    for event in stream_events(stdout):
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            skills = event.get("skills")
            listed = len(skills) if isinstance(skills, list) else None
        elif kind == "assistant":
            picked.extend(skill_calls(event))
        elif kind == "result":
            failed = bool(event.get("is_error", False))
            completed = not failed
            error = str(event.get("subtype") or "error")[:80] if failed else error
            usage.update(result_usage(event))
    return {
        "picked": picked,
        "listed": listed,
        "usage": usage,
        "completed": completed,
        "error": error,
    }


def run_one(
    model: str,
    arm: str,
    query: dict[str, str],
    catalog: dict[str, dict[str, str]],
    out: Path,
    timeout: float,
    char_budget: int | None = None,
) -> None:
    record: dict[str, object] = {
        "model": model,
        "arm": arm,
        "id": query["id"],
        "skill": query["skill"],
        "kind": query["kind"],
        "char_budget": char_budget,
    }
    started = time.time()
    try:
        provider = _ClaudeCLIProvider(executable="claude", timeout=timeout)
        with tempfile.TemporaryDirectory(prefix="eval-route-") as profile:
            credential = provider._resolve_credential("claude")
            env = provider._build_env(Path(profile), credential, inherit=False)
            if char_budget:
                env["SLASH_COMMAND_TOOL_CHAR_BUDGET"] = str(char_budget)
            done = run_cli(
                argv(model),
                query["query"],
                provider_label=PROVIDER_LABEL,
                env=env,
                timeout=timeout,
                prepare=installer(catalog),
            )
        facts = read_stream(done.stdout)
        record.update(facts)
        first = facts["picked"][0].lstrip("/") if facts["picked"] else None
        record["first"] = first
        record["outcome"] = (
            "none" if first is None else "correct" if first == query["skill"] else "wrong"
        )
        if not facts["completed"] and first is None:
            record["outcome"] = "error"
    except Exception as exc:
        record["outcome"] = "error"
        record["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    record["seconds"] = round(time.time() - started, 1)
    with _LOCK, out.open("a") as handle:
        handle.write(json.dumps(record) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--arm-names", nargs="+", default=["before", "after"])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument(
        "--char-budget",
        type=int,
        help="SLASH_COMMAND_TOOL_CHAR_BUDGET for the child; lifts the listing cap",
    )
    args = parser.parse_args()
    if args.workers > 2:
        parser.error("at most 2 workers: the hub cap for eval streams")
    return args


def finished_runs(out: Path) -> set[tuple[str, str, str]]:
    """Return the (model, arm, query id) of every row that did not error."""
    if not out.exists():
        return set()
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    return {(row["model"], row["arm"], row["id"]) for row in rows if row.get("outcome") != "error"}


def main() -> int:
    args = parse_args()
    ambient = ambient_instruction_paths(Path(tempfile.gettempdir()))
    if ambient:
        print(f"sandbox sits under instruction files: {ambient}", file=sys.stderr)
        return 2
    arms = json.load(open(args.arms))
    queries = json.load(open(args.queries))
    if args.limit:
        queries = queries[: args.limit]
    out = Path(args.out)
    seen = finished_runs(out)
    jobs = [
        (model, arm, query)
        for model in args.models
        for query in queries
        for arm in args.arm_names
        if (model, arm, query["id"]) not in seen
    ]
    print(f"jobs {len(jobs)} (skipped {len(seen)})", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for model, arm, query in jobs:
            pool.submit(run_one, model, arm, query, arms[arm], out, args.timeout, args.char_budget)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
