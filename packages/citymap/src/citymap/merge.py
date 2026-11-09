# Copyright (c) 2026 nm_health contributors
"""Join lines that share endpoints into longer chains.

OpenStreetMap splits one road into many ways (at every change of speed limit, lanes, bridge...). Joining them before
simplifying lets RDP see the whole road, so fewer points survive and fewer tiny pieces remain. Multipolygon members
are joined the same way to rebuild their rings.
"""

from collections import defaultdict
from collections.abc import Sequence

from citymap.geometry import Line, Point


def _index_ends(lines: Sequence[Line]) -> dict[Point, list[int]]:
    """Every endpoint, mapped to the lines that start or end there."""
    ends: dict[Point, list[int]] = defaultdict(list)
    for i, line in enumerate(lines):
        ends[line[0]].append(i)
        ends[line[-1]].append(i)
    return ends


def _extend(chain: Line, lines: Sequence[Line], ends: dict[Point, list[int]], used: set[int]) -> None:
    """Grow chain forward from its last point, taking unused lines (reversed if need be) until none fits."""
    while True:
        tip = chain[-1]
        nxt = next((j for j in ends.get(tip, ()) if j not in used), None)
        if nxt is None:
            return
        used.add(nxt)
        other = lines[nxt]
        chain.extend(other[1:] if other[0] == tip else reversed(other[:-1]))


def merge_lines(lines: Sequence[Sequence[Point]]) -> list[Line]:
    """Join lines end to end wherever they share an endpoint. Order and direction are not preserved."""
    usable = [list(line) for line in lines if len(line) > 1]
    ends = _index_ends(usable)
    used: set[int] = set()
    merged: list[Line] = []
    for i, line in enumerate(usable):
        if i in used:
            continue
        used.add(i)
        chain = list(line)
        _extend(chain, usable, ends, used)
        chain.reverse()
        _extend(chain, usable, ends, used)
        merged.append(chain)
    return merged
