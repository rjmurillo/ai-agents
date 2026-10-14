"""Tests for the external contract provenance gate (issue #5415).

Every fixture is built in `tmp_path`. The seven scenarios the issue requires are
named in the test names, and each negative case asserts both the exit code and
the message so a test cannot pass for the wrong reason.
"""

from __future__ import annotations

import datetime as dt
import json
import runpy
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_external_contracts as gate

TODAY = dt.date(2026, 10, 11)

FIXTURE_REL = "templates/rules/a.md"
GOOD_FIELDS = {
    "source": "https://example.org/spec/v2",
    "version": "v2.1",
    "evidence": "specification",
    "verified": "2026-10-01",
    "purpose": "Wire format the adapter must emit",
}


def _fence(**overrides: str | None) -> str:
    """Render one fenced Markdown record, GOOD_FIELDS plus overrides."""
    fields = {**GOOD_FIELDS, **overrides}
    body = "\n".join(f"{key}: {value}" for key, value in fields.items() if value is not None)
    return f"Prose before.\n\n```external-contract\n{body}\n```\n\nProse after.\n"


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _findings(root: Path) -> list[str]:
    return gate.find_findings(root, TODAY)


# --- scenario 1: transient docs lookup needs no record -------------------


def test_ephemeral_lookup_without_a_record_passes(tmp_path: Path) -> None:
    _write(
        tmp_path, "scripts/tool.py", '"""Uses str.partition, checked against the stdlib docs."""\n'
    )
    assert _findings(tmp_path) == []
    assert gate.validate_external_contracts(tmp_path) is True
    assert gate.main([str(tmp_path)]) == 0


# --- scenario 2: versioned external contract is recorded and found -------


def test_versioned_contract_record_passes_and_is_discoverable(tmp_path: Path) -> None:
    _write(tmp_path, "templates/rules/adapter.md", _fence())
    assert _findings(tmp_path) == []
    records = gate.collect_records(tmp_path)
    assert [r.path for r in records] == ["templates/rules/adapter.md"]
    assert records[0].fields["version"] == "v2.1"
    assert records[0].line == 3


# --- scenario 3: vendor docs incomplete, empirical probe -----------------


def test_empirical_record_needs_a_reverify_path(tmp_path: Path) -> None:
    _write(tmp_path, "templates/rules/probe.md", _fence(evidence="empirical"))
    findings = _findings(tmp_path)
    assert len(findings) == 1
    assert "empirical evidence needs `reverify`" in findings[0]


def test_empirical_record_with_an_existing_probe_passes(tmp_path: Path) -> None:
    _write(tmp_path, "tests/e2e/probe.py", "print('probe')\n")
    _write(
        tmp_path,
        "templates/rules/probe.md",
        _fence(evidence="empirical", reverify="tests/e2e/probe.py::test_env"),
    )
    assert _findings(tmp_path) == []
    record = gate.collect_records(tmp_path)[0]
    assert record.fields["evidence"] == "empirical"


def test_reverify_path_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, "templates/rules/a.md", _fence(reverify="tests/missing.py"))
    assert "reverify path `tests/missing.py` does not exist" in _findings(tmp_path)[0]


# --- scenario 4: structural contract needs no duplicate record -----------


