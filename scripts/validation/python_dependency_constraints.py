"""Partition marker environments without consulting the host environment.

PEP 440 interval operations use the locked packaging 26.3 range engine.
Marker syntax comes from packaging.markers.Marker._markers. Each variable's
reachable atom truth vectors form a finite partition for supported predicates.
Their Cartesian product retains alternatives beyond the current platform.
Python minor/full versions share one dimension. Other environment variables
remain independent; this module does not encode OS-specific field correlations.
"""

from __future__ import annotations

from collections import defaultdict, deque
from itertools import product

from packaging._parser import MarkerItem, MarkerList, Variable
from packaging.markers import MARKERS_ALLOWING_SET, MARKERS_REQUIRING_VERSION, Marker
from packaging.ranges import VersionRange
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


def satisfiable(specs: list[str]) -> bool:
    """Intersect exact intervals while retaining each declaration's pre policy."""
    sets = [SpecifierSet(spec) for spec in specs if spec]
    prereleases = all(spec.prereleases for spec in sets)
    combined = SpecifierSet(",".join(specs), prereleases=prereleases)
    return not combined.is_unsatisfiable()


def _atoms(expression: MarkerList) -> list[MarkerItem]:
    found: list[MarkerItem] = []
    for node in expression:
        if isinstance(node, tuple):
            found.append(node)
        elif isinstance(node, list):
            found.extend(_atoms(node))
    return found


def _atom_text(atom: MarkerItem) -> str:
    return " ".join(part.serialize() for part in atom)


def _variable(atom: MarkerItem) -> str:
    left, _, right = atom
    if isinstance(left, Variable):
        return left.value
    return right.value


def _literal(atom: MarkerItem) -> str:
    left, _, right = atom
    if isinstance(left, Variable):
        return right.value
    return left.value


def _string_states(atoms: list[MarkerItem]) -> list[str]:
    """Traverse the finite substring/equality automaton, not sampled strings.

    A state retains the longest pattern prefix suffix, every matched substring,
    and a still-possible exact value. All other characters share one transition.
    """
    literals = {_literal(atom) for atom in atoms}
    exact = set(literals)
    for atom in atoms:
        if isinstance(atom[0], Variable) and atom[1].value in {"in", "not in"}:
            literal = _literal(atom)
            exact.update(
                literal[i:j] for i in range(len(literal) + 1) for j in range(i, len(literal) + 1)
            )
    tokens = {
        _literal(atom)
        for atom in atoms
        if not isinstance(atom[0], Variable) and atom[1].value in {"in", "not in"}
    }
    prefixes = {text[:i] for text in exact | tokens for i in range(len(text) + 1)}
    alphabet = set("".join(literals))
    other = 1
    while chr(other) in alphabet:
        other += 1
    alphabet.add(chr(other))
    initial: tuple[str, frozenset[str], str | None] = ("", frozenset({""}), "")
    queue = deque([(initial, "")])
    seen = {initial}
    witnesses = []
    while queue:
        state, text = queue.popleft()
        witnesses.append(text)
        for char in sorted(alphabet):
            next_state = _string_transition(state, char, tokens, prefixes)
            if next_state not in seen:
                seen.add(next_state)
                queue.append((next_state, text + char))
    return witnesses


def _string_transition(
    state: tuple[str, frozenset[str], str | None],
    char: str,
    tokens: set[str],
    prefixes: set[str],
) -> tuple[str, frozenset[str], str | None]:
    suffix, matched, exact = state
    tail = suffix + char
    matched = matched | {token for token in tokens if tail.endswith(token)}
    suffix = max((p for p in prefixes if tail.endswith(p)), key=len)
    exact = exact + char if exact is not None else None
    if exact not in prefixes:
        exact = None
    return suffix, matched, exact


def _string_signatures(atoms: list[MarkerItem]) -> set[tuple[bool, ...]]:
    variable = _variable(atoms[0])
    markers = [Marker(_atom_text(atom)) for atom in atoms]
    return {
        tuple(marker.evaluate({variable: text}) for marker in markers)
        for text in _string_states(atoms)
    }


def _version_range(atom: MarkerItem) -> VersionRange:
    left, operator, _ = atom
    if not isinstance(left, Variable):
        return _reversed_range(atom)
    return SpecifierSet(f"{operator.value}{_literal(atom)}", prereleases=True).to_range()


