"""Clean-checkout reproduction of the audit chain from frozen synthetic inputs (epic #7248, M4).

The chain is audit_scores -> assemble_report -> render_report -> public_export, run
through each script's ``main`` with network access blocked. Every output must match
the committed golden files under ``fixtures/audit/reproduction/expected/``.

To refresh the goldens after an intended output change, run this module with
``SKILL_DOCTOR_UPDATE_GOLDEN=1`` and review the diff before committing.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

import assemble_report
import audit_scores
import public_export
import pytest
import render_report

INPUTS = Path(__file__).resolve().parent / "fixtures" / "audit" / "reproduction"
EXPECTED = INPUTS / "expected"
GENERATED_AT = re.compile(r"Generated [^<]*<")
BUNDLE_PLACEHOLDER = "/* @pierre/diffs bundle: covered by test_vendored_bundle.py */"
UPDATE_GOLDEN = os.environ.get("SKILL_DOCTOR_UPDATE_GOLDEN") == "1"


def _normalize_html(html: str) -> str:
    """Drop the render timestamp and the vendored 1 MB diff bundle; keep everything else."""
    bundle = render_report.embedded_diffs_script()
    assert html.count(bundle) == 1
    return GENERATED_AT.sub("Generated <", html.replace(bundle, BUNDLE_PLACEHOLDER))


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the reproduction chain must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def chain(tmp_path: Path, offline: None, capsys: pytest.CaptureFixture[str]) -> Path:
    """Run the documented chain once into tmp_path and return that directory."""
    artifact = tmp_path / "score_artifact.json"
    report = tmp_path / "report.json"
    steps = [
        audit_scores.main([str(INPUTS / "scores.json"), "--out", str(artifact)]),
        assemble_report.main(
            [
                str(INPUTS / "draft.json"),
                "--scores",
                str(INPUTS / "scores.json"),
                "--artifact",
                str(artifact),
                "--manifest",
                str(INPUTS / "audit_manifest.json"),
                "--out",
                str(report),
            ]
        ),
        public_export.main([str(report), "--out", str(tmp_path / "public.json")]),
    ]
    render_report.main([str(report)])
    capsys.readouterr()
    assert steps == [0, 0, 0]
    return tmp_path


def _canonical_json(path: Path) -> str:
    """Same bytes as ``python3 -m json.tool --sort-keys --compact``, which the recipe diffs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


def _outputs(directory: Path) -> dict[str, str]:
    html = (directory / "report.html").read_text(encoding="utf-8")
    texts = {
        name: _canonical_json(directory / name)
        for name in ("score_artifact.json", "report.json", "public.json")
    }
    texts["report.html"] = _normalize_html(html)
    return texts


def test_chain_reproduces_the_golden_artifacts(chain: Path) -> None:
    outputs = _outputs(chain)
    if UPDATE_GOLDEN:
        EXPECTED.mkdir(exist_ok=True)
        for name, text in outputs.items():
            (EXPECTED / name).write_text(text, encoding="utf-8")

    for name, text in outputs.items():
        assert text == (EXPECTED / name).read_text(encoding="utf-8"), name


def test_rerunning_the_chain_gives_identical_outputs(chain: Path, tmp_path_factory: Any) -> None:
    first = _outputs(chain)
    second_dir = tmp_path_factory.mktemp("second")
    for name in ("score_artifact.json", "report.json"):
        text = (chain / name).read_text(encoding="utf-8")
        (second_dir / name).write_text(text, encoding="utf-8")
    render_report.main([str(second_dir / "report.json")])
    public_export.main([str(second_dir / "report.json"), "--out", str(second_dir / "public.json")])

    assert _outputs(second_dir) == first


def test_report_numbers_match_the_artifact_and_the_html(chain: Path) -> None:
    report = json.loads((chain / "report.json").read_text(encoding="utf-8"))
    artifact = json.loads((chain / "score_artifact.json").read_text(encoding="utf-8"))
    html = (chain / "report.html").read_text(encoding="utf-8")

    assert report["audit"]["scores"] == artifact
    assert report["stats"]["sessions_analyzed"] == artifact["sessions_scored"] == 6
    assert f'data-records="{len(report["audit"]["records"])}"' in html
    for record in report["audit"]["records"]:
        assert record["session_id"] in html
    for definition in report["audit"]["catalog"]:
        assert definition["sha256"] in html


def test_public_export_holds_no_seeded_canary(chain: Path) -> None:
    text = (chain / "public.json").read_text(encoding="utf-8")

    assert "CANARY-" not in text


def test_inputs_are_synthetic_and_reference_no_network() -> None:
    for path in INPUTS.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text and "https://" not in text, path.name
        assert "CANARY-" in text, path.name


REPO_ROOT = Path(__file__).resolve().parents[3]
FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def _recipe_blocks() -> list[str]:
    return FENCE.findall((INPUTS / "README.md").read_text(encoding="utf-8"))


def test_recipe_commands_run_and_match_the_goldens(tmp_path: Path) -> None:
    run_block, check_block = _recipe_blocks()[:2]
    script = run_block.replace('OUT="$(mktemp -d)"', f'OUT="{tmp_path}"') + check_block
    assert f'OUT="{tmp_path}"' in script

    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "overall: 0.8579 from 6 sessions" in result.stdout
    assert _normalize_html((tmp_path / "report.html").read_text(encoding="utf-8")) == (
        EXPECTED / "report.html"
    ).read_text(encoding="utf-8")


def test_recipe_refresh_command_names_this_module() -> None:
    assert "SKILL_DOCTOR_UPDATE_GOLDEN=1" in _recipe_blocks()[2]
    assert Path(__file__).name in _recipe_blocks()[2]
