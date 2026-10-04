"""Read the ratchet registry as it exists at a commit, never from the working tree.

A base-derived ratchet takes its ceiling from the merge base, but the decision
to skip the comparison (bootstrap) used to rest on the branch's own registry. A
branch could rename a ratchet script, or drop a label, and the ratchet then
looked new. This module answers from the fork instead: which labels the
registry held there, and which script each one named.

The registry file is parsed with ``ast`` and never imported, so reading a
commit runs none of its code. Both registry shapes are understood:
``MergeTreeRatchet(label, baseline, module[, script])`` and
``_base_derived(label, module)``, whose script is the module's ``_SCRIPT``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.ci.count_ratchet import baseline_absent_at_ref, git_environment
from scripts.ci.merge_tree_materialization import run_git

__all__ = ["REGISTRY_PATH", "RegistryEntries", "registry_drift", "registry_labels_at"]

REGISTRY_PATH = "scripts/ci/merge_tree_ratchet_registry.py"
_CALLS = {"MergeTreeRatchet", "_base_derived"}

# label -> script path at that commit, or None when the commit records none.
RegistryEntries = dict[str, str | None]


def _show(repo_root: Path, commit: str, rel: str) -> str | None:
    proc = run_git(repo_root, "show", f"{commit}:{rel}", env=git_environment())
    return proc.stdout if proc.returncode == 0 else None


def _string(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _module_script(repo_root: Path, commit: str, module: str) -> str | None:
    text = _show(repo_root, commit, f"scripts/ci/{module}.py")
    if text is None:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_SCRIPT" for t in node.targets
        ):
            return _string(node.value)
    return None


def _entry(repo_root: Path, commit: str, call: ast.Call) -> tuple[str, str | None] | None:
    label = _string(call.args[0]) if call.args else None
    if label is None:
        return None
    name = call.func.id if isinstance(call.func, ast.Name) else ""
    if name == "MergeTreeRatchet":
        explicit = _string(call.args[3]) if len(call.args) > 3 else None
        if explicit is not None:
            return label, explicit
        module_arg = call.args[2] if len(call.args) > 2 else None
    else:
        module_arg = call.args[1] if len(call.args) > 1 else None
    if isinstance(module_arg, ast.Name):
        return label, _module_script(repo_root, commit, module_arg.id)
    return label, None


def registry_labels_at(repo_root: Path, commit: str) -> RegistryEntries | None:
    """Return the registry at ``commit``, or None when it cannot be read.

    A commit that carries no registry file yet holds an empty registry. Any
    other failure (unresolvable ref, unparseable file) returns None so the
    caller fails closed instead of reading an error as an empty registry.
    """
    text = _show(repo_root, commit, REGISTRY_PATH)
    if text is None:
        return {} if baseline_absent_at_ref(repo_root, commit, repo_root / REGISTRY_PATH) else None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    entries: RegistryEntries = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in _CALLS:
            found = _entry(repo_root, commit, node)
            if found is not None:
                entries[found[0]] = found[1]
    return entries


def registry_drift(fork: RegistryEntries, branch: RegistryEntries) -> list[str]:
    """Return one typed message per fork label the branch removed or re-pointed.

    ``branch`` maps each label the branch registers to its script path. A fork
    entry with no recorded script constrains only the label.
    """
    problems: list[str] = []
    for label, fork_script in sorted(fork.items()):
        if label not in branch:
            problems.append(
                f"{label}: RATCHET REMOVED. The fork point registers this ratchet and "
                f"the branch registry does not. Restore it; a ratchet cannot leave "
                f"the registry inside the change that adds violations."
            )
        elif fork_script is not None and branch[label] != fork_script:
            problems.append(
                f"{label}: RATCHET SCRIPT MOVED. The fork point names {fork_script} "
                f"and the branch names {branch[label]}. A moved script would read "
                f"as a new ratchet and skip the comparison; keep the path."
            )
    return problems
