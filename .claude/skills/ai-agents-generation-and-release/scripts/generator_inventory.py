#!/usr/bin/env python3
"""Inventory the ai-agents generation machinery from source, read-only.

Subcommands:
  generators       GENERATORS order, OWNED_PREFIXES, and the exit-2 producer
                   count sentence from build/scripts/build_all.py.
  path <repo-path> Which tree is canonical for a path and what regenerates it,
                   from templates/platforms/binplace.yaml rows.
  skills           Template count and repo-local skills from
                   templates/skills/*.SKILL.md.tmpl.
  gates            Wiring (lefthook job or workflow job) for each drift gate.

Output is JSON with an "examined" count. Exit codes: 0 ok, 1 findings
(unmapped path, gate with missing wiring), 2 configuration or bad arguments,
3 external failure (reserved; this script runs no external command).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

BUILD_ALL = "build/scripts/build_all.py"
BINPLACE = "templates/platforms/binplace.yaml"
TEMPLATES = "templates/skills"
REGEN = "uv run python build/scripts/build_all.py"

# Each gate: local command and the (file, needle) probes that prove CI or a
# hook runs it. A probe needle must appear in the file; the nearest enclosing
# job name is reported.
GATES: list[dict] = [
    {
        "id": "agent-template-drift",
        "local": "uv run python build/generate_agents.py --validate",
        "probes": [
            (".github/workflows/agent-drift-detection.yml", "build/generate_agents.py --validate")
        ],
    },
    {
        "id": "build-all-staleness",
        "local": "uv run python build/scripts/build_all.py --check",
        "probes": [(".github/workflows/validate-generated-agents.yml", "build_all.py --check")],
    },
    {
        "id": "lib-mirror-drift",
        "local": "uv run python build/scripts/build_all.py --check",
        "probes": [(".github/workflows/agent-drift-detection.yml", "check_plugin_lib_mirrors.py")],
    },
    {
        "id": "install-parity",
        "local": "python3 scripts/validation/run_install_parity_ci.py",
        "probes": [(".github/workflows/validate-generated-agents.yml", "run_install_parity_ci.py")],
    },
    {
        "id": "manifest-description-parity",
        "local": "python3 build/scripts/check_plugin_manifest_parity.py",
        "probes": [
            (".github/workflows/validate-generated-agents.yml", "check_plugin_manifest_parity.py"),
            (".github/workflows/agent-drift-detection.yml", "check_plugin_manifest_parity.py"),
        ],
    },
    {
        "id": "plugin-version-field",
        "local": "python3 build/scripts/validate_plugin_version_bump.py",
        "probes": [
            (".github/workflows/validate-plugin-version-bump.yml", "run_plugin_version_bump_ci.py"),
            ("lefthook.yml", "scripts/validation/pre_pr.py --compact"),
        ],
    },
    {
        "id": "semantic-agent-drift",
        "local": "python3 build/scripts/detect_agent_drift.py",
        "probes": [(".github/workflows/drift-detection.yml", "drift_run_detection.py")],
    },
]


def _read(repo: Path, rel: str) -> str | None:
    try:
        return (repo / rel).read_text(encoding="utf-8")
    except OSError:
        return None


def _assigned(tree: ast.Module, name: str) -> ast.expr | None:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                return node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    return None


def cmd_generators(repo: Path) -> tuple[dict, int]:
    text = _read(repo, BUILD_ALL)
    if text is None:
        return {"error": f"missing {BUILD_ALL}", "examined": 0}, 2
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"error": f"cannot parse {BUILD_ALL}: {exc}", "examined": 0}, 2
    gens = _assigned(tree, "GENERATORS")
    owned = _assigned(tree, "OWNED_PREFIXES")
    if not isinstance(gens, ast.List) or not isinstance(owned, ast.Tuple):
        return {"error": "GENERATORS or OWNED_PREFIXES not found", "examined": 0}, 2
    names = []
    for elt in gens.elts:
        if isinstance(elt, ast.Tuple) and elt.elts and isinstance(elt.elts[0], ast.Constant):
            names.append(str(elt.elts[0].value))
    prefixes = [e.value for e in owned.elts if isinstance(e, ast.Constant)]
    doc = ast.get_docstring(tree) or ""
    match = re.search(r"Exit 2 has (\w+) producers", doc)
    out = {
        "source": BUILD_ALL,
        "generators": [{"n": i + 1, "name": n} for i, n in enumerate(names)],
        "generator_count": len(names),
        "owned_prefixes": prefixes,
        "owned_prefix_count": len(prefixes),
        "exit2_producers": match.group(1) if match else None,
        "examined": len(names) + len(prefixes),
    }
    return out, 0


def parse_binplace(text: str) -> list[dict]:
    """Parse the flat `rows:` list of binplace.yaml without PyYAML."""
    rows: list[dict] = []
    for raw in text.splitlines():
        line = raw.split(" #")[0] if " #" in raw else raw
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^  - (\w+):\s*(.*)$", line)
        if m:
            rows.append({})
            line = f"    {m.group(1)}: {m.group(2)}"
        m = re.match(r"^    (\w+):\s*(.*)$", line)
        if m and rows:
            val = m.group(2).strip().strip('"')
            rows[-1][m.group(1)] = {"null": None, "true": True, "false": False}.get(val, val)
    return rows


def _under(path: str, base: str | None) -> bool:
    return bool(base) and (path == base or path.startswith(base.rstrip("/") + "/"))


def _norm(raw: str) -> str:
    p = raw.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def cmd_path(repo: Path, raw: str) -> tuple[dict, int]:
    text = _read(repo, BINPLACE)
    if text is None:
        return {"error": f"missing {BINPLACE}", "examined": 0}, 2
    rows = parse_binplace(text)
    path = _norm(raw)
    matches = []
    for row in rows:
        for role, key in (
            ("canonical", "source"),
            ("generated", "plugin_tree"),
            ("installed", "install_tree"),
        ):
            base = row.get(key)
            if not _under(path, base):
                continue
            if role == "generated" and base == row.get("source"):
                continue
            if role == "installed":
                role = "link" if row.get("link") else "binplaced-copy"
            matches.append(
                {
                    "role": role,
                    "class": row.get("class"),
                    "specificity": len(base),
                    "canonical_source": row.get("source"),
                    "plugin_tree": row.get("plugin_tree"),
                    "install_tree": row.get("install_tree"),
                    "compile": row.get("compile"),
                    "regenerate": REGEN,
                }
            )
    out: dict = {"path": path, "examined": len(rows)}
    if matches:
        matches.sort(key=lambda m: -m["specificity"])
        top = matches[0]["specificity"]
        best = [m for m in matches if m["specificity"] == top]
        for m in best:
            del m["specificity"]
        out["role"] = best[0]["role"]
        out["matches"] = best
        out["repo_local_skill"] = _repo_local_skill(repo, path)
        if out["repo_local_skill"]:
            out["role"] = "repo-local-rendered"
            out["note"] = (
                "repo-local skill: template renders straight to install_tree, no plugin hop"
            )
        return out, 0
    gtext = _read(repo, BUILD_ALL)
    if gtext is not None:
        owned = _assigned(ast.parse(gtext), "OWNED_PREFIXES")
        if isinstance(owned, ast.Tuple):
            for e in owned.elts:
                if isinstance(e, ast.Constant) and (path == e.value or path.startswith(e.value)):
                    out.update(role="generated", owned_prefix=e.value, regenerate=REGEN, matches=[])
                    return out, 0
    out.update(role=None, matches=[], note="no binplace row or owned prefix covers this path")
    return out, 1


def _repo_local_skill(repo: Path, path: str) -> bool:
    m = re.match(r"^\.claude/skills/([^/]+)/", path)
    if not m:
        return False
    return m.group(1) in _skills(repo)[1]


def _skills(repo: Path) -> tuple[list[str], list[str]]:
    tdir = repo / TEMPLATES
    names, local = [], []
    if not tdir.is_dir():
        return names, local
    for f in sorted(tdir.glob("*.SKILL.md.tmpl")):
        name = f.name[: -len(".SKILL.md.tmpl")]
        names.append(name)
        try:
            head = f.read_text(encoding="utf-8").split("\n---", 2)[0]
        except OSError:
            continue
        if re.search(r"^\s+distribution:\s*repo-local\s*$", head, re.MULTILINE):
            local.append(name)
    return names, local


def cmd_skills(repo: Path) -> tuple[dict, int]:
    if not (repo / TEMPLATES).is_dir():
        return {"error": f"missing {TEMPLATES}", "examined": 0}, 2
    names, local = _skills(repo)
    return {
        "templates": len(names),
        "shipped": len(names) - len(local),
        "repo_local": local,
        "repo_local_count": len(local),
        "examined": len(names),
    }, 0


def _enclosing(lines: list[str], idx: int, is_lefthook: bool) -> str | None:
    pattern = r"^\s*- name:\s*(\S+)" if is_lefthook else r"^  ([A-Za-z0-9_-]+):\s*$"
    for j in range(idx, -1, -1):
        m = re.match(pattern, lines[j])
        if m:
            return m.group(1)
    return None


def cmd_gates(repo: Path) -> tuple[dict, int]:
    results, bad = [], 0
    examined = 0
    for gate in GATES:
        wired, missing = [], []
        for rel, needle in gate["probes"]:
            examined += 1
            text = _read(repo, rel)
            lines = text.splitlines() if text is not None else []
            hit = next(
                (
                    i
                    for i, ln in enumerate(lines)
                    if needle in ln and not ln.lstrip().startswith(("#", "- '", '- "'))
                ),
                None,
            )
            if hit is None:
                missing.append({"file": rel, "needle": needle})
            else:
                wired.append(
                    {
                        "file": rel,
                        "job": _enclosing(lines, hit, rel == "lefthook.yml"),
                        "line": hit + 1,
                    }
                )
        if missing:
            bad += 1
        results.append(
            {"id": gate["id"], "local": gate["local"], "wired": wired, "missing": missing}
        )
    return {"gates": results, "unwired": bad, "examined": examined}, 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generators")
    p = sub.add_parser("path")
    p.add_argument("target")
    sub.add_parser("skills")
    sub.add_parser("gates")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    repo = Path(args.repo)
    if not repo.is_dir():
        print(json.dumps({"error": f"not a directory: {repo}", "examined": 0}))
        return 2
    if args.cmd == "generators":
        out, code = cmd_generators(repo)
    elif args.cmd == "path":
        out, code = cmd_path(repo, args.target)
    elif args.cmd == "skills":
        out, code = cmd_skills(repo)
    else:
        out, code = cmd_gates(repo)
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
