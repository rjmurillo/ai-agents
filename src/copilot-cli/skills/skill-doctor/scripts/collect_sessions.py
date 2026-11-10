#!/usr/bin/env python3
"""Collect local agent sessions and skills for scoring, including Copilot CLI.

Scans Claude Code project history, Codex rollout files, Warp's local
conversation databases, Pi agent session JSONL, Grok Build chat history,
and/or ZCode model-io rollouts, discovers installed skills, detects which
sessions used which skills, and emits:

  <out>/inventory.json        - skills, per-session stats, sampling decisions
  <out>/transcripts/<id>.md   - condensed transcripts for sampled sessions

Everything runs locally; nothing is uploaded. Python 3.10+, stdlib only.
Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from io import TextIOWrapper
from pathlib import Path
from typing import Any

from repository_scope import print_scope_roots, resolve_repository_scope
from session_common import (
    CLAUDE_CODE_EDIT_TOOLS,
    CODE_EDIT_HINTS,
    GENERIC_EDIT_TOOLS,
    MAX_MSG_CHARS,
    MAX_TOOL_CHARS,
    MAX_TRANSCRIPT_ENTRIES,
    TRANSCRIPT_HEAD,
    TRANSCRIPT_TAIL,
    TranscriptBuffer,
    assistant_tool_calls,
    collect_diagnostics,
    collection_issue_counts,
    detect_skill_candidates,
    detect_skills_from_entries,
    extract_text,
    iter_jsonl_records,
    looks_injected,
    record_collection_issue,
    render_transcript,
    truncate,
)
from session_databases import (
    MAX_WARP_CONVERSATION_BYTES,
    find_hermes_sessions,
    find_warp_conversations,
    hermes_database_has_sessions,
    load_warp_conversation_data,
    open_warp_database,
    parse_epoch_timestamp,
    parse_hermes_session,
    parse_sqlite_timestamp,
    parse_warp_conversation,
    skill_name_from_reference,
    sqlite_table_columns,
    warp_database_has_sessions,
)
from session_discovery import (
    copilot_session_matches_repos,
    discover_hermes_databases,
    discover_skills,
    find_claude_session_files,
    find_codex_session_files,
    find_copilot_session_files,
    find_grok_session_files,
    find_pi_session_files,
    find_zcode_session_files,
    infer_session_repos,
    parse_collector_args,
    resolve_hermes_home,
    resolve_repo,
    resolve_repos,
    session_cwd_within_repo,
    session_matches_repo,
    session_matches_repos,
    warp_data_roots,
    warp_database_candidates,
)
from session_json import (
    parse_claude_session,
    parse_codex_session,
    parse_copilot_session,
    parse_grok_session,
    parse_pi_session,
    parse_zcode_session,
)

__all__ = [
    "CLAUDE_CODE_EDIT_TOOLS",
    "CODE_EDIT_HINTS",
    "GENERIC_EDIT_TOOLS",
    "MAX_MSG_CHARS",
    "MAX_TOOL_CHARS",
    "MAX_TRANSCRIPT_ENTRIES",
    "MAX_WARP_CONVERSATION_BYTES",
    "TRANSCRIPT_HEAD",
    "TRANSCRIPT_TAIL",
    "TranscriptBuffer",
    "assistant_tool_calls",
    "copilot_session_matches_repos",
    "detect_skill_candidates",
    "detect_skills_from_entries",
    "discover_hermes_databases",
    "discover_skills",
    "discover_warp_databases",
    "extract_text",
    "find_claude_session_files",
    "find_codex_session_files",
    "find_copilot_session_files",
    "find_grok_session_files",
    "find_hermes_sessions",
    "find_pi_session_files",
    "find_warp_conversations",
    "find_zcode_session_files",
    "hermes_database_has_sessions",
    "infer_session_repos",
    "iter_jsonl_records",
    "load_warp_conversation_data",
    "looks_injected",
    "main",
    "open_warp_database",
    "parse_args",
    "parse_claude_session",
    "parse_codex_session",
    "parse_copilot_session",
    "parse_epoch_timestamp",
    "parse_grok_session",
    "parse_hermes_session",
    "parse_pi_session",
    "parse_sqlite_timestamp",
    "parse_warp_conversation",
    "parse_zcode_session",
    "render_transcript",
    "resolve_hermes_home",
    "resolve_repo",
    "resolve_repos",
    "session_cwd_within_repo",
    "session_matches_repo",
    "session_matches_repos",
    "skill_name_from_reference",
    "sqlite_table_columns",
    "truncate",
    "warp_database_has_sessions",
]


def parse_args() -> argparse.Namespace:
    return parse_collector_args(__doc__)


def discover_warp_databases(explicit_paths: Any = (), data_dir: Any = None) -> Any:
    """Keep platform probes at the public collector's monkeypatch boundary."""
    roots = warp_data_roots(data_dir, sys.platform, os.name, os.environ)
    return warp_database_candidates(explicit_paths, roots)


