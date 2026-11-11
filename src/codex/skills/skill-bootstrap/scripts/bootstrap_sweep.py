#!/usr/bin/env python3
# taste-lint: ignore file-size, plan, index, import, and tally share one sweep schema and digest chain.
"""Cross-source friction sweep: plan, index, import, tally; see references/friction-sources.md.

Offline and stdlib-only. The agent reads sources through harness tools and writes
evidence files; this script classifies, validates, batches, and tallies them.
Exit codes: 0 ok, 1 validation violation, 2 config or malformed input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

from bootstrap_friction import read_json

Payload = dict[str, Any]

SCHEMA_VERSION = 1
AGENT = "agent_sessions"
OTHER = "other"
CLASSES = (
    "code_review",
    "work_tracking",
    "chat",
    "email",
    "documents",
    "meetings",
    "build_ops",
    "memory",
    "work_intelligence",
    AGENT,
    OTHER,
)
STATES = ("read", "partial", "declined", "not_connected", "unavailable")
CONSENT = ("granted", "not_needed")
VISIBILITY = ("public", "private")
TYPE_ORDER = (
    "knowledge-gap",
    "human-agent",
    "agent-process",
    "agent-tool",
    "agent-agent",
    "human-process",
    "human-tool",
    "human-human",
)
PATTERNS = (
    "fragmented-context",
    "inconsistent-linking",
    "incomplete-evidence",
    "surface-switching",
    "review-gate-latency",
    "work-item-drift",
    "shadow-work",
    "lagging-indicator",
    "access-barrier",
    "oversized-change",
    "unclear-ownership",
    "missing-context",
    "unstable-checks",
    "other",
)
ACTIONS = (
    "create-skill",
    "update-skill",
    "write-doc",
    "add-instrument",
    "fix-process",
    "ask-owner",
)
ANSWER_LOCATIONS = (
    "repo",
    "maintained_doc",
    "chat",
    "email",
    "meeting",
    "memory",
    "person",
    "unknown",
)
DOCUMENTED_LOCATIONS = ("repo", "maintained_doc")
DISCOVERY_STATES = ("ok", "unsupported", "failed")
DISCOVERY_KEYS = ("tools_list", "resources_list", "prompts_list", "skills_list")
DISPOSITIONS = ("unresolved", "document", "covered")
METRIC_NUMERIC = frozenset(
    "commits revisions rebases review_rounds review_comments reviewers_requested "
    "reviewers_engaged hours_to_first_review days_open idle_days lines_changed files_changed "
    "ci_runs ci_failures ci_failures_before_review days_unassigned days_since_activity "
    "comments reopen_count".split()
)
METRIC_BOOLEAN = frozenset(
    "linked_issue has_test_changes has_description_context stacked assigned prioritized "
    "linked_change".split()
)
# Booleans where false is a missing practice; `stacked` is descriptive, not a gap.
METRIC_EXPECTED_TRUE = (
    "assigned",
    "has_description_context",
    "has_test_changes",
    "linked_change",
    "linked_issue",
    "prioritized",
)
OUTLIER_MIN_ITEMS = 5

DEFAULT_WINDOW_DAYS = 180
DEFAULT_BATCH_SIZE = 20
DEFAULT_JUDGE_RUNS = 2
HOTSPOT_CAP = 20
TOP_INCIDENTS = 5
MAX_EVIDENCE_BYTES = 64 * 1024
MAX_LOCATOR = 500
MAX_DESCRIPTION = 1000
EVIDENCE_DIR = "evidence"
GIT_TIMEOUT_S = 30

SKILL_DIR = Path(__file__).resolve().parent.parent

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
FINDING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
JUDGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")

# Sensitive shapes rejected at index time; only the class name is ever reported.
SENSITIVE = {
    "email": EMAIL_RE,
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "github_pat": re.compile(r"github_pat_"),
    "slack_token": re.compile(r"xox[abprs]-"),
    "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "api_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "phone_e164": re.compile(r"\+[1-9]\d{7,14}"),
    "phone_us": re.compile(r"\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}"),
    "user_mention": re.compile(r"<@[UW][A-Z0-9]{6,}>"),
}

# Keyword tables are a fallback hint on a server or skill name, never a source filter.
KEYWORDS = {
    "code_review": (
        "github",
        "gitlab",
        "bitbucket",
        "azure devops",
        "azure devops repos",
        "ado",
    ),
    "work_tracking": (
        "jira",
        "linear",
        "github",
        "ado",
        "azure devops",
        "azure devops boards",
        "asana",
        "youtrack",
    ),
    "chat": ("slack", "teams", "discord", "mattermost"),
    "email": ("gmail", "outlook", "mail", "m365", "microsoft 365", "exchange"),
    "documents": (
        "google drive",
        "google docs",
        "google sheets",
        "sheets",
        "slides",
        "confluence",
        "notion",
        "sharepoint",
        "onedrive",
    ),
    "meetings": ("calendar", "zoom", "meet", "fireflies", "otter"),
    "build_ops": (
        "actions",
        "ci",
        "circleci",
        "jenkins",
        "sentry",
        "datadog",
        "pagerduty",
        "grafana",
        "buildkite",
    ),
    "memory": ("mem0", "hindsight", "serena", "memory", "claude mem", "letta", "zep"),
    "work_intelligence": ("workiq", "work iq", "copilot", "glean", "m365 copilot"),
}
SKILL_ONLY_KEYWORDS = {AGENT: ("skill doctor", "session", "sessions")}
PHRASES = {
    cls: tuple(tuple(p.split()) for p in phrases)
    for cls, phrases in {**KEYWORDS, **SKILL_ONLY_KEYWORDS}.items()
}

WRITE_VERBS = frozenset(
    "send post create update delete trash label unlabel mark unmark add apply merge write "
    "schedule share copy move archive unarchive react respond retain clear invalidate resolve "
    "unresolve enable disable trigger fire fork push edit set refresh sync upload insert "
    "append rename request run execute cancel invite assign close reopen approve dismiss "
    "submit lock pin unpin star".split()
)
READ_VERBS = frozenset(
    "get list search read query fetch recall view find lookup describe download export".split()
)

SIGNALS = {
    "code_review": [
        "changes requested",
        "please document",
        "why is this",
        "same comment as",
        "nit again",
    ],
    "work_tracking": ["reopened", "duplicate of", "blocked on", "works as designed", "waiting on"],
    "chat": [
        "does anyone know",
        "who owns",
        "where is this documented",
        "ask in",
        "the AI got this wrong",
    ],
    "email": [
        "waiting on approval",
        "following up",
        "FYI here is how",
        "escalation",
        "can you confirm",
    ],
    "documents": ["out of date", "see the runbook", "outdated", "which doc is right", "TODO"],
    "meetings": ["triage", "office hours", "action items", "decision", "weekly sync"],
    "build_ops": ["flaky", "rerun", "manual deploy", "postmortem action item", "runbook"],
    "memory": ["convention", "decided", "always", "never", "lesson learned"],
    "work_intelligence": [
        "who worked on",
        "recent decisions",
        "owner of",
        "who knows",
        "related documents",
    ],
    AGENT: ["repeated tool call", "retry", "error output", "user correction"],
    OTHER: ["how do we", "who decides", "workaround"],
}


class ConfigError(Exception):
    """Bad input or unsafe path: exit 2."""


class EvidenceError(Exception):
    """One evidence file failed a path, size, or encoding rule."""


# ------------------------------------------------------------------ validation toolkit


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def _obj(value: Any, what: str) -> Payload:
    _need(isinstance(value, dict), f"{what} must be an object")
    return value


def _lst(value: Any, what: str) -> list[Any]:
    _need(isinstance(value, list), f"{what} must be a list")
    return value


def _str(value: Any, what: str) -> str:
    _need(isinstance(value, str) and bool(value.strip()), f"{what} must be nonempty text")
    return value


def _int(value: Any, what: str, minimum: int = 0) -> int:
    _need(type(value) is int and value >= minimum, f"{what} must be an integer >= {minimum}")
    return value


def _enum(value: Any, allowed: tuple[str, ...], what: str) -> str:
    _need(isinstance(value, str) and value in allowed, f"{what} must be one of {list(allowed)}")
    return value


def _keys(obj: Payload, required: set[str], optional: set[str], what: str) -> None:
    missing = sorted(required - obj.keys())
    unknown = sorted(obj.keys() - required - optional)
    _need(not missing, f"{what} is missing keys {missing}")
    _need(not unknown, f"{what} has unknown keys {unknown}")


def _opt_text(obj: Payload, key: str, what: str) -> str | None:
    if key not in obj:
        return None
    value = obj[key]
    _need(isinstance(value, str) and len(value) <= MAX_DESCRIPTION, f"{what}.{key} must be text")
    return value


def _class_list(value: Any, what: str) -> list[str]:
    items = _lst(value, what)
    _need(bool(items), f"{what} must not be empty")
    chosen = {_enum(item, CLASSES, f"{what} entry") for item in items}
    return [cls for cls in CLASSES if cls in chosen]


def _parse_day(value: Any, what: str) -> date:
    _need(isinstance(value, str) and bool(DAY_RE.match(value)), f"{what} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{what} is not a real date") from exc


# ------------------------------------------------------------------ io helpers


def digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def load_json(path: Path) -> Payload:
    try:
        data, _ = read_json(str(path))
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return data


def repo_toplevel(repo: Path) -> Path:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigError(f"git failed: {exc}") from exc
    _need(proc.returncode == 0, f"{repo} is not a git repository")
    return Path(proc.stdout.strip()).resolve()


def tracked_paths(root: Path) -> tuple[set[str], set[str]]:
    """Return tracked files and their parent directories (`git ls-files`)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigError(f"git ls-files failed: {exc}") from exc
    _need(proc.returncode == 0, "git ls-files failed")
    files = {name for name in proc.stdout.split("\0") if name}
    dirs = {parent.as_posix() for name in files for parent in PurePosixPath(name).parents}
    return files, dirs - {"."}


