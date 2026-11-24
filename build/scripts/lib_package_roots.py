"""Per-package render scope for ``lib_mirror`` (ADR-109 amendment 2026-11-20, issue #7493).

``lib_mirror.PACKAGES`` renders every package into every plugin lib root unless
this module narrows it. ``memory_enhancement`` ships to the Claude plugin only:
no other harness has a caller for per-prompt recall. It also carries a ``hooks``
sub-package, and ``lib_mirror.sync_pair`` copies one directory's ``.py`` files,
so each sub-package is its own source and destination pair.
"""

from __future__ import annotations

from collections.abc import Iterator

# Packages that render into a subset of lib_mirror.PLUGIN_ROOTS. A package
# absent here renders into every root.
PACKAGE_ROOTS: dict[str, tuple[str, ...]] = {
    "memory_enhancement": ("src/claude/lib",),
}

# Sub-packages a package carries below its top-level directory.
PACKAGE_SUBDIRS: dict[str, tuple[str, ...]] = {
    "memory_enhancement": ("hooks",),
}


def package_plugin_roots(package: str, default_roots: tuple[str, ...]) -> tuple[str, ...]:
    """Return the plugin lib roots *package* renders into."""
    return PACKAGE_ROOTS.get(package, default_roots)


def package_pairs(package: str, plugin_root: str) -> list[tuple[str, str]]:
    """Return (source, destination) directory pairs for one package and root."""
    pairs = [(f"scripts/{package}", f"{plugin_root}/{package}")]
    for sub in PACKAGE_SUBDIRS.get(package, ()):
        pairs.append((f"scripts/{package}/{sub}", f"{plugin_root}/{package}/{sub}"))
    return pairs


def iter_package_pairs(
    packages: tuple[str, ...], default_roots: tuple[str, ...]
) -> Iterator[tuple[str, str]]:
    """Yield every (source, destination) directory pair ``compile_all`` syncs."""
    for package in packages:
        for root in package_plugin_roots(package, default_roots):
            yield from package_pairs(package, root)