def _minor_boundaries(atom: MarkerItem) -> list[Version]:
    literal = _literal(atom)
    texts = {literal.rstrip(".*")}
    if atom[1].value in {"in", "not in"}:
        if not isinstance(atom[0], Variable):
            raise ValueError(f"unsupported unbounded version substring marker: {_atom_text(atom)}")
        texts = {literal[i:j] for i in range(len(literal)) for j in range(i + 1, len(literal) + 1)}
    boundaries = {Version("0.dev0")}
    for text in _valid_versions(texts):
        version = Version(text)
        major, minor = (*version.release, 0)[:2]
        boundaries.update(
            Version(f"{a}.{b}.dev0")
            for a, b in [(major, 0), (major, minor), (major, minor + 1), (major + 1, 0)]
        )
    return sorted(boundaries)


def _python_minor_range(atom: MarkerItem) -> VersionRange:
    """Lift major.minor predicates into full-version prefix intervals.

    Boundaries come from the literal's major/minor prefix and its successors.
    packaging evaluates each resulting discrete minor interval, including
    reversed operators and substring membership in finite literals.
    """
    boundaries = _minor_boundaries(atom)
    marker = Marker(_atom_text(atom))
    found = VersionRange.empty(prereleases=True)
    for index, lower in enumerate(boundaries):
        major, minor = (*lower.release, 0)[:2]
        if not marker.evaluate({"python_version": f"{major}.{minor}"}):
            continue
        spec = f">={lower}"
        if index + 1 < len(boundaries):
            spec += f",<{boundaries[index + 1]}"
        found = found.union(SpecifierSet(spec, prereleases=True).to_range())
    return found


def _reversed_range(atom: MarkerItem) -> VersionRange:
    """Invert the PEP 440 post/pre exclusions, not just the comparison sign.

    The exclusions originate in packaging._ranges.standard_ranges. Its strict
    operators differ from ordinary ordered comparisons at pre/post boundaries.
    """
    op = atom[1].value
    version = Version(_literal(atom))
    if op == "~=":
        raise ValueError(f"unsupported reversed compatible-release marker: {_atom_text(atom)}")
    inverse = {"<=": ">=", ">=": "<="}.get(op, op)
    if op not in {"<", ">"}:
        return SpecifierSet(f"{inverse}{version}", prereleases=True).to_range()
    opposite = ">=" if op == ">" else "<="
    region = SpecifierSet(f"{opposite}{version}", prereleases=True).to_range().complement()
    excluded = None
    if op == ">" and version.post is not None:
        excluded = version.public.split(".post", 1)[0]
    if op == "<" and version.is_prerelease:
        excluded = version.base_version
        if version.pre is None and version.post is not None:
            excluded = f"{excluded}.post{version.post}"
    if excluded is not None:
        region = region.difference(SpecifierSet(f"=={excluded}", prereleases=True).to_range())
    return region


def _range_signatures(ranges: list[VersionRange]) -> set[tuple[bool, ...]]:
    states: list[tuple[tuple[bool, ...], VersionRange]] = [
        ((), VersionRange.full(prereleases=True))
    ]
    for constraint in ranges:
        states = _split_ranges(states, constraint)
    return {bits for bits, _ in states}


def _split_ranges(
    states: list[tuple[tuple[bool, ...], VersionRange]], constraint: VersionRange
) -> list[tuple[tuple[bool, ...], VersionRange]]:
    found = []
    for bits, region in states:
        for value, half in [(True, constraint), (False, constraint.complement())]:
            intersection = region.intersection(half)
            if not intersection.is_empty:
                found.append(((*bits, value), intersection))
    return found