def ensure_outside(root: Path, path: Path, label: str) -> Path:
    target = path.resolve()
    _need(
        target != root and root not in target.parents,
        f"{label} {target} is inside the repository {root}; use a path outside it",
    )
    return target


def ensure_inside(run_dir: Path, path: Path, label: str) -> Path:
    target = path.resolve()
    _need(run_dir in target.parents, f"{label} {target} must be inside the run directory")
    _need(not target.is_dir(), f"{label} {target} is a directory")
    return target


# ------------------------------------------------------------------ classification


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", text.lower()) if token]


def _contains(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    size = len(phrase)
    return any(tuple(tokens[i : i + size]) == phrase for i in range(len(tokens) - size + 1))


def keyword_classes(name: str, *, skill: bool = False) -> list[str]:
    """Match the keyword tables against a name, with and without camelCase splitting."""
    variants = [_tokens(name), _tokens(CAMEL_RE.sub(" ", name))]
    found = []
    for cls in CLASSES:
        if cls == AGENT and not skill:
            continue
        phrases = PHRASES.get(cls, ())
        if any(_contains(tokens, phrase) for phrase in phrases for tokens in variants):
            found.append(cls)
    return found


def resolve_classes(
    name: str, declared: list[str] | None, overrides: dict[str, list[str]], *, skill: bool
) -> tuple[list[str], str]:
    """Override, then declared, then keyword, else `other`."""
    if name in overrides:
        return overrides[name], "override"
    if declared:
        return declared, "declared"
    found = keyword_classes(name, skill=skill)
    if found:
        return found, "keyword"
    return [OTHER], "default"


def tool_access(tool: Payload) -> tuple[str, str | None]:
    """Fail closed: any write verb excludes; unknown verbs need a declared read plus a description."""
    words = set(_tokens(CAMEL_RE.sub(" ", tool["name"])))
    if words & WRITE_VERBS:
        return "write", None
    if words & READ_VERBS:
        return "read", "verb"
    if tool["access"] == "read" and tool["description"].strip():
        return "read", "declared"
    return "unknown", None


# ------------------------------------------------------------------ inventory


def _described(entry: Any, what: str, extra: set[str]) -> Payload:
    """Normalize `str | object` to an object with a name and optional description."""
    if isinstance(entry, str):
        entry = {"name": entry}
    obj = _obj(entry, what)
    _keys(obj, {"name"}, {"description"} | extra, what)
    _str(obj["name"], f"{what}.name")
    _opt_text(obj, "description", what)
    return obj


def _parse_tool(entry: Any, what: str) -> Payload:
    tool = _described(entry, what, {"access"})
    if "access" in tool:
        _need(tool["access"] == "read", f"{what}.access must be 'read'")
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "access": tool.get("access"),
    }


def _parse_resource(entry: Any, what: str) -> Payload:
    if isinstance(entry, str):
        entry = {"uri": entry}
    obj = _obj(entry, what)
    _keys(obj, {"uri"}, {"name", "description"}, what)
    _str(obj["uri"], f"{what}.uri")
    for key in ("name", "description"):
        _opt_text(obj, key, what)
    return obj


def _unique(entries: list[Payload], key: str) -> list[Payload]:
    seen: dict[str, Payload] = {}
    for entry in entries:
        seen.setdefault(entry[key], entry)
    return list(seen.values())


def _parse_server(entry: Any, index: int) -> Payload:
    what = f"servers[{index}]"
    if isinstance(entry, str):
        entry = {"name": entry}
    obj = _obj(entry, what)
    _keys(obj, {"name"}, {"description", "classes", "tools", "resources", "prompts"}, what)
    _str(obj["name"], f"{what}.name")
    _opt_text(obj, "description", what)
    tools = [_parse_tool(t, f"{what}.tools") for t in _lst(obj.get("tools", []), f"{what}.tools")]
    resources = [
        _parse_resource(r, f"{what}.resources")
        for r in _lst(obj.get("resources", []), f"{what}.resources")
    ]
    prompts = [_described(p, f"{what}.prompts", set()) for p in _lst(obj.get("prompts", []), what)]
    declared = _class_list(obj["classes"], f"{what}.classes") if "classes" in obj else None
    return {
        "name": obj["name"],
        "classes": declared,
        "tools": _unique(tools, "name"),
        "resources": _unique(resources, "uri"),
        "prompts": _unique(prompts, "name"),
    }


def _parse_skill(entry: Any, index: int) -> Payload:
    what = f"skills[{index}]"
    skill = _described(entry, what, {"classes"})
    declared = _class_list(skill["classes"], f"{what}.classes") if "classes" in skill else None
    return {"name": skill["name"], "classes": declared}


def _parse_discovery(value: Any) -> Payload:
    discovery = _obj(value, "discovery")
    _keys(discovery, set(), set(DISCOVERY_KEYS), "discovery")
    for key, state in discovery.items():
        _enum(state, DISCOVERY_STATES, f"discovery.{key}")
    return discovery


def _unique_names(entries: list[Payload], what: str) -> None:
    names = [entry["name"] for entry in entries]
    _need(len(names) == len(set(names)), f"duplicate {what} names")


def parse_inventory(data: Payload) -> Payload:
    _keys(data, {"schema_version", "servers", "skills"}, {"discovery"}, "tool inventory")
    _need(data["schema_version"] == SCHEMA_VERSION, "unsupported inventory schema_version")
    servers = [_parse_server(s, i) for i, s in enumerate(_lst(data["servers"], "servers"))]
    skills = [_parse_skill(s, i) for i, s in enumerate(_lst(data["skills"], "skills"))]
    _unique_names(servers, "server")
    _unique_names(skills, "skill")
    discovery = _parse_discovery(data["discovery"]) if "discovery" in data else {}
    return {"servers": servers, "skills": skills, "discovery": discovery}


def parse_overrides(values: list[str], inventory: Payload) -> dict[str, list[str]]:
    known = {s["name"] for s in inventory["servers"]} | {s["name"] for s in inventory["skills"]}
    chosen: dict[str, set[str]] = {}
    for value in values:
        name, sep, cls = value.rpartition("=")
        _need(bool(sep and name), f"--class-override {value!r} must be SERVER=CLASS")
        _enum(cls, CLASSES, "--class-override class")
        _need(name in known, f"--class-override names unknown server or skill {name!r}")
        chosen.setdefault(name, set()).add(cls)
    return {name: [c for c in CLASSES if c in cls_set] for name, cls_set in chosen.items()}


# ------------------------------------------------------------------ plan


def _empty_classes() -> dict[str, Payload]:
    return {
        cls: {"servers": [], "read_tools": [], "skills": [], "resources": []} for cls in CLASSES
    }


