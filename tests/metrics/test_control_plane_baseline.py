"""Tests for control_plane_baseline.py (REQ-021, TASK-024-AC5/AC6).

Positive, negative, edge, CLI exit-code, parity (AC-06), reproducibility
(AC-11), and no-content-leak (AC-09) coverage, plus the exit-0-regardless
matrix that makes DR1 verifiable (AC-08). ``repo`` builds a small git
fixture with known counts for all seven dimensions (``fanout_residue``
removed, review F2); dimension-level edge cases use a bare ``tmp_path``
instead, since only ``main()`` needs a real repository.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci.lefthook_budget_model import REPO_ROOT, declared_budget, load_config
from scripts.metrics import control_plane_baseline as cpb
from scripts.validation.token_budget import estimate_token_count
from tests.gc_real_git import git, write_and_commit

_ALWAYS_ON_RULE = '---\npaths: ["**"]\n---\n\n# Always on\n'
_SCOPED_RULE = '---\npaths: ["tests/**"]\n---\n\n# Scoped\n'
_ALWAYS_ON_INSTRUCTION = "---\napplyTo: '**'\n---\n\n# Always on instruction\n"
_LEFTHOOK_YML = """\
pre-commit:
  piped: true
  jobs:
    - name: job-a
      run: echo a
      timeout: 10s
    - name: job-b
      run: echo b
      timeout: 5s
pre-push:
  piped: true
  jobs:
    - name: job-c
      group:
        parallel: true
        jobs:
          - name: job-c1
            run: echo c1
            timeout: 20s
          - name: job-c2
            run: echo c2
            timeout: 30s
