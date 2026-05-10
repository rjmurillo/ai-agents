"""Tests for orphan-ref-validator scan.py.

Covers REQ-008 acceptance criteria:
- AC2: skill_name detection (positive + negative)
- AC4: count_claim detection (positive + negative + warn-when-undeterminable)
- AC5: ADR-056 envelope + VERDICT line
- AC6: vendored install (missing target path -> skip, no raise)
- AC9: edge cases (empty file, mixed living+dead refs)
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load scan.py via a spec keyed to this file's location so the test suite
# does not collide with a sibling mirror at src/copilot-cli/skills/.../tests/
# that imports a bare module name. The stable cache key prevents two test
# suites from racing on sys.modules["scan"]. Use Path.parts (cross-platform)
# rather than substring matching against str(_SCRIPT_DIR); on Windows the
# substring "claude/skills" never matches because the separator is "\\".
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_PARTS = _SCRIPT_DIR.parts
_MODULE_KEY = (
    "_orphan_ref_validator_scan"
    if ".claude" in _PARTS
    else "_orphan_ref_validator_scan_mirror"
)
sys.path.insert(0, str(_SCRIPT_DIR))
_spec = importlib.util.spec_from_file_location(_MODULE_KEY, _SCRIPT_DIR / "scan.py")
assert _spec is not None and _spec.loader is not None
_scan = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_KEY] = _scan
_spec.loader.exec_module(_scan)

Finding = _scan.Finding
ScanResult = _scan.ScanResult
extract_count_claims = _scan.extract_count_claims
extract_script_refs = _scan.extract_script_refs
extract_skill_refs = _scan.extract_skill_refs
enumerate_count = _scan.enumerate_count
enumerate_skills = _scan.enumerate_skills
main = _scan.main
render_envelope = _scan.render_envelope
scan = _scan.scan


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Build a minimal repo layout with two living skills and one agent.

    fake_repo is nested under tmp_path so tests can place files in
    tmp_path that are outside the repo root.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    skills = repo / ".claude" / "skills"
    skills.mkdir(parents=True)
    for name in ("alpha-skill", "beta-skill"):
        d = skills / name
        d.mkdir()
        (d / "SKILL.md").write_text("# stub\n", encoding="utf-8")
    agents = repo / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "agent-one.md").write_text("# agent\n", encoding="utf-8")
    (repo / ".git").mkdir()
    return repo


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------- extractor unit tests ----------


def test_extract_skill_refs_kebab_in_backticks():
    text = "Use `alpha-skill` and not `beta-skill`."
    refs = list(extract_skill_refs(text))
    assert (1, "alpha-skill") in refs
    assert (1, "beta-skill") in refs


def test_extract_skill_refs_ignores_inline_kebab_outside_backticks():
    text = "alpha-skill mentioned without backticks"
    assert list(extract_skill_refs(text)) == []


def test_extract_script_refs_full_path_match():
    text = "See `build/scripts/foo.py` for details."
    refs = list(extract_script_refs(text))
    assert refs == [(1, "build/scripts/foo.py")]


def test_extract_count_claims_matches_canonical_labels():
    text = "Toolkit: 67 reusable skills, 23 agents, 12 slash commands, 30 lifecycle hooks."
    claims = list(extract_count_claims(text))
    kinds = [(c, k) for _, c, k in claims]
    assert (67, "reusable skill") in kinds
    assert (23, "agent") in kinds
    assert (12, "slash command") in kinds
    assert (30, "lifecycle hook") in kinds


def test_extract_count_claims_does_not_match_unknown_kinds():
    text = "We have 5 cats and 99 problems."
    assert list(extract_count_claims(text)) == []


# ---------- enumerator tests ----------


def test_enumerate_skills_returns_set(fake_repo):
    assert enumerate_skills(fake_repo) == {"alpha-skill", "beta-skill"}


def test_enumerate_skills_handles_missing_dir(tmp_path):
    assert enumerate_skills(tmp_path) is None


def test_enumerate_count_skills_canonical_label(fake_repo):
    assert enumerate_count(fake_repo, "reusable skill") == 2


def test_enumerate_count_skills_legacy_alias(fake_repo):
    assert enumerate_count(fake_repo, "skills") == 2


def test_enumerate_count_agents_canonical_label(fake_repo):
    assert enumerate_count(fake_repo, "agent") == 1


def test_enumerate_count_returns_none_when_dir_missing(tmp_path):
    assert enumerate_count(tmp_path, "reusable skill") is None
    assert enumerate_count(tmp_path, "skills") is None
    assert enumerate_count(tmp_path, "agent") is None


def test_enumerate_count_unknown_kind_returns_none(fake_repo):
    assert enumerate_count(fake_repo, "elephants") is None


# ---------- AC2: skill_name detection ----------


def test_ac2_orphan_skill_name_yields_critical_finding(fake_repo):
    target = fake_repo / "docs" / "stale.md"
    write(target, "Use the `gamma-skill` for things.\n")
    result = scan([target], fake_repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    assert len(skill_findings) == 1
    f = skill_findings[0]
    assert f.severity == "critical"
    assert f.referenced_entity == "gamma-skill"
    assert f.line == 1
    assert result.verdict == "CRITICAL_FAIL"


def test_ac2_living_skill_name_yields_no_finding(fake_repo):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Use `alpha-skill` and `beta-skill`.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert result.verdict == "PASS"


def test_ac2_known_kebab_words_excluded(fake_repo):
    target = fake_repo / "docs" / "prose.md"
    write(target, "This is `well-known` and `open-source`.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []


# ---------- AC3: script_path detection ----------


def test_ac3_missing_script_path_yields_critical_finding(fake_repo):
    target = fake_repo / "docs" / "spec.md"
    write(target, "Run `build/scripts/nonexistent.py` for the thing.\n")
    result = scan([target], fake_repo)
    script_findings = [f for f in result.findings if f.kind == "script_path"]
    assert len(script_findings) == 1
    f = script_findings[0]
    assert f.severity == "critical"
    assert f.referenced_entity == "build/scripts/nonexistent.py"


def test_ac3_existing_script_path_yields_no_finding(fake_repo):
    target = fake_repo / "docs" / "spec.md"
    real = fake_repo / "build" / "scripts" / "real.py"
    write(real, "# real script\n")
    write(target, "Run `build/scripts/real.py` for the thing.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "script_path"] == []


# ---------- AC4: count_claim detection ----------


def test_ac4_count_extraction_runs_but_findings_delegated(fake_repo):
    """Per canonical-source-mirror.md, count_claim enforcement is delegated
    to build/scripts/validate_marketplace_counts.py. orphan-ref-validator
    extracts the claim (refs_checked increments) but emits no Finding."""
    plugin = fake_repo / ".claude-plugin" / "marketplace.json"
    write(plugin, '{"description": "Catalog has 99 reusable skills total."}')
    result = scan([plugin], fake_repo)
    assert [f for f in result.findings if f.kind == "count_claim"] == []
    # Refs are still counted so observability of detection coverage works.
    assert result.refs_checked >= 1


def test_ac4_count_match_yields_no_finding(fake_repo):
    plugin = fake_repo / ".claude-plugin" / "marketplace.json"
    write(plugin, '{"description": "Catalog has 2 reusable skills."}')
    result = scan([plugin], fake_repo)
    assert [f for f in result.findings if f.kind == "count_claim"] == []


def test_ac4_count_only_in_manifest_files(fake_repo):
    target = fake_repo / "docs" / "prose.md"
    write(target, "We have 99 reusable skills.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "count_claim"] == []


# ---------- AC5: envelope + verdict ----------


def test_ac5_envelope_shape_and_verdict_line(fake_repo, capsys):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Hello world\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
        "--output", "json",
    ])
    assert rc == 0
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured[-1].startswith("VERDICT:")
    body = "\n".join(captured[:-1])
    payload = json.loads(body)
    assert set(payload.keys()) == {"Success", "Data", "Error", "Metadata"}
    assert "verdict" in payload["Data"]
    assert "findings" in payload["Data"]
    assert "counts" in payload["Data"]
    assert payload["Metadata"]["Script"] == "scan.py"


def test_ac5_human_output_includes_verdict_line(fake_repo, capsys):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Hello\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
        "--output", "human",
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "VERDICT: PASS" in captured


# ---------- AC6: vendored install scenario ----------


def test_ac6_missing_target_path_does_not_raise(fake_repo, caplog):
    missing = fake_repo / "no-such-dir"
    with caplog.at_level("INFO"):
        result = scan([missing], fake_repo)
    assert result.verdict == "PASS"
    assert result.findings == []
    assert any("skipping" in r.getMessage() for r in caplog.records)


def test_ac6_default_targets_skip_when_absent(fake_repo, capsys):
    rc = main(["--repo-root", str(fake_repo), "--output", "json"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "VERDICT: PASS" in captured


def test_ac6_paths_outside_repo_are_skipped(tmp_path, fake_repo, caplog):
    other = tmp_path / "other"
    other.mkdir()
    target = other / "x.md"
    write(target, "content\n")
    with caplog.at_level("WARNING"):
        result = scan([target], fake_repo)
    assert any("outside repo root" in r.getMessage() for r in caplog.records)
    assert result.verdict == "PASS"


# ---------- AC9: edge cases ----------


def test_ac9_empty_file_yields_pass(fake_repo):
    target = fake_repo / "docs" / "empty.md"
    write(target, "")
    result = scan([target], fake_repo)
    assert result.verdict == "PASS"
    assert result.findings == []


def test_ac9_mixed_living_and_dead_refs(fake_repo):
    target = fake_repo / "docs" / "mixed.md"
    write(
        target,
        "Use `alpha-skill` and `dead-skill`. Run `build/scripts/missing.py`.\n",
    )
    result = scan([target], fake_repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    script_findings = [f for f in result.findings if f.kind == "script_path"]
    assert {f.referenced_entity for f in skill_findings} == {"dead-skill"}
    assert {f.referenced_entity for f in script_findings} == {"build/scripts/missing.py"}
    assert result.verdict == "CRITICAL_FAIL"


def test_ac9_directory_target_walks_files(fake_repo):
    target_dir = fake_repo / "docs"
    write(target_dir / "a.md", "Use `alpha-skill`.\n")
    write(target_dir / "b.md", "Use `dead-skill`.\n")
    result = scan([target_dir], fake_repo)
    bad = [f for f in result.findings if f.kind == "skill_name"]
    assert {f.referenced_entity for f in bad} == {"dead-skill"}


def test_ac9_secret_files_skipped(fake_repo):
    target_dir = fake_repo / "docs"
    write(target_dir / ".env.local", "Use `dead-skill`.\n")
    write(target_dir / "ok.md", "Use `alpha-skill`.\n")
    result = scan([target_dir], fake_repo)
    files = {f.target_file for f in result.findings}
    assert not any(".env" in p for p in files)


def test_ac9_large_files_skipped(fake_repo, caplog):
    target = fake_repo / "docs" / "huge.md"
    write(target, "X" * (5 * 1024 * 1024 + 1))
    with caplog.at_level("WARNING"):
        result = scan([target], fake_repo)
    assert any("exceeds" in r.getMessage() for r in caplog.records)
    assert result.verdict == "PASS"


# ---------- exit code tests ----------


def test_exit_code_pass(fake_repo, capsys):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Use `alpha-skill`.\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
    ])
    assert rc == 0


def test_exit_code_critical_fail(fake_repo, capsys):
    target = fake_repo / "docs" / "bad.md"
    write(target, "Use `dead-skill`.\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
    ])
    assert rc == 1


def test_exit_code_warn_does_not_block(fake_repo, capsys):
    """A scan with no critical findings must exit 0. With count_claim
    enforcement delegated, this manifest produces zero findings -> PASS,
    which still satisfies the WARN-does-not-block contract."""
    plugin = fake_repo / ".claude-plugin" / "marketplace.json"
    write(plugin, '{"description": "Catalog has 5 agents."}')
    rc = main([
        "--targets", str(plugin),
        "--repo-root", str(fake_repo),
    ])
    assert rc == 0


# ---------- render_envelope direct tests ----------


def test_render_envelope_json_carries_findings(fake_repo):
    result = ScanResult(
        findings=[
            Finding(
                kind="skill_name",
                severity="critical",
                target_file="x.md",
                line=2,
                referenced_entity="ghost",
                recommendation="restore or remove",
            )
        ],
        files_scanned=1,
        refs_checked=3,
    )
    out = render_envelope(result, "json")
    payload = json.loads(out.split("\nVERDICT:")[0])
    assert payload["Data"]["verdict"] == "CRITICAL_FAIL"
    assert payload["Data"]["counts"]["files_scanned"] == 1
    assert payload["Data"]["findings"][0]["referenced_entity"] == "ghost"
    assert out.strip().endswith("VERDICT: CRITICAL_FAIL")


def test_render_envelope_human_lists_findings(fake_repo):
    result = ScanResult(
        findings=[
            Finding(
                kind="script_path",
                severity="critical",
                target_file="x.md",
                line=4,
                referenced_entity="scripts/missing.py",
                recommendation="restore or remove",
            )
        ],
    )
    out = render_envelope(result, "human")
    assert "[critical]" in out
    assert "x.md:4" in out
    assert "VERDICT: CRITICAL_FAIL" in out


# ---------- ADR-056: Success contract ----------


def test_adr056_success_true_on_critical_fail(fake_repo, capsys):
    target = fake_repo / "docs" / "bad.md"
    write(target, "Use `dead-skill`.\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
        "--output", "json",
    ])
    assert rc == 1
    captured = capsys.readouterr().out.strip().splitlines()
    body = "\n".join(captured[:-1])
    payload = json.loads(body)
    # ADR-056: Success reflects scan execution, not finding presence.
    assert payload["Success"] is True
    assert payload["Data"]["verdict"] == "CRITICAL_FAIL"
    assert payload["Error"] is None


# ---------- _resolve_repo_root validation ----------


def test_invalid_repo_root_returns_config_error(tmp_path, capsys):
    bogus = tmp_path / "does-not-exist"
    rc = main([
        "--repo-root", str(bogus),
        "--targets", str(tmp_path / "noop.md"),
    ])
    assert rc == 2


def test_repo_root_pointing_at_file_returns_config_error(tmp_path, capsys):
    f = tmp_path / "regular-file"
    f.write_text("not a directory")
    rc = main([
        "--repo-root", str(f),
        "--targets", str(tmp_path / "noop.md"),
    ])
    assert rc == 2


# ---------- walk pruning + symlink containment ----------


def test_walk_prunes_excluded_directories(fake_repo):
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Use `alpha-skill`.\n")
    nm = docs / "node_modules" / "pkg"
    write(nm / "trap.md", "Use `dead-skill`.\n")
    refs = docs / "references"
    write(refs / "trap.md", "Use `dead-skill`.\n")
    result = scan([docs], fake_repo)
    bad = [f for f in result.findings if f.kind == "skill_name"]
    assert bad == []


def test_skill_name_warn_when_catalog_absent(tmp_path):
    """A vendored install without .claude/skills/ should not produce critical
    findings on backticked kebab tokens; downgrade to warn."""
    repo = tmp_path / "vendored"
    repo.mkdir()
    (repo / ".git").mkdir()
    docs = repo / "docs"
    write(docs / "x.md", "Use `dead-skill`.\n")
    result = scan([docs], repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    assert len(skill_findings) == 1
    assert skill_findings[0].severity == "warn"
    # WARN does not block; verdict is WARN, not CRITICAL_FAIL.
    assert result.verdict == "WARN"


def test_skill_name_critical_when_catalog_empty(tmp_path):
    """An empty .claude/skills/ is authoritative: emit critical for
    backticked kebab tokens."""
    repo = tmp_path / "empty-catalog"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".claude" / "skills").mkdir(parents=True)
    docs = repo / "docs"
    write(docs / "x.md", "Use `dead-skill`.\n")
    result = scan([docs], repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    assert len(skill_findings) == 1
    assert skill_findings[0].severity == "critical"
    assert result.verdict == "CRITICAL_FAIL"


def test_walk_skips_symlink_resolving_outside_repo(tmp_path, fake_repo, caplog):
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Hello\n")
    outside = tmp_path / "outside"
    write(outside / "trap.md", "Use `dead-skill`.\n")
    link = docs / "link.md"
    link.symlink_to(outside / "trap.md")
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert any("outside repo root" in r.getMessage() for r in caplog.records)


def test_walk_skips_symlink_to_directory_outside_repo(tmp_path, fake_repo, caplog):
    """A symlink directory under an allowed target that points outside the
    repo must not be recursed into. CWE-22 / CWE-59 hardening."""
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Use `alpha-skill`.\n")
    outside = tmp_path / "outside_dir"
    write(outside / "trap.md", "Use `dead-skill`.\n")
    link = docs / "external_dir"
    link.symlink_to(outside)
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert any("outside repo root" in r.getMessage() for r in caplog.records)


def test_enumerate_skills_returns_none_when_path_is_file(tmp_path):
    """A vendored install with .claude/skills/ as a regular file (corrupt
    layout, broken symlink) must return None, not raise NotADirectoryError."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").write_text("oops not a directory")
    assert enumerate_skills(tmp_path) is None
    assert enumerate_count(tmp_path, "skills") is None


