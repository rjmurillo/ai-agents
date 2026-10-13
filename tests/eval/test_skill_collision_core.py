"""Tests for the skill collision core, _skill_collision.py (issue #5763).

Covers exact, normalized, truncated-identical, and near collisions, the negative
case where distinct descriptions stay distinguishable, the truncation boundary,
stable ordering, clusters, and the git-backed changed-skill lookup.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
for _path in (_EVAL_DIR, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import _skill_collision as scr  # noqa: E402
from _skill_collision_test_support import SHARED_PREFIX, make_catalog, write_skill  # noqa: E402


@pytest.fixture
def catalog(tmp_path: Path) -> Path:
    return make_catalog(tmp_path)


def kinds(findings: list[scr.Finding]) -> list[tuple[str, str, str]]:
    return [(f.kind, f.field, f.profile) for f in findings]


class TestNormalize:
    def test_collapses_case_punctuation_and_spacing(self) -> None:
        assert scr.normalize("  Hello,   WORLD!! ") == "hello world"

    def test_applies_nfkc_so_fullwidth_matches_ascii(self) -> None:
        assert scr.normalize("ＡＢＣ") == "abc"

    def test_empty_string_stays_empty(self) -> None:
        assert scr.normalize("") == ""


class TestJaccard:
    def test_identical_token_sets_score_one(self) -> None:
        assert scr.jaccard("a b c", "c b a") == 1.0

    def test_disjoint_token_sets_score_zero(self) -> None:
        assert scr.jaccard("a b", "c d") == 0.0

    def test_two_empty_strings_score_zero(self) -> None:
        assert scr.jaccard("", "") == 0.0

    def test_partial_overlap_is_intersection_over_union(self) -> None:
        assert scr.jaccard("a b c", "b c d") == 0.5


class TestLoadCatalog:
    def test_loads_sorted_entries_with_name_and_path(self, catalog: Path) -> None:
        entries = scr.load_catalog(catalog)

        assert [e.skill for e in entries] == ["alpha", "bravo", "charlie"]
        assert entries[0].name == "alpha"
        assert entries[0].path.endswith("alpha/SKILL.md")

    def test_name_falls_back_to_directory_when_frontmatter_has_none(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "solo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\ndescription: Only text\n---\n", encoding="utf-8")

        entry = scr.load_catalog(tmp_path / "skills")[0]

        assert entry.name == "solo"

    def test_skips_skills_without_usable_frontmatter(self, catalog: Path) -> None:
        for directory, text in {
            "nofront": "# no frontmatter\n",
            "badyaml": "---\nname: [unclosed\n---\n",
            "scalar": "---\njust a string\n---\n",
            "nodesc": "---\nname: nodesc\n---\n",
            "numdesc": "---\ndescription: 42\n---\n",
        }.items():
            (catalog / directory).mkdir()
            (catalog / directory / "SKILL.md").write_text(text, encoding="utf-8")

        assert [e.skill for e in scr.load_catalog(catalog)] == ["alpha", "bravo", "charlie"]

    def test_skips_unreadable_skill_file(self, catalog: Path) -> None:
        (catalog / "binary").mkdir()
        (catalog / "binary" / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")

        assert "binary" not in [e.skill for e in scr.load_catalog(catalog)]

    def test_missing_root_raises_report_error(self, tmp_path: Path) -> None:
        with pytest.raises(scr.ReportError, match="not found"):
            scr.load_catalog(tmp_path / "absent")

    def test_empty_root_raises_report_error(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()

        with pytest.raises(scr.ReportError, match="No skill"):
            scr.load_catalog(tmp_path / "empty")


class TestFindCollisions:
    def test_distinct_catalog_reports_nothing(self, catalog: Path) -> None:
        assert scr.find_collisions(scr.load_catalog(catalog)) == []

    def test_exact_duplicate_description_is_high_confidence(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )

        findings = scr.find_collisions(scr.load_catalog(catalog))

        assert kinds(findings) == [(scr.KIND_EXACT, "description", scr.PROFILE_FULL)]
        assert findings[0].confidence == scr.HIGH
        assert findings[0].skills == ("alpha", "alpha-copy")
        assert findings[0].similarity == 1.0

    def test_case_and_punctuation_difference_is_normalized(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-loud", "PARSE yaml configuration files, and report schema errors!"
        )

        findings = scr.find_collisions(scr.load_catalog(catalog))

        assert kinds(findings) == [(scr.KIND_NORMALIZED, "description", scr.PROFILE_FULL)]

    def test_matching_names_collide_even_with_distinct_descriptions(self, catalog: Path) -> None:
        write_skill(catalog, "delta", "Summarize pull request review threads.", name="alpha")

        findings = scr.find_collisions(scr.load_catalog(catalog))

        assert kinds(findings) == [(scr.KIND_EXACT, "name", scr.PROFILE_FULL)]
        assert findings[0].skills == ("alpha", "delta")

    def test_near_duplicate_is_low_confidence(self, catalog: Path) -> None:
        write_skill(
            catalog, "bravo-v2", "Render a dashboard of weekly build durations as charts today."
        )

        findings = scr.find_collisions(scr.load_catalog(catalog))

        assert kinds(findings) == [(scr.KIND_NEAR, "description", scr.PROFILE_FULL)]
        assert findings[0].confidence == scr.LOW
        assert 0.8 <= findings[0].similarity < 1.0

    def test_near_threshold_one_suppresses_near_findings(self, catalog: Path) -> None:
        write_skill(
            catalog, "bravo-v2", "Render a dashboard of weekly build durations as charts today."
        )

        findings = scr.find_collisions(scr.load_catalog(catalog), near_threshold=1.0)

        assert findings == []


class TestTruncationBoundary:
    """Two descriptions differ only after a shared prefix. The cutoff decides."""

    @pytest.fixture
    def pair(self, catalog: Path) -> list[scr.SkillEntry]:
        write_skill(catalog, "ledger-read", SHARED_PREFIX + "Read balances only.")
        write_skill(catalog, "ledger-write", SHARED_PREFIX + "Post new journal entries.")
        return scr.load_catalog(catalog)

    def test_pair_is_not_high_confidence_when_cutoff_keeps_the_difference(
        self, pair: list[scr.SkillEntry]
    ) -> None:
        cutoff = len(SHARED_PREFIX) + 4

        findings = scr.find_collisions(pair, truncations=[cutoff])

        assert [f.confidence for f in findings] == [scr.LOW]

    def test_pair_becomes_indistinguishable_when_cutoff_ends_in_shared_prefix(
        self, pair: list[scr.SkillEntry]
    ) -> None:
        cutoff = len(SHARED_PREFIX)

        findings = scr.find_collisions(pair, truncations=[cutoff])

        assert kinds(findings) == [(scr.KIND_TRUNCATED, "description", f"chars:{cutoff}")]
        assert findings[0].confidence == scr.HIGH
        assert findings[0].skills == ("ledger-read", "ledger-write")

    def test_one_character_past_the_shared_prefix_is_no_longer_identical(
        self, pair: list[scr.SkillEntry]
    ) -> None:
        cutoff = len(SHARED_PREFIX) + 1

        findings = scr.find_collisions(pair, truncations=[cutoff])

        assert scr.KIND_TRUNCATED not in [f.kind for f in findings]

    def test_full_text_collision_is_not_repeated_under_truncation(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )

        findings = scr.find_collisions(scr.load_catalog(catalog), truncations=[10, 20])

        assert [f.profile for f in findings] == [scr.PROFILE_FULL]

    def test_truncation_induced_near_collision_is_low_confidence(self, catalog: Path) -> None:
        shared = "one two three four five six seven eight nine ten"
        write_skill(catalog, "wide-a", shared + " alpha beta gamma delta epsilon")
        write_skill(catalog, "wide-b", shared + " omega sigma tau rho psi")
        cutoff = len(shared) + len(" alpha")

        full = scr.find_collisions(scr.load_catalog(catalog))
        cut = scr.find_collisions(scr.load_catalog(catalog), truncations=[cutoff])

        assert full == []
        assert [(f.kind, f.confidence, f.profile) for f in cut] == [
            (scr.KIND_NEAR, scr.LOW, f"chars:{cutoff}")
        ]

    def test_empty_truncation_does_not_collide(self, catalog: Path) -> None:
        findings = scr.find_collisions(scr.load_catalog(catalog), truncations=[0])

        assert findings == []

    def test_profiles_repeat_only_once(self, pair: list[scr.SkillEntry]) -> None:
        cutoff = len(SHARED_PREFIX)

        findings = scr.find_collisions(pair, truncations=[cutoff, cutoff])

        assert len(findings) == 1


class TestOrderingAndClusters:
    @pytest.fixture
    def findings(self, catalog: Path) -> list[scr.Finding]:
        write_skill(catalog, "zeta", "Rotate expired API credentials in the secrets manager.")
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        write_skill(
            catalog, "bravo-v2", "Render a dashboard of weekly build durations as charts today."
        )
        return scr.find_collisions(scr.load_catalog(catalog))

    def test_high_confidence_sorts_before_low(self, findings: list[scr.Finding]) -> None:
        assert [f.confidence for f in findings] == [scr.HIGH, scr.HIGH, scr.LOW]

    def test_order_is_stable_across_input_order(self, catalog: Path) -> None:
        write_skill(catalog, "zeta", "Rotate expired API credentials in the secrets manager.")
        entries = scr.load_catalog(catalog)

        forward = scr.find_collisions(entries)
        backward = scr.find_collisions(list(reversed(entries)))

        assert forward == backward

    def test_clusters_group_colliding_skills_sorted(self, findings: list[scr.Finding]) -> None:
        clusters = scr.build_clusters(findings)

        assert clusters == (("alpha", "alpha-copy"), ("bravo", "bravo-v2"), ("charlie", "zeta"))

    def test_chain_of_collisions_forms_one_cluster(self, findings: list[scr.Finding]) -> None:
        chain = [
            f for f in findings if f.skills in {("alpha", "alpha-copy"), ("alpha-copy", "alpha-x")}
        ]
        extra = scr.Finding(
            kind=scr.KIND_NEAR,
            confidence=scr.LOW,
            field="description",
            profile=scr.PROFILE_FULL,
            skills=("alpha-copy", "alpha-x"),
            paths=("a", "b"),
            compared=("a", "b"),
            similarity=0.9,
            remediation="r",
        )

        assert scr.build_clusters([*chain, extra]) == (("alpha", "alpha-copy", "alpha-x"),)

    def test_no_findings_means_no_clusters(self) -> None:
        assert scr.build_clusters([]) == ()

    def test_filter_keeps_findings_that_involve_selected_skills(
        self, findings: list[scr.Finding]
    ) -> None:
        kept = scr.filter_findings(findings, ["zeta"])

        assert [f.skills for f in kept] == [("charlie", "zeta")]

    def test_empty_selection_keeps_everything(self, findings: list[scr.Finding]) -> None:
        assert scr.filter_findings(findings, []) == findings


class TestFindingShape:
    def test_finding_names_skills_paths_compared_text_profile_and_remediation(
        self, catalog: Path
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )

        data = scr.find_collisions(scr.load_catalog(catalog))[0].to_dict()

        assert data["skills"] == ["alpha", "alpha-copy"]
        assert data["paths"][0].endswith("alpha/SKILL.md")
        assert data["compared"][0].startswith("Parse YAML")
        assert data["profile"] == "full"
        assert "Merge the skills" in data["remediation"]

    def test_long_compared_text_is_excerpted(self, catalog: Path) -> None:
        long_text = "word " * 100
        write_skill(catalog, "long-a", long_text)
        write_skill(catalog, "long-b", long_text)

        finding = scr.find_collisions(scr.load_catalog(catalog))[0]

        assert finding.compared[0].endswith("...")
        assert len(finding.compared[0]) == 163

    def test_report_assumptions_label_profiles_as_controlled(self, catalog: Path) -> None:
        report = scr.build_report(catalog, truncations=[100])
        data = report.to_dict()["assumptions"]

        assert data["truncation_profiles"]["controlled"] is True
        assert data["truncation_profiles"]["profiles"] == ["chars:100"]
        assert data["host_observed_abbreviation"]["status"] == "not_observed"
        assert data["semantic_routing"] == {
            "measured": False,
            "model": None,
            "harness": None,
            "note": "Lexical comparison only. No skill-selection accuracy is claimed.",
        }


class TestChangedSkills:
    def git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
        )

    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        self.git(tmp_path, "init", "-q")
        root = tmp_path / "skills"
        write_skill(root, "alpha", "Alpha text one.")
        write_skill(root, "bravo", "Bravo text two.")
        self.git(tmp_path, "add", "-A")
        self.git(tmp_path, "commit", "-q", "-m", "base")
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_reports_skill_directories_with_modified_files(self, repo: Path) -> None:
        (repo / "skills" / "bravo" / "SKILL.md").write_text("changed\n", encoding="utf-8")

        assert scr.changed_skills(Path("skills"), "HEAD") == ["bravo"]

    def test_ignores_files_outside_the_root_and_loose_root_files(self, repo: Path) -> None:
        (repo / "README.md").write_text("x\n", encoding="utf-8")
        (repo / "skills" / "loose.txt").write_text("x\n", encoding="utf-8")
        self.git(repo, "add", "-A")

        assert scr.changed_skills(Path("skills"), "HEAD") == []

    def test_bad_ref_raises_git_error(self, repo: Path) -> None:
        with pytest.raises(scr.GitError, match="failed"):
            scr.changed_skills(Path("skills"), "no-such-ref")

    def test_missing_git_binary_raises_git_error(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("git")

        monkeypatch.setattr(scr.subprocess, "run", boom)

        with pytest.raises(scr.GitError, match="unavailable"):
            scr.changed_skills(Path("skills"), "HEAD")