def _version_signatures(atoms: list[MarkerItem]) -> set[tuple[bool, ...]]:
    """Partition numeric predicates and finite membership literals exactly.

    Different than canonical: numeric regions contain valid PEP 440 versions.
    Pure string fallbacks use the string automaton instead. Mixed numeric and
    nonnumeric predicates, unbounded reversed version substrings, and reversed
    full-version compatible-release predicates fail instead of guessing overlap.
    """
    finite: set[str] = set()
    ranges: list[VersionRange | None] = []
    variable = _variable(atoms[0])
    for atom in atoms:
        if _variable(atom) == "python_version":
            ranges.append(_python_minor_range(atom))
        elif atom[1].value == "===":
            finite.update(_case_spellings(_literal(atom)))
            ranges.append(None)
        elif atom[1].value in {"in", "not in"}:
            if not isinstance(atom[0], Variable):
                raise ValueError(
                    f"unsupported unbounded version substring marker: {_atom_text(atom)}"
                )
            literal = _literal(atom)
            finite.update(
                literal[i:j] for i in range(len(literal)) for j in range(i + 1, len(literal) + 1)
            )
            ranges.append(None)
        else:
            ranges.append(_version_range(atom))
    if all(r is not None for r in ranges):
        return _range_signatures([r for r in ranges if r is not None])
    markers = [Marker(_atom_text(atom)) for atom in atoms]
    versions = _valid_versions(finite)
    signatures = {
        tuple(m.evaluate(_version_environment(variable, text)) for m in markers)
        for text in versions
    }
    # Every numeric version also has spellings outside any finite string list.
    # PEP 440 equality cannot subtract only one literal spelling.
    outside = VersionRange.full(prereleases=True)
    states: list[tuple[tuple[bool, ...], VersionRange]] = [((), outside)]
    for atom, region in zip(atoms, ranges, strict=True):
        if region is None:
            states = [
                ((*bits, atom[1].value == "not in"), r) for bits, r in states if not r.is_empty
            ]
        else:
            states = _split_ranges(states, region)
    return signatures | {bits for bits, _ in states}


def _case_spellings(text: str) -> set[str]:
    return {"".join(chars) for chars in product(*({char.lower(), char.upper()} for char in text))}


def _version_environment(variable: str, text: str) -> dict[str, str]:
    if variable not in {"python_version", "python_full_version"}:
        return {variable: text}
    major, minor = (*Version(text).release, 0)[:2]
    return {"python_full_version": text, "python_version": f"{major}.{minor}"}


def _valid_versions(texts: set[str]) -> set[str]:
    valid = set()
    for text in texts:
        try:
            Version(text)
        except InvalidVersion:
            continue
        valid.add(text)
    return valid


def _signatures(atoms: list[MarkerItem]) -> set[tuple[bool, ...]]:
    if _variable(atoms[0]) in MARKERS_ALLOWING_SET:
        return _set_signatures(atoms)
    if _variable(atoms[0]) not in MARKERS_REQUIRING_VERSION:
        return _string_signatures(atoms)
    try:
        return _version_signatures(atoms)
    except InvalidSpecifier as exc:
        if any(_numeric_marker(atom) for atom in atoms):
            raise ValueError(f"mixed numeric/string version markers: {exc}") from exc
        return _string_signatures(atoms)


def _numeric_marker(atom: MarkerItem) -> bool:
    try:
        SpecifierSet(f"{atom[1].value}{_literal(atom)}")
    except InvalidSpecifier:
        return False
    return True


def _set_signatures(atoms: list[MarkerItem]) -> set[tuple[bool, ...]]:
    variable = _variable(atoms[0])
    literals = sorted({_literal(atom) for atom in atoms})
    markers = [Marker(_atom_text(atom)) for atom in atoms]
    signatures = set()
    for bits in product((False, True), repeat=len(literals)):
        selected = frozenset(text for text, bit in zip(literals, bits, strict=True) if bit)
        signatures.add(tuple(marker.evaluate({variable: selected}) for marker in markers))
    return signatures


def _evaluate(expression: MarkerList, values: dict[str, bool]) -> bool:
    groups: list[list[bool]] = [[]]
    for node in expression:
        if isinstance(node, tuple):
            groups[-1].append(values[_atom_text(node)])
        elif isinstance(node, list):
            groups[-1].append(_evaluate(node, values))
        elif node == "or":
            groups.append([])
    return any(all(group) for group in groups)


def active_groups(markers: list[str]) -> set[tuple[int, ...]]:
    """Return every reachable declaration set, including unmarked requirements."""
    expressions = [Marker(marker)._markers if marker else [] for marker in markers]
    by_variable: dict[str, dict[str, MarkerItem]] = defaultdict(dict)
    for expression in expressions:
        for atom in _atoms(expression):
            variable = _variable(atom)
            if variable == "python_version":
                variable = "python_full_version"
            by_variable[variable][_atom_text(atom)] = atom
    partitions: list[list[dict[str, bool]]] = []
    for atoms_by_text in by_variable.values():
        atoms = list(atoms_by_text.values())
        names = list(atoms_by_text)
        partitions.append([dict(zip(names, bits, strict=True)) for bits in _signatures(atoms)])
    groups = set()
    for assignment in product(*partitions):
        values: dict[str, bool] = {}
        for part in assignment:
            values.update(part)
        groups.add(
            tuple(i for i, expression in enumerate(expressions) if _evaluate(expression, values))
        )
    return groups
