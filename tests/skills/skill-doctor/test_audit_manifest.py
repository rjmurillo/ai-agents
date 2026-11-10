"""Contract tests for the reusable audit manifest (epic #7248, M1)."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

import audit_manifest as am
import pytest
from repository_scope import resolve_repository_scope
from session_discovery import discover_skills
from test_repository_scope import OTHER_UPSTREAM, UPSTREAM, add_worktree, make_clone

RUN_INPUTS = {
    "harness": "copilot",
    "include_global_skills": False,
    "no_worktrees": False,
    "explicit_repos": [],
    "max_sessions": 12,
    "per_skill": 3,
    "no_skill": 4,
    "min_idle_minutes": 15.0,
    "include_subagents": False,
}


def write_skill(repo: Path, name: str, text: str) -> Path:
    path = repo / ".claude" / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def inventory_for(repos, skills=None, sessions=(), expand=True):
    scope = resolve_repository_scope(repos, expand)
    return {
        "conversation_scope": "projects",
        "repos": [str(repo) for repo in repos],
        "harness": "copilot",
        "window_days": 45,
        "scope_resolution": scope.report(sessions),
        "skills": sorted((skills or {}).values(), key=lambda skill: skill["name"]),
        "sessions": list(sessions),
    }


def manifest_for(repos, explicit=None, skills=None, sessions=(), **kwargs):
    inputs = {**RUN_INPUTS, "explicit_repos": [str(r) for r in explicit or []]}
    return am.build_manifest(inventory_for(repos, skills, sessions), inputs, **kwargs)


def restamp(manifest):
    manifest["fingerprint"] = am._fingerprint(manifest)
    return manifest


@pytest.fixture
def family(tmp_path):
    main = make_clone(tmp_path / "clones" / "widgets", UPSTREAM)
    feature = add_worktree(main, tmp_path / "trees" / "feature-a", "feature-a")
    return {"tmp": tmp_path, "main": main, "feature": feature}


def test_repeated_exports_match_after_excluding_timestamps(family):
    first = manifest_for([family["main"]], generated_at="2026-01-01T00:00:00+00:00")
    second = manifest_for([family["main"]], generated_at="2027-06-06T06:06:06+00:00")

    assert first["generated_at"] != second["generated_at"]
    assert first["fingerprint"] == second["fingerprint"]
    assert {k: v for k, v in first.items() if k != "generated_at"} == {
        k: v for k, v in second.items() if k != "generated_at"
    }


def test_fingerprint_changes_when_a_declared_cap_changes(family):
    base = manifest_for([family["main"]])
    inputs = {**RUN_INPUTS, "max_sessions": 99}
    changed = am.build_manifest(inventory_for([family["main"]]), inputs)

    assert changed["fingerprint"] != base["fingerprint"]
    assert changed["evidence_caps"]["max_sessions"] == 99


def test_manifest_declares_inputs_window_caps_branch_policy_and_revision(family):
    manifest = manifest_for([family["main"]], explicit=[family["main"]])

    assert manifest["manifest_version"] == am.MANIFEST_VERSION
    assert manifest["declared_inputs"]["explicit_repos"] == [str(family["main"])]
    assert manifest["declared_inputs"]["conversation_scope"] == "projects"
    assert manifest["window_days"] == 45
    assert set(manifest["evidence_caps"]) == set(am._CAP_KEYS)
    assert manifest["branch_policy"] == {"branch_filter": "none"}
    assert len(manifest["source_revision"]["sha256"]) == 64
    assert am.validate_manifest(manifest) == []


def test_worktree_family_shares_one_identity_and_is_authorized_by_the_selected_root(family):
    manifest = manifest_for([family["feature"]])

    identity = {item["path"]: item for item in manifest["upstream_identity"]}
    assert str(family["main"]) in identity and str(family["feature"]) in identity
    assert {item["common_dir"] for item in identity.values()} == {str(family["main"] / ".git")}
    assert {item["origin_url"] for item in identity.values()} == {UPSTREAM}
    assert {item["evidence"] for item in identity.values()} == {"git-config"}
    assert am.validate_manifest(manifest) == []


def test_unauthorized_clone_is_rejected(family):
    stranger = make_clone(family["tmp"] / "clones-b" / "widgets-copy", UPSTREAM)
    manifest = manifest_for([family["main"]])
    manifest["scope_resolution"]["included"].append(
        {"path": str(stranger), "kind": "main", "reason": "injected", "sessions_considered": 0}
    )
    manifest["upstream_identity"].append(am._identity_for(stranger))
    restamp(manifest)

    errors = am.validate_manifest(manifest)

    assert any("unauthorized root" in e and str(stranger) in e for e in errors)


def test_clone_with_matching_origin_never_joins_without_repo(family):
    stranger = make_clone(family["tmp"] / "clones-b" / "widgets-copy", UPSTREAM)

    manifest = manifest_for([family["main"]])

    paths = {item["path"] for item in manifest["upstream_identity"]}
    assert str(stranger) not in paths
    assert am.validate_manifest(manifest) == []


def test_separate_clones_are_accepted_only_when_each_is_passed_explicitly(family):
    second = make_clone(family["tmp"] / "clones-b" / "widgets-copy", UPSTREAM)
    both = [family["main"], second]

    explicit = manifest_for(both, explicit=both)
    implicit = manifest_for(both, explicit=[])

    assert am.validate_manifest(explicit) == []
    assert any("passed as --repo" in e for e in am.validate_manifest(implicit))


def test_conflicting_origin_within_one_common_dir_is_rejected(family):
    manifest = manifest_for([family["feature"]])
    manifest["upstream_identity"][0]["origin_url"] = OTHER_UPSTREAM
    restamp(manifest)

    errors = am.validate_manifest(manifest)

    assert any("conflicting origin URLs" in e for e in errors)


def test_shared_upstream_claim_matching_evidence_is_accepted(family):
    second = make_clone(family["tmp"] / "clones-b" / "widgets-copy", UPSTREAM + "/")
    claim = [
        {"upstream": UPSTREAM.removesuffix(".git"), "roots": [str(family["main"]), str(second)]}
    ]

    manifest = manifest_for(
        [family["main"], second], explicit=[family["main"], second], upstream_claims=claim
    )

    assert am.validate_manifest(manifest) == []


def test_shared_upstream_claim_contradicted_by_evidence_is_rejected(family):
    other = make_clone(family["tmp"] / "elsewhere" / "widgets", OTHER_UPSTREAM)
    claim = [{"upstream": UPSTREAM, "roots": [str(family["main"]), str(other)]}]

    manifest = manifest_for(
        [family["main"], other], explicit=[family["main"], other], upstream_claims=claim
    )

    errors = am.validate_manifest(manifest)
    assert any("conflicting shared-upstream claim" in e and str(other) in e for e in errors)


def test_claim_over_a_root_without_origin_evidence_is_rejected(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    claim = [{"upstream": UPSTREAM, "roots": [str(plain)]}]

    manifest = manifest_for([plain], explicit=[plain], upstream_claims=claim)

    assert any("conflicting shared-upstream claim" in e for e in am.validate_manifest(manifest))


def test_claim_naming_an_unincluded_root_is_rejected(family):
    claim = [{"upstream": UPSTREAM, "roots": [str(family["tmp"] / "nowhere")]}]

    manifest = manifest_for([family["main"]], upstream_claims=claim)

    assert any("not included" in e for e in am.validate_manifest(manifest))


def test_non_git_selection_is_kept_with_explicit_no_metadata_evidence(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    manifest = manifest_for([plain])

    (item,) = manifest["upstream_identity"]
    assert item["evidence"] == "no-git-metadata" and item["origin_url"] is None
    assert am.validate_manifest(manifest) == []


def test_rejected_roots_are_recorded_and_do_not_fail_validation(family):
    removed = add_worktree(family["main"], family["tmp"] / "trees" / "gone", "gone")
    shutil.rmtree(removed)

    manifest = manifest_for([family["main"]])

    assert [r["path"] for r in manifest["scope_resolution"]["rejected"]] == [str(removed)]
    assert am.validate_manifest(manifest) == []


def test_distinct_contents_keep_two_definitions_and_identical_copies_keep_aliases(tmp_path):
    repos = [tmp_path / name for name in ("a", "b", "c")]
    paths = [
        write_skill(repo, "shared", "Other" if index == 1 else "Same")
        for index, repo in enumerate(repos)
    ]
    skills = discover_skills(repos, tmp_path / "codex", [], False)

    manifest = manifest_for(repos, explicit=repos, skills=skills)

    entries = [e for e in manifest["catalog"] if e["name"] == "shared"]
    assert len(entries) == 2
    assert len({e["sha256"] for e in entries}) == 2
    same = next(e for e in entries if str(paths[0]) in [e["path"], *e["aliases"]])
    assert sorted([same["path"], *same["aliases"]]) == sorted([str(paths[0]), str(paths[2])])
    other = next(e for e in entries if e is not same)
    assert other["aliases"] == [] and other["path"] == str(paths[1])
    assert sum(e["current_edit_target"] for e in entries) == 1
    assert am.validate_manifest(manifest) == []


def test_catalog_classifies_scope_by_included_roots(tmp_path):
    repo = tmp_path / "repo"
    write_skill(repo, "local", "L")
    outside = write_skill(tmp_path / "global-home", "outer", "O")
    skills = discover_skills([repo], tmp_path / "codex", [outside.parents[1]], False)

    manifest = manifest_for([repo], skills=skills)

    scopes = {e["name"]: e["scope"] for e in manifest["catalog"]}
    assert scopes == {"local": "repository", "outer": "global-or-extra"}


def test_duplicate_catalog_definition_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    write_skill(repo, "one", "x")
    manifest = manifest_for([repo], skills=discover_skills([repo], tmp_path / "c", [], False))
    manifest["catalog"].append(copy.deepcopy(manifest["catalog"][0]))
    restamp(manifest)

    assert any("duplicate catalog definition" in e for e in am.validate_manifest(manifest))


def session(notes):
    return {"meta": {"cwd": None}, "skill_attribution": notes}


def test_attribution_summary_counts_kinds_and_keeps_history_unverified(tmp_path):
    sessions = [
        session(
            {"a": {"evidence": "qualified_name", "unresolved_because": ["namespace_unverified"]}}
        ),
        session(
            {
                "a": {
                    "evidence": "unrecorded",
                    "unresolved_because": ["evidence_not_in_transcript"],
                },
                "b": {
                    "evidence": "qualified_name",
                    "unresolved_because": ["conflicting_definitions"],
                },
            }
        ),
        {"meta": {"cwd": None}},
    ]

    manifest = manifest_for([tmp_path], sessions=sessions)

    attribution = manifest["attribution"]
    assert attribution["evidence_kinds"] == {"qualified_name": 2, "unrecorded": 1}
    assert attribution["unresolved_count"] == 3
    assert attribution["sessions_with_unresolved"] == 2
    assert attribution["verified_count"] == 0
    assert attribution["historical_verification"] == "none"
    assert "never verifies" in attribution["note"]
    assert am.validate_manifest(manifest) == []


def test_unresolved_attribution_is_not_a_failure(tmp_path):
    notes = {"a": {"evidence": "unrecorded", "unresolved_because": ["x"]}}

    manifest = manifest_for([tmp_path], sessions=[session(notes)])

    assert manifest["attribution"]["unresolved_count"] == 1
    assert am.validate_manifest(manifest) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["attribution"].update(historical_verification="hash"),
        lambda m: m["attribution"].update(verified_count=5),
    ],
)
def test_hash_only_verified_attribution_is_rejected(tmp_path, mutate):
    manifest = manifest_for([tmp_path])
    mutate(manifest)
    restamp(manifest)

    errors = am.validate_manifest(manifest)

    assert any("verif" in e for e in errors)


def test_catalog_entry_claiming_execution_verification_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    write_skill(repo, "one", "x")
    manifest = manifest_for([repo], skills=discover_skills([repo], tmp_path / "c", [], False))
    manifest["catalog"][0]["verified_executed"] = True
    restamp(manifest)

    assert any("claims execution verification" in e for e in am.validate_manifest(manifest))


def test_tampered_content_fails_the_fingerprint(tmp_path):
    manifest = manifest_for([tmp_path])
    manifest["window_days"] = 1

    assert "fingerprint does not match" in " ".join(am.validate_manifest(manifest))


@pytest.mark.parametrize("bad", [None, [], "text", 3])
def test_non_object_manifest_is_rejected(bad):
    assert am.validate_manifest(bad) == ["manifest must be a JSON object"]


def test_missing_fields_and_wrong_version_are_listed():
    errors = am.validate_manifest({"manifest_version": 99})

    assert any("unsupported manifest_version" in e for e in errors)
    assert "missing field: catalog" in errors


def test_malformed_nested_structure_is_reported_not_raised(tmp_path):
    manifest = manifest_for([tmp_path])
    manifest["declared_inputs"] = "oops"
    restamp(manifest)

    assert any("malformed manifest structure" in e for e in am.validate_manifest(manifest))


def test_identity_missing_for_an_included_root_is_rejected(family):
    manifest = manifest_for([family["feature"]])
    manifest["upstream_identity"].pop()
    restamp(manifest)

    assert any("identity evidence missing" in e for e in am.validate_manifest(manifest))


def test_origin_url_is_read_from_config_without_credentials(tmp_path):
    common = tmp_path / ".git"
    common.mkdir()
    (common / "config").write_text(
        '[core]\n\tbare = false\n[remote "upstream"]\n\turl = https://x.invalid/up.git\n'
        '[remote "origin"]\n\turl = https://user:secret@Example.invalid/acme/w.git\n'
        "\tfetch = +refs/heads/*:refs/remotes/origin/*\n",
        encoding="utf-8",
    )

    assert am.read_origin_url(common) == "https://Example.invalid/acme/w.git"
    assert am.normalize_upstream("https://u:p@Example.invalid/acme/w.git/") == (
        "https://example.invalid/acme/w"
    )


@pytest.mark.parametrize(
    "config",
    [None, "[core]\n\tbare = false\n", '[remote "other"]\n\turl = https://x.invalid/o\n'],
)
def test_missing_config_or_origin_yields_no_url(tmp_path, config):
    common = tmp_path / ".git"
    common.mkdir()
    if config is not None:
        (common / "config").write_text(config, encoding="utf-8")

    assert am.read_origin_url(common) is None
    assert am.normalize_upstream(None) is None
    assert am.normalize_upstream("") is None


def test_scp_style_origin_normalizes_without_a_scheme():
    assert am.normalize_upstream("git@host.invalid:acme/w.git") == "git@host.invalid:acme/w"


def test_source_revision_is_stable_and_tracks_file_content(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "b.py").write_text("two", encoding="utf-8")
    (scripts / "a.py").write_text("one", encoding="utf-8")
    (scripts / "sub").mkdir()
    first = am.source_revision(scripts)

    assert am.source_revision(scripts) == first
    assert first["files"] == 2
    (scripts / "a.py").write_text("changed", encoding="utf-8")
    assert am.source_revision(scripts)["sha256"] != first["sha256"]
