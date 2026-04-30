#!/usr/bin/env python3
"""Synchronize session documentation by scanning git history and generating reports.

Collects session activity from git history, identifies agents invoked, files
changed, and decisions made, then generates a structured Markdown session sync
report with a Mermaid workflow diagram.

Supports the /9-sync command for auto-documentation integration.

Usage:
    python sync_session_documentation.py [--session-number N] [--lookback-hours 8]
                                         [--output-path PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

MCP_HISTORY_ENV = "AGENTS_HISTORY_JSON"
SERENA_MEMORY_DIR = ".serena/memories"


KNOWN_AGENTS = [
    "orchestrator", "planner", "implementer", "qa", "security",
    "architect", "critic", "devops", "analyst", "explainer",
    "task-generator", "retrospective", "memory", "skillbook",
    "context-retrieval", "high-level-advisor", "independent-thinker",
    "roadmap", "merge-resolver",
]

AGENT_ABBREV = {
    "orchestrator": "O", "planner": "P", "implementer": "I",
    "qa": "Q", "security": "S", "architect": "A", "critic": "C",
    "devops": "D", "analyst": "An", "explainer": "E",
    "retrospective": "R", "memory": "M", "merge-resolver": "MR",
    "high-level-advisor": "HLA", "independent-thinker": "IT", "roadmap": "RM",
}


def _run_git(*args: str) -> list[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def get_repo_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: Not inside a git repository.", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_recent_commits(hours: int) -> list[dict]:
    since = (datetime.now(UTC) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    lines = _run_git("log", f"--since={since}", "--format=%H%x1f%s%x1f%an%x1f%ai")

    commits = []
    for line in lines:
        parts = line.split("\x1f", 3)
        if len(parts) >= 2:
            commits.append({
                "Hash": parts[0][:8],
                "Message": parts[1],
                "Author": parts[2] if len(parts) >= 3 else "unknown",
                "Date": parts[3] if len(parts) >= 4 else "",
            })
    return commits


def get_agents_from_commits(commits: list[dict]) -> list[str]:
    found: list[str] = []

    for commit in commits:
        msg = commit["Message"].lower()
        for agent in KNOWN_AGENTS:
            if re.search(re.escape(agent), msg) and agent not in found:
                found.append(agent)

    # Infer from conventional commit prefixes
    for commit in commits:
        msg = commit["Message"].lower()
        if msg.startswith("feat") and "implementer" not in found:
            found.append("implementer")
        if msg.startswith("fix") and "implementer" not in found:
            found.append("implementer")
        if msg.startswith("test") and "qa" not in found:
            found.append("qa")
        if msg.startswith("docs") and "explainer" not in found:
            found.append("explainer")
        if msg.startswith("ci") and "devops" not in found:
            found.append("devops")
        if re.search(r"security|cwe|owasp", msg) and "security" not in found:
            found.append("security")

    return found


def get_decisions(commits: list[dict]) -> list[str]:
    decisions = []
    for commit in commits:
        msg = commit["Message"]
        if re.search(r"ADR-\d+", msg):
            decisions.append(f"ADR reference: {msg}")
        if re.search(r"(?i)(decision|chose|selected|adopted|switched to|migrated)", msg):
            decisions.append(f"Design: {msg}")
    return decisions


def get_artifacts(hours: int) -> list[dict]:
    since = (datetime.now(UTC) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    added = _run_git("log", f"--since={since}", "--diff-filter=A", "--name-only", "--format=")
    modified = _run_git("log", f"--since={since}", "--diff-filter=M", "--name-only", "--format=")

    artifacts: list[dict] = []
    seen: set[str] = set()

    for f in added:
        if f not in seen:
            artifacts.append({"File": f, "Status": "new"})
            seen.add(f)

    for f in modified:
        if f not in seen:
            artifacts.append({"File": f, "Status": "modified"})
            seen.add(f)

    return artifacts


def generate_mermaid_diagram(agents: list[str]) -> str:
    lines = ["```mermaid", "sequenceDiagram", "    participant U as User"]

    for agent in agents:
        abbr = AGENT_ABBREV.get(agent, agent[:3].upper())
        lines.append(f"    participant {abbr} as {agent}")

    if agents:
        first = AGENT_ABBREV.get(agents[0], agents[0][:3].upper())
        lines.append(f"    U->>{first}: Initiate workflow")

        for i in range(len(agents) - 1):
            curr = AGENT_ABBREV.get(agents[i], agents[i][:3].upper())
            nxt = AGENT_ABBREV.get(agents[i + 1], agents[i + 1][:3].upper())
            lines.append(f"    {curr}->>{nxt}: Handoff")

        last = AGENT_ABBREV.get(agents[-1], agents[-1][:3].upper())
        lines.append(f"    {last}->>U: Results")

    lines.append("```")
    return "\n".join(lines)


def get_retrospective_suggestions(
    commits: list[dict], agents: list[str], artifacts: list[dict]
) -> list[str]:
    suggestions = []

    if len(commits) > 15:
        suggestions.append(
            f"Consider squashing related commits — {len(commits)} commits "
            "may indicate overly granular work"
        )
    if agents and "qa" not in agents:
        suggestions.append(
            "No QA agent was invoked during this session — "
            "consider running /3-qa before completion"
        )
    script_changes = [a for a in artifacts if re.search(r"\.(ps1|py|sh|bash)$", a["File"])]
    if script_changes and "security" not in agents:
        suggestions.append(
            "Script files were modified without security review — "
            "consider running /4-security"
        )
    adr_changes = [
        a for a in artifacts if re.search(r"ADR-\d+", a["File"]) and a["Status"] == "new"
    ]
    if adr_changes and "critic" not in agents:
        suggestions.append(
            "New ADR created without critic review — "
            "consider architect/critic consensus"
        )
    if not suggestions:
        suggestions.append(
            "Session followed standard patterns — no specific improvements identified"
        )
    return suggestions


def build_report(
    *,
    date: str,
    session_label: str,
    branch: str,
    lookback_hours: int,
    commits: list[dict],
    agents: list[str],
    decisions: list[str],
    artifacts: list[dict],
    diagram: str,
    learnings: list[str],
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"## Session Sync Report — {date} {session_label}\n",
        f"**Branch**: `{branch}`",
        f"**Commits**: {len(commits)} in last {lookback_hours} hours",
        f"**Generated**: {now}\n",
        "### Workflow Diagram\n",
        diagram,
        "\n### Agents Invoked\n",
    ]

    if agents:
        for i, agent in enumerate(agents, 1):
            parts.append(f"{i}. {agent}")
    else:
        parts.append("_No agents detected from commit history._")

    parts.append("\n### Recent Commits\n")
    parts.append("| Hash | Message |")
    parts.append("|------|---------|")
    for commit in commits[:20]:
        escaped = commit["Message"].replace("|", "\\|")
        parts.append(f"| `{commit['Hash']}` | {escaped} |")

    parts.append("\n### Decisions Made\n")
    if decisions:
        for d in decisions:
            parts.append(f"- {d}")
    else:
        parts.append("_No explicit decisions detected from commit messages._")

    parts.append("\n### Artifacts Created/Modified\n")
    parts.append("| File | Status |")
    parts.append("|------|--------|")
    if artifacts:
        for a in artifacts[:30]:
            parts.append(f"| `{a['File']}` | {a['Status']} |")
    else:
        parts.append("| _(none detected)_ | — |")

    parts.append("\n### Retrospective Learnings\n")
    for learning in learnings:
        parts.append(f"- {learning}")

    parts.append("\n---")
    parts.append("_Generated by /9-sync (sync_session_documentation.py)_")

    return "\n".join(parts) + "\n"


def validate_output_path(output_path: str, repo_root: str) -> str:
    """Validate output path is within the repository root (CWE-22 prevention)."""
    allowed_dir = os.path.realpath(repo_root)
    resolved_path = os.path.realpath(output_path)
    if not resolved_path.startswith(allowed_dir + os.sep):
        raise ValueError(
            f"Path traversal attempt detected. Output path '{output_path}' "
            "is outside the repository root."
        )
    return resolved_path


def query_agents_history(lookback_hours: int) -> list[dict] | None:
    """Query agents://history MCP resource for session invocations.

    Returns list of history entries, or None if MCP is unavailable.
    Falls back gracefully to allow git-based history collection.
    """
    # Check for MCP-provided history via environment variable
    env_json = os.environ.get(MCP_HISTORY_ENV)
    if env_json:
        try:
            data = json.loads(env_json)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    # Try reading from MCP cache file if available
    mcp_cache = os.path.join(".agents", "mcp-cache", "history.json")
    if os.path.isfile(mcp_cache):
        try:
            with open(mcp_cache, encoding="utf-8") as f:
                data = json.loads(f.read())
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    # MCP not available — caller should fall back to git history
    return None


def sync_serena_memory(
    repo_root: str,
    *,
    agents: list[str],
    decisions: list[str],
    learnings: list[str],
    branch: str,
    date: str,
) -> bool:
    """Sync session context to Serena memory for cross-session persistence.

    Writes a memory file to .serena/memories/ so future sessions can recall
    what happened. Returns True if memory was written successfully.
    """
    memory_dir = os.path.join(repo_root, SERENA_MEMORY_DIR)
    if not os.path.isdir(memory_dir):
        # Serena not configured — skip gracefully
        return False

    memory_name = f"session-sync-{date}"
    memory_path = os.path.join(memory_dir, f"{memory_name}.md")

    content_parts = [
        f"# Session Sync Memory — {date}",
        f"\n**Branch**: `{branch}`",
        f"**Agents**: {', '.join(agents) if agents else 'none detected'}",
        "\n## Decisions",
    ]
    if decisions:
        for d in decisions:
            content_parts.append(f"- {d}")
    else:
        content_parts.append("_No explicit decisions._")

    content_parts.append("\n## Learnings")
    for learning in learnings:
        content_parts.append(f"- {learning}")

    content_parts.append(
        f"\n---\n_Auto-synced by /9-sync on {date}_\n"
    )

    try:
        Path(memory_path).write_text("\n".join(content_parts), encoding="utf-8")
        return True
    except OSError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate session sync documentation"
    )
    parser.add_argument("--session-number", type=int, default=0)
    parser.add_argument("--lookback-hours", type=int, default=8)
    parser.add_argument("--output-path", type=str, default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = get_repo_root()
    branch_result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

    print("\u001b[36m🔄 /9-sync: Generating session documentation...\u001b[0m")
    print(f"  Branch: {current_branch}")
    print(f"  Lookback: {args.lookback_hours} hours")

    # Query agents://history MCP resource first, fall back to git
    mcp_history = query_agents_history(args.lookback_hours)
    if mcp_history is not None:
        print("  Source: agents://history (MCP)")
        # Extract agent names from MCP history entries
        mcp_agents = [
            entry.get("agent", "") for entry in mcp_history if entry.get("agent")
        ]
    else:
        print("  Source: git history (MCP unavailable)")
        mcp_agents = []

    commits = get_recent_commits(args.lookback_hours)
    agents = get_agents_from_commits(commits)
    # Merge MCP-detected agents (preserving order, no duplicates)
    for agent in mcp_agents:
        if agent not in agents:
            agents.append(agent)
    decisions = get_decisions(commits)
    artifacts = get_artifacts(args.lookback_hours)
    diagram = generate_mermaid_diagram(agents)
    learnings = get_retrospective_suggestions(commits, agents, artifacts)

    date = datetime.now().strftime("%Y-%m-%d")
    session_label = f"Session {args.session_number}" if args.session_number > 0 else "Session"

    report = build_report(
        date=date,
        session_label=session_label,
        branch=current_branch,
        lookback_hours=args.lookback_hours,
        commits=commits,
        agents=agents,
        decisions=decisions,
        artifacts=artifacts,
        diagram=diagram,
        learnings=learnings,
    )

    if args.dry_run:
        print("\n\u001b[33m📋 DRY RUN — Report preview:\u001b[0m\n")
        print(report)
        print("\u001b[32m✅ Dry run complete. No files written.\u001b[0m")
        output_path = None
    else:
        output_path = args.output_path
        if not output_path:
            sessions_dir = os.path.join(repo_root, ".agents", "sessions")
            os.makedirs(sessions_dir, exist_ok=True)
            slug = f"session-{args.session_number}" if args.session_number > 0 else "session"
            output_path = os.path.join(sessions_dir, f"{date}-{slug}-sync.md")

        resolved = validate_output_path(output_path, repo_root)
        Path(resolved).write_text(report, encoding="utf-8")
        print(f"\n\u001b[32m✅ Session sync report written to: {resolved}\u001b[0m")
        print(f"  Commits: {len(commits)}")
        print(f"  Agents detected: {len(agents)}")
        print(f"  Artifacts: {len(artifacts)}")
        print(f"  Learnings: {len(learnings)}")

        # Sync to Serena memory for cross-session persistence
        synced = sync_serena_memory(
            repo_root,
            agents=agents,
            decisions=decisions,
            learnings=learnings,
            branch=current_branch,
            date=date,
        )
        if synced:
            print("  Memory: synced to Serena")
        else:
            print("  Memory: Serena unavailable (manual sync needed)")

    # Structured JSON output
    json_output = json.dumps(
        {
            "date": date,
            "branch": current_branch,
            "commits": len(commits),
            "agents": agents,
            "artifacts": len(artifacts),
            "decisions": len(decisions),
            "learnings": learnings,
            "outputPath": output_path,
        },
        indent=2,
    )
    print("\n\u001b[36m📊 Structured Output:\u001b[0m")
    print(json_output)


if __name__ == "__main__":
    main()