def _place_server(server: Payload, classes: list[str], plan: Payload) -> None:
    reads: list[Payload] = []
    for tool in sorted(server["tools"], key=lambda t: t["name"]):
        verdict, source = tool_access(tool)
        if verdict == "read":
            reads.append({"server": server["name"], "tool": tool["name"], "access_source": source})
        else:
            plan["excluded_tools"].append(
                {"server": server["name"], "tool": tool["name"], "reason": verdict}
            )
        if source == "declared":
            plan["declared_read_tools"].append(
                {
                    "server": server["name"],
                    "tool": tool["name"],
                    "description": tool["description"],
                }
            )
    resources = [
        {"server": server["name"], **{k: v for k, v in r.items() if k in ("uri", "name")}}
        for r in sorted(server["resources"], key=lambda r: r["uri"])
    ]
    for cls in classes:
        entry = plan["classes"][cls]
        entry["servers"].append(server["name"])
        entry["read_tools"].extend(reads)
        entry["resources"].extend(resources)
    plan["prompts"].extend({"server": server["name"], "name": p["name"]} for p in server["prompts"])


def assemble_classes(inventory: Payload, overrides: dict[str, list[str]]) -> Payload:
    plan: Payload = {
        "classes": _empty_classes(),
        "servers": [],
        "skills": [],
        "needs_classification": [],
        "excluded_tools": [],
        "declared_read_tools": [],
        "prompts": [],
    }
    for kind, key, skill in (("server", "servers", False), ("skill", "skills", True)):
        for entry in sorted(inventory[key], key=lambda e: e["name"]):
            classes, source = resolve_classes(
                entry["name"], entry["classes"], overrides, skill=skill
            )
            plan[key].append({"name": entry["name"], "classes": classes, "class_source": source})
            if source == "default":
                plan["needs_classification"].append({"kind": kind, "name": entry["name"]})
            if skill:
                for cls in classes:
                    plan["classes"][cls]["skills"].append(entry["name"])
            else:
                _place_server(entry, classes, plan)
    return plan


def connected_classes(plan: Payload) -> list[str]:
    classes = plan["classes"]
    return [c for c in CLASSES if classes[c]["servers"] or classes[c]["skills"]]


def derive_connectivity(classes: dict[str, Payload]) -> tuple[list[str], list[str]]:
    """Return (not_connected, connected_without_read)."""
    connected = [c for c in CLASSES if classes[c]["servers"] or classes[c]["skills"]]
    absent = [c for c in CLASSES if c not in connected and c not in (AGENT, OTHER)]
    no_read = [
        c
        for c in connected
        if not (classes[c]["read_tools"] or classes[c]["skills"] or classes[c]["resources"])
    ]
    return absent, no_read


def hotspot_paths(candidates: Payload) -> list[str]:
    paths: list[str] = []
    for key in ("churn", "todo_hotspots"):
        for row in _lst(candidates.get(key, []), f"candidates.{key}"):
            path = _str(_obj(row, f"candidates.{key} row").get("path"), "hotspot path")
            if path not in paths:
                paths.append(path)
    return paths[:HOTSPOT_CAP]