class Collection:
    """Track source counts separately from in-scope and scoreable records."""

    def __init__(self, args: Any, repos: Any, skills: Any) -> None:
        self.args, self.repos, self.skills = args, repos, skills
        self.scope = resolve_repository_scope(repos, not args.no_worktrees)
        self.sessions: list[dict[str, Any]] = []
        self.sources: dict[str, Any] = {}
        self.scanned = 0
        self.in_scope = 0
        self.warp_databases: list[Path] = []

    def add(self, harness: str, parsed: Any, file: str, modified_at: str) -> None:
        if parsed is None:
            return
        meta, stats, entries, skills_used = parsed
        if not self.args.all_conversations and not self.matches(harness, meta):
            return
        self.in_scope += 1
        if stats["assistant_turns"] < 1 or stats["tool_calls"] < 1:
            return
        self.sessions.append(
            {
                "harness": harness,
                "meta": meta,
                "stats": stats,
                "skills_used": skills_used,
                "file": file,
                "modified_at": modified_at,
                "_entries": entries,
            }
        )

    def matches(self, harness: str, meta: Any) -> bool:
        if harness == "copilot":
            return copilot_session_matches_repos(meta, self.scope.paths)
        return session_matches_repos(meta.get("cwd"), self.scope.paths)

    def requested(self, harness: str) -> bool:
        return self.args.harness in ("auto", "all", harness)

    def files(
        self,
        name: str,
        home: Path,
        root: Path,
        finder: Any,
        parser: Any,
        cutoff: datetime,
        error: str,
    ) -> None:
        if not self.requested(name):
            return
        if not root.is_dir():
            if self.args.harness == name:
                _fatal(error)
            return
        paths = finder(home, cutoff)
        self.sources[name] = {"home": str(home), "records_in_window": len(paths)}
        self.scanned += len(paths)
        for mtime, path in paths:
            parsed = parser(path, self.skills.keys(), self.args.include_subagents)
            self.add(name, parsed, str(path), mtime.isoformat())

    def warp(self, cutoff: datetime) -> None:
        if not self.requested("warp"):
            return
        self.warp_databases = discover_warp_databases(self.args.warp_db, self.args.warp_data_dir)
        if not self.warp_databases:
            if self.args.harness == "warp":
                _fatal("no Warp conversation databases found")
            return
        records, scanned = find_warp_conversations(self.warp_databases, cutoff)
        self.sources["warp"] = {
            "databases": [str(path) for path in self.warp_databases],
            "records_in_window": scanned,
            "records_after_channel_deduplication": len(records),
        }
        self.scanned += scanned
        for record in records:
            parsed = parse_warp_conversation(
                record, self.skills.keys(), self.args.include_subagents
            )
            file = f"{record['database']}#agent_conversations/{record['conversation_id']}"
            self.add("warp", parsed, file, record["modified_at"].isoformat())

    def hermes(self, cutoff: datetime) -> None:
        databases = discover_hermes_databases(self.args.hermes_home)
        if not self.requested("hermes"):
            return
        if not databases:
            if self.args.harness == "hermes":
                _fatal(f"Hermes state.db not found under {self.args.hermes_home}")
            return
        records, scanned = find_hermes_sessions(databases, cutoff)
        self.sources["hermes"] = {
            "home": str(databases[0].parent),
            "records_in_window": len(records),
        }
        self.scanned += scanned
        for database, row in records:
            try:
                connection = open_warp_database(database)
                try:
                    parsed = parse_hermes_session(
                        connection, row, self.skills.keys(), self.args.include_subagents
                    )
                finally:
                    connection.close()
            except (OSError, sqlite3.Error):
                record_collection_issue("database_failures")
                continue
            if parsed is not None:
                self.add("hermes", parsed, str(database), parsed[0]["timestamp"])


