#!/usr/bin/env python3
"""
Memory system health dashboard.

Produces a summary report of memory system metrics:
- Total file count and aggregate size
- Size distribution (pass/warn/fail thresholds)
- Token cost estimates
- Age distribution
- Index coverage

Exit codes per ADR-035:
  0 - Success (report generated)
  1 - Error (path not found)
"""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Thresholds from memory-size-001-decomposition-thresholds
MAX_CHARS = 10_000
WARN_CHARS = 8_000
STALE_DAYS = 180


def get_git_age_days(file_path: Path) -> int | None:
    """Get days since last git modification."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"Warning: git log failed for {file_path.name}: {result.stderr.strip()}", file=sys.stderr)
            return None
        if result.stdout.strip():
            mod_date = datetime.fromisoformat(result.stdout.strip())
            return (datetime.now(UTC) - mod_date).days
    except ValueError as e:
        print(f"Warning: invalid git date for {file_path.name}: {e}", file=sys.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def main() -> int:
    # Auto-detect repo root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print("Error: not in a git repository", file=sys.stderr)
            return 1
        repo_root = Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Error: git not available", file=sys.stderr)
        return 1

    memories_dir = repo_root / ".serena" / "memories"
    if not memories_dir.exists():
        print(f"Error: {memories_dir} not found", file=sys.stderr)
        return 1

    # Collect metrics
    files = sorted(f for f in memories_dir.glob("*.md") if f.name != "README.md")
    total = len(files)

    if total == 0:
        print("No memory files found", file=sys.stderr)
        return 1

    sizes = []
    ages = []
    pass_count = 0
    warn_count = 0
    fail_count = 0
    index_count = 0
    total_chars = 0

    skipped = 0
    for f in files:
        try:
            char_count = len(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            print(f"Warning: Failed to read {f.name}: {e}", file=sys.stderr)
            skipped += 1
            continue
        sizes.append(char_count)
        total_chars += char_count

        if char_count <= WARN_CHARS:
            pass_count += 1
        elif char_count <= MAX_CHARS:
            warn_count += 1
        else:
            fail_count += 1

        if f.name.endswith("-index.md"):
            index_count += 1

        age = get_git_age_days(f)
        if age is not None:
            ages.append(age)

    if skipped:
        print(f"Warning: {skipped} file(s) skipped due to read errors", file=sys.stderr)

    # Calculate statistics (adjust total for skipped files)
    counted = total - skipped
    avg_size = total_chars // counted if counted > 0 else 0
    median_size = sorted(sizes)[counted // 2] if counted > 0 else 0
    max_size = max(sizes) if sizes else 0
    est_tokens = total_chars // 4  # rough estimate

    avg_age = sum(ages) // len(ages) if ages else 0
    stale_count = sum(1 for a in ages if a > STALE_DAYS)

    compliance_pct = (pass_count * 100) // counted if counted > 0 else 0

    # Output report
    now = datetime.now(UTC)
    print("# Memory Health Dashboard")
    print()
    print(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    print("## Overview")
    print()
    print("| Metric | Value |")
    print("|--------|-------|")
    print(f"| Total memories | {total} |")
    print(f"| Index files | {index_count} |")
    print(f"| Total characters | {total_chars:,} |")
    print(f"| Estimated tokens | ~{est_tokens:,} |")
    print()
    print("## Size Distribution")
    print()
    print("| Category | Count | % |")
    print("|----------|-------|---|")
    print(f"| Pass (<{WARN_CHARS:,} chars) | {pass_count} | {pass_count * 100 // counted if counted else 0}% |")
    warn_pct = warn_count * 100 // counted if counted else 0
    print(f"| Warn ({WARN_CHARS:,}-{MAX_CHARS:,}) | {warn_count} | {warn_pct}% |")
    print(f"| Fail (>{MAX_CHARS:,} chars) | {fail_count} | {fail_count * 100 // counted if counted else 0}% |")
    print()
    print(f"**Size compliance**: {compliance_pct}%")
    print()
    print("| Stat | Chars |")
    print("|------|-------|")
    print(f"| Average | {avg_size:,} |")
    print(f"| Median | {median_size:,} |")
    print(f"| Maximum | {max_size:,} |")
    print()
    print("## Age Distribution")
    print()
    print("| Metric | Value |")
    print("|--------|-------|")
    print(f"| Average age | {avg_age} days |")
    print(f"| Stale (>{STALE_DAYS} days) | {stale_count} |")
    print(f"| Files with git history | {len(ages)}/{total} |")

    return 0


if __name__ == "__main__":
    sys.exit(main())