def judge_digests() -> list[Payload]:
    folder = SKILL_DIR / "judges"
    if not folder.is_dir():
        return []
    return [
        {"name": path.stem, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(folder.glob("*.md"))
    ]


def _window(today: str | None, days: int) -> Payload:
    end = _parse_day(today, "--today") if today else datetime.now(timezone.utc).date()
    return {"start": (end - timedelta(days=days)).isoformat(), "end": end.isoformat()}


def _check_fresh_run_dir(run_dir: Path) -> None:
    if run_dir.exists():
        _need(run_dir.is_dir(), f"--run-dir {run_dir} is not a directory")
        _need(not any(run_dir.iterdir()), f"--run-dir {run_dir} is not empty; use a new run dir")


def plan_examined(plan: Payload) -> Payload:
    classes = plan["classes"]
    return {
        "servers": len(plan["servers"]),
        "skills": len(plan["skills"]),
        "classes_connected": len(connected_classes(plan)),
        "read_tools": len(
            {(t["server"], t["tool"]) for c in classes.values() for t in c["read_tools"]}
        ),
        "excluded_tools": len(plan["excluded_tools"]),
        "declared_read_tools": len(plan["declared_read_tools"]),
        "resources": sum(len(c["resources"]) for c in classes.values()),
        "needs_classification": len(plan["needs_classification"]),
    }


def cmd_plan(args: argparse.Namespace) -> tuple[int, Payload]:
    root = repo_toplevel(Path(args.repo))
    run_dir = ensure_outside(root, Path(args.run_dir), "--run-dir")
    _check_fresh_run_dir(run_dir)
    _need(args.window_days >= 1, "--window-days must be >= 1")
    _need(args.judge_runs >= 2, "--judge-runs must be >= 2")
    inventory = parse_inventory(load_json(Path(args.tools)))
    overrides = parse_overrides(args.class_override or [], inventory)
    hotspots = hotspot_paths(load_json(Path(args.candidates))) if args.candidates else []
    body = assemble_classes(inventory, overrides)
    body["not_connected"], body["connected_without_read"] = derive_connectivity(body["classes"])
    body.update(
        {
            "schema_version": SCHEMA_VERSION,
            "repo": root.as_posix(),
            "window": _window(args.today, args.window_days),
            "judge_runs": args.judge_runs,
            "discovery": inventory["discovery"],
            "query_seeds": {
                "repo_terms": [root.name],
                "hotspots": hotspots,
                "signals": SIGNALS,
            },
            "judges": judge_digests(),
        }
    )
    plan = {**body, "plan_id": digest(body)}
    write_text_atomic(run_dir / "plan.json", dumps(plan))
    return 0, {**plan, "plan_path": str(run_dir / "plan.json"), "examined": plan_examined(plan)}


# ------------------------------------------------------------------ plan and index loading


@dataclass
class Context:
    run_dir: Path
    root: Path
    plan: Payload
    index: Payload


PLAN_KEYS = {
    "schema_version",
    "repo",
    "window",
    "judge_runs",
    "discovery",
    "classes",
    "servers",
    "skills",
    "needs_classification",
    "not_connected",
    "connected_without_read",
    "excluded_tools",
    "declared_read_tools",
    "prompts",
    "query_seeds",
    "judges",
    "plan_id",
}


def _check_plan_shape(plan: Payload) -> None:
    _need(plan["schema_version"] == SCHEMA_VERSION, "unsupported plan schema_version")
    _str(plan["repo"], "plan.repo")
    window = _obj(plan["window"], "plan.window")
    _need(
        _parse_day(window.get("start"), "window.start") <= _parse_day(window.get("end"), "end"),
        "bad window",
    )
    _int(plan["judge_runs"], "plan.judge_runs", 2)
    classes = _obj(plan["classes"], "plan.classes")
    _need(set(classes) == set(CLASSES), "plan.classes must cover every source class")
    for cls in CLASSES:
        entry = _obj(classes[cls], f"plan.classes.{cls}")
        _keys(entry, {"servers", "read_tools", "skills", "resources"}, set(), f"plan.classes.{cls}")
        for key in entry:
            _lst(entry[key], f"plan.classes.{cls}.{key}")
    for key in ("not_connected", "connected_without_read"):
        for cls in _lst(plan[key], f"plan.{key}"):
            _enum(cls, CLASSES, f"plan.{key} entry")
    for judge in _lst(plan["judges"], "plan.judges"):
        _keys(_obj(judge, "plan judge"), {"name", "sha256"}, set(), "plan judge")
        _need(bool(JUDGE_NAME_RE.match(str(judge["name"]))), "plan judge name is unsafe")


def load_plan(path: Path) -> Payload:
    plan = _obj(load_json(path), "plan")
    _keys(plan, PLAN_KEYS, set(), "plan")
    _check_plan_shape(plan)
    body = {key: value for key, value in plan.items() if key != "plan_id"}
    _need(digest(body) == plan["plan_id"], "plan_id does not match the plan content")
    return plan


def verify_judges(plan: Payload) -> None:
    """Exit 2 when a rubric file is missing or changed since `plan`."""
    for judge in plan["judges"]:
        path = SKILL_DIR / "judges" / f"{judge['name']}.md"
        _need(path.is_file(), f"judge rubric {judge['name']} is missing")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        _need(actual == judge["sha256"], f"judge rubric {judge['name']} changed since plan")


def batch_id(index_id: str, number: int, ids: list[str]) -> str:
    seed = f"{index_id}\n{number}\n" + "\n".join(ids)
    return f"b{number:03d}-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def make_batches(index_id: str, items: list[Payload], size: int) -> list[Payload]:
    ids = [item["id"] for item in items]
    chunks = [ids[start : start + size] for start in range(0, len(ids), size)]
    metrics = {item["id"]: item["metrics"] for item in items if item.get("metrics")}
    batches = []
    for number, chunk in enumerate(chunks, start=1):
        batch: Payload = {"batch_id": batch_id(index_id, number, chunk), "items": chunk}
        shown = {item_id: metrics[item_id] for item_id in chunk if item_id in metrics}
        if shown:
            batch["metrics"] = shown
        batches.append(batch)
    return batches


INDEX_KEYS = {
    "schema_version",
    "index_id",
    "plan_id",
    "items",
    "coverage",
    "metric_thresholds",
    "batches",
}
INDEX_ITEM_KEYS = {
    "id",
    "class",
    "server",
    "locator",
    "thread",
    "visibility",
    "date",
    "path",
    "sha256",
    "bytes",
}


def _check_index_shape(index: Payload, plan: Payload) -> None:
    _need(index["schema_version"] == SCHEMA_VERSION, "unsupported index schema_version")
    _need(index["plan_id"] == plan["plan_id"], "index plan_id differs from the plan")
    for item in _lst(index["items"], "index.items"):
        _keys(_obj(item, "index item"), INDEX_ITEM_KEYS, ITEM_OPTIONAL, "index item")
    for row in _lst(index["coverage"], "index.coverage"):
        _obj(row, "index coverage row")
    for key, entry in _obj(index["metric_thresholds"], "index.metric_thresholds").items():
        _need(key in METRIC_NUMERIC, f"index.metric_thresholds has unknown key {key!r}")
        _keys(_obj(entry, "metric threshold"), {"threshold", "items"}, set(), "metric threshold")
    ids = [item["id"] for item in index["items"]]
    flat: list[str] = []
    for number, batch in enumerate(_lst(index["batches"], "index.batches"), start=1):
        _keys(_obj(batch, "index batch"), {"batch_id", "items"}, {"metrics"}, "index batch")
        _need(
            batch["batch_id"] == batch_id(index["index_id"], number, batch["items"]), "bad batch_id"
        )
        flat.extend(batch["items"])
    _need(flat == ids, "index batches do not list the items in order")


def load_index(path: Path, plan: Payload) -> Payload:
    index = _obj(load_json(path), "index")
    _keys(index, INDEX_KEYS, set(), "index")
    body = {
        k: index[k] for k in ("schema_version", "plan_id", "items", "coverage", "metric_thresholds")
    }
    _need(digest(body) == index["index_id"], "index_id does not match the index content")
    _check_index_shape(index, plan)
    return index


def load_context(index_path: str, repo: str | None = None) -> Context:
    path = Path(index_path).resolve()
    run_dir = path.parent
    plan = load_plan(run_dir / "plan.json")
    root = repo_toplevel(Path(repo)) if repo else Path(plan["repo"]).resolve()
    ensure_outside(root, run_dir, "run directory")
    return Context(run_dir, root, plan, load_index(path, plan))


# ------------------------------------------------------------------ evidence files


def locate_file(run_dir: Path, rel: str) -> Path:
    posix = PurePosixPath(rel)
    if (
        posix.is_absolute()
        or PureWindowsPath(rel).drive
        or "\\" in rel
        or ".." in posix.parts
        or any(ord(char) < 32 for char in rel)
    ):
        raise EvidenceError("path must be relative without '..'")
    if not posix.parts or posix.parts[0] != EVIDENCE_DIR:
        raise EvidenceError("path must be under evidence/")
    base = run_dir.resolve()
    evidence_root = (base / EVIDENCE_DIR).resolve()
    target = (base / rel).resolve()
    if not evidence_root.is_relative_to(base) or not target.is_relative_to(evidence_root):
        raise EvidenceError("path resolves outside the evidence directory")
    if not target.is_file():
        raise EvidenceError("file missing")
    return target


def read_evidence(run_dir: Path, rel: str) -> tuple[bytes, str]:
    """Return the raw bytes and decoded text of one evidence file, or raise EvidenceError."""
    target = locate_file(run_dir, rel)
    try:
        if target.stat().st_size > MAX_EVIDENCE_BYTES:
            raise EvidenceError("file is over 64 KiB")
        raw = target.read_bytes()
    except OSError as exc:
        raise EvidenceError("file is unreadable") from exc
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise EvidenceError("file is over 64 KiB")
    try:
        return raw, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError("file is not valid UTF-8") from exc


def sensitive_classes(text: str) -> list[str]:
    return [name for name, pattern in SENSITIVE.items() if pattern.search(text)]


def check_evidence_file(run_dir: Path, rel: str) -> tuple[list[str], str | None, int]:
    try:
        raw, text = read_evidence(run_dir, rel)
    except EvidenceError as exc:
        return [str(exc)], None, 0
    problems = [f"sensitive pattern {name}" for name in sensitive_classes(text)]
    return problems, hashlib.sha256(raw).hexdigest(), len(raw)


# ------------------------------------------------------------------ manifest


COVERAGE_REQUIRED = {"class", "state", "items_read"}
COVERAGE_OPTIONAL = {"reason", "unread", "consent"}
ITEM_REQUIRED = {"id", "class", "server", "locator", "thread", "visibility", "date", "path"}
ITEM_OPTIONAL = {"metrics"}


def _parse_coverage_row(row: Any, index: int) -> Payload:
    what = f"coverage[{index}]"
    obj = _obj(row, what)
    _keys(obj, COVERAGE_REQUIRED, COVERAGE_OPTIONAL, what)
    _enum(obj["class"], CLASSES, f"{what}.class")
    _enum(obj["state"], STATES, f"{what}.state")
    _int(obj["items_read"], f"{what}.items_read")
    for key in ("reason", "unread"):
        _need(isinstance(obj.get(key, ""), str), f"{what}.{key} must be text")
    if "consent" in obj:
        _enum(obj["consent"], CONSENT, f"{what}.consent")
    return obj


def _parse_item(item: Any, index: int) -> Payload:
    what = f"items[{index}]"
    obj = _obj(item, what)
    _keys(obj, ITEM_REQUIRED, ITEM_OPTIONAL, what)
    _need(isinstance(obj.get("metrics", {}), dict), f"{what}.metrics must be an object")
    _need(
        isinstance(obj["id"], str) and len(obj["id"]) <= 64 and bool(ITEM_ID_RE.match(obj["id"])),
        f"{what}.id must be alphanumeric words joined by hyphens, at most 64 characters",
    )
    _enum(obj["class"], CLASSES, f"{what}.class")
    _enum(obj["visibility"], VISIBILITY, f"{what}.visibility")
    _parse_day(obj["date"], f"{what}.date")
    for key in ("server", "path"):
        _str(obj[key], f"{what}.{key}")
    for key in ("locator", "thread"):
        _need(isinstance(obj[key], str), f"{what}.{key} must be text")
    return obj


def parse_manifest(data: Payload, plan: Payload) -> Payload:
    _keys(data, {"schema_version", "plan_id", "coverage", "items"}, set(), "evidence manifest")
    _need(data["schema_version"] == SCHEMA_VERSION, "unsupported manifest schema_version")
    _need(data["plan_id"] == plan["plan_id"], "manifest plan_id differs from the plan")
    coverage = [_parse_coverage_row(r, i) for i, r in enumerate(_lst(data["coverage"], "coverage"))]
    items = [_parse_item(item, i) for i, item in enumerate(_lst(data["items"], "items"))]
    ids = [item["id"] for item in items]
    _need(len(ids) == len(set(ids)), "duplicate evidence item ids")
    return {"coverage": coverage, "items": items}


def coverage_violations(rows: list[Payload], plan: Payload) -> tuple[dict[str, Payload], list[str]]:
    violations: list[str] = []
    by_class: dict[str, Payload] = {}
    for row in rows:
        cls = row["class"]
        if cls in by_class:
            violations.append(f"coverage: duplicate row for class {cls}")
            continue
        by_class[cls] = row
        violations.extend(_row_violations(row))
    for cls in connected_classes(plan):
        if cls not in by_class:
            violations.append(f"coverage: connected class {cls} has no coverage row")
    for cls in plan["connected_without_read"]:
        state = by_class.get(cls, {}).get("state")
        if cls in by_class and state != "unavailable":
            violations.append(f"coverage: class {cls} has no read route; state must be unavailable")
    return by_class, violations


def _row_violations(row: Payload) -> list[str]:
    cls, found = row["class"], []
    if row["state"] != "read" and not row.get("reason", "").strip():
        found.append(f"coverage: class {cls} state {row['state']} needs a reason")
    if row["state"] == "partial" and not row.get("unread", "").strip():
        found.append(f"coverage: class {cls} is partial and needs unread")
    return found


def locator_problem(value: str) -> str | None:
    if not value or any(char.isspace() for char in value):
        return "must be nonempty without whitespace"
    if len(value) > MAX_LOCATOR:
        return f"must be at most {MAX_LOCATOR} characters"
    try:
        netloc = urlsplit(value).netloc
    except ValueError:
        return "is not a parseable URL"
    return "must not carry credentials" if "@" in netloc else None


def metric_violations(metrics: Payload) -> list[str]:
    """Unknown keys and wrong types are violations; values are never judged here."""
    found = []
    for key in sorted(metrics):
        value = metrics[key]
        if key in METRIC_BOOLEAN:
            ok = isinstance(value, bool)
        elif key in METRIC_NUMERIC:
            ok = type(value) in (int, float) and value >= 0
        else:
            found.append(f"metrics.{key} is not an allowed metric")
            continue
        if not ok:
            found.append(f"metrics.{key} has the wrong type or a negative value")
    return found


def item_violations(
    item: Payload, plan: Payload, coverage: dict[str, Payload], window: tuple[date, date]
) -> list[str]:
    found = []
    cls = item["class"]
    entry = plan["classes"][cls]
    if cls not in connected_classes(plan):
        found.append(f"class {cls} is not connected in the plan")
    elif item["server"] not in entry["servers"] + entry["skills"]:
        found.append(f"server is not a server or skill under class {cls}")
    for key in ("locator", "thread"):
        problem = locator_problem(item[key])
        if problem:
            found.append(f"{key} {problem}")
    when = date.fromisoformat(item["date"])
    if not window[0] <= when <= window[1]:
        found.append("date is outside the plan window")
    if item["visibility"] == "private" and coverage.get(cls, {}).get("consent") != "granted":
        found.append(f"private item needs consent granted on class {cls}")
    return found + metric_violations(item.get("metrics", {}))


def validate_manifest(
    manifest: Payload, plan: Payload, run_dir: Path
) -> tuple[list[str], list[Payload], int]:
    coverage, violations = coverage_violations(manifest["coverage"], plan)
    window = (
        date.fromisoformat(plan["window"]["start"]),
        date.fromisoformat(plan["window"]["end"]),
    )
    indexed, total = [], 0
    for item in manifest["items"]:
        problems = item_violations(item, plan, coverage, window)
        file_problems, sha, size = check_evidence_file(run_dir, item["path"])
        violations.extend(f"{item['id']}: {p}" for p in problems + file_problems)
        indexed.append({**item, "sha256": sha, "bytes": size})
        total += size
    return violations, indexed, total


def cmd_index(args: argparse.Namespace) -> tuple[int, Payload]:
    plan_path = Path(args.plan).resolve()
    run_dir = plan_path.parent
    plan = load_plan(plan_path)
    ensure_outside(Path(plan["repo"]).resolve(), run_dir, "run directory")
    _need(args.batch_size >= 1, "--batch-size must be >= 1")
    manifest = parse_manifest(load_json(run_dir / "evidence.json"), plan)
    violations, indexed, total = validate_manifest(manifest, plan, run_dir)
    examined = {"items": len(indexed), "bytes": total, "coverage_rows": len(manifest["coverage"])}
    if violations:
        return 1, {"violations": violations, "examined": examined}
    items = sorted(indexed, key=lambda i: (i["class"], i["date"], i["id"]))
    coverage = sorted(manifest["coverage"], key=lambda r: r["class"])
    body = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan["plan_id"],
        "items": items,
        "coverage": coverage,
        "metric_thresholds": metric_thresholds(items),
    }
    index_id = digest(body)
    batches = make_batches(index_id, items, args.batch_size)
    index = {**body, "index_id": index_id, "batches": batches}
    write_text_atomic(run_dir / "index.json", dumps(index))
    examined["batches"] = len(batches)
    summary = [{"batch_id": b["batch_id"], "items": len(b["items"])} for b in batches]
    return 0, {
        "index_id": index_id,
        "plan_id": plan["plan_id"],
        "index_path": str(run_dir / "index.json"),
        "batches": summary,
        "examined": examined,
    }


