"""Guard the ``os`` spawn entry points against a Copilot launch (issue #6506).

``subprocess`` is covered by ``GuardedPopen`` in ``local_smoke_guard``. Python code can also
start a program through ``os.system``, ``os.posix_spawn``, and the ``exec*`` and ``spawn*``
families, so each is wrapped to read its program and argv before it runs.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable, Mapping
from typing import Any

from local_smoke_refuse import CopilotCallRefusedError, refuse_copilot

# The os spawn entry points, mapped to the positions of the program and of the argv
# (None when the entry point takes a command line instead). The ``exec*`` and
# ``spawn*`` names with an ``l`` call these through the os module, so they are covered.
_OS_ENTRY_POINTS: dict[str, tuple[int, int | None]] = {
    "system": (0, None),
    "posix_spawn": (0, 1),
    "posix_spawnp": (0, 1),
    "execv": (0, 1),
    "execve": (0, 1),
    "execvp": (0, 1),
    "execvpe": (0, 1),
    "spawnv": (1, 2),
    "spawnve": (1, 2),
    "spawnvp": (1, 2),
    "spawnvpe": (1, 2),
}
_ORIGINAL_OS = {name: getattr(os, name) for name in _OS_ENTRY_POINTS if hasattr(os, name)}


def _bind(
    signature: inspect.Signature | None, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Mapping[int, Any]:
    """Map a call to its values by position, binding keywords through ``signature``.

    ``execve(path=..., argv=...)`` and ``spawnv(0, file=..., args=...)`` pass the program by
    keyword, so reading only ``args`` would miss them. ``posix_spawn`` and ``execv`` take their
    first parameters positional-only, so Python itself rejects a keyword there. A call the
    signature cannot bind is left to the original, which raises its own ``TypeError``.
    """
    if signature is None or not kwargs:
        return dict(enumerate(args))
    try:
        bound = signature.bind_partial(*args, **kwargs)
    except TypeError:
        return dict(enumerate(args))
    names = list(signature.parameters)
    return {i: bound.arguments[n] for i, n in enumerate(names) if n in bound.arguments}


def _signature_of(function: Callable[..., Any]) -> inspect.Signature | None:
    try:
        return inspect.signature(function)
    except (TypeError, ValueError):
        return None


# Read from the real functions at import: a test may later swap ``_ORIGINAL_OS`` entries for
# stand-ins whose ``(*args, **kwargs)`` signature names no parameter.
_SIGNATURES = {name: _signature_of(original) for name, original in _ORIGINAL_OS.items()}


_RESOLVE: Any = object()  # "no signature given": read it from the original


def _names_parameters(signature: inspect.Signature | None) -> bool:
    """Return True when keywords can be mapped to positions through ``signature``."""
    variadic = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    return signature is not None and all(
        p.kind not in variadic for p in signature.parameters.values()
    )


def _guarded_os(
    original: Callable[..., Any],
    program: int,
    argv: int | None,
    signature: inspect.Signature | None = _RESOLVE,
) -> Callable[..., Any]:
    if signature is _RESOLVE:
        signature = _signature_of(original)

    def guarded(*args: Any, **kwargs: Any) -> Any:
        values = _bind(signature, args, kwargs)
        if kwargs and not _names_parameters(signature):
            # Keyword names cannot be mapped to positions, so fail closed.
            if argv is None and "command" in kwargs:  # os.system(command=...)
                refuse_copilot(kwargs["command"])
            raise CopilotCallRefusedError(
                "The local CLI smoke cannot read keyword arguments of this os spawn function "
                f"(got {sorted(kwargs)!r}), so it refuses the call. Pass the arguments by position."
            )
        if program in values:
            refuse_copilot(values[program] if argv is None else [values[program]])
        if argv is not None and isinstance(values.get(argv), (list, tuple)):
            refuse_copilot(list(values[argv]))
        return original(*args, **kwargs)

    return guarded


def install_os(setattr_fn: Callable[[object, str, object], None]) -> None:
    """Replace the ``os`` spawn entry points through ``setattr_fn``."""
    for name, original in _ORIGINAL_OS.items():
        program, argv = _OS_ENTRY_POINTS[name]
        setattr_fn(os, name, _guarded_os(original, program, argv, _SIGNATURES[name]))
