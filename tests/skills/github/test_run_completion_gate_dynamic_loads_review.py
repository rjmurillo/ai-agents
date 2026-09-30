"""Cases the security review of the dynamic-load change raised, each with its fix."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import gate, write


class TestSecurityReviewFindings:
    """Cases the security review of this change raised, each with its fix."""

    def test_constant_code_that_imports_is_not_inert(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "exec('import sibling')\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    @pytest.mark.parametrize(
        "code",
        [
            "__import__('os')",
            "import_module('os')",
            "exec('1')",
            "def f(:",
            "x = (",
        ],
    )
    def test_constant_code_that_loads_or_does_not_parse_is_not_inert(
        self, tmp_path: Path, code: str
    ) -> None:
        write(tmp_path, "verify.py", f"exec({code!r})\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_constant_code_with_no_import_or_load_stays_inert(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "exec('total = 1 + 1')\neval('[1, 2][0]')\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_dotdot_segment_in_a_derived_path_is_unresolvable(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location(\n"
            "    'x', Path(__file__).parent / 'a' / '..' / 'b.py')\n",
        )
        write(tmp_path, "b.py", "")
        (tmp_path / "a").mkdir()

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_non_python_target_is_unresolvable(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "from importlib.machinery import SourceFileLoader\nfrom pathlib import Path\n"
            "SourceFileLoader('x', Path(__file__).parent / 'data.txt')\n",
        )
        write(tmp_path, "data.txt", "print(1)\n")

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert len(sites) == 1
        assert "SourceFileLoader" in sites[0]

    @pytest.mark.parametrize(
        "preamble",
        [
            "class Path:\n    pass\n",
            "def Path(x):\n    return x\n",
            "os = fake\n",
            "__file__ = '/elsewhere/x.py'\n",
            "from mypkg import Path\n",
            "import mypkg as os\n",
            "def f(os):\n    pass\n",
        ],
    )
    def test_a_file_that_rebinds_path_os_or_file_is_never_resolved(
        self, tmp_path: Path, preamble: str
    ) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path as _P\n"
            + preamble
            + "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'sibling.py')\n",
        )
        write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_trusted_pathlib_import_does_not_count_as_shadowing(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nimport os\nimport pathlib\n"
            "from pathlib import Path, PurePath\n"
            "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'sibling.py')\n",
        )
        write(tmp_path, "sibling.py", "")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    @pytest.mark.parametrize(
        "binding",
        [
            "for target in items:\n    pass\n",
            "a, target = pair\n",
            "with open(p) as target:\n    pass\n",
            "(target := compute())\n",
            "[target, other] = pair\n",
            "target += 'x'\n",
            "try:\n    pass\nexcept OSError as target:\n    pass\n",
            "import target\n",
            "def target():\n    pass\n",
        ],
    )
    def test_a_name_bound_in_another_way_in_the_same_scope_is_ambiguous(
        self, tmp_path: Path, binding: str
    ) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target = Path(__file__).parent / 'sibling.py'\n"
            + binding
            + "importlib.util.spec_from_file_location('x', target)\n",
        )
        write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    @pytest.mark.parametrize(
        "load_site",
        [
            "def f(target):\n    importlib.util.spec_from_file_location('x', target)\n",
            "g = lambda target: importlib.util.spec_from_file_location('x', target)\n",
            "[importlib.util.spec_from_file_location('x', target) for target in items]\n",
            "{target: importlib.util.spec_from_file_location('x', target) for target in items}\n",
        ],
    )
    def test_a_parameter_or_loop_variable_shadows_the_module_name_at_the_load(
        self, tmp_path: Path, load_site: str
    ) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target = Path(__file__).parent / 'sibling.py'\n" + load_site,
        )
        write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_binding_in_another_function_does_not_make_a_module_name_ambiguous(
        self, tmp_path: Path
    ) -> None:
        """The scope-blind resolver read this as ambiguous; Python does not."""
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target = Path(__file__).parent / 'sibling.py'\n"
            "def unrelated(target):\n    return target\n"
            "importlib.util.spec_from_file_location('x', target)\n",
        )
        write(tmp_path, "sibling.py", "")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_name_local_to_the_function_resolves_there(self, tmp_path: Path) -> None:
        """The shape build/generate_agents_common.py uses: a local built from a module constant."""
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "HERE = Path(__file__).resolve().parent\n"
            "def load():\n"
            "    path = HERE / 'sibling.py'\n"
            "    return importlib.util.spec_from_file_location('x', path)\n"
            "def other(path):\n    return path\n",
        )
        write(tmp_path, "sibling.py", "")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []
        assert gate._expand_import_closure(["verify.py"], tmp_path) == ["verify.py", "sibling.py"]

    def test_a_name_assigned_twice_in_the_function_is_ambiguous(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "def load():\n"
            "    path = Path(__file__).parent / 'a.py'\n"
            "    path = Path(__file__).parent / 'b.py'\n"
            "    return importlib.util.spec_from_file_location('x', path)\n",
        )
        write(tmp_path, "a.py", "")
        write(tmp_path, "b.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_an_annotated_single_assignment_still_resolves(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target: Path = Path(__file__).parent / 'sibling.py'\n"
            "importlib.util.spec_from_file_location('x', target)\n",
        )
        write(tmp_path, "sibling.py", "")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_declaration_without_a_value_is_not_an_assignment(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target: Path\n"
            "importlib.util.spec_from_file_location('x', target)\n",
        )

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_file_the_parser_gives_up_on_is_reported_not_read_as_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write(tmp_path, "verify.py", "x = 1\n")

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RecursionError("too deep")

        monkeypatch.setattr(gate.ast, "parse", _boom)

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert sites == ["verify.py:1: unresolvable dynamic load (unparseable)"]

    def test_line_breaks_in_a_listed_name_are_escaped(self) -> None:
        forged = "a.py\n  b.py\r\u2028c.py\u2029"

        rendered = gate._one_line(forged)

        assert "\n" not in rendered
        assert "\r" not in rendered
        assert "\u2028" not in rendered
        assert "\u2029" not in rendered
        assert rendered == "a.py\\n  b.py\\r\\u2028c.py\\u2029"


class TestConfirmationPassFindings:
    """The confirmation pass over the final revision, each case with its fix."""

    @pytest.mark.parametrize(
        "expression",
        [
            '(Path(__file__).parent / "..").resolve().parent / "x.py"',
            'Path(__file__).parent / "a/../x.py"',
            'Path(__file__).parent.joinpath("..", "x.py")',
            'Path(__file__).parent.with_name("../x.py")',
            'os.path.join(os.path.dirname(__file__), "..", "x.py")',
        ],
    )
    def test_a_dotdot_anywhere_in_the_derivation_is_unresolvable(
        self, tmp_path: Path, expression: str
    ) -> None:
        write(
            tmp_path,
            "sub/verify.py",
            f"import importlib.util, os\nfrom pathlib import Path\n"
            f"importlib.util.spec_from_file_location('x', {expression})\n",
        )
        write(tmp_path, "x.py", "")
        write(tmp_path, "sub/x.py", "")

        assert len(gate._unresolvable_dynamic_sites(["sub/verify.py"], tmp_path)) == 1

    @pytest.mark.parametrize(
        ("literal", "climbs"),
        [
            ("..", True),
            ("a/../b", True),
            ("a\\..\\b", True),
            ("../b", True),
            ("a/..b/c", False),
            ("..hidden", False),
            ("a/b.py", False),
            ("", False),
        ],
    )
    def test_dotdot_detection_is_by_segment(self, literal: str, climbs: bool) -> None:
        assert gate._has_dotdot(literal) is climbs

    def test_run_module_is_recognised_and_never_resolved(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "import runpy\nrunpy.run_module('pkg')\n")
        write(tmp_path, "pkg/__init__.py", "")
        write(tmp_path, "pkg/__main__.py", "")

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert len(sites) == 1
        assert "run_module" in sites[0]

    @pytest.mark.parametrize(
        "rebinding",
        [
            "def rebind():\n    global target\n    target = other\n",
            "def outer():\n    target = 1\n    def inner():\n        nonlocal target\n"
            "        target = other\n",
            "match value:\n    case target:\n        pass\n",
            "match value:\n    case [*target]:\n        pass\n",
            "match value:\n    case {'k': 1, **target}:\n        pass\n",
            "[(target := p) for p in items]\n",
        ],
    )
    def test_bindings_a_scope_table_cannot_place_make_the_name_ambiguous_everywhere(
        self, tmp_path: Path, rebinding: str
    ) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target = Path(__file__).parent / 'sibling.py'\n"
            + rebinding
            + "importlib.util.spec_from_file_location('x', target)\n",
        )
        write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    @pytest.mark.parametrize(
        "site",
        [
            "class C:\n    attr = importlib.util.spec_from_file_location('x', target)\n",
            "def f(p=importlib.util.spec_from_file_location('x', target)):\n    pass\n",
            "def f(p: importlib.util.spec_from_file_location('x', target)):\n    pass\n",
            "def f() -> importlib.util.spec_from_file_location('x', target):\n    pass\n",
            "@importlib.util.spec_from_file_location('x', target)\ndef f():\n    pass\n",
        ],
    )
    def test_a_name_read_where_python_uses_another_scope_is_not_resolved(
        self, tmp_path: Path, site: str
    ) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target = Path(__file__).parent / 'sibling.py'\n" + site,
        )
        write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_class_body_load_with_no_names_still_resolves(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "class C:\n    spec = importlib.util.spec_from_file_location(\n"
            "        'x', Path(__file__).parent / 'sibling.py')\n",
        )
        write(tmp_path, "sibling.py", "")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    @pytest.mark.parametrize(
        "code",
        [
            "__file__ = '/x/y.py'",
            "Path = object",
            "class Path: pass",
            "try:\n    pass\nexcept OSError as Path:\n    pass",
        ],
    )
    def test_constant_code_that_rebinds_a_guarded_name_is_not_inert(
        self, tmp_path: Path, code: str
    ) -> None:
        write(tmp_path, "verify.py", f"exec({code!r})\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_an_except_or_match_binding_of_path_refuses_derivation(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path as P\n"
            "try:\n    pass\nexcept OSError as Path:\n    pass\n"
            "importlib.util.spec_from_file_location('x', P(__file__).parent / 'sibling.py')\n",
        )
        write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1
