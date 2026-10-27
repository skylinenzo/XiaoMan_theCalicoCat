"""Plan whole-body pose changes without coupling them to timers or rendering.

The caller displays each returned state in order and pauses autonomous behavior
until the route finishes. Walking edges may expand into the existing turn/sit
drawings. ``held`` is an immediate handling overlay; its only release edge is
``idle``, so a dropped pet never resumes an old walking or rolling route.
"""

from collections import deque
from types import MappingProxyType


# Order is stable, making route choice deterministic if the graph is extended.
# A window perch shares the prone posture. Attaching/detaching the actual window
# surface is deliberately the caller's responsibility, not a pose-graph edge.
TRANSITION_GRAPH = MappingProxyType({
    'idle': ('groom', 'walk_left', 'walk_right', 'rest_prone'),
    'groom': ('idle',),
    'walk_left': ('idle',),
    'walk_right': ('idle',),
    'rest_prone': ('idle', 'rest_side', 'window_perch', 'play_kick', 'play_lick'),
    'play_kick': ('rest_prone',),
    'play_lick': ('rest_prone',),
    'rest_side': ('rest_prone', 'rest_supine'),
    'rest_supine': ('rest_side',),
    'window_perch': ('rest_prone', 'window_straddle'),
    'window_straddle': ('window_perch',),
})
ACTION_STATES = frozenset((*TRANSITION_GRAPH, 'held'))


def transition_route(source: str, target: str) -> tuple[str, ...]:
    """Return the shortest legal pose route, excluding source and including target.

    Equal known states return an empty tuple. Unknown or non-string states raise
    ``ValueError``. Pickup overrides the current pose immediately. Release goes
    through seated idle before any requested subsequent action.

    For an interrupted route, pass the currently displayed *named pose*, rather
    than its abandoned destination. The caller can retain the actual rendered
    image as the first visual frame when that pose is partway through a motion.
    """
    for label, state in (('source', source), ('target', target)):
        if not isinstance(state, str) or state not in ACTION_STATES:
            raise ValueError(f'Unknown {label} action: {state!r}')
    if source == target:
        return ()
    if target == 'held':
        return ('held',)
    if source == 'held':
        return ('idle', *transition_route('idle', target))

    pending = deque([(source, ())])
    visited = {source}
    while pending:
        current, route = pending.popleft()
        for neighbor in TRANSITION_GRAPH[current]:
            if neighbor in visited:
                continue
            next_route = (*route, neighbor)
            if neighbor == target:
                return next_route
            visited.add(neighbor)
            pending.append((neighbor, next_route))
    # Every supported normal pose belongs to the same connected graph.
    raise RuntimeError(f'No transition route from {source!r} to {target!r}')
