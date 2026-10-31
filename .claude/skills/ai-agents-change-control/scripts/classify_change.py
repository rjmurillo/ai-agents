#!/usr/bin/env python3
"""Classify changed paths into change-control classes and list the gates each triggers.

Input: paths as arguments, or --staged (git diff --cached --name-only), or
--base REF (git diff --name-only REF...HEAD). Output: JSON with an `examined`
count, one row per path, the union of classes and gates, and any allowlist
violation. The class-to-gate map is data in CLASS_MAP below.

Exit codes: 0 ok, 1 finding (investigation-only paths mixed with paths outside
the allowlist), 2 bad arguments or missing allowlist module, 3 git failed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ALLOWLIST_MODULE = "scripts/modules/investigation_allowlist.py"

# Each class: id, path regexes (any match), obligation, extra gates. This map is
# canonical for path globs and gates; SKILL.md defers to it and keeps only the
# obligations. A path can match several classes.
CLASS_MAP: list[dict] = [
    {
        "id": "docs-only",
        "match": [],  # derived: markdown with no stricter class
        "obligation": "QA evidence row `SKIPPED: docs-only`",
        "gates": ["scoped markdownlint on changed files", "dash prohibition"],
    },
    {
        "id": "investigation-only",
        "match": [],  # derived from the allowlist module
        "obligation": "QA evidence row `SKIPPED: investigation-only`",
        "gates": ["staged-file allowlist check in the pre-commit QA validator (ADR-034)"],
    },
    {
        "id": "code",
        "match": [r"\.(py|ps1|psm1|sh|cs|ts|js)$", r"^(scripts|tests|build)/"],
        "obligation": "Full QA evidence per .agents/governance/TESTING-RIGOR.md",
        "gates": [
            "test rigor: positive, negative, edge, branch coverage, mocked I/O",
            "coverage floors 100 security / 80 business / 60 docs",
        ],
    },
    {
        "id": "plugin-content",
        "match": [r"^\.claude/", r"^src/claude/", r"^src/copilot-cli/"],
        "obligation": "No manifest edit; manifests carry no version (ADR-092)",
        "gates": [
            "pre_pr.py wrapping build/scripts/validate_plugin_version_bump.py",
            ".github/workflows/validate-plugin-version-bump.yml",
        ],
    },
    {
        "id": "git-hook-config",
        "match": [r"^lefthook\.yml$"],
        "obligation": "Named-job validation and relevant validator tests",
        "gates": ["lefthook validate", "validator tests for the changed job"],
    },
    {
        "id": "claude-lifecycle-hook",
        "match": [r"^\.claude/hooks/", r"^build/.*generate_hooks"],
        "obligation": "Dual-registration sync; runtime-contract tests",
        "gates": [
            "scripts/validation/validate_hook_anchoring.py",
            "tests/build_scripts/test_generate_hooks_runtime_contract.py",
            "edit templates/hooks/ sources and run build_all.py; settings.json and hooks.json are generated",
        ],
    },
    {
        "id": "workflow",
        "match": [r"^\.github/workflows/.*\.ya?ml$"],
        "obligation": "No logic in YAML (ADR-006); SHA-pinned actions",
        "gates": [
            "SHA-pin validation",
            "yamllint style",
            "local workflow run gate in pre-push",
        ],
    },
    {
        "id": "adr-governance",
        "match": [r"(^|/)ADR-[^/]*\.md$"],
        "obligation": "adr-review debate gate; debate log required; human approval for governance",
        "gates": [
            "adr-review debate to consensus",
            "blocking git_hook_policy.py adr-review Lefthook job",
        ],
    },
    {
        "id": "canonical-source",
        "match": [r"^templates/", r"^src/claude/", r"^build/"],
        "obligation": "Edit the canonical side only; regenerate, never hand-edit generated trees",
        "gates": [
            "uv run python build/generate_agents.py --validate",
            "uv run python build/scripts/build_all.py --check",
            "agent-drift-detection.yml and drift-detection.yml in CI",
        ],
    },
]

_BY_ID = {c["id"]: c for c in CLASS_MAP}
_MARKDOWN = re.compile(r"\.(md|mdx)$")
_STRICTER_THAN_DOCS = {"plugin-content", "claude-lifecycle-hook", "canonical-source"}


def load_allowlist(repo: Path) -> list[re.Pattern[str]]:
    """Load the enforced allowlist regexes from the repo's own module."""
    mod_path = repo / ALLOWLIST_MODULE
    if not mod_path.is_file():
        raise FileNotFoundError(f"{ALLOWLIST_MODULE} not found under {repo}")
    spec = importlib.util.spec_from_file_location("_inv_allowlist", mod_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [re.compile(p) for p in mod.get_investigation_allowlist()]


def normalize(path: str, repo: Path) -> str:
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("/"):
        try:
            p = Path(p).resolve().relative_to(repo).as_posix()
        except ValueError:
            pass
    return p


def classify(path: str, allow: list[re.Pattern[str]]) -> list[str]:
    if any(r.search(path) for r in allow):
        return ["investigation-only"]
    classes = [
        c["id"] for c in CLASS_MAP if c["match"] and any(re.search(m, path) for m in c["match"])
    ]
    if (
        _MARKDOWN.search(path)
        and not (set(classes) & _STRICTER_THAN_DOCS)
        and "adr-governance" not in classes
    ):
        classes.append("docs-only")
    return classes


def gates_for(classes: list[str]) -> list[str]:
    out: list[str] = []
    for cid in classes:
        for g in _BY_ID[cid]["gates"]:
            if g not in out:
                out.append(g)
    return out


def analyze(paths: list[str], allow: list[re.Pattern[str]]) -> dict:
    rows = []
    for p in paths:
        cls = classify(p, allow)
        rows.append({"path": p, "classes": cls or ["unclassified"], "gates": gates_for(cls)})
    all_classes = [c for r in rows for c in r["classes"]]
    classes = sorted(set(all_classes))
    gates = gates_for([c["id"] for c in CLASS_MAP if c["id"] in classes])
    violations = []
    if "investigation-only" in classes:
        violations = [r["path"] for r in rows if "investigation-only" not in r["classes"]]
    return {
        "examined": len(rows),
        "paths": rows,
        "classes": classes,
        "mixed": len([c for c in classes if c != "unclassified"]) > 1,
        "gates": gates,
        "allowlist_violations": violations,
    }


def git_paths(repo: Path, args: list[str]) -> list[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise RuntimeError(f"git failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Classify changed paths and list triggered gates.")
    ap.add_argument("--repo", default=".", help="repository root (default: .)")
    ap.add_argument("--staged", action="store_true", help="use git diff --cached --name-only")
    ap.add_argument("--base", metavar="REF", help="use git diff --name-only REF...HEAD")
    ap.add_argument("--map", action="store_true", help="print the class-to-gate map and exit")
    ap.add_argument("paths", nargs="*", help="changed paths")
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()

    if a.map:
        print(json.dumps({"classes": CLASS_MAP, "examined": len(CLASS_MAP)}, indent=2))
        return 0
    modes = sum([bool(a.paths), a.staged, bool(a.base)])
    if modes != 1:
        print(
            json.dumps({"error": "give exactly one of: paths, --staged, --base REF"}),
            file=sys.stderr,
        )
        return 2
    try:
        allow = load_allowlist(repo)
    except (OSError, ImportError, AttributeError, re.error) as exc:
        print(json.dumps({"error": f"allowlist unavailable: {exc}"}), file=sys.stderr)
        return 2
    try:
        if a.staged:
            raw = git_paths(repo, ["diff", "--cached", "--name-only"])
        elif a.base:
            raw = git_paths(repo, ["diff", "--name-only", f"{a.base}...HEAD"])
        else:
            raw = a.paths
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3
    result = analyze([normalize(p, repo) for p in raw], allow)
    print(json.dumps(result, indent=2))
    return 1 if result["allowlist_violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
