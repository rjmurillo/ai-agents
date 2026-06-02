"""Regression simulation for ADR Part B (Issue #2252).

Compares 4 Check-1 stripping policies against 40 merged PRs from the
last 30 days:
  baseline  - current default (all 4 patterns, anywhere not stripped)
  strict    - only bullet-list pattern[2] inside ## Per-file changes /
              ## Files Changed / ## Changes
  permissive- all 4 patterns, but only inside change-claim sections
  hybrid    - patterns 1 (inline-backtick) and 3 (markdown-link) require
              change-claim section context; patterns 0 (bold) and 2
              (bullet-list) fire anywhere

Prints per-PR removed CRITICAL counts and totals.
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

sys.path.insert(0, "/home/richard/.hermes/kanban/boards/ai-agents/workspaces/t_7805f181/ai-agents")
from scripts.validation.pr_description import (
    _strip_informational_sections,
    FILE_MENTION_PATTERNS,
    normalize_path,
    file_matches,
)

CHANGE_CLAIM_SECTION_PATTERN = re.compile(
    r"^##\s+(?:Per[- \t]?file[ \t]+changes|Files[ \t]+Changed|Changes|Changed[ \t]+files)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

def _split_change_claim_regions(cleaned: str) -> list[tuple[int,int]]:
    """Return list of (start,end) char spans that are inside a change-claim H2 section."""
    headings = [(m.start(), m.end()) for m in CHANGE_CLAIM_SECTION_PATTERN.finditer(cleaned)]
    if not headings:
        return []
    regions = []
    # Find any H1/H2 to terminate each region
    boundary = re.compile(r"^#{1,2}(?!#)", re.MULTILINE)
    for h_start, h_end in headings:
        # next H1/H2 after this heading line
        next_h = None
        for m in boundary.finditer(cleaned, pos=h_end):
            next_h = m.start()
            break
        end = next_h if next_h is not None else len(cleaned)
        regions.append((h_end, end))
    return regions

def _in_regions(pos: int, regions: list[tuple[int,int]]) -> bool:
    for s,e in regions:
        if s <= pos < e:
            return True
    return False

def extract_under_policy(description: str, policy: str) -> list[str]:
    if not description:
        return []
    cleaned = _strip_informational_sections(description)
    regions = _split_change_claim_regions(cleaned)
    mentioned: list[str] = []
    for idx, pattern in enumerate(FILE_MENTION_PATTERNS):
        for match in pattern.finditer(cleaned):
            raw = match.group(1)
            if " " in raw.strip():
                continue
            in_cc = _in_regions(match.start(), regions)
            if policy == "baseline":
                ok = True
            elif policy == "strict":
                ok = (idx == 2) and in_cc
            elif policy == "permissive":
                ok = in_cc
            elif policy == "hybrid":
                # pattern 1 (bold) and 2 (bullet-list) fire anywhere;
                # pattern 0 (inline-backtick) and 3 (markdown-link) require context
                if idx in (1, 2):
                    ok = True
                else:
                    ok = in_cc
            else:
                raise ValueError(policy)
            if ok:
                mentioned.append(normalize_path(raw))
    seen=set(); out=[]
    for p in mentioned:
        if p not in seen:
            seen.add(p); out.append(p)
    return out

def critical_files(mentioned: list[str], actual: list[str]) -> list[str]:
    out=[]
    for m in mentioned:
        if not any(file_matches(a, m) for a in actual):
            out.append(m)
    return out

POLICIES = ["baseline","strict","permissive","hybrid"]

def main():
    pr_nums = [int(x) for x in open("/tmp/sample_prs.txt") if x.strip()]
    totals = {p:0 for p in POLICIES}
    rows = []
    removed_per_pr = {p:{} for p in POLICIES}
    for n in pr_nums:
        body_path = f"/tmp/pr_bodies/{n}.md"
        files_path = f"/tmp/pr_files/{n}.txt"
        if not os.path.exists(body_path):
            continue
        body = open(body_path).read()
        actual = [x.strip() for x in open(files_path) if x.strip()]
        results = {}
        for pol in POLICIES:
            m = extract_under_policy(body, pol)
            crit = critical_files(m, actual)
            results[pol] = crit
            totals[pol] += len(crit)
        base_set = set(results["baseline"])
        rows.append({
            "pr": n,
            "actual_files": len(actual),
            **{f"{p}_crit": len(results[p]) for p in POLICIES},
            "removed_strict": sorted(base_set - set(results["strict"])),
            "removed_permissive": sorted(base_set - set(results["permissive"])),
            "removed_hybrid": sorted(base_set - set(results["hybrid"])),
        })
    print(f"{'PR':>6} {'files':>6} " + " ".join(f"{p:>10}" for p in POLICIES) + "  removed_strict_examples")
    for r in rows:
        ex = (r["removed_strict"][:2] + ["..."]) if len(r["removed_strict"])>2 else r["removed_strict"]
        print(f"{r['pr']:>6} {r['actual_files']:>6} " +
              " ".join(f"{r[p+'_crit']:>10}" for p in POLICIES) +
              "  " + (",".join(ex) if ex else "-"))
    print()
    print("TOTALS:")
    for p in POLICIES:
        print(f"  {p:>10}: {totals[p]} CRITICAL Check-1 findings")
    print()
    rem_strict = totals["baseline"] - totals["strict"]
    rem_hybrid = totals["baseline"] - totals["hybrid"]
    rem_perm   = totals["baseline"] - totals["permissive"]
    print(f"Removed by strict:     {rem_strict} ({rem_strict/max(totals['baseline'],1)*100:.0f}%)")
    print(f"Removed by hybrid:     {rem_hybrid} ({rem_hybrid/max(totals['baseline'],1)*100:.0f}%)")
    print(f"Removed by permissive: {rem_perm} ({rem_perm/max(totals['baseline'],1)*100:.0f}%)")
    # save details
    json.dump(rows, open("/tmp/regression_rows.json","w"), indent=2)

if __name__=="__main__":
    main()
