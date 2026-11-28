"""CLI, comment rendering, shipped files, and the no-network import boundary."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts.pr_approval import cli
from scripts.pr_approval.codeowners import parse_codeowners
from scripts.pr_approval.comment import render_comment
from scripts.pr_approval.engine import evaluate, evidence_fingerprint
from scripts.pr_approval.policy import parse_policy
from scripts.pr_approval.registry import parse_registry
from scripts.pr_approval.snapshot import parse_snapshot
from tests.pr_approval.fixtures import CODEOWNERS, HEAD, POLICY_TOML, REGISTRY_TOML, golden, run

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "scripts" / "pr_approval"
SHIPPED_POLICY = REPO_ROOT / ".github" / "pr-approval-policy.toml"
SHIPPED_REGISTRY = REPO_ROOT / ".github" / "pr-approval-registry.toml"
SHIPPED_CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"

BANNED_IMPORTS = {
    "subprocess",
    "socket",
    "urllib",
    "http",
    "requests",
    "httpx",
    "ssl",
    "ftplib",
    "smtplib",
}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", sorted(PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_package_has_no_network_or_github_imports(module: Path) -> None:
    for name in _imports(module):
        root = name.split(".")[0]
        assert root not in BANNED_IMPORTS, f"{module.name} imports {name}"
        assert not name.startswith("scripts.github_core"), f"{module.name} imports {name}"
        assert root in {
            "__future__",
            "scripts",
            "argparse",
            "collections",
            "ast",
            "copy",
            "dataclasses",
            "fnmatch",
            "hashlib",
            "json",
            "pathlib",
            "sys",
            "tomllib",
            "typing",
        }, f"{module.name} imports {name}"


def test_package_never_calls_open_for_write() -> None:
    for module in PACKAGE.glob("*.py"):
        text = module.read_text(encoding="utf-8")
        for marker in ("write_text(", "write_bytes(", "open(", "os.system", "eval(", "exec("):
            assert marker not in text, f"{module.name} contains {marker}"


def test_shipped_policy_is_observe_with_one_allow_rule() -> None:
    policy = parse_policy(SHIPPED_POLICY.read_bytes())
    assert policy.mode == "observe"
    assert [(r.id, r.mode, r.effect) for r in policy.rules] == [
        ("docs-prose-only", "observe", "allow")
    ]
    selector = policy.rules[0].selector
    assert (selector.max_files, selector.max_changed_lines, selector.author_class) == (
        5,
        100,
        "independent",
    )
    assert selector.forbid_renames and selector.forbid_binary and selector.forbid_code_fences


def test_shipped_registry_is_empty_so_everything_holds() -> None:
    registry = parse_registry(SHIPPED_REGISTRY.read_bytes())
    assert not (
        registry.independent_authors or registry.approver_principals or registry.alias_groups
    )
    raw = golden()
    decision = evaluate(
        parse_snapshot(raw),
        parse_policy(SHIPPED_POLICY.read_bytes()),
        registry,
        parse_codeowners(SHIPPED_CODEOWNERS.read_text(encoding="utf-8")),
        evidence_fingerprint(raw),
    )
    assert decision.verdict == "HOLD"
    assert {"AUTHOR_UNKNOWN", "APPROVER_UNCONFIGURED"} <= set(decision.reasons)


@pytest.mark.parametrize(
    "path",
    [
        "docs/design/external-signal-gating.md",
        "docs/runbooks/red-ci-on-main.md",
        "docs/patterns/prompt-vs-agent.md",
    ],
)
def test_shipped_rule_is_reachable_under_real_codeowners(path: str) -> None:
    raw = golden()
    raw["files"]["items"][0]["path"] = path
    decision = evaluate(
        parse_snapshot(raw),
        parse_policy(SHIPPED_POLICY.read_bytes()),
        parse_registry(REGISTRY_TOML.encode()),
        parse_codeowners(SHIPPED_CODEOWNERS.read_text(encoding="utf-8")),
        evidence_fingerprint(raw),
    )
    assert (decision.verdict, decision.rule_id) == ("WOULD_APPROVE", "docs-prose-only")


def test_comment_would_approve() -> None:
    body = render_comment(run(golden()))
    assert body.splitlines()[0] == f"<!-- pr-approval-policy:v1 head={HEAD} -->"
    assert "WOULD APPROVE" in body and "`docs-prose-only`" in body and "`RULE_MATCHED`" in body
    assert "APPROVED" not in body


def test_comment_hold_with_unknown_fields() -> None:
    raw = golden()
    raw["pull_request"].pop("head_sha")
    body = render_comment(evaluate(parse_snapshot(raw), None, None, None, "f"))
    assert "head=unknown" in body and "**PR approval policy (observe): HOLD**" in body
    assert "`none`" in body


def _write_inputs(tmp_path: Path, raw: object) -> list[str]:
    (tmp_path / "s.json").write_text(json.dumps(raw), encoding="utf-8")
    (tmp_path / "p.toml").write_text(POLICY_TOML, encoding="utf-8")
    (tmp_path / "r.toml").write_text(REGISTRY_TOML, encoding="utf-8")
    (tmp_path / "CODEOWNERS").write_text(CODEOWNERS, encoding="utf-8")
    return [
        "--snapshot",
        str(tmp_path / "s.json"),
        "--policy",
        str(tmp_path / "p.toml"),
        "--registry",
        str(tmp_path / "r.toml"),
        "--codeowners",
        str(tmp_path / "CODEOWNERS"),
    ]


def test_cli_prints_decision(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(_write_inputs(tmp_path, golden())) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "WOULD_APPROVE"


def test_cli_comment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([*_write_inputs(tmp_path, golden()), "--comment"]) == 0
    assert "WOULD APPROVE" in capsys.readouterr().out


def test_cli_bad_snapshot(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = _write_inputs(tmp_path, golden())
    (tmp_path / "s.json").write_text("{", encoding="utf-8")
    assert cli.main(args) == 2
    assert "cannot read snapshot" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("target", "content", "reason"),
    [
        ("p.toml", "schema_version = 9", "POLICY_INVALID"),
        ("r.toml", "nope = 1", "REGISTRY_INVALID"),
    ],
)
def test_cli_invalid_config_prints_hold(
    tmp_path: Path, capsys, target: str, content: str, reason: str
) -> None:
    args = _write_inputs(tmp_path, golden())
    (tmp_path / target).write_text(content, encoding="utf-8")
    assert cli.main(args) == 2
    captured = capsys.readouterr()
    decision = json.loads(captured.out)
    assert (decision["verdict"], decision["reasons"]) == ("HOLD", [reason])
    assert "error:" in captured.err


def test_cli_missing_codeowners_holds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = _write_inputs(tmp_path, golden())
    (tmp_path / "CODEOWNERS").unlink()
    assert cli.main(args) == 2
    decision = json.loads(capsys.readouterr().out)
    assert decision["verdict"] == "HOLD" and "EVIDENCE_INCOMPLETE" in decision["reasons"]


def test_cli_module_entry_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    import runpy
    import sys

    monkeypatch.delitem(sys.modules, "scripts.pr_approval.cli", raising=False)
    monkeypatch.setattr(sys, "argv", ["cli", *_write_inputs(tmp_path, golden())])
    with pytest.raises(SystemExit) as exited:
        runpy.run_module("scripts.pr_approval.cli", run_name="__main__")
    assert exited.value.code == 0
    assert "WOULD_APPROVE" in capsys.readouterr().out
