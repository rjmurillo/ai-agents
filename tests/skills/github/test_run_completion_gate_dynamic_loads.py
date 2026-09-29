"""Dynamic-load handling in the completion gate's verifier closure.

ADR-101 Application B, issue #5245. The static import pass cannot see a load by
computed name, so a verifier reached through one was dispatched unverified. The
decision under test: a load whose target is a literal, or a path built only from
`__file__` and string literals, joins the closure and is byte-verified; any
recognised load that cannot be resolved fails closed as untrusted. The review
cases live in test_run_completion_gate_dynamic_loads_review.py and the trust
integration cases in test_run_completion_gate_dynamic_loads_trust.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import closure, gate, loads, write


class TestResolvableLoads:
    def test_import_module_with_a_literal_name_joins_theclosure(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "import importlib\nimportlib.import_module('sibling')\n")
        write(tmp_path, "sibling.py", "X = 1\n")

        assert closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_dunder_import_with_a_literal_name_joins_theclosure(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "__import__('sibling')\n")
        write(tmp_path, "sibling.py", "X = 1\n")

        assert "sibling.py" in closure(tmp_path, "verify.py")

    @pytest.mark.parametrize(
        "expression",
        [
            "Path(__file__).resolve().parent / 'sibling.py'",
            "Path(__file__).resolve().with_name('sibling.py')",
            "Path(__file__).parent.joinpath('sibling.py')",
            "pathlib.Path(__file__).absolute().parent / 'sibling.py'",
            "os.path.join(os.path.dirname(__file__), 'sibling.py')",
            "os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sibling.py')",
            "Path(__file__).resolve().parents[0] / 'sibling.py'",
        ],
    )
    def test_a_path_built_from_file_and_literals_joins_theclosure(
        self, tmp_path: Path, expression: str
    ) -> None:
        write(
            tmp_path,
            "verify.py",
            f"""\
            import importlib.util, os, pathlib
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("sibling", {expression})
            """,
        )
        write(tmp_path, "sibling.py", "X = 1\n")

        assert closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_a_path_held_in_a_single_assignment_is_followed(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path
            target = Path(__file__).resolve().parent / "sibling.py"
            spec = importlib.util.spec_from_file_location("sibling", target)
            """,
        )
        write(tmp_path, "sibling.py", "X = 1\n")

        assert closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_the_loaded_files_own_imports_are_followed(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('s', Path(__file__).parent / 'sibling.py')\n",
        )
        write(tmp_path, "sibling.py", "import deep\n")
        write(tmp_path, "deep.py", "X = 1\n")

        assert closure(tmp_path, "verify.py") == ["verify.py", "sibling.py", "deep.py"]

    def test_an_already_listed_target_is_not_added_twice(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "import sibling\n__import__('sibling')\n")
        write(tmp_path, "sibling.py", "X = 1\n")

        assert closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_a_literal_stdlib_module_resolves_to_nothing_and_is_not_reported(
        self, tmp_path: Path
    ) -> None:
        write(tmp_path, "verify.py", "import importlib\nimportlib.import_module('json')\n")

        assert closure(tmp_path, "verify.py") == ["verify.py"]
        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []


class TestUnresolvableLoads:
    @pytest.mark.parametrize(
        ("body", "kind"),
        [
            ("import importlib\nimportlib.import_module(name)\n", "import_module"),
            ("import importlib\nimportlib.import_module('.rel')\n", "import_module"),
            ("__import__(name)\n", "__import__"),
            ("import runpy\nrunpy.run_module(name)\n", "run_module"),
            ("import runpy\nrunpy.run_path(path)\n", "run_path"),
            ("exec(source)\n", "exec"),
            ("eval(build())\n", "eval"),
            (
                "import importlib.util\nimportlib.util.spec_from_file_location('x', path)\n",
                "spec_from_file_location",
            ),
            (
                "import importlib.machinery\nimportlib.machinery.SourceFileLoader('x', path)\n",
                "SourceFileLoader",
            ),
            (
                "import importlib.util\nimportlib.util.spec_from_file_location('x')\n",
                "spec_from_file_location",
            ),
        ],
    )
    def test_a_computed_target_fails_closed(self, tmp_path: Path, body: str, kind: str) -> None:
        write(tmp_path, "verify.py", body)

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert len(sites) == 1
        assert re.match(r"verify\.py:\d+: unresolvable dynamic load \(", sites[0])
        assert kind in sites[0]

    @pytest.mark.parametrize(
        "expression",
        [
            "Path(__file__).resolve().parent / name",
            "Path(__file__).resolve().with_name(f'{name}.py')",
            "Path(__file__).parent / 'missing.py'",
            "Path(__file__).parents[9] / 'x.py'",
            "Path(__file__).parents[-1] / 'x.py'",
            "Path(f'{name}')",
            "Path(__file__, 'extra')",
            "Path(__file__).parent.joinpath(name)",
            "Path(__file__).parent.with_name('a', 'b')",
            "os.path.join(name, 'x.py')",
            "os.path.join(os.path.dirname(__file__))",
            "Path(__file__).parent.somewhere('x')",
        ],
    )
    def test_a_path_not_built_from_file_and_literals_fails_closed(
        self, tmp_path: Path, expression: str
    ) -> None:
        write(
            tmp_path,
            "verify.py",
            f"""\
            import importlib.util, os
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("x", {expression})
            """,
        )

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert len(sites) == 1

    def test_a_name_assigned_twice_is_ambiguous_and_fails_closed(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path
            target = Path(__file__).parent / "a.py"
            target = Path(__file__).parent / "b.py"
            importlib.util.spec_from_file_location("x", target)
            """,
        )
        write(tmp_path, "a.py", "")
        write(tmp_path, "b.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_an_augmented_assignment_makes_a_name_ambiguous(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path
            target = Path(__file__).parent
            target /= "a.py"
            importlib.util.spec_from_file_location("x", target)
            """,
        )
        write(tmp_path, "a.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_target_that_does_not_exist_fails_closed(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'gone.py')\n",
        )

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_target_outside_the_work_tree_fails_closed(
        self, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        outside = tmp_path_factory.mktemp("outside")
        (outside / "evil.py").write_text("", encoding="utf-8")
        tree = tmp_path / "tree"
        depth = len(tree.resolve().parts)
        climbs = "/".join([".."] * (depth - 1))
        write(
            tree,
            "verify.py",
            "import importlib.util\nimport os\n"
            "importlib.util.spec_from_file_location('x', os.path.join("
            f"os.path.dirname(__file__), '{climbs}', '{outside.resolve().as_posix().lstrip('/')}',"
            " 'evil.py'))\n",
        )

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tree)

        assert len(sites) == 1

    def test_a_symlinked_target_fails_closed(
        self, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        outside = tmp_path_factory.mktemp("outside")
        real = outside / "real.py"
        real.write_text("", encoding="utf-8")
        (tmp_path / "link.py").symlink_to(real)
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'link.py')\n",
        )

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_string_constant_exec_is_not_a_dynamic_load(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "exec('x = 1')\neval('1 + 1')\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_method_named_exec_is_not_the_builtin(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "conn.exec(query)\ncursor.eval(expr)\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_only_python_files_are_scanned(self, tmp_path: Path) -> None:
        write(tmp_path, "data.json", "exec(source)\n")

        assert gate._unresolvable_dynamic_sites(["data.json"], tmp_path) == []

    def test_an_unreadable_file_is_skipped_without_crashing(self, tmp_path: Path) -> None:
        assert gate._unresolvable_dynamic_sites(["absent.py"], tmp_path) == []

    def test_an_unparseable_file_yields_no_sites(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "def broken(:\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []
        assert loads(tmp_path, "def broken(:\n", "other.py") == []

    def test_sites_are_reported_in_line_order(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "\n\n__import__(b)\n\nexec(a)\n")

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert [site.split(": ")[0] for site in sites] == ["verify.py:3", "verify.py:5"]


class TestPathDerivationEdges:
    """Direct cases for the evaluator behind the resolvable side of the decision."""

    @staticmethod
    def _derive(expression: str, script: Path, names: dict | None = None):
        import ast

        node = ast.parse(expression, mode="eval").body
        return gate._derive_file_path(node, script, names or {})

    def test_with_suffix_on_a_derived_path(self, tmp_path: Path) -> None:
        script = tmp_path / "verify.py"

        assert self._derive("Path(__file__).with_suffix('.txt')", script) == (
            tmp_path / "verify.txt"
        )

    def test_a_bad_suffix_is_unresolvable_not_a_crash(self, tmp_path: Path) -> None:
        assert self._derive("Path(__file__).with_suffix('txt')", tmp_path / "v.py") is None

    def test_parents_with_a_literal_index(self, tmp_path: Path) -> None:
        script = tmp_path / "a" / "b" / "verify.py"

        assert self._derive("Path(__file__).parents[1]", script) == tmp_path / "a"

    @pytest.mark.parametrize(
        "expression",
        [
            "Path(__file__).ancestors[0]",
            "Path(name).parents[0]",
            "Path(__file__).parents[name]",
            "Path(__file__).parents[-1]",
            "Path(__file__).parents[99]",
            "Path(__file__) + 'x'",
            "Path(__file__).name",
            "name",
            "Path(__file__).parent / other",
        ],
    )
    def test_unmodelled_shapes_derive_nothing(self, tmp_path: Path, expression: str) -> None:
        assert self._derive(expression, tmp_path / "verify.py") is None

    def test_a_reference_chain_longer_than_the_depth_limit_derives_nothing(
        self, tmp_path: Path
    ) -> None:
        import ast

        script = tmp_path / "verify.py"
        names = {f"a{i}": ast.parse(f"a{i - 1}", mode="eval").body for i in range(1, 16)}
        names["a0"] = ast.parse("Path(__file__)", mode="eval").body

        assert self._derive("a3", script, names) == script
        assert self._derive("a15", script, names) is None

    def test_keyword_arguments_are_read(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location(\n"
            "    name='s', location=Path(__file__).parent / 'sibling.py')\n",
        )
        write(tmp_path, "sibling.py", "X = 1\n")

        assert closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_a_call_on_a_call_result_is_not_named(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "factory()()\n(lambda: 1)()\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_missing_path_argument_is_unresolvable(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "import runpy\nrunpy.run_path()\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1