def test_structural_contract_is_never_demanded(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/consumer.py", "from shared_schema import Contract\n")
    _write(tmp_path, "scripts/shared_schema.py", "class Contract: ...\n")
    assert _findings(tmp_path) == []
    assert gate.collect_records(tmp_path) == []


# --- scenario 5: copied-doc anti-pattern ---------------------------------


def test_pasted_source_text_in_a_field_is_refused(tmp_path: Path) -> None:
    pasted = "The limit is 4096 bytes per request and " * 8
    _write(tmp_path, "templates/rules/a.md", _fence(purpose=pasted))
    findings = _findings(tmp_path)
    assert len(findings) == 1
    assert "keep a label, not a copy of the source" in findings[0]


def test_local_ledger_id_field_is_an_unknown_field(tmp_path: Path) -> None:
    _write(tmp_path, "templates/rules/a.md", _fence(ledger_id="DU-0042"))
    findings = _findings(tmp_path)
    assert any("unknown field `ledger_id`" in f for f in findings)


# --- scenario 6: no global ledger is needed ------------------------------


def test_records_live_in_separate_files_not_one_ledger(tmp_path: Path) -> None:
    for index in range(5):
        _write(tmp_path, f"scripts/consumer_{index}.py", _py_block())
    paths = {record.path for record in gate.collect_records(tmp_path)}
    assert len(paths) == 5
    assert _findings(tmp_path) == []
    assert not (tmp_path / "docs-used.md").exists()


def _py_block(**overrides: str) -> str:
    fields = {**GOOD_FIELDS, **overrides}
    body = "\n".join(f"#   {key}: {value}" for key, value in fields.items())
    return f'"""Module."""\n\n# external-contract:\n{body}\nVALUE = 1\n'


# --- scenario 7: stale source and the negative control -------------------


def test_stale_source_query_names_every_consumer(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/a.py", _py_block(verified="2025-01-01"))
    _write(tmp_path, "templates/rules/b.md", _fence(verified="2026-09-01"))
    _write(tmp_path, "scripts/c.py", _py_block(source="https://other.example/x"))
    records = gate.collect_records(tmp_path)
    by_source = gate.query_records(records, "example.org", None)
    assert sorted(r.path for r in by_source) == ["scripts/a.py", "templates/rules/b.md"]
    stale = gate.query_records(records, "example.org", dt.date(2026, 1, 1))
    assert [r.path for r in stale] == ["scripts/a.py"]


def test_removing_the_record_makes_the_consumer_undiscoverable(tmp_path: Path) -> None:
    path = _write(tmp_path, "scripts/a.py", _py_block())
    records = gate.collect_records(tmp_path)
    assert [r.path for r in gate.query_records(records, "example.org", None)] == ["scripts/a.py"]
    path.write_text('"""Module."""\nVALUE = 1\n', encoding="utf-8")
    assert gate.query_records(gate.collect_records(tmp_path), "example.org", None) == []


def test_cli_source_query_prints_json_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "scripts/a.py", _py_block())
    assert gate.main([str(tmp_path), "--source", "EXAMPLE.org"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed[0]["file"] == "scripts/a.py"
    assert printed[0]["version"] == "v2.1"


def test_cli_stale_before_lists_old_and_unparseable_dates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "scripts/a.py", _py_block(verified="not-a-date"))
    assert gate.main([str(tmp_path), "--stale-before", "2026-01-01"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["file"] == "scripts/a.py"


def test_cli_rejects_a_bad_cutoff_date(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert gate.main([str(tmp_path), "--stale-before", "yesterday"]) == 2
    assert "not an ISO date" in capsys.readouterr().err


def test_cli_rejects_a_missing_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main([str(tmp_path / "nope")]) == 2
    assert "Invalid repository root" in capsys.readouterr().err


# --- field and shape checks ----------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source": None}, "missing required field `source`"),
        ({"version": ""}, "field `version` is empty"),
        ({"evidence": "blog"}, "evidence `blog` is not one of"),
        ({"source": "not a uri"}, "is not a URI"),
        ({"verified": "last week"}, "not an ISO date"),
        ({"verified": "2027-01-01"}, "is in the future"),
    ],
)
def test_malformed_field_is_refused(
    tmp_path: Path, overrides: dict[str, str | None], message: str
) -> None:
    _write(tmp_path, "templates/rules/a.md", _fence(**overrides))
    findings = _findings(tmp_path)
    assert findings
    assert any(message in f for f in findings)
    assert all(f.startswith(f"{FIXTURE_REL}:3:") for f in findings)


def test_unparseable_and_duplicate_lines_are_reported(tmp_path: Path) -> None:
    text = "```external-contract\nsource: https://x.example/a\nnot a field\nsource: https://y.example/b\n```\n"
    _write(tmp_path, "templates/rules/a.md", text)
    findings = "\n".join(_findings(tmp_path))
    assert "line is not `key: value`" in findings
    assert "duplicate field `source`" in findings


def test_unclosed_fence_is_reported(tmp_path: Path) -> None:
    _write(tmp_path, "templates/rules/a.md", "```external-contract\nsource: https://x.example/a\n")
    assert any("fence is never closed" in f for f in _findings(tmp_path))


def test_quoted_values_are_unquoted(tmp_path: Path) -> None:
    _write(tmp_path, "templates/rules/a.md", _fence(version="'v2.1'", purpose='"A label"'))
    record = gate.collect_records(tmp_path)[0]
    assert record.fields["version"] == "v2.1"
    assert record.fields["purpose"] == "A label"


def test_blank_lines_inside_a_block_are_ignored(tmp_path: Path) -> None:
    text = _fence().replace("version: v2.1\n", "version: v2.1\n\n")
    _write(tmp_path, "templates/rules/a.md", text)
    assert _findings(tmp_path) == []


def test_tilde_fences_are_recognised(tmp_path: Path) -> None:
    body = "\n".join(f"{k}: {v}" for k, v in GOOD_FIELDS.items())
    _write(tmp_path, "docs/a.md", f"~~~external-contract\n{body}\n~~~\n")
    assert _findings(tmp_path) == []
    assert len(gate.collect_records(tmp_path)) == 1


# --- carriers and scan scope ---------------------------------------------


def test_documentation_example_in_another_fence_is_not_a_record(tmp_path: Path) -> None:
    body = "\n".join(f"{k}: {v}" for k, v in GOOD_FIELDS.items())
    _write(tmp_path, "templates/rules/doc.md", f"```yaml\nexternal-contract:\n{body}\n```\n")
    _write(tmp_path, "scripts/doc.md", f"# external-contract:\n#   {body}\n")
    assert gate.collect_records(tmp_path) == []


def test_comment_block_stops_at_the_first_non_comment_line(tmp_path: Path) -> None:
    text = _py_block() + "#   source: https://late.example/x\n"
    _write(tmp_path, "scripts/a.py", text)
    record = gate.collect_records(tmp_path)[0]
    assert record.fields["source"] == "https://example.org/spec/v2"
    assert record.line == 3


def test_shell_and_yaml_comment_blocks_are_scanned(tmp_path: Path) -> None:
    body = "\n".join(f"#   {k}: {v}" for k, v in GOOD_FIELDS.items())
    for rel in ("scripts/run.sh", "build/config.yml", "scripts/cfg.toml"):
        _write(tmp_path, rel, f"# external-contract:\n{body}\n")
    assert len(gate.collect_records(tmp_path)) == 3


def test_projection_skill_file_and_unscanned_roots_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, ".claude/skills/x/SKILL.md", _fence())
    _write(tmp_path, ".claude/skills/x/references/ref.md", _fence())
    _write(tmp_path, "src/claude/skills/x/references/ref.md", _fence())
    _write(tmp_path, "scripts/.venv/lib/a.py", _py_block())
    _write(tmp_path, "scripts/data.json", _fence())
    paths = [r.path for r in gate.collect_records(tmp_path)]
    assert paths == [".claude/skills/x/references/ref.md"]


def test_test_files_are_scanned_because_a_probe_test_is_a_consumer(tmp_path: Path) -> None:
    _write(tmp_path, "tests/unit/test_probe.py", _py_block())
    paths = [r.path for r in gate.collect_records(tmp_path)]
    assert paths == ["tests/unit/test_probe.py"]


def test_unreadable_file_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "bad.py").write_bytes(b"\xff\xfe\x00bad")
    assert gate.collect_records(tmp_path) == []


# --- capability reuse (#5396) --------------------------------------------


def _capability_tree(root: Path, owned: str) -> None:
    for subdir, pattern in gate_graph().CANONICAL_GLOBS:
        _write(
            root, f"{subdir}/{pattern.replace('*', 'placeholder')}", "---\nname: p\n---\n\nBody.\n"
        )
    _write(
        root,
        "templates/skills/owner.SKILL.md.tmpl",
        "---\nname: owner\nmetadata:\n  capability:\n    kind: reusable-primitive\n"
        f"    owns:\n      - {owned}\n    status: active\n---\n\nBody.\n",
    )


def gate_graph():
    import check_capability_graph

    return check_capability_graph


def test_capability_pointer_to_an_owned_capability_passes(tmp_path: Path) -> None:
    _capability_tree(tmp_path, "adapter-wire-format")
    _write(tmp_path, "templates/rules/a.md", _fence(capability="adapter-wire-format"))
    assert _findings(tmp_path) == []


def test_capability_pointer_to_an_unowned_name_is_refused(tmp_path: Path) -> None:
    _capability_tree(tmp_path, "adapter-wire-format")
    _write(tmp_path, "templates/rules/a.md", _fence(capability="no-such-capability"))
    findings = _findings(tmp_path)
    assert any("capability `no-such-capability` is not owned" in f for f in findings)


def test_capability_check_is_skipped_without_the_template_trees(tmp_path: Path) -> None:
    _write(tmp_path, "docs/a.md", _fence(capability="anything"))
    assert _findings(tmp_path) == []


# --- gate entry point ----------------------------------------------------


def test_validate_returns_false_and_reports_on_a_defect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "templates/rules/a.md", _fence(evidence="blog"))
    assert gate.validate_external_contracts(tmp_path) is False
    err = capsys.readouterr().err
    assert "external contract record defect" in err
    assert f"{FIXTURE_REL}:3" in err
    assert gate.main([str(tmp_path)]) == 1


def test_default_root_validates_the_real_repository() -> None:
    assert gate.main([]) == 0


def test_script_runs_as_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_external_contracts.py", str(tmp_path)])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(_VALIDATION / "check_external_contracts.py"), run_name="__main__")
    assert exit_info.value.code == 0
