"""Generated ADR-119 install links that the dispatch closure cannot reach (issue #7398).

A pull request that adds a skill adds `.claude/skills/<name>` and
`.agents/skills/<name>`. Those links are exempt only when every condition in
`scripts/ci/_link_exemption.py` holds. Every other new link still fails, and each
negative case below changes exactly one condition.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ci import verify_dispatch_closure as vdc
from tests.ci.dispatch_closure_helpers import CONFIG, VERIFIER, git, link_demo_skill, rev, write
from tests.ci.dispatch_closure_runner import check

BINPLACE = "templates/platforms/binplace.yaml"
ROWS = [
    {
        "class": "skills",
        "plugin_tree": "src/claude/skills",
        "install_tree": ".claude/skills",
        "link": True,
    },
    {
        "class": "skills-codex",
        "plugin_tree": "src/codex/skills",
        "install_tree": ".agents/skills",
        "link": True,
    },
    {
        "class": "rules",
        "plugin_tree": "src/claude/rules",
        "install_tree": ".claude/rules",
        "link": True,
    },
    {
        "class": "instructions-github",
        "plugin_tree": "src/copilot-cli/instructions",
        "install_tree": ".github/instructions",
        "link": True,
    },
    {"class": "lib", "plugin_tree": "src/claude/lib", "install_tree": ".claude/lib", "link": True},
    {
        "class": "hooks-github",
        "plugin_tree": "src/copilot-cli/hooks",
        "install_tree": ".github/hooks",
        "link": True,
    },
]


def _commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


@pytest.fixture
def skill_trees(trees: tuple[Path, Path]) -> tuple[Path, Path]:
    """Base with the demo skill linked and a binplace manifest; head checked out at it."""
    base, head = trees
    write(base, BINPLACE, yaml.safe_dump({"rows": ROWS}))
    write(base, ".claude/skills/legacy/SKILL.md", "real directory\n")
    _commit(base, "binplace manifest")
    link_demo_skill(base)
    git(head, "checkout", "--detach", "-q", "--force", rev(base))
    return base, head


def _new_skill(
    head: Path, name: str, *, plugin: str = "src/claude/skills", install: str = ".claude/skills"
) -> Path:
    write(head, f"{plugin}/{name}/SKILL.md", f"# {name}\n")
    link = head / install / name
    link.parent.mkdir(parents=True, exist_ok=True)
    depth = len(Path(install).parts)
    link.symlink_to("../" * depth + f"{plugin}/{name}")
    return link


def _new_rule_links(head: Path) -> tuple[Path, Path]:
    write(head, "src/claude/rules/core.md", "# Core\n")
    write(head, "src/copilot-cli/instructions/core.instructions.md", "# Core\n")
    claude = head / ".claude/rules/core.md"
    github = head / ".github/instructions/core.instructions.md"
    claude.parent.mkdir(parents=True, exist_ok=True)
    github.parent.mkdir(parents=True, exist_ok=True)
    try:
        claude.symlink_to("../../src/claude/rules/core.md")
        github.symlink_to("../../src/copilot-cli/instructions/core.instructions.md")
    except OSError as exc:
        pytest.skip(f"symlink creation unsupported: {exc}")
    return claude, github


def _main(base: Path, head: Path) -> int:
    return vdc.main(["--tool-root", str(base), "--base-ref", "HEAD", "--head-root", str(head)])


def _split(
    base: Path,
    head: Path,
    named: set[str] | None = None,
    roots: set[str] | None = None,
    ref: str = "HEAD",
) -> tuple[list[str], list[str]]:
    """Classify the one new link `.claude/skills/fresh` directly."""
    trees = (base, head, ref, vdc._REF_LINKS.INERT_GIT)
    return vdc._EXEMPTION.split([".claude/skills/fresh"], trees, named or set(), roots or set())


def _rebase_head(base: Path, head: Path, message: str) -> None:
    """Commit the base edit and move the head to it."""
    _commit(base, message)
    git(head, "checkout", "--detach", "-q", "--force", rev(base))


class TestExemptInstallLinks:
    def test_a_new_skill_and_its_codex_link_exit_zero(
        self, skill_trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        _new_skill(head, "fresh", plugin="src/codex/skills", install=".agents/skills")

        assert _main(base, head) == 0
        out = capsys.readouterr().out
        assert "dispatch-closure: EXEMPT .claude/skills/fresh" in out
        assert "dispatch-closure: EXEMPT .agents/skills/fresh" in out
        assert "2 exempt install links" in out

    def test_new_rule_and_instruction_links_exit_zero(
        self, skill_trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, head = skill_trees
        _new_rule_links(head)

        assert _main(base, head) == 0
        out = capsys.readouterr().out
        assert "dispatch-closure: EXEMPT .claude/rules/core.md" in out
        assert "dispatch-closure: EXEMPT .github/instructions/core.instructions.md" in out
        assert "2 exempt install links" in out

    def test_a_committed_new_skill_is_exempt_with_a_head_sha(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        _commit(head, "add fresh")

        report = vdc.verify(base, head, "HEAD", head_sha=rev(head))

        assert report.clean, report.to_json()
        assert report.exempt == [".claude/skills/fresh"]


class TestCiPath:
    def test_main_with_a_head_sha_exempts_a_new_skill(
        self, skill_trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The CI shape: --head-sha writes the head with checkout-index, then verifies."""
        base, _ = skill_trees
        upstream = base.parent / "upstream"
        subprocess.run(
            ["git", "clone", "-q", str(base), str(upstream)], capture_output=True, check=True
        )
        git(upstream, "config", "user.email", "t@example.invalid")
        git(upstream, "config", "user.name", "t")
        _new_skill(upstream, "fresh")
        _commit(upstream, "add a skill")
        sha = rev(upstream)
        git(upstream, "update-ref", "refs/pull/1/head", sha)

        report = check(base, upstream, sha, capsys)

        assert report["code"] == vdc.EXIT_OK, report
        assert report["exempt_links"] == [".claude/skills/fresh"]
        assert report["symlinks"] == []