def test_resolve_repo_root_falls_back_to_cwd_when_no_git(tmp_path, monkeypatch):
    """When no parent has a .git directory, _resolve_repo_root returns CWD."""
    isolated = tmp_path / "no-git-here"
    isolated.mkdir()
    monkeypatch.chdir(isolated)
    rc = main(["--targets", str(isolated)])
    assert rc == 0


def test_glob_target_pattern_expansion(fake_repo):
    """--targets accepts glob patterns that expand against repo_root."""
    skills_dir = fake_repo / ".claude" / "skills"
    (skills_dir / "alpha-skill" / "SKILL.md").write_text(
        "# alpha\nUse `dead-skill` here.\n"
    )
    (skills_dir / "beta-skill" / "SKILL.md").write_text("# beta living-only\n")
    rc = main([
        "--targets", ".claude/skills/*/SKILL.md",
        "--repo-root", str(fake_repo),
    ])
    assert rc == 1


def test_walk_skips_file_symlink_resolving_outside_repo(tmp_path, fake_repo, caplog):
    """A FILE symlink under an allowed dir whose target is outside the
    repo must be skipped at yield time. CWE-22 / CWE-59 hardening."""
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Hello\n")
    outside_file = tmp_path / "outside-target.md"
    write(outside_file, "Use `dead-skill`.\n")
    link = docs / "external_file.md"
    link.symlink_to(outside_file)
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert any("outside repo root" in r.getMessage() for r in caplog.records)