# ------------------------------------------------------------------ findings


FINDING_REQUIRED = {
    "finding_id",
    "incident",
    "type",
    "pattern",
    "evidence",
    "summary",
    "people",
    "suggestion",
}
FINDING_OPTIONAL = {"repo_paths", "gap"}


def _text_problem(value: Any, limit: int, name: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return f"{name} must be nonempty text"
    if len(value) > limit:
        return f"{name} exceeds {limit} characters"
    if any(ord(char) < 32 for char in value):
        return f"{name} must be one line"
    if EMAIL_RE.search(value):
        return f"{name} holds an email address"
    return None


def _in_enum(value: Any, allowed: tuple[str, ...], name: str) -> list[str]:
    ok = isinstance(value, str) and value in allowed
    return [] if ok else [f"{name} must be one of {list(allowed)}"]


def _identity_errors(finding: Payload) -> list[str]:
    errors = []
    if not (
        isinstance(finding.get("finding_id"), str) and FINDING_ID_RE.match(finding["finding_id"])
    ):
        errors.append("finding_id must be 1..64 characters of letters, digits, '.', '_', '-'")
    incident = finding.get("incident")
    if not (isinstance(incident, str) and len(incident) <= 80 and KEBAB_RE.match(incident)):
        errors.append("incident must be a kebab-case key of at most 80 characters")
    errors += _in_enum(finding.get("type"), TYPE_ORDER, "type")
    errors += _in_enum(finding.get("pattern"), PATTERNS, "pattern")
    problem = _text_problem(finding.get("summary"), 240, "summary")
    if problem:
        errors.append(problem)
    if not (type(finding.get("people")) is int and finding["people"] >= 1):
        errors.append("people must be an integer >= 1")
    return errors


def _evidence_errors(finding: Payload, batch_ids: set[str]) -> list[str]:
    evidence = finding.get("evidence")
    if not (isinstance(evidence, list) and evidence):
        return ["evidence must be a nonempty list of item ids"]
    errors = []
    if not all(isinstance(e, str) for e in evidence):
        return ["evidence entries must be item ids"]
    if len(set(evidence)) != len(evidence):
        errors.append("evidence lists an id more than once")
    if not set(evidence) <= batch_ids:
        errors.append("evidence cites an id outside the batch")
    return errors


def _repo_path_problem(path: Any) -> str | None:
    if not isinstance(path, str) or not path.strip():
        return "repo_paths entries must be nonempty text"
    posix = PurePosixPath(path)
    unsafe = (
        "\\" in path
        or any(ord(char) < 32 for char in path)
        or posix.is_absolute()
        or bool(PureWindowsPath(path).drive)
        or ".." in posix.parts
    )
    return "repo_paths entries must be relative without '..'" if unsafe else None


def _path_errors(paths: Any) -> list[str]:
    if paths is None:
        return []
    if not isinstance(paths, list):
        return ["repo_paths must be a list"]
    return [p for p in (_repo_path_problem(path) for path in paths) if p]


def _suggestion_errors(suggestion: Any) -> list[str]:
    if not isinstance(suggestion, dict) or set(suggestion) != {"action", "target", "rationale"}:
        return ["suggestion must be an object with action, target, rationale"]
    errors = _in_enum(suggestion["action"], ACTIONS, "suggestion.action")
    for key, limit in (("target", 200), ("rationale", 500)):
        problem = _text_problem(suggestion[key], limit, f"suggestion.{key}")
        if problem:
            errors.append(problem)
    return errors


def _gap_errors(finding: Payload) -> list[str]:
    is_gap = finding.get("type") == "knowledge-gap"
    gap = finding.get("gap")
    if not is_gap:
        return ["gap is only allowed on knowledge-gap findings"] if "gap" in finding else []
    if not isinstance(gap, dict) or set(gap) != {"question", "answer_location", "documented"}:
        return ["knowledge-gap findings need gap {question, answer_location, documented}"]
    errors = _in_enum(gap["answer_location"], ANSWER_LOCATIONS, "gap.answer_location")
    problem = _text_problem(gap["question"], 300, "gap.question")
    if problem:
        errors.append(problem)
    if not isinstance(gap["documented"], bool):
        errors.append("gap.documented must be a boolean")
    return errors


def validate_finding(finding: Any, batch_ids: set[str]) -> list[str]:
    """Return every reason `finding` is invalid; empty means accepted."""
    if not isinstance(finding, dict):
        return ["finding must be an object"]
    missing = sorted(FINDING_REQUIRED - finding.keys())
    unknown = sorted(finding.keys() - FINDING_REQUIRED - FINDING_OPTIONAL)
    if missing or unknown:
        return [f"finding keys: missing {missing}, unknown {unknown}"]
    return (
        _identity_errors(finding)
        + _evidence_errors(finding, batch_ids)
        + _path_errors(finding.get("repo_paths"))
        + _suggestion_errors(finding["suggestion"])
        + _gap_errors(finding)
    )


# ------------------------------------------------------------------ accepted file


ROW_META = ("judge", "run", "batch_id")
ACCEPTED_KEYS = {"schema_version", "index_id", "imported", "rows"}


def triple(entry: Payload) -> tuple[str, int, str]:
    return entry["judge"], entry["run"], entry["batch_id"]


def sort_key(entry: Payload) -> tuple[str, str, int]:
    return entry["judge"], entry["batch_id"], entry["run"]


def rows_digest(findings: list[Payload]) -> str:
    return digest(sorted(findings, key=lambda f: f["finding_id"]))


def _strip_meta(row: Payload) -> Payload:
    return {key: value for key, value in row.items() if key not in ROW_META}


def _check_accepted(accepted: Payload, index: Payload) -> None:
    _need(accepted["schema_version"] == SCHEMA_VERSION, "unsupported accepted schema_version")
    _need(accepted["index_id"] == index["index_id"], "accepted index_id differs from the index")
    seen = set()
    for entry in _lst(accepted["imported"], "accepted.imported"):
        _keys(_obj(entry, "imported entry"), {*ROW_META, "rows_sha256"}, set(), "imported entry")
        _need(triple(entry) not in seen, "duplicate imported entry")
        seen.add(triple(entry))
    grouped: dict[tuple[str, int, str], list[Payload]] = {}
    for row in _lst(accepted["rows"], "accepted.rows"):
        _obj(row, "accepted row")
        _need(all(key in row for key in ROW_META), "accepted row lacks judge, run, batch_id")
        grouped.setdefault(triple(row), []).append(_strip_meta(row))
    _need(set(grouped) <= seen, "accepted rows without an imported entry")
    for entry in accepted["imported"]:
        found = rows_digest(grouped.get(triple(entry), []))
        _need(found == entry["rows_sha256"], "accepted rows do not match rows_sha256")


def load_accepted(path: Path, index: Payload, *, must_exist: bool) -> Payload:
    if not path.exists():
        _need(not must_exist, f"accepted file {path} does not exist")
        return {
            "schema_version": SCHEMA_VERSION,
            "index_id": index["index_id"],
            "imported": [],
            "rows": [],
        }
    accepted = _obj(load_json(path), "accepted file")
    _keys(accepted, ACCEPTED_KEYS, set(), "accepted file")
    _check_accepted(accepted, index)
    return accepted


# ------------------------------------------------------------------ import


ROWS_KEYS = {"schema_version", "index_id", "judge", "run", "batch_id", "findings"}


def parse_rows_doc(data: Payload, index: Payload) -> Payload:
    _keys(data, ROWS_KEYS, set(), "rows file")
    _need(data["schema_version"] == SCHEMA_VERSION, "unsupported rows schema_version")
    _need(data["index_id"] == index["index_id"], "rows index_id differs from the index")
    _need(isinstance(data["judge"], str), "judge must be text")
    _need(type(data["run"]) is int, "run must be an integer")
    _need(isinstance(data["batch_id"], str), "batch_id must be text")
    _lst(data["findings"], "findings")
    return data


def batch_items(index: Payload) -> dict[str, set[str]]:
    return {batch["batch_id"]: set(batch["items"]) for batch in index["batches"]}


def rows_doc_errors(doc: Payload, plan: Payload, index: Payload) -> list[str]:
    errors: list[str] = []
    if doc["judge"] not in {j["name"] for j in plan["judges"]}:
        errors.append("unknown judge")
    if not 1 <= doc["run"] <= plan["judge_runs"]:
        errors.append(f"run must be between 1 and {plan['judge_runs']}")
    batches = batch_items(index)
    if doc["batch_id"] not in batches:
        errors.append("unknown batch_id")
        return errors
    seen: set[str] = set()
    for number, finding in enumerate(doc["findings"]):
        errors.extend(
            f"findings[{number}]: {e}" for e in validate_finding(finding, batches[doc["batch_id"]])
        )
        fid = finding.get("finding_id") if isinstance(finding, dict) else None
        if isinstance(fid, str) and fid in seen:
            errors.append(f"findings[{number}]: duplicate finding_id")
        if isinstance(fid, str):
            seen.add(fid)
    return errors


def merge_import(accepted: Payload, doc: Payload) -> Payload:
    key = (doc["judge"], doc["run"], doc["batch_id"])
    meta = dict(zip(ROW_META, key, strict=True))
    rows = [r for r in accepted["rows"] if triple(r) != key]
    rows.extend({**meta, **finding} for finding in doc["findings"])
    imported = [e for e in accepted["imported"] if triple(e) != key]
    imported.append({**meta, "rows_sha256": rows_digest(doc["findings"])})
    rows.sort(key=lambda r: (*sort_key(r), r["finding_id"]))
    imported.sort(key=sort_key)
    return {**accepted, "rows": rows, "imported": imported}


def cmd_import(args: argparse.Namespace) -> tuple[int, Payload]:
    ctx = load_context(args.index)
    verify_judges(ctx.plan)
    target = ensure_inside(ctx.run_dir, Path(args.accepted), "--accepted")
    doc = parse_rows_doc(load_json(Path(args.rows)), ctx.index)
    errors = rows_doc_errors(doc, ctx.plan, ctx.index)
    examined = {"findings": len(doc["findings"])}
    if errors:
        return 1, {"errors": errors, "examined": examined}
    accepted = load_accepted(target, ctx.index, must_exist=False)
    key = (doc["judge"], doc["run"], doc["batch_id"])
    replaced = sum(1 for row in accepted["rows"] if triple(row) == key)
    merged = merge_import(accepted, doc)
    write_text_atomic(target, dumps(merged))
    examined.update({"rows_total": len(merged["rows"]), "imported_pairs": len(merged["imported"])})
    return 0, {
        "accepted_path": str(target),
        "judge": doc["judge"],
        "run": doc["run"],
        "batch_id": doc["batch_id"],
        "imported": len(doc["findings"]),
        "replaced": replaced,
        "examined": examined,
    }


# ------------------------------------------------------------------ tally


def check_accepted_rows(ctx: Context, accepted: Payload) -> None:
    """Re-validate rows read back from disk; a bad row means a tampered file."""
    batches = batch_items(ctx.index)
    judges = {j["name"] for j in ctx.plan["judges"]}
    for entry in accepted["imported"]:
        _need(entry["judge"] in judges, "accepted file names a judge outside the plan")
        _need(1 <= entry["run"] <= ctx.plan["judge_runs"], "accepted file has a bad run")
        _need(entry["batch_id"] in batches, "accepted file names an unknown batch")
    for row in accepted["rows"]:
        errors = validate_finding(_strip_meta(row), batches[row["batch_id"]])
        _need(
            not errors,
            f"accepted row {row.get('finding_id')} is invalid: {errors[0] if errors else ''}",
        )


def load_aliases(path: str | None, index_id: str, rows: list[Payload]) -> dict[str, str]:
    if not path:
        return {}
    data = _obj(load_json(Path(path)), "aliases file")
    _keys(data, {"schema_version", "index_id", "aliases"}, set(), "aliases file")
    _need(data["schema_version"] == SCHEMA_VERSION, "unsupported aliases schema_version")
    _need(data["index_id"] == index_id, "aliases index_id differs from the index")
    aliases = _obj(data["aliases"], "aliases")
    known = {row["incident"] for row in rows}
    errors = []
    for key, canonical in aliases.items():
        if key not in known:
            errors.append(f"alias {key!r} names no accepted incident")
        if not (isinstance(canonical, str) and KEBAB_RE.match(canonical)):
            errors.append(f"alias {key!r} needs a kebab-case canonical key")
        elif canonical == key or canonical in aliases:
            errors.append(f"alias {key!r} forms a chain or cycle")
    _need(not errors, "; ".join(errors))
    return dict(aliases)


def split_agreed(rows: list[Payload]) -> tuple[list[Payload], list[Payload]]:
    """A finding is agreed when another run of the same judge on the batch matches type and evidence."""
    groups: dict[tuple[str, str], list[Payload]] = {}
    for row in rows:
        groups.setdefault((row["judge"], row["batch_id"]), []).append(row)
    agreed, single = [], []
    for row in rows:
        peers = [o for o in groups[(row["judge"], row["batch_id"])] if o["run"] != row["run"]]
        matched = any(
            o["type"] == row["type"] and set(o["evidence"]) & set(row["evidence"]) for o in peers
        )
        (agreed if matched else single).append(row)
    return agreed, single


class EvidenceTexts:
    """Lazily read cited evidence files, checking each against its indexed digest."""

    def __init__(self, ctx: Context) -> None:
        self._run_dir = ctx.run_dir
        self._items = {item["id"]: item for item in ctx.index["items"]}
        self._cache: dict[str, str] = {}

    def text(self, item_id: str) -> str:
        if item_id not in self._cache:
            item = self._items[item_id]
            try:
                raw, text = read_evidence(self._run_dir, item["path"])
            except EvidenceError as exc:
                raise ConfigError(f"evidence {item_id} cannot be re-read: {exc}") from exc
            _need(
                hashlib.sha256(raw).hexdigest() == item["sha256"],
                f"evidence {item_id} changed since indexing",
            )
            self._cache[item_id] = text
        return self._cache[item_id]


def is_tracked(path: str, tracked: tuple[set[str], set[str]]) -> bool:
    name = PurePosixPath(path).as_posix()
    return name in tracked[0] or name in tracked[1]


def primary_type(types: Counter[str]) -> str:
    return min(types, key=lambda t: (-types[t], TYPE_ORDER.index(t)))


def corroboration(
    evidence: list[str],
    classes: list[str],
    threads: list[str],
    paths: list[str],
    texts: EvidenceTexts,
) -> list[str]:
    reasons = []
    if len(classes) >= 2:
        reasons.append("classes")
    if len(threads) >= 2:
        reasons.append("threads")
    if any(path in texts.text(item) for path in paths for item in evidence):
        reasons.append("repo_path")
    return reasons


def build_incident(
    key: str,
    group: list[Payload],
    items: dict[str, Payload],
    tracked: tuple[set[str], set[str]],
    texts: EvidenceTexts,
) -> Payload:
    evidence = sorted({e for row in group for e in row["evidence"]})
    types = Counter(row["type"] for row in group)
    paths = sorted(
        {
            PurePosixPath(p).as_posix()
            for row in group
            for p in row.get("repo_paths", [])
            if is_tracked(p, tracked)
        }
    )
    classes = sorted({items[e]["class"] for e in evidence})
    threads = sorted({items[e]["thread"] for e in evidence})
    reasons = corroboration(evidence, classes, threads, paths, texts)
    suggestions: dict[tuple[str, str], Payload] = {}
    for row in group:
        suggestion = row["suggestion"]
        suggestions.setdefault((suggestion["action"], suggestion["target"]), suggestion)
    return {
        "incident": key,
        "primary_type": primary_type(types),
        "types": dict(sorted(types.items())),
        "patterns": dict(sorted(Counter(row["pattern"] for row in group).items())),
        "evidence": evidence,
        "locators": sorted({items[e]["locator"] for e in evidence}),
        "threads": threads,
        "classes": classes,
        "judges": sorted({row["judge"] for row in group}),
        "people": max(row["people"] for row in group),
        "repo_paths": paths,
        "corroborated": bool(reasons),
        "corroboration": reasons,
        "suggestions": [suggestions[k] for k in sorted(suggestions)],
        "findings": len(group),
        "summary": group[0]["summary"],
    }


def rank_key(incident: Payload) -> tuple[int, int, int, int, str]:
    return (
        -int(incident["corroborated"]),
        int(incident["primary_type"] != "knowledge-gap"),
        -len(incident["threads"]),
        -len(incident["evidence"]),
        incident["incident"],
    )


def gap_disposition(gaps: list[Payload]) -> str:
    locations = {g["answer_location"] for g in gaps}
    if locations & {"person", "unknown"}:
        return "unresolved"
    if locations <= set(DOCUMENTED_LOCATIONS) and all(g["documented"] for g in gaps):
        return "covered"
    return "document"


def build_gaps(groups: dict[str, list[Payload]]) -> list[Payload]:
    result = []
    for key, group in groups.items():
        gaps = [row["gap"] for row in group if "gap" in row]
        if not gaps:
            continue
        result.append(
            {
                "incident": key,
                "findings": len(gaps),
                "questions": sorted({g["question"] for g in gaps}),
                "answer_locations": sorted({g["answer_location"] for g in gaps}),
                "documented": all(g["documented"] for g in gaps),
                "disposition": gap_disposition(gaps),
            }
        )
    return sorted(result, key=lambda g: (DISPOSITIONS.index(g["disposition"]), g["incident"]))


def coverage_rows(ctx: Context) -> list[Payload]:
    given = {row["class"]: row for row in ctx.index["coverage"]}
    counts = Counter(item["class"] for item in ctx.index["items"])
    missing = {"state": "not_connected", "items_read": 0, "reason": "no server or skill in plan"}
    return [
        {**given.get(cls, {"class": cls, **missing}), "indexed_items": counts.get(cls, 0)}
        for cls in CLASSES
    ]


def find_incomplete(ctx: Context, accepted: Payload) -> list[Payload]:
    done = {triple(entry) for entry in accepted["imported"]}
    runs = range(1, ctx.plan["judge_runs"] + 1)
    missing = [
        {"judge": j["name"], "run": run, "batch_id": b["batch_id"]}
        for j in ctx.plan["judges"]
        for b in ctx.index["batches"]
        for run in runs
        if (j["name"], run, b["batch_id"]) not in done
    ]
    return sorted(missing, key=sort_key)


def nearest_rank_p90(ordered: list[float]) -> float:
    """Nearest-rank 90th percentile of sorted values: index ceil(0.9 * n) - 1."""
    return ordered[-(-9 * len(ordered) // 10) - 1]


def _numeric_metrics(items: list[Payload]) -> dict[str, list[tuple[float, str, str]]]:
    numeric: dict[str, list[tuple[float, str, str]]] = {}
    for item in items:
        for key, value in item.get("metrics", {}).items():
            if key in METRIC_NUMERIC:
                numeric.setdefault(key, []).append((value, item["id"], item["server"]))
    return numeric


def metric_thresholds(items: list[Payload]) -> Payload:
    """Per-key nearest-rank p90 for keys reported by enough items; computed at index time."""
    return {
        key: {"threshold": nearest_rank_p90(sorted(v for v, _, _ in rows)), "items": len(rows)}
        for key, rows in sorted(_numeric_metrics(items).items())
        if len(rows) >= OUTLIER_MIN_ITEMS
    }


def compute_outliers(items: list[Payload], thresholds: Payload) -> tuple[Payload, Payload]:
    """Apply the index's thresholds; returns (outliers, outliers_not_computed)."""
    numeric = _numeric_metrics(items)
    metrics: Payload = {}
    for key, entry in thresholds.items():
        above = [r for r in numeric.get(key, []) if r[0] > entry["threshold"]]
        above.sort(key=lambda r: (-r[0], r[1]))
        metrics[key] = {
            "threshold": entry["threshold"],
            "items": [{"id": i, "server": srv, "value": v} for v, i, srv in above],
        }
    skipped = {k: len(r) for k, r in sorted(numeric.items()) if k not in thresholds}
    flags: dict[str, list[str]] = {}
    for item in items:
        for key, value in item.get("metrics", {}).items():
            if key in METRIC_EXPECTED_TRUE:
                flags.setdefault(key, [])
                if value is False:
                    flags[key].append(item["id"])
    missing = {key: sorted(ids) for key, ids in sorted(flags.items())}
    return {"metrics": metrics, "missing": missing}, skipped


def outlier_ids(outliers: Payload) -> set[str]:
    ids = {row["id"] for entry in outliers["metrics"].values() for row in entry["items"]}
    return ids.union(*outliers["missing"].values()) if outliers["missing"] else ids


def build_friction_map(
    items: list[Payload], incidents: list[Payload], gaps: list[Payload], flagged: set[str]
) -> list[Payload]:
    by_id = {item["id"]: item for item in items}
    gap_keys = {gap["incident"] for gap in gaps}
    systems: dict[str, list[Payload]] = {}
    for item in items:
        systems.setdefault(item["server"], []).append(item)
    rows = []
    for server in sorted(systems):
        cited = [i for i in incidents if any(by_id[e]["server"] == server for e in i["evidence"])]
        patterns = Counter(p for incident in cited for p in incident["patterns"])
        rows.append(
            {
                "server": server,
                "classes": sorted({item["class"] for item in systems[server]}),
                "items": len(systems[server]),
                "incidents": len(cited),
                "patterns": {p: patterns.get(p, 0) for p in PATTERNS},
                "knowledge_gaps": sum(1 for i in cited if i["incident"] in gap_keys),
                "outlier_items": sorted(i["id"] for i in systems[server] if i["id"] in flagged),
                "top_incidents": [i["incident"] for i in cited[:TOP_INCIDENTS]],
            }
        )
    return rows


def build_sweep(ctx: Context, accepted: Payload, aliases: dict[str, str], tracked: Any) -> Payload:
    rows = [{**r, "incident": aliases.get(r["incident"], r["incident"])} for r in accepted["rows"]]
    agreed, single = split_agreed(rows)
    items = {item["id"]: item for item in ctx.index["items"]}
    texts = EvidenceTexts(ctx)
    groups: dict[str, list[Payload]] = {}
    for row in sorted(agreed, key=lambda r: (*sort_key(r), r["finding_id"])):
        groups.setdefault(row["incident"], []).append(row)
    incidents = sorted(
        (build_incident(k, g, items, tracked, texts) for k, g in groups.items()), key=rank_key
    )
    gaps = build_gaps(groups)
    incomplete = find_incomplete(ctx, accepted)
    outliers, not_computed = compute_outliers(ctx.index["items"], ctx.index["metric_thresholds"])
    return {
        "schema_version": SCHEMA_VERSION,
        "index_id": ctx.index["index_id"],
        "plan_id": ctx.plan["plan_id"],
        "coverage": coverage_rows(ctx),
        "incidents": incidents,
        "knowledge_gaps": gaps,
        "incomplete": incomplete,
        "single_reader": [
            {k: r[k] for k in (*ROW_META, "finding_id", "incident")}
            for r in sorted(single, key=lambda r: (*sort_key(r), r["finding_id"]))
        ],
        "pattern_counts": {p: sum(1 for i in incidents if p in i["patterns"]) for p in PATTERNS},
        "friction_map": build_friction_map(
            ctx.index["items"], incidents, gaps, outlier_ids(outliers)
        ),
        "outliers": outliers,
        "outliers_not_computed": not_computed,
        "examined": {
            "items": len(ctx.index["items"]),
            "batches": len(ctx.index["batches"]),
            "findings": len(rows),
            "incidents": len(incidents),
            "corroborated": sum(1 for i in incidents if i["corroborated"]),
        },
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _map_table(sweep: Payload) -> list[str]:
    rows = sweep["friction_map"]
    columns = [p for p in PATTERNS if any(r["patterns"][p] for r in rows)]
    head = ["System", "Classes", "Items", "Incidents", *columns, "Knowledge gaps"]
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    for row in rows:
        cells = [
            _cell(row["server"]),
            ", ".join(row["classes"]),
            str(row["items"]),
            str(row["incidents"]),
            *(str(row["patterns"][p]) for p in columns),
            str(row["knowledge_gaps"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _outlier_lines(sweep: Payload) -> list[str]:
    """One line per metric key, keys sorted; counts and thresholds only."""
    outliers = sweep["outliers"]
    lines = {
        key: f"- `{key}`: threshold {entry['threshold']}, {len(entry['items'])} above"
        for key, entry in outliers["metrics"].items()
    }
    lines.update(
        {key: f"- `{key}`: {len(ids)} missing" for key, ids in outliers["missing"].items()}
    )
    lines.update(
        {
            key: f"- `{key}`: not computed ({n} items)"
            for key, n in sweep["outliers_not_computed"].items()
        }
    )
    return [lines[key] for key in sorted(lines)]


def render_friction_map(sweep: Payload) -> str:
    """Render keys, counts, and enums only; no summary or rationale text."""
    gaps = [
        f"- `{g['incident']}`: {g['disposition']} ({', '.join(g['answer_locations'])})"
        for g in sweep["knowledge_gaps"]
    ]
    conventions = [
        f"- `{i['incident']}`: {', '.join(p for p in i['patterns'] if p in CONVENTION_PATTERNS)}"
        for i in sweep["incidents"]
        if CONVENTION_PATTERNS & i["patterns"].keys()
    ]
    lines = ["# Friction map", "", *_map_table(sweep), "", "## Knowledge gaps", ""]
    lines += [*(gaps or ["- none"]), "", "## Missing conventions", ""]
    lines += [*(conventions or ["- none"]), "", "## Outliers", ""]
    lines += [*(_outlier_lines(sweep) or ["- none"]), "", "## Incomplete", ""]
    lines += [f"{len(sweep['incomplete'])} judge runs not imported", "", "## Single reader", ""]
    lines += [f"{len(sweep['single_reader'])} findings without a matching second run", ""]
    return "\n".join(lines)


CONVENTION_PATTERNS = frozenset({"inconsistent-linking", "work-item-drift"})


def cmd_tally(args: argparse.Namespace) -> tuple[int, Payload]:
    ctx = load_context(args.index, args.repo)
    verify_judges(ctx.plan)
    out = ensure_outside(ctx.root, Path(args.out), "--out") if args.out else None
    _need(out is None or not out.is_dir(), f"--out {out} is a directory")
    target = ensure_inside(ctx.run_dir, Path(args.accepted), "--accepted")
    accepted = load_accepted(target, ctx.index, must_exist=True)
    check_accepted_rows(ctx, accepted)
    aliases = load_aliases(args.aliases, ctx.index["index_id"], accepted["rows"])
    sweep = build_sweep(ctx, accepted, aliases, tracked_paths(ctx.root))
    text = dumps(sweep)
    write_text_atomic(ctx.run_dir / "sweep.json", text)
    write_text_atomic(ctx.run_dir / "friction-map.md", render_friction_map(sweep))
    if out is not None:
        write_text_atomic(out, text)
    return (1 if sweep["incomplete"] else 0), sweep


# ------------------------------------------------------------------ CLI


HELP_EPILOG = """\
examples:
  %(prog)s plan --tools tools.json --repo . --run-dir ~/sweeps/run1
  %(prog)s index --plan ~/sweeps/run1/plan.json
  %(prog)s import --index ~/sweeps/run1/index.json --rows rows.json --accepted ~/sweeps/run1/accepted.json
  %(prog)s tally --index ~/sweeps/run1/index.json --accepted ~/sweeps/run1/accepted.json --repo .

exit codes:
  0  success
  1  validation violation, or tally found judge runs never imported
  2  bad arguments, malformed input, digest mismatch, or a path inside the repository
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        prog="bootstrap_sweep",
        description=(__doc__ or "").split("\n\n")[0],
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan", allow_abbrev=False, help="classify the tool inventory")
    p_plan.add_argument("--tools", required=True, metavar="FILE")
    p_plan.add_argument("--repo", required=True)
    p_plan.add_argument("--run-dir", required=True, metavar="DIR")
    p_plan.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    p_plan.add_argument("--today", metavar="YYYY-MM-DD")
    p_plan.add_argument("--candidates", metavar="FILE")
    p_plan.add_argument("--class-override", action="append", metavar="SERVER=CLASS")
    p_plan.add_argument("--judge-runs", type=int, default=DEFAULT_JUDGE_RUNS)
    p_index = sub.add_parser("index", allow_abbrev=False, help="validate evidence, make batches")
    p_index.add_argument("--plan", required=True, metavar="FILE")
    p_index.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p_import = sub.add_parser("import", allow_abbrev=False, help="accept one judge run's rows")
    p_import.add_argument("--index", required=True, metavar="FILE")
    p_import.add_argument("--rows", required=True, metavar="FILE")
    p_import.add_argument("--accepted", required=True, metavar="FILE")
    p_tally = sub.add_parser("tally", allow_abbrev=False, help="merge findings into a sweep")
    p_tally.add_argument("--index", required=True, metavar="FILE")
    p_tally.add_argument("--accepted", required=True, metavar="FILE")
    p_tally.add_argument("--repo", required=True)
    p_tally.add_argument("--out", metavar="FILE")
    p_tally.add_argument("--aliases", metavar="FILE")
    return parser


HANDLERS = {"plan": cmd_plan, "index": cmd_index, "import": cmd_import, "tally": cmd_tally}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, payload = HANDLERS[args.command](args)
    except ConfigError as exc:
        print(json.dumps({"error": "config", "message": str(exc), "examined": {}}))
        return 2
    except OSError as exc:
        print(json.dumps({"error": "io", "message": str(exc), "examined": {}}))
        return 2
    print(dumps(payload), end="")
    return code


if __name__ == "__main__":
    sys.exit(main())