def _fatal(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def _collect(collection: Collection, homes: Any, cutoff: datetime) -> None:
    args = collection.args

    def claude_finder(home: Path, when: datetime) -> Any:
        return find_claude_session_files(home, when, args.include_subagents)

    specs = (
        (
            "copilot",
            "session-state",
            find_copilot_session_files,
            parse_copilot_session,
            "Copilot session history not found at",
        ),
        (
            "claude",
            "projects",
            claude_finder,
            parse_claude_session,
            "Claude Code project history not found at",
        ),
        ("codex", "", find_codex_session_files, parse_codex_session, "Codex home not found at"),
        ("pi", "sessions", find_pi_session_files, parse_pi_session, "Pi session home not found at"),
        (
            "grok",
            "sessions",
            find_grok_session_files,
            parse_grok_session,
            "Grok Build session home not found at",
        ),
        (
            "zcode",
            "cli/rollout",
            find_zcode_session_files,
            parse_zcode_session,
            "ZCode model-io rollouts not found at",
        ),
    )
    for name, subdir, finder, parser, message in specs:
        if name == "pi":
            collection.warp(cutoff)
        home = homes[name]
        root = home / subdir if subdir else home
        collection.files(name, home, root, finder, parser, cutoff, f"{message} {root}")
    collection.hermes(cutoff)


def _discover(args: Any, repos: Any, homes: Any) -> Any:
    return discover_skills(
        repos,
        homes["codex"],
        args.skills_dir,
        args.include_global_skills,
        pi_home=homes["pi"],
        grok_home=homes["grok"],
        zcode_home=homes["zcode"],
        hermes_home=homes["hermes"],
        copilot_home=homes["copilot"],
        claude_home=homes["claude"],
    )


def _sample(sessions: Any, skills: Any, args: Any) -> set[str]:
    sampled: set[str] = set()
    counts = dict.fromkeys(skills, 0)
    for session in sessions:
        if len(sampled) >= args.max_sessions:
            break
        used = session["skills_used"]
        if any(counts.get(name, 0) < args.per_skill for name in used):
            sampled.add(session["_key"])
            # Count every skill the session used, so a multi-skill session fills each quota.
            for name in used:
                counts[name] = counts.get(name, 0) + 1
    no_skill = 0
    for session in sessions:
        if len(sampled) >= args.max_sessions or no_skill >= args.no_skill:
            break
        if not session["skills_used"] and session["_key"] not in sampled:
            sampled.add(session["_key"])
            no_skill += 1
    return sampled


def _write_transcripts(sessions: Any, sampled: set[str], directory: Path) -> None:
    for session in sessions:
        session["sampled"] = session["_key"] in sampled
        if session["sampled"]:
            path = directory / f"{session['harness']}-{session['meta']['id']}.md"
            path.write_text(
                render_transcript(
                    session["meta"], session["stats"], session["skills_used"], session["_entries"]
                ),
                encoding="utf-8",
            )
            session["transcript_path"] = str(path)
        del session["_entries"]
        del session["_key"]


def _inventory(collection: Collection, homes: Any, sampled: set[str]) -> Any:
    args, repos, skills = collection.args, collection.repos, collection.skills
    usage = dict.fromkeys(skills, 0)
    for session in collection.sessions:
        for name in session["skills_used"]:
            usage[name] += 1
    scope_name = repos[0].name if len(repos) == 1 else "multiple-projects"
    if args.all_conversations:
        scope_name = "all-conversations"
    inventory = {
        "collection_issues": collection_issue_counts(),
        "collection_status": "partial" if collection_issue_counts() else "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "harness": next(iter(collection.sources)) if len(collection.sources) == 1 else "mixed",
        "sources": collection.sources,
        "warp_databases": [str(path) for path in collection.warp_databases],
        "conversation_scope": "all" if args.all_conversations else "projects",
        "repo": str(repos[0]) if len(repos) == 1 else None,
        "repos": [str(repo) for repo in repos],
        "repo_name": scope_name,
        "repo_names": [repo.name for repo in repos],
        "scope_resolution": collection.scope.report(collection.sessions),
        "window_days": args.days,
        "skills": sorted(skills.values(), key=lambda skill: skill["name"]),
        "skill_usage": usage,
        "stats": {
            "session_files_in_window": collection.scanned,
            "session_records_in_window": collection.scanned,
            "sessions_in_repo": collection.in_scope,
            "sessions_in_scope": collection.in_scope,
            "sessions_considered": len(collection.sessions),
            "sessions_sampled": len(sampled),
            "skills_found": len(skills),
            "skills_used": sum(1 for count in usage.values() if count > 0),
        },
        "sessions": collection.sessions,
    }
    inventory.update(
        {
            f"{name}_home": str(home) if name in collection.sources else None
            for name, home in homes.items()
        }
    )
    return inventory


def _print_summary(inventory: Any, args: Any, repos: Any, out: Path) -> None:
    if inventory["collection_issues"]:
        issues = ", ".join(
            f"{key}={value}" for key, value in inventory["collection_issues"].items()
        )
        print(f"warning: partial collection: {issues}", file=sys.stderr)
    stats = inventory["stats"]
    scope = (
        "all conversations" if args.all_conversations else ", ".join(str(repo) for repo in repos)
    )
    print(f"scope:             {scope}")
    print_scope_roots(inventory["scope_resolution"])
    print(f"sources:           {', '.join(inventory['sources'])}")
    print(f"skills found:      {stats['skills_found']} ({stats['skills_used']} used in window)")
    print(
        f"sessions in window: {stats['session_records_in_window']} records, "
        f"{stats['sessions_in_scope']} in scope, {stats['sessions_considered']} scoreable"
    )
    print(f"sessions sampled:  {stats['sessions_sampled']} -> {out / 'transcripts'}")
    print(f"inventory:         {out / 'inventory.json'}")


def _run() -> None:
    args = parse_args()
    if args.all_conversations and args.repo:
        print("error: --all-conversations cannot be combined with --repo", file=sys.stderr)
        sys.exit(2)
    homes = {
        name: Path(getattr(args, f"{name}_home")).expanduser()
        for name in ("claude", "codex", "copilot", "pi", "grok", "zcode")
    }
    homes["hermes"] = resolve_hermes_home(args.hermes_home)
    out = Path(args.out).expanduser()
    (out / "transcripts").mkdir(parents=True, exist_ok=True)
    repos = [] if args.all_conversations else resolve_repos(args.repo)
    collection = Collection(args, repos, _discover(args, repos, homes))
    _collect(collection, homes, datetime.now(timezone.utc) - timedelta(days=args.days))
    if not collection.sources:
        _fatal(
            "no supported session source found "
            "(Copilot, Claude Code, Codex, Warp, Pi, Grok, ZCode, or Hermes)"
        )
    if args.all_conversations:
        collection.repos = infer_session_repos(collection.sessions)
        collection.skills = _discover(args, collection.repos, homes)
    installed = set(collection.skills)
    for session in collection.sessions:
        detected = detect_skills_from_entries(session["_entries"], installed)
        session["skills_used"] = sorted((set(session["skills_used"]) | set(detected)) & installed)
        session["_key"] = f"{session['harness']}:{session['meta']['id']}"
    collection.sessions.sort(key=lambda session: session["modified_at"], reverse=True)
    sampled = _sample(collection.sessions, collection.skills, args)
    _write_transcripts(collection.sessions, sampled, out / "transcripts")
    inventory = _inventory(collection, homes, sampled)
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    _print_summary(inventory, args, collection.repos, out)


def main() -> None:
    with collect_diagnostics():
        _run()


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    main()
