"""The per-run memo for the completion gate's dynamic-load scan.

Issue #6734, decision D8. The closure pass and the unresolvable-site pass both
scan every file for dynamic loads. A caller-owned cache lets the second pass
reuse the first pass's scan. These cases pin that the cache changes no result:
the key keeps two path spellings of one file apart, a rewritten file misses,
and an unresolvable load is still reported when the scan comes from the cache.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from tests.skills.github.dynamic_load_helpers import gate, write

_VALIDATION_DIR = Path(__file__).resolve().parents[3] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

LOAD_SIBLING = (
    "from importlib.util import spec_from_file_location\n"
    "from pathlib import Path\n"
    "spec_from_file_location('s', Path(__file__).parent / 'sibling.py')\n"
)


@pytest.fixture
def scan_count(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count real scans by wrapping ``gate._dynamic_loads``."""
    counts: dict[str, int] = {}
    real = gate._dynamic_loads

    def counting(source: bytes, script: Path) -> list[Any]:
        counts[str(script)] = counts.get(str(script), 0) + 1
        return real(source, script)

    monkeypatch.setattr(gate, "_dynamic_loads", counting)
    return counts


class TestCacheReuse:
    def test_shared_cache_scans_each_file_once_and_matches_uncached(
        self, tmp_path: Path, scan_count: dict[str, int]
    ) -> None:
        write(tmp_path, "verify.py", "import helper\n" + LOAD_SIBLING)
        write(tmp_path, "helper.py", "import sys\n__import__(sys.argv[1])\n")
        write(tmp_path, "sibling.py", "X = 1\n")

        uncached_closure = gate._expand_import_closure(["verify.py"], tmp_path)
        uncached_sites = gate._unresolvable_dynamic_sites(uncached_closure, tmp_path)
        uncached_scans = sum(scan_count.values())
        scan_count.clear()

        cache: dict[Any, Any] = {}
        closure = gate._expand_import_closure(["verify.py"], tmp_path, load_cache=cache)
        sites = gate._unresolvable_dynamic_sites(closure, tmp_path, load_cache=cache)

        assert closure == uncached_closure
        assert sites == uncached_sites
        assert uncached_scans == 2 * len(closure)
        assert set(scan_count.values()) == {1}
        assert len(scan_count) == len(closure)

    def test_no_cache_scans_on_every_call(self, tmp_path: Path, scan_count: dict[str, int]) -> None:
        script = write(tmp_path, "verify.py", LOAD_SIBLING)
        source = script.read_bytes()

        gate._memoized_dynamic_loads(source, script, None)
        gate._memoized_dynamic_loads(source, script, None)

        assert scan_count == {str(script): 2}

    def test_a_returned_list_is_a_copy_the_caller_cannot_corrupt(self, tmp_path: Path) -> None:
        script = write(tmp_path, "verify.py", LOAD_SIBLING)
        source = script.read_bytes()
        cache: dict[Any, Any] = {}

        first = gate._memoized_dynamic_loads(source, script, cache)
        first.clear()
        second = gate._memoized_dynamic_loads(source, script, cache)

        assert len(second) == 1
        assert second == gate._dynamic_loads(source, script)


