"""Tests for the zero-LLM routing labels in .github/labeler-route.yml.

route:docs, route:code, and docs-touched decide whether the docs bot or the
code bot wakes on a PR. This evaluator mirrors actions/labeler semantics:
top-level entries and entries inside ``all`` are AND-ed, entries inside
``any`` are OR-ed, and globs use minimatch rules with ``dot: true``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

glob = pytest.importorskip("wcmatch.glob")

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / ".github" / "labeler-route.yml").read_text(encoding="utf-8"))
FLAGS = glob.GLOBSTAR | glob.BRACE | glob.DOTGLOB
ROUTING = ("route:docs", "route:code", "docs-touched")


def _match(path: str, pattern: str) -> bool:
    if pattern.startswith("!"):
        return not glob.globmatch(path, pattern[1:], flags=FLAGS)
    return glob.globmatch(path, pattern, flags=FLAGS)


def _rule(files: list[str], kind: str, globs: list[str]) -> bool:
    if kind == "any-glob-to-any-file":
        return any(_match(f, g) for g in globs for f in files)
    if kind == "any-glob-to-all-files":
        return any(all(_match(f, g) for f in files) for g in globs)
    if kind == "all-globs-to-any-file":
        return any(all(_match(f, g) for g in globs) for f in files)
    if kind == "all-globs-to-all-files":
        return all(_match(f, g) for g in globs for f in files)
    raise AssertionError(f"unsupported matcher {kind}")


def _changed_files(files: list[str], rules: list[dict]) -> bool:
    return all(_rule(files, k, v) for r in rules for k, v in r.items())


def _base(files: list[str], cfg: dict, combine) -> bool:
    return combine(_changed_files(files, v) for k, v in cfg.items() if k == "changed-files")


def _label(files: list[str], label: str) -> bool:
    results = []
    for entry in CONFIG[label]:
        if "any" in entry:
            results.append(any(_base(files, c, all) for c in entry["any"]))
        elif "all" in entry:
            results.append(all(_base(files, c, all) for c in entry["all"]))
        else:
            results.append(_base(files, entry, any))
    return all(results)


def labels_for(files: list[str]) -> set[str]:
    return {lbl for lbl in ROUTING if _label(files, lbl)}


CASES = [
    # Pure prose docs route to the docs bot.
    (["README.md"], {"route:docs"}),
    (["docs/customization.md", "docs/img/flow.png"], {"route:docs"}),
    (
        [".project-toolkit/architecture/ADR-092-x.md", ".project-toolkit/critique/ADR-092-log.md"],
        {"route:docs"},
    ),
    ([".serena/memories/lsp/lsp-first-enforcement.md"], {"route:docs"}),
    ([".agents/governance/code-quality.md", "CONTRIBUTING.md", "LICENSE"], {"route:docs"}),
    # Behavior sources are code even though they are markdown.
    ([".claude/skills/push-pr/SKILL.md"], {"route:code"}),
    (["templates/skills/skillopt.SKILL.md.tmpl"], {"route:code"}),
    (["src/claude/skills/retrospective/SKILL.md"], {"route:code"}),
    ([".claude/rules/claude-agents.md"], {"route:code"}),
    ([".github/instructions/ci-scripts.instructions.md"], {"route:code"}),
    (["AGENTS.md"], {"route:code"}),
    (["scripts/CLAUDE.md"], {"route:code"}),
    ([".agents/steering/testing-approach.md"], {"route:code"}),
    # Code plus docs gets docs-touched.
    (["scripts/validation/pr_description.py", "CONTRIBUTING.md"], {"route:code", "docs-touched"}),
    ([".claude/skills/x/SKILL.md", "docs/agent-catalog.md"], {"route:code", "docs-touched"}),
    # Code plus only behavior markdown does not.
    (["scripts/a.py", ".claude/skills/x/SKILL.md"], {"route:code"}),
    (["scripts/validation/git_hook_policy.py"], {"route:code"}),
    # Executable files under docs/ are code.
    (["docs/tools/build.py"], {"route:code"}),
    (["docs/guide.md", "docs/tools/build.py"], {"route:code", "docs-touched"}),
    # Rules and instructions outside the listed trees are code.
    ([".agents/rules/review.md"], {"route:code"}),
    (["docs/review.instructions.md"], {"route:code"}),
]


@pytest.mark.parametrize(("files", "expected"), CASES)
def test_routing_labels(files: list[str], expected: set[str]) -> None:
    assert labels_for(files) == expected


@pytest.mark.parametrize("files", [c[0] for c in CASES])
def test_docs_and_code_are_exclusive_and_exhaustive(files: list[str]) -> None:
    got = labels_for(files)
    assert ("route:docs" in got) != ("route:code" in got)
    if "docs-touched" in got:
        assert "route:code" in got


def test_doc_and_behavior_lists_stay_in_sync() -> None:
    docs_rule = CONFIG["route:docs"][0]["changed-files"][0]["all-globs-to-all-files"]
    doc_glob, behavior = docs_rule[0], [g[1:] for g in docs_rule[1:]]
    code_any = CONFIG["route:code"][0]["any"]
    assert code_any[0]["changed-files"][0]["all-globs-to-any-file"] == ["!" + doc_glob]
    assert code_any[1]["changed-files"][0]["any-glob-to-any-file"] == behavior
    assert CONFIG["docs-touched"][0] == CONFIG["route:code"][0]
    touched = CONFIG["docs-touched"][1]["all"][0]["changed-files"][0]["all-globs-to-any-file"]
    assert touched == docs_rule


def test_workflow_syncs_only_routing_config() -> None:
    wf_path = ROOT / ".github" / "workflows" / "label-pr.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    steps = {
        s["with"]["configuration-path"]: s["with"]["sync-labels"]
        for s in wf["jobs"]["label"]["steps"]
    }
    assert steps == {".github/labeler.yml": False, ".github/labeler-route.yml": True}
    shared = yaml.safe_load((ROOT / ".github" / "labeler.yml").read_text(encoding="utf-8"))
    assert not set(shared) & set(ROUTING)
