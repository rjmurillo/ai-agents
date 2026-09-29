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
            "SourceFileLoader('x', str(Path(__file__).parent / 'data.txt'))\n",
        )
        write(tmp_path, "data.txt", "print(1)\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

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
            "def f(target):\n    load(target)\n",
            "for target in items:\n    load(target)\n",
            "a, target = pair\n",
            "with open(p) as target:\n    load(target)\n",
            "[load(target) for target in items]\n",
            "(target := compute())\n",
            "[target, other] = pair\n",
        ],
    )
    def test_a_name_bound_in_another_way_is_ambiguous(self, tmp_path: Path, binding: str) -> None:
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
