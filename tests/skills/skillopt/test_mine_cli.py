"""Tests for the mine_sessions CLI: rank, tasks, collect, and merge."""

from __future__ import annotations

import json
from pathlib import Path

import mine_sessions as ms
import pytest
from skillopt_helpers import (
    Capture,
    skill_use,
    user,
    write_handoff,
    write_jsonl,
)


class TestCli:
    def test_rank_cmd(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("a"), user("no wrong"), skill_use("b")])
        sk = tmp_path / "skills"
        (sk / "a").mkdir(parents=True)
        rc = ms.main(
            ["rank", "--root", str(f), "--skills-dir", str(sk), "--top", "5", "--no-copilot"]
        )
        assert rc == 0
        rows = json.loads(capsys.readouterr().out)
        assert rows[0]["skill"] == "a" and rows[0]["in_repo"] is True

    def test_rank_repo_only(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("a"), skill_use("b")])
        sk = tmp_path / "skills"
        (sk / "a").mkdir(parents=True)
        ms.main(["rank", "--root", str(f), "--skills-dir", str(sk), "--repo-only", "--no-copilot"])
        assert [r["skill"] for r in json.loads(capsys.readouterr().out)] == ["a"]

    def test_rank_top_limits_rows(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("a"), skill_use("b"), skill_use("c")])
        ms.main(["rank", "--root", str(f), "--no-copilot", "--top", "2"])
        assert len(json.loads(capsys.readouterr().out)) == 2

    def test_tasks_dedup(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [user("same"), skill_use("x"), user("same"), skill_use("x")])
        assert ms.main(["tasks", "--skill", "x", "--root", str(f), "--no-copilot"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tasks"] == ["same"] and out["count"] == 1

    def test_tasks_output_shape_is_prompts_only(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [user("go"), skill_use("x"), user("that's wrong")])
        ms.main(["tasks", "--skill", "x", "--root", str(f), "--no-copilot"])
        assert set(json.loads(capsys.readouterr().out)) == {"skill", "count", "tasks"}

    def test_tasks_limit(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [user("one"), skill_use("x"), user("two"), skill_use("x")])
        ms.main(["tasks", "--skill", "x", "--root", str(f), "--no-copilot", "--limit", "1"])
        out = json.loads(capsys.readouterr().out)
        assert out["count"] == 2 and out["tasks"] == ["one"]

    def test_rank_from_companion_skill_handoff(
        self, tmp_path: Path, capsys: Capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handoff = tmp_path / "patterns.json"
        write_handoff(handoff)
        monkeypatch.setattr(ms, "_source_records", lambda _args: pytest.fail("raw stores read"))
        assert ms.main(["rank", "--patterns", str(handoff)]) == 0
        rows = json.loads(capsys.readouterr().out)
        assert rows[0]["skill"] == "build"
        assert rows[0]["invocations"] == 3
        assert rows[0]["corrections"] == 1

    def test_tasks_from_companion_skill_handoff_are_deduplicated(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        handoff = tmp_path / "patterns.json"
        write_handoff(handoff)
        assert ms.main(["tasks", "--patterns", str(handoff), "--skill", "build"]) == 0
        assert json.loads(capsys.readouterr().out) == {
            "skill": "build",
            "count": 2,
            "tasks": ["build the feature", "fix the build"],
        }

    def test_missing_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            ms.build_parser().parse_args([])

    def test_collect_requires_out(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            ms.build_parser().parse_args(["collect", "--no-copilot"])


class TestCollectMerge:
    def test_collect_writes_only_to_out(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("a"), user("that's wrong")])
        out = tmp_path / "nested" / "dir" / "boxA.json"
        rc = ms.main(
            ["collect", "--root", str(f), "--no-copilot", "--host", "boxA", "--out", str(out)]
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "boxA" in captured.err
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["host"] == "boxA" and doc["stats"]["a"]["corrections"] == 1
        assert doc["skill_count"] == 1

    def test_collect_default_host_label(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("a")])
        monkeypatch.setattr(ms.socket, "gethostname", lambda: "labelled")
        out = tmp_path / "b.json"
        assert ms.main(["collect", "--root", str(f), "--no-copilot", "--out", str(out)]) == 0
        assert json.loads(out.read_text(encoding="utf-8"))["host"] == "labelled"

    def test_collect_unwritable_out_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("a")])
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        rc = ms.main(
            ["collect", "--root", str(f), "--no-copilot", "--out", str(blocker / "b.json")]
        )
        assert rc == 2
        assert capsys.readouterr().err.startswith("Error: ")

    def test_collect_from_patterns(self, tmp_path: Path) -> None:
        handoff = tmp_path / "p.json"
        write_handoff(handoff)
        out = tmp_path / "b.json"
        assert (
            ms.main(["collect", "--patterns", str(handoff), "--host", "h", "--out", str(out)]) == 0
        )
        assert json.loads(out.read_text(encoding="utf-8"))["stats"]["build"]["invocations"] == 3

    def test_collect_then_merge(self, tmp_path: Path, capsys: Capture) -> None:
        f1 = tmp_path / "1.jsonl"
        write_jsonl(f1, [skill_use("a"), skill_use("a")])
        f2 = tmp_path / "2.jsonl"
        write_jsonl(f2, [skill_use("a"), user("that's wrong")])
        bdir = tmp_path / "baselines"
        ms.main(
            [
                "collect",
                "--root",
                str(f1),
                "--no-copilot",
                "--host",
                "boxA",
                "--out",
                str(bdir / "boxA.json"),
            ]
        )
        ms.main(
            [
                "collect",
                "--root",
                str(f2),
                "--no-copilot",
                "--host",
                "boxB",
                "--out",
                str(bdir / "boxB.json"),
            ]
        )
        capsys.readouterr()
        sk = tmp_path / "skills"
        (sk / "a").mkdir(parents=True)
        assert (
            ms.main(["merge", "--baselines-dir", str(bdir), "--skills-dir", str(sk), "--top", "5"])
            == 0
        )
        out = json.loads(capsys.readouterr().out)
        assert out["hosts"] == ["boxA", "boxB"]
        assert out["ranked"][0]["skill"] == "a"
        assert out["ranked"][0]["invocations"] == 3  # 2 + 1 across hosts

    def test_merge_explicit_files_and_repo_only(self, tmp_path: Path, capsys: Capture) -> None:
        b = tmp_path / "h.json"
        b.write_text(json.dumps({"host": "h", "stats": {
            "a": {"invocations": 1, "corrections": 0},
            "z": {"invocations": 9, "corrections": 0}}}), encoding="utf-8")  # fmt: skip
        sk = tmp_path / "skills"
        (sk / "a").mkdir(parents=True)
        ms.main(["merge", str(b), "--skills-dir", str(sk), "--repo-only"])
        assert [r["skill"] for r in json.loads(capsys.readouterr().out)["ranked"]] == ["a"]

    def test_merge_missing_baselines_dir_is_empty(self, tmp_path: Path, capsys: Capture) -> None:
        assert ms.main(["merge", "--baselines-dir", str(tmp_path / "none")]) == 0
        assert json.loads(capsys.readouterr().out) == {"hosts": [], "ranked": []}

    def test_merge_without_inputs_is_empty(self, capsys: Capture) -> None:
        assert ms.main(["merge"]) == 0
        assert json.loads(capsys.readouterr().out) == {"hosts": [], "ranked": []}

    @pytest.mark.parametrize("content", ["{nope", "[]", '{"stats": {"a": {"invocations": "3"}}}'])
    def test_merge_bad_baseline_exit_two_names_file(
        self, tmp_path: Path, capsys: Capture, content: str
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(content, encoding="utf-8")
        assert ms.main(["merge", str(bad)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("Error: ")
        assert "bad.json" in err
        assert "Traceback" not in err

    def test_merge_missing_explicit_file_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        assert ms.main(["merge", str(tmp_path / "gone.json")]) == 2
        assert "gone.json" in capsys.readouterr().err

    def test_merge_bad_file_in_dir_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        bdir = tmp_path / "b"
        bdir.mkdir()
        (bdir / "ok.json").write_text(json.dumps({"stats": {}}), encoding="utf-8")
        (bdir / "bad.json").write_text("{", encoding="utf-8")
        assert ms.main(["merge", "--baselines-dir", str(bdir)]) == 2
        assert "bad.json" in capsys.readouterr().err