class TestLinksThatStillFail:
    def _reported(self, base: Path, head: Path, link: str) -> None:
        assert _main(base, head) == 1
        report = vdc.verify(base, head, "HEAD")
        assert link in report.symlinks, report.to_json()
        assert link not in report.exempt

    def test_wrong_link_text(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        write(head, "src/claude/skills/fresh/SKILL.md", "x\n")
        write(head, "src/claude/skills/other/SKILL.md", "y\n")
        (head / ".claude/skills/fresh").symlink_to("../../src/claude/skills/other")

        self._reported(base, head, ".claude/skills/fresh")

    def test_a_target_outside_the_tree(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        (head.parent / "outside").mkdir()
        (head / ".claude/skills/fresh").symlink_to("../../../outside")

        self._reported(base, head, ".claude/skills/fresh")

    def test_a_target_that_is_itself_a_link(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        write(head, "src/claude/skills/real/SKILL.md", "x\n")
        (head / "src/claude/skills/fresh").symlink_to("real")
        (head / ".claude/skills/fresh").symlink_to("../../src/claude/skills/fresh")

        self._reported(base, head, ".claude/skills/fresh")

    def test_a_link_two_levels_under_the_install_tree(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        write(head, "src/claude/skills/fresh/SKILL.md", "x\n")
        write(head, ".claude/skills/outer/SKILL.md", "x\n")
        (head / ".claude/skills/outer/fresh").symlink_to("../../../src/claude/skills/fresh")

        self._reported(base, head, ".claude/skills/outer/fresh")

    def test_a_real_base_directory_replaced_by_a_link(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        git(head, "rm", "-q", "-r", ".claude/skills/legacy")
        _new_skill(head, "legacy")

        self._reported(base, head, ".claude/skills/legacy")

    def test_a_skill_named_lib_is_an_import_root(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "lib")

        self._reported(base, head, ".claude/skills/lib")

    def test_a_link_nested_under_a_non_toplevel_import_root(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        config = yaml.safe_load((base / CONFIG).read_text(encoding="utf-8"))
        config["scripts"]["claude_code"]["top"] = "python3 .claude/run.py"
        write(base, CONFIG, yaml.safe_dump(config))
        write(base, ".claude/run.py", "X = 1\n")
        _rebase_head(base, head, "a verifier directly under .claude makes it an import root")
        _new_skill(head, "fresh")

        self._reported(base, head, ".claude/skills/fresh")

    @pytest.mark.parametrize(
        ("verifier", "link"),
        [
            (".claude/rules/run.py", ".claude/rules/core.md"),
            (".github/instructions/run.py", ".github/instructions/core.instructions.md"),
        ],
    )
    def test_a_rule_link_under_an_import_root(
        self, skill_trees: tuple[Path, Path], verifier: str, link: str
    ) -> None:
        base, head = skill_trees
        config = yaml.safe_load((base / CONFIG).read_text(encoding="utf-8"))
        config["scripts"]["claude_code"]["top"] = f"python3 {verifier}"
        write(base, CONFIG, yaml.safe_dump(config))
        write(base, verifier, "X = 1\n")
        _rebase_head(base, head, "a verifier in a rule install tree makes it an import root")
        _new_rule_links(head)

        self._reported(base, head, link)

    def test_a_link_under_a_lib_install_tree(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "yaml", plugin="src/claude/lib", install=".claude/lib")

        self._reported(base, head, ".claude/lib/yaml")

    def test_a_link_under_a_non_exempt_install_tree(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh", plugin="src/copilot-cli/hooks", install=".github/hooks")

        self._reported(base, head, ".github/hooks/fresh")

    def test_a_link_the_base_config_names_a_path_under(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        config = yaml.safe_load((base / CONFIG).read_text(encoding="utf-8"))
        config["scripts"]["claude_code"]["go"] += " --rules .claude/skills/fresh/rules.yaml"
        write(base, CONFIG, yaml.safe_dump(config))
        _rebase_head(base, head, "name a fresh script")
        _new_skill(head, "fresh")
        write(head, "src/claude/skills/fresh/rules.yaml", "rules: []\n")

        self._reported(base, head, ".claude/skills/fresh")

    def test_a_dot_slash_spelling_in_the_base_config_still_counts(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        config = yaml.safe_load((base / CONFIG).read_text(encoding="utf-8"))
        config["scripts"]["claude_code"]["go"] += " --rules ./.claude/skills/fresh/rules.yaml"
        write(base, CONFIG, yaml.safe_dump(config))
        _rebase_head(base, head, "name a fresh data file with a ./ spelling")
        _new_skill(head, "fresh")
        write(head, "src/claude/skills/fresh/rules.yaml", "rules: []\n")

        self._reported(base, head, ".claude/skills/fresh")

    def test_an_absolute_named_spelling_is_normalized(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        absolute = str(head / ".claude/skills/fresh/rules.yaml")
        assert _split(base, head, named={absolute}) == ([".claude/skills/fresh"], [])

    def test_a_dangling_target_with_the_right_link_text(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        (head / ".claude/skills/fresh").symlink_to("../../src/claude/skills/fresh")

        self._reported(base, head, ".claude/skills/fresh")

    def test_a_named_path_under_the_target_spelling(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        assert _split(base, head, named={"src/claude/skills/fresh/rules.yaml"}) == (
            [".claude/skills/fresh"],
            [],
        )

    def test_an_import_root_under_the_link(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        assert _split(base, head, roots={".claude/skills/fresh/lib"}) == (
            [".claude/skills/fresh"],
            [],
        )

    def test_a_row_that_is_not_a_link_row(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        rows = [{**r, "link": False} if r["class"] == "skills" else r for r in ROWS]
        write(base, BINPLACE, yaml.safe_dump({"rows": rows}))
        _rebase_head(base, head, "skills row is not a link row")
        _new_skill(head, "fresh")

        self._reported(base, head, ".claude/skills/fresh")

    def test_a_skill_row_without_a_dot_led_install_tree(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        rows = [
            *ROWS,
            {
                "class": "skills",
                "plugin_tree": "src/claude/skills",
                "install_tree": "plain",
                "link": True,
            },
        ]
        write(
            base,
            BINPLACE,
            yaml.safe_dump({"rows": [r for r in rows if r["install_tree"] != ".claude/skills"]}),
        )
        _rebase_head(base, head, "skills row installs into a dotless tree")
        _new_skill(head, "fresh", install="plain")

        self._reported(base, head, "plain/fresh")

    def test_a_named_directory_above_the_link(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        assert _split(base, head, named={".claude/skills"}) == ([".claude/skills/fresh"], [])

    def test_a_malformed_base_manifest_exempts_nothing(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        write(base, BINPLACE, "rows: [unclosed\n")
        _rebase_head(base, head, "break the manifest")
        _new_skill(head, "fresh")

        self._reported(base, head, ".claude/skills/fresh")

    def test_an_unlistable_base_ref_exempts_nothing(self, skill_trees: tuple[Path, Path]) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        assert _split(base, head, ref="no-such-ref") == ([".claude/skills/fresh"], [])

    def test_a_row_the_head_adds_to_binplace_is_not_trusted(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        rows = [
            *ROWS,
            {"class": "x", "plugin_tree": "src/x", "install_tree": ".github/agents", "link": True},
        ]
        write(head, BINPLACE, yaml.safe_dump({"rows": [r for r in rows if r["class"] != "skills"]}))
        _new_skill(head, "fresh")
        report = vdc.verify(base, head, "HEAD")

        assert report.exempt == [".claude/skills/fresh"], (
            "the base manifest decides, not the head's"
        )

    def test_a_base_without_a_manifest_exempts_nothing(self, trees: tuple[Path, Path]) -> None:
        base, head = trees
        link_demo_skill(base)
        git(head, "checkout", "--detach", "-q", "--force", rev(base))
        _new_skill(head, "fresh")

        self._reported(base, head, ".claude/skills/fresh")

    def test_an_exempt_link_beside_a_failing_link_still_exits_one(
        self, skill_trees: tuple[Path, Path]
    ) -> None:
        base, head = skill_trees
        _new_skill(head, "fresh")
        (head / "README.link").symlink_to("README.md")

        assert _main(base, head) == 1
        report = vdc.verify(base, head, "HEAD")
        assert report.exempt == [".claude/skills/fresh"]
        assert report.symlinks == ["README.link"]


def test_the_demo_verifier_stays_in_the_closure(skill_trees: tuple[Path, Path]) -> None:
    base, head = skill_trees

    report = vdc.verify(base, head, "HEAD")

    assert report.clean, report.to_json()
    assert VERIFIER.startswith(".claude/skills/demo")
