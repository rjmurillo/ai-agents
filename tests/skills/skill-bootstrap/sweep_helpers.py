"""Fixtures and drivers for the bootstrap_sweep tests: one Run walks plan to tally."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

import bootstrap_sweep
import pytest

TODAY = "2026-11-11"
Result = tuple[int, dict[str, Any]]
JUDGES = ("friction", "knowledge-gap")
CONNECTED = ("chat", "code_review", "work_tracking", "memory", "agent_sessions")

INVENTORY: dict[str, Any] = {
    "schema_version": 1,
    "servers": [
        {
            "name": "Slack",
            "tools": ["slack_read_channel", "slack_send_message", "slack_search_public"],
        },
        {"name": "github", "tools": ["get_me", "issue_write", "list_issues", "mystery_op"]},
    ],
    "skills": ["memory-search", "skill-doctor"],
}


def dump(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_item(item_id: str, cls: str = "chat", **overrides: Any) -> dict[str, Any]:
    item = {
        "id": item_id,
        "class": cls,
        "server": {"chat": "Slack", "code_review": "github", "memory": "memory-search"}.get(
            cls, "x"
        ),
        "locator": f"loc://{item_id}",
        "thread": f"thread-{item_id}",
        "visibility": "public",
        "date": "2026-10-01",
        "path": f"evidence/{item_id}.md",
    }
    item.update(overrides)
    return item


def default_items() -> list[dict[str, Any]]:
    return [
        make_item("chat-1"),
        make_item("chat-2", date="2026-10-02"),
        make_item("pr-1", "code_review", date="2026-10-03"),
        make_item("mem-1", "memory"),
    ]


def cov(cls: str, **overrides: Any) -> dict[str, Any]:
    return {"class": cls, "state": "read", "items_read": 1, **overrides}


def default_coverage() -> list[dict[str, Any]]:
    return [cov(c) for c in CONNECTED]


def make_finding(**overrides: Any) -> dict[str, Any]:
    finding = {
        "finding_id": "f1",
        "incident": "slow-onboarding",
        "type": "knowledge-gap",
        "pattern": "fragmented-context",
        "evidence": ["chat-1"],
        "summary": "People ask the same onboarding question",
        "people": 2,
        "suggestion": {"action": "write-doc", "target": "docs/onboarding", "rationale": "Missing"},
        "gap": {"question": "How do I start?", "answer_location": "person", "documented": False},
    }
    finding.update(overrides)
    return finding


def _writable_evidence_path(rel: str) -> bool:
    """Only write fixtures to a clean relative path under evidence/, never an escape."""
    parts = PurePosixPath(rel).parts
    clean = rel.startswith("evidence/") and ".." not in parts and "\\" not in rel
    return clean and len(parts) > 1


class Run:
    """One sweep run directory outside the fixture repo, driven through main()."""

    def __init__(self, tmp_path: Path, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self.tmp, self.repo, self.capsys = tmp_path, repo, capsys
        self.run_dir = tmp_path / "run"
        self.plan_path = self.run_dir / "plan.json"
        self.index_path = self.run_dir / "index.json"
        self.accepted = self.run_dir / "accepted.json"

    def cli(self, *argv: str) -> Result:
        code = bootstrap_sweep.main(list(argv))
        return code, json.loads(self.capsys.readouterr().out)

    def plan(self, inventory: dict[str, Any] | None = None, *extra: str) -> Result:
        tools = dump(self.tmp / "tools.json", inventory or INVENTORY)
        return self.cli(
            "plan",
            "--tools",
            str(tools),
            "--repo",
            str(self.repo),
            "--run-dir",
            str(self.run_dir),
            "--today",
            TODAY,
            *extra,
        )

    def load_plan(self) -> dict[str, Any]:
        return json.loads(self.plan_path.read_text(encoding="utf-8"))

    def evidence(
        self,
        items: list[dict[str, Any]] | None = None,
        coverage: list[dict[str, Any]] | None = None,
        texts: dict[str, str | bytes] | None = None,
        **manifest: Any,
    ) -> None:
        chosen = default_items() if items is None else items
        for item in chosen:
            body = (texts or {}).get(item["id"], f"Notes for {item['id']}, nothing sensitive.")
            if not _writable_evidence_path(item["path"]):
                continue
            target = self.run_dir / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(body, bytes):
                target.write_bytes(body)
            else:
                target.write_text(body, encoding="utf-8")
        data = {
            "schema_version": 1,
            "plan_id": self.load_plan()["plan_id"],
            "coverage": default_coverage() if coverage is None else coverage,
            "items": chosen,
        }
        data.update(manifest)
        dump(self.run_dir / "evidence.json", data)

    def index(self, *extra: str) -> Result:
        return self.cli("index", "--plan", str(self.plan_path), *extra)

    def batches(self) -> list[str]:
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        return [b["batch_id"] for b in index["batches"]]

    def index_id(self) -> str:
        return json.loads(self.index_path.read_text(encoding="utf-8"))["index_id"]

    def rows_file(
        self, judge: str, run: int, batch: str, findings: list[Any], /, **overrides: Any
    ) -> Path:
        doc = {
            "schema_version": 1,
            "index_id": self.index_id(),
            "judge": judge,
            "run": run,
            "batch_id": batch,
            "findings": findings,
        }
        doc.update(overrides)
        return dump(self.tmp / f"rows-{judge}-{run}-{batch}.json", doc)

    def import_(
        self, judge: str, run: int, batch: str, findings: list[Any], /, **overrides: Any
    ) -> Result:
        rows = self.rows_file(judge, run, batch, findings, **overrides)
        return self.cli(
            "import",
            "--index",
            str(self.index_path),
            "--rows",
            str(rows),
            "--accepted",
            str(self.accepted),
        )

    def import_all(self, findings: list[Any], batch: str | None = None) -> None:
        """Import the same findings for every judge and run on one batch."""
        target = batch or self.batches()[0]
        for judge in JUDGES:
            for run in (1, 2):
                code, payload = self.import_(judge, run, target, findings)
                assert code == 0, payload

    def tally(self, *extra: str) -> Result:
        return self.cli(
            "tally",
            "--index",
            str(self.index_path),
            "--accepted",
            str(self.accepted),
            "--repo",
            str(self.repo),
            *extra,
        )

    def ready(self, *index_extra: str) -> None:
        """Plan and index the default inventory and evidence; both must succeed."""
        assert self.plan()[0] == 0
        self.evidence()
        code, payload = self.index(*index_extra)
        assert code == 0, payload

    def sweep(self, findings: list[Any]) -> dict[str, Any]:
        """Import `findings` for every judge and run on every batch, then tally."""
        for batch in self.batches():
            self.import_all(findings, batch)
        code, payload = self.tally()
        assert code == 0, payload
        return payload


def make_run(tmp_path: Path, repo: Path, capsys: pytest.CaptureFixture[str]) -> Run:
    return Run(tmp_path, repo, capsys)


def make_skill_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    skill = tmp_path / "skill"
    judges = skill / "judges"
    judges.mkdir(parents=True)
    for name in JUDGES:
        (judges / f"{name}.md").write_text(f"# {name} rubric\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap_sweep, "SKILL_DIR", skill)
    return skill
