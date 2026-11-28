"""Console summary for the skill-doctor collector.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from repository_scope import print_scope_roots
from session_threads import print_thread_summary


def print_summary(inventory: Any, args: Any, repos: Any, out: Path) -> None:
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
    print_thread_summary(inventory)
    if inventory["sampling"]["notice"]:
        print(f"warning: {inventory['sampling']['notice']}", file=sys.stderr)
    print(f"inventory:         {out / 'inventory.json'}")