def test_walk_breaks_in_repo_symlink_cycle(tmp_path, fake_repo, caplog):
    """A symlinked directory pointing back to an ancestor inside the
    repo must not cause infinite recursion."""
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Hello\n")
    sub = docs / "sub"
    sub.mkdir()
    write(sub / "leaf.md", "Hello\n")
    # sub/back -> docs (cycle)
    (sub / "back").symlink_to(docs)
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert any("symlink cycle" in r.getMessage() for r in caplog.records)
    assert result.verdict == "PASS"


def test_walk_filters_suffix_on_direct_file_target(fake_repo):
    """A direct file target with a non-scanned suffix should be skipped."""
    target = fake_repo / "notes.txt"
    write(target, "Use `dead-skill`.\n")
    result = scan([target], fake_repo)
    assert result.findings == []
    assert result.files_scanned == 0


def test_max_findings_cap_truncates_with_warn_finding(fake_repo):
    """When findings exceed max_findings, scan halts and appends a warn
    finding so the operator knows the result is partial. The total list
    must never exceed max_findings (one slot is reserved for the
    truncation finding)."""
    docs = fake_repo / "docs"
    # Each line produces one finding for `dead-skill`.
    payload = "\n".join(["Use `dead-skill`." for _ in range(10)])
    write(docs / "huge.md", payload)
    result = scan([docs], fake_repo, max_findings=3)
    truncation = [f for f in result.findings if f.kind == "parse_error"]
    assert len(truncation) == 1
    assert truncation[0].severity == "warn"
    assert "halted" in truncation[0].recommendation.lower()
    # Hard bound: total findings must respect the budget.
    assert len(result.findings) <= 3


def test_render_error_envelope_emitted_on_invalid_repo_root(tmp_path, capsys):
    """ADR-056: exit-2 path must emit the envelope with Success=false and
    a populated Error block. The contract is documented in render_envelope's
    docstring; this test pins it."""
    bogus = tmp_path / "does-not-exist"
    rc = main([
        "--repo-root", str(bogus),
        "--targets", str(tmp_path / "x.md"),
        "--output", "json",
    ])
    assert rc == 2
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured[-1] == "VERDICT: ERROR"
    body = "\n".join(captured[:-1])
    payload = json.loads(body)
    assert payload["Success"] is False
    assert payload["Data"] is None
    assert payload["Error"] is not None
    # Per .agents/schemas/skill-output.schema.json: Code is the integer
    # exit code, Type is the canonical enum.
    assert payload["Error"]["Code"] == 2
    assert payload["Error"]["Type"] == "InvalidParams"
    assert "does not exist" in payload["Error"]["Message"]