class TestCacheKey:
    def test_two_spellings_of_one_file_keep_separate_entries(self, tmp_path: Path) -> None:
        # ``link`` is a directory symlink to ``real``, so both paths resolve to
        # one file with one source. The load derives its path from __file__, so
        # each spelling names a different sibling. A key on the resolved path
        # would hand the second spelling the first spelling's path.
        real = write(tmp_path, "real/verify.py", LOAD_SIBLING)
        write(tmp_path, "real/sibling.py", "X = 1\n")
        (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
        linked = tmp_path / "link" / "verify.py"
        assert linked.resolve() == real.resolve()
        source = real.read_bytes()
        cache: dict[Any, Any] = {}

        via_real = gate._memoized_dynamic_loads(source, real, cache)
        via_link = gate._memoized_dynamic_loads(source, linked, cache)

        assert [load.path for load in via_real] == [tmp_path / "real" / "sibling.py"]
        assert [load.path for load in via_link] == [tmp_path / "link" / "sibling.py"]
        assert len(cache) == 2

    def test_the_link_spelling_is_still_reported_with_a_shared_cache(self, tmp_path: Path) -> None:
        write(tmp_path, "real/verify.py", LOAD_SIBLING)
        write(tmp_path, "real/sibling.py", "X = 1\n")
        (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
        paths = ["real/verify.py", "link/verify.py"]
        cache: dict[Any, Any] = {}

        cached = gate._unresolvable_dynamic_sites(paths, tmp_path, load_cache=cache)
        uncached = gate._unresolvable_dynamic_sites(paths, tmp_path)

        assert cached == uncached
        assert [site.split(":")[0] for site in cached] == ["link/verify.py"]

    def test_a_rewritten_file_misses_the_cache(self, tmp_path: Path) -> None:
        script = write(tmp_path, "verify.py", "X = 1\n")
        cache: dict[Any, Any] = {}
        assert gate._memoized_dynamic_loads(script.read_bytes(), script, cache) == []

        write(tmp_path, "verify.py", "import sys\n__import__(sys.argv[1])\n")
        after = gate._memoized_dynamic_loads(script.read_bytes(), script, cache)

        assert [(load.line, load.kind) for load in after] == [(2, "__import__")]
        assert len(cache) == 2


class TestSitesStillReported:
    def test_an_unresolvable_load_is_reported_from_a_warm_cache(self, tmp_path: Path) -> None:
        write(tmp_path, "verify.py", "import helper\n")
        write(tmp_path, "helper.py", "import sys\n__import__(sys.argv[1])\n")
        cache: dict[Any, Any] = {}

        closure = gate._expand_import_closure(["verify.py"], tmp_path, load_cache=cache)
        assert any(key[0] == tmp_path / "helper.py" for key in cache)
        sites = gate._unresolvable_dynamic_sites(closure, tmp_path, load_cache=cache)

        assert sites == ["helper.py:2: unresolvable dynamic load (__import__)"]


class TestClosureManifestCacheLifetime:
    def test_each_build_passes_one_fresh_cache_to_both_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import closure_manifest as cm

        from tests.validation.closure_helpers import make_repo, workflow

        monkeypatch.setattr(cm, "REQUIRED_CONTEXTS", frozenset({"Run Python Tests"}))
        make_repo(
            tmp_path,
            {
                ".github/workflows/t.yml": workflow("g", "      - run: python scripts/entry.py\n"),
                "scripts/entry.py": "import sys\n__import__(sys.argv[1])\n",
            },
        )
        seen: list[tuple[str, int, int]] = []
        real_load = cm._load_gate

        def spying_load(gate_root: Path) -> Any:
            loaded = real_load(gate_root)
            expand = loaded._expand_import_closure
            sites = loaded._unresolvable_dynamic_sites

            def spy_expand(*args: Any, load_cache: Any) -> Any:
                seen.append(("expand", id(load_cache), len(load_cache)))
                return expand(*args, load_cache=load_cache)

            def spy_sites(*args: Any, load_cache: Any) -> Any:
                seen.append(("sites", id(load_cache), len(load_cache)))
                return sites(*args, load_cache=load_cache)

            loaded._expand_import_closure = spy_expand
            loaded._unresolvable_dynamic_sites = spy_sites
            return loaded

        monkeypatch.setattr(cm, "_load_gate", spying_load)

        first = cm.build_manifest(tmp_path, gate_root=tmp_path)
        second = cm.build_manifest(tmp_path, gate_root=tmp_path)

        assert [kind for kind, _, _ in seen] == ["expand", "sites", "expand", "sites"]
        assert seen[0][1] == seen[1][1]
        assert seen[2][1] == seen[3][1]
        assert seen[0][2] == 0 and seen[2][2] == 0
        assert seen[1][2] > 0
        assert first.to_json() == second.to_json()
        assert [u.source for u in first.unresolved] == ["scripts/entry.py"]