"""
_SETTINGS_JSON = json.dumps(
    {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": "a"},
                        {"type": "command", "command": "b"},
                    ]
                }
            ]
        }
    }
)
_MATRIX_JSON = json.dumps(
    {
        "harnesses": [
            {
                "capabilities": {
                    "a": {"status": "VERIFIED"},
                    "b": {"status": "UNVERIFIED"},
                    "c": {"status": "UNVERIFIED"},
                }
            }
        ]
    }
)


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small git repo with a known, hand-countable value for every dimension."""
    root = tmp_path / "fixture-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")

    _write(root, "CLAUDE.md", "claude root file\n")
    _write(root, "AGENTS.md", "See `skill-one` for routing details.\n")
    _write(root, ".claude/CLAUDE.md", "claude nested file\n")
    _write(root, ".github/copilot-instructions.md", "copilot root file\n")
    _write(root, ".claude/agents/a1.md", "agent one\n")
    _write(root, ".claude/agents/a2.md", "agent two\n")
    _write(root, ".claude/skills/skill-one/SKILL.md", "skill one\n")
    _write(root, ".claude/skills/skill-two/SKILL.md", "skill two\n")
    _write(root, ".claude/skills/autoplan/SKILL.md", "Route via /skill-two for details.\n")
    _write(root, ".claude/rules/always.md", _ALWAYS_ON_RULE)
    _write(root, ".claude/rules/scoped.md", _SCOPED_RULE)
    _write(root, ".claude/hooks/hook_one.py", "# a claude hook\n")
    _write(root, ".claude/settings.json", _SETTINGS_JSON)
    _write(root, "scripts/validation/check_foo.py", "# validator\n")
    _write(root, "scripts/validation/checks_bar.py", "# validator\n")
    _write(root, "scripts/validate_baz.py", "# validator\n")
    _write(root, "scripts/validation/nested/validate_deep.py", "# nested validator\n")
    _write(root, "scripts/validation/tests/check_excluded.py", "# excluded: tests\n")
    _write(root, "scripts/validation/__pycache__/checks_excluded.py", "# excluded: pycache\n")
    _write(root, ".github/workflows/ci.yml", "name: ci\n")
    _write(root, "lefthook.yml", _LEFTHOOK_YML)
    _write(root, ".github/instructions/always.instructions.md", _ALWAYS_ON_INSTRUCTION)
    _write(root, "src/copilot-cli/instructions/one.instructions.md", "generated instruction\n")
    _write(root, ".agents/architecture/ADR-001-foo.md", "an adr\n")
    _write(root, ".agents/governance/bar.md", "governance doc\n")
    _write(root, ".serena/memories/foo.md", "a memory\n")
    _write(root, ".agents/memory/episodes/e1.json", "{}\n")
    _write(root, ".agents/sessions/s1.md", "a session\n")
    _write(root, ".agents/archive/a1.md", "archived\n")
    _write(root, ".agents/eval-results/r1.json", "{}\n")
    _write(root, "scripts/eval/examples/harness-capability-matrix.json", _MATRIX_JSON)
    _write(root, "tests/skills/skill-one/test_placeholder.py", "# placeholder\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


def test_positive_all_dimensions_present_with_known_counts(repo: Path) -> None:
    baseline = cpb.build_baseline(repo, "control_plane_baseline.py --repo .")
    dims = baseline.dimensions
    assert set(dims) == {
        "canonical",
        "policy_owners",
        "always_loaded",
        "generated_historical",
        "gate_budget",
        "activation",
        "accepted_tasks",
    }

    canonical = dims["canonical"]
    assert canonical["agents"] == 2
    assert canonical["skills"] == 3
    assert canonical["rules"] == 2
    assert "hooks" not in canonical  # review F5: combined key dropped, double counted
    assert canonical["hooks_by_event"] == {"SessionStart": 2}
    assert canonical["hooks_python_files"] == 1
    # review F4: rglob under scripts/; fixture adds a nested validator, plus a
    # decoy each under tests/ and __pycache__/, both excluded.
    assert canonical["validators"] == 4
    assert canonical["workflows"] == 1
    assert canonical["lefthook_jobs"] == 5
    assert canonical["lefthook_jobs_by_hook"] == {"pre-commit": 2, "pre-push": 3}

    policy = dims["policy_owners"]
    assert policy["rule_mirrors"] == {"github_instructions": 1, "copilot_cli_instructions": 1}
    assert policy["adrs"] == 1
    assert policy["governance_docs"] == 1
    assert policy["serena_memories"] == 1
    assert policy["always_on"]["claude_rules"] == [".claude/rules/always.md"]
    assert policy["always_on"]["github_instructions"] == [
        ".github/instructions/always.instructions.md"
    ]

    loaded = dims["always_loaded"]  # _measure_harness_load already sorts files_listed
    assert loaded["claude_code"]["files"] == [
        ".claude/CLAUDE.md",
        ".claude/rules/always.md",
        "AGENTS.md",
        "CLAUDE.md",
    ]
    assert loaded["copilot"]["files"] == [
        ".github/copilot-instructions.md",
        ".github/instructions/always.instructions.md",
        "AGENTS.md",
    ]
    assert loaded["codex"]["files"] == ["AGENTS.md"]
    expected_agents_tokens = estimate_token_count((repo / "AGENTS.md").read_text(encoding="utf-8"))
    assert loaded["codex"]["tokens"] == expected_agents_tokens

    hist = dims["generated_historical"]
    for key in ("episodes", "sessions", "archive", "eval_results"):
        assert hist[key]["count"] == 1
    projections = hist["generated_projections"]
    assert projections["copilot_cli_src"]["count"] == 1
    assert projections["github_instructions"]["count"] == 1

    assert dims["gate_budget"] == {"seconds_by_hook": {"pre-commit": 15.0, "pre-push": 30.0}}
    # review F3: structured refs only (AGENTS.md backticks skill-one, autoplan slashes skill-two).
    assert dims["activation"]["referenced_count"] == 2
    assert set(dims["activation"]["referenced_names"]) == {"skill-one", "skill-two"}
    assert dims["activation"]["tested_count"] == 1
    assert dims["activation"]["tested_names"] == ["skill-one"]
    assert dims["accepted_tasks"] == {"verified": 1, "unverified": 2, "other": 0, "total": 3}
    assert baseline.exclusions == []
    # review F1: release_targets is populated by the script, not hand-typed.
    owner_total = 2 + 3 + 2 + 2 + 4 + 1 + 5  # agents+skills+rules+hooks+validators+workflows+jobs
    metrics = {t["metric"]: t for t in baseline.release_targets}
    assert metrics["canonical owner total"]["target"] == f"strictly below {owner_total}"
    claude_tokens = dims["always_loaded"]["claude_code"]["tokens"]
    target = metrics["always_loaded.claude_code.tokens"]["target"]
    assert target == f"strictly below {claude_tokens}"
    assert (
        metrics["gate_budget.seconds_by_hook.pre-push"]["target"]
        == "must not rise above 30.0 seconds"
    )


def test_positive_cli_writes_json_and_markdown_with_all_seven_keys(
    repo: Path, tmp_path: Path
) -> None:
    json_path = tmp_path / "out.json"
    md_path = tmp_path / "out.md"
    rc = cpb.main(["--repo", str(repo), "--json", str(json_path), "--markdown", str(md_path)])
    assert rc == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(data["dimensions"]) == {
        "canonical",
        "policy_owners",
        "always_loaded",
        "generated_historical",
        "gate_budget",
        "activation",
        "accepted_tasks",
    }
    assert data["commit_sha"]
    assert data["release_targets"], "release_targets must be populated by the script (review F1)"
    md_text = md_path.read_text(encoding="utf-8")
    assert "# Control-plane baseline" in md_text
    assert "## canonical" in md_text
    assert "## Exclusions" in md_text
    # review F1: Measurement command/Release targets are script-rendered, not hand-typed.
    assert "## Measurement command" in md_text
    assert data["command"] in md_text
    assert "any clean checkout" in md_text.lower()
    assert "## Definitions" in md_text
    for glob in cpb.VALIDATOR_GLOBS:  # review F4: globs documented in the markdown
        assert glob in md_text
    assert "## Release targets for v0.7.0" in md_text
    assert "canonical owner total" in md_text
    assert "fanout_residue dimension was removed" in md_text  # review F2 exclusion note
    # review F1: no more 200-line bullet dump, one compact table per dimension.
    assert "| key | value |" in md_text


def test_negative_dirty_tree_needs_allow_dirty(repo: Path, tmp_path: Path) -> None:
    (repo / "AGENTS.md").write_text("dirty change\n", encoding="utf-8")
    json_path = tmp_path / "out.json"
    assert cpb.main(["--repo", str(repo), "--json", str(json_path)]) == 1
    assert not json_path.exists()
    assert cpb.main(["--repo", str(repo), "--json", str(json_path), "--allow-dirty"]) == 0
    assert json_path.exists()


def test_negative_missing_or_non_git_repo_path_exits_2(tmp_path: Path) -> None:
    assert cpb.main(["--repo", str(tmp_path / "does-not-exist")]) == 2
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    assert cpb.main(["--repo", str(plain_dir)]) == 2


def test_negative_symlinked_json_target_exits_1_and_refuses_write(
    repo: Path, tmp_path: Path
) -> None:
    real_target = tmp_path / "real.json"
    real_target.write_text("do not overwrite\n", encoding="utf-8")
    symlink_path = tmp_path / "out.json"
    symlink_path.symlink_to(real_target)
    rc = cpb.main(["--repo", str(repo), "--json", str(symlink_path)])
    assert rc == 1
    assert real_target.read_text(encoding="utf-8") == "do not overwrite\n"


def test_edge_missing_directories_degrade_to_zero_with_exclusions(tmp_path: Path) -> None:
    exclusions: list[dict[str, str]] = []
    result = cpb.canonical(tmp_path, exclusions)
    assert result["agents"] == 0
    assert result["skills"] == 0
    assert any(e["dimension"] == "canonical.hooks" for e in exclusions)
    assert any(e["dimension"] == "canonical.lefthook_jobs" for e in exclusions)


def test_edge_scoped_rule_is_not_always_on(repo: Path) -> None:
    exclusions: list[dict[str, str]] = []
    always_on_paths = cpb._always_on_rules(repo, exclusions)
    names = {p.name for p in always_on_paths}
    assert "always.md" in names
    assert "scoped.md" not in names


def test_edge_missing_harness_capability_matrix_degrades_accepted_tasks_to_null(
    tmp_path: Path,
) -> None:
    exclusions: list[dict[str, str]] = []
    result = cpb.accepted_tasks(tmp_path, exclusions)
    assert result is None
    expected_path = tmp_path / "scripts" / "eval" / "examples" / "harness-capability-matrix.json"
    assert exclusions == [{"dimension": "accepted_tasks", "reason": f"missing {expected_path}"}]


def test_edge_single_source_dimensions_degrade_to_null(tmp_path: Path) -> None:
    exclusions: list[dict[str, str]] = []
    assert cpb.gate_budget(tmp_path, exclusions) is None
    assert cpb.activation(tmp_path, exclusions) is None
    dims = {e["dimension"] for e in exclusions}
    assert dims == {"gate_budget", "activation"}


def test_edge_pycache_under_tests_skills_is_not_a_tested_skill(tmp_path: Path) -> None:
    """A bytecode-cache directory is not a tested skill (regression: main checkout)."""
    _write(tmp_path, ".claude/skills/skill-one/SKILL.md", "skill one\n")
    _write(tmp_path, "tests/skills/skill-one/test_placeholder.py", "# placeholder\n")
    _write(tmp_path, "tests/skills/__pycache__/cache.pyc", "not real bytecode\n")
    _write(tmp_path, "tests/skills/.hidden/marker", "should also be excluded\n")
    exclusions: list[dict[str, str]] = []
    result = cpb.activation(tmp_path, exclusions)
    assert result is not None
    assert result["tested_names"] == ["skill-one"]


def test_ac08_synthetic_extreme_values_never_change_exit_code(
    monkeypatch: pytest.MonkeyPatch, repo: Path, tmp_path: Path
) -> None:
    """Extreme (10**9) but real-shaped values must never flip the exit code (DR1)."""
    n = 10**9
    simple_fields = (
        "agents",
        "skills",
        "rules",
        "hooks_python_files",
        "validators",
        "workflows",
        "lefthook_jobs",
    )
    huge_canonical: dict[str, object] = dict.fromkeys(simple_fields, n)
    huge_canonical |= {"hooks_by_event": {"x": n}, "lefthook_jobs_by_hook": {"x": n}}
    huge_gate_budget = {"seconds_by_hook": {"pre-commit": n, "pre-push": n}}
    huge_loaded = {
        h: {"bytes": n, "tokens": n, "files": []} for h in ("claude_code", "copilot", "codex")
    }
    huge_activation = {
        "referenced_count": n,
        "referenced_names": [],
        "tested_count": n,
        "tested_names": [],
    }
    huge_accepted = {"verified": n, "unverified": n, "other": 0, "total": 2 * n}

    monkeypatch.setattr(cpb, "canonical", lambda repo, exclusions: huge_canonical)
    monkeypatch.setattr(cpb, "gate_budget", lambda repo, exclusions: huge_gate_budget)
    monkeypatch.setattr(cpb, "always_loaded", lambda repo, exclusions: huge_loaded)
    monkeypatch.setattr(cpb, "activation", lambda repo, exclusions: huge_activation)
    monkeypatch.setattr(cpb, "accepted_tasks", lambda repo, exclusions: huge_accepted)

    json_path = tmp_path / "extreme.json"
    rc = cpb.main(["--repo", str(repo), "--json", str(json_path), "--allow-dirty"])
    assert rc == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["dimensions"]["canonical"]["agents"] == n
    metrics = {t["metric"]: t for t in data["release_targets"]}
    assert metrics["canonical owner total"]["target"] == f"strictly below {7 * n}"


def test_ac08_none_for_every_dimension_still_exits_0(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    for name in ("gate_budget", "activation", "accepted_tasks"):
        monkeypatch.setattr(cpb, name, lambda repo, exclusions: None)
    rc = cpb.main(["--repo", str(repo), "--allow-dirty"])
    assert rc == 0


def test_parity_gate_budget_matches_declared_budget_on_this_repository() -> None:
    exclusions: list[dict[str, str]] = []
    ours = cpb.gate_budget(REPO_ROOT, exclusions)
    assert ours is not None
    config = load_config()
    for hook in ("pre-commit", "pre-push"):
        expected_total, _rows = declared_budget(config, hook)
        assert ours["seconds_by_hook"][hook] == expected_total


def test_reproducibility_two_runs_produce_identical_dimensions_and_exclusions(repo: Path) -> None:
    first = cpb.build_baseline(repo, "cmd")
    second = cpb.build_baseline(repo, "cmd")
    assert first.dimensions == second.dimensions
    assert first.exclusions == second.exclusions
    assert first.commit_sha == second.commit_sha


def test_no_content_leak_secret_shaped_rule_body_never_reaches_output(
    repo: Path, tmp_path: Path
) -> None:
    secret = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"  # 40 hex chars, hex-secret shape
    write_and_commit(
        repo,
        ".claude/rules/with-secret.md",
        f'---\npaths: ["**"]\n---\n\nBody carries {secret}.\n',
        "add secret-bearing rule",
    )
    json_path = tmp_path / "out.json"
    rc = cpb.main(["--repo", str(repo), "--json", str(json_path)])
    assert rc == 0
    text = json_path.read_text(encoding="utf-8")
    assert secret not in text
    for value in dataclasses.asdict(cpb.build_baseline(repo, "cmd")).values():
        assert secret not in json.dumps(value)


def test_cli_entry_point_via_subprocess(repo: Path, tmp_path: Path) -> None:
    json_path = tmp_path / "sub.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "metrics" / "control_plane_baseline.py"),
            "--repo",
            str(repo),
            "--json",
            str(json_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert json_path.exists()


def test_frontmatter_paths_handles_string_and_invalid_yaml() -> None:
    assert cpb._frontmatter_paths('---\npaths: "single-glob/**"\n---\n') == {"single-glob/**"}
    assert cpb._frontmatter_paths("no frontmatter here") == set()
    assert cpb._frontmatter_paths("---\n[invalid: yaml: here\n---\n") == set()
    assert cpb._frontmatter_paths("---\npaths: 5\n---\n") == set()


def test_lefthook_config_rejects_non_mapping_or_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "lefthook.yml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    assert cpb._lefthook_config(tmp_path) is None
    path.write_text("pre-commit: [unterminated\n", encoding="utf-8")
    assert cpb._lefthook_config(tmp_path) is None


def test_safe_open_refuses_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    with pytest.raises(cpb.SymlinkRefusedError):
        cpb._safe_open(link)


def test_git_output_raises_runtime_error_on_failure(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        cpb._git_output(tmp_path, ["rev-parse", "HEAD"])


def test_validator_count_sums_all_three_patterns_recursively(tmp_path: Path) -> None:
    """review F4: recursive under scripts/, excluding tests/ and __pycache__/."""
    assert cpb._validator_count(tmp_path) == 0  # missing scripts/ is zero, not an error
    _write(tmp_path, "scripts/validation/check_a.py", "")
    _write(tmp_path, "scripts/validation/checks_b.py", "")
    _write(tmp_path, "scripts/validate_c.py", "")
    _write(tmp_path, "scripts/validation/nested/deep/validate_d.py", "")
    _write(tmp_path, "scripts/validation/tests/check_excluded.py", "")
    _write(tmp_path, "scripts/validation/__pycache__/checks_excluded.py", "")
    assert cpb._validator_count(tmp_path) == 4


def test_job_names_ignores_non_dict_entries() -> None:
    acc: list[str] = []
    cpb._job_names([{"name": "a"}, "not-a-dict", {"group": {"jobs": [{"name": "b"}]}}], acc)
    assert acc == ["a", "b"]


def test_skill_referenced_matches_structured_forms_only() -> None:
    """review F3: backticked, slash-prefixed, or skills/name path segment only."""
    assert cpb._skill_referenced("test", "Run the `test` skill.")
    assert cpb._skill_referenced("test", "Invoke /test now.")
    assert cpb._skill_referenced("test", "See .claude/skills/test/SKILL.md for details.")
    assert not cpb._skill_referenced("test", "Run a runtime test suite.")
    assert not cpb._skill_referenced("autoplan", "autoplan handles routing.")
    assert not cpb._skill_referenced("test", "contest this")
    assert not cpb._skill_referenced("test", "/testing is a different skill")


def test_lefthook_config_reuses_shared_load_config() -> None:
    """review F7: no second parse-and-validate implementation."""
    from scripts.ci.lefthook_budget_model import load_config as shared_load_config

    assert cpb.load_config is shared_load_config
    exclusions: list[dict[str, str]] = []
    assert cpb.gate_budget(REPO_ROOT, exclusions) is not None
