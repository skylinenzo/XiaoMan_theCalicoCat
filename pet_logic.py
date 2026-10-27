"""Platform-independent positioning and seamless blink timing."""
import random

REST_STATES = ('rest_prone', 'rest_supine', 'rest_side')


def sequence_frame(seconds, order, durations_ms):
    remaining = (seconds * 1000) % sum(durations_ms)
    for index, duration in zip(order, durations_ms):
        if remaining < duration:
            return index
        remaining -= duration
    return order[0]


def sequence_blend(seconds, order, durations_ms, transition_ms):
    """Hold each pose, then blend briefly into the next, including the loop seam."""
    remaining = (seconds * 1000) % sum(durations_ms)
    for position, (index, duration) in enumerate(zip(order, durations_ms)):
        if remaining < duration:
            transition = min(max(transition_ms, 0), duration)
            if transition == 0 or remaining <= duration - transition:
                return index, index, 0.0
            progress = (remaining - (duration - transition)) / transition
            blend = progress * progress * (3 - 2 * progress)
            return index, order[(position + 1) % len(order)], blend
        remaining -= duration
    return order[0], order[0], 0.0


def stride_speed(stride_pixels, display_width, frame_width, cycle_seconds):
    """Move one scaled source stride during one complete animation cycle."""
    return stride_pixels * display_width / frame_width / cycle_seconds


class PetBehavior:
    """Small state machine; time advances only while the pet is not being handled."""
    def __init__(self, rng=None, cycle_seconds=None):
        self.rng = rng or random.Random()
        # The application supplies asset timings; a one-second cycle is useful
        # for standalone simulations without loading graphics or asset files.
        self.cycle_seconds = dict(cycle_seconds) if cycle_seconds is not None else {
            'groom': 1.0, 'walk_left': 1.0, 'walk_right': 1.0}
        if any(duration <= 0 for duration in self.cycle_seconds.values()):
            raise ValueError('Animation cycles must have a positive duration')
        self.enabled = True
        self.state = 'idle'
        self.elapsed = 0.0
        self.duration = self.rng.uniform(4, 9)

    def start(self, state):
        self.state = state
        self.elapsed = 0.0
        if state == 'idle':
            self.duration = self.rng.uniform(4, 10)
        elif state in ('play_kick', 'play_lick'):
            self.duration = self.cycle_seconds[state]
        elif state == 'groom':
            self.duration = self.cycle_seconds[state] * self.rng.randint(2, 4)
        elif state in REST_STATES:
            self.duration = self.cycle_seconds.get(state, 3.2) * self.rng.randint(2, 3)
        else:
            self.duration = self.cycle_seconds[state] * self.rng.randint(3, 7)

    def advance(self, dt, x, left, right, speed, can_walk=True, surface_moving=False):
        right = max(left, right)
        x = max(left, min(x, right))
        if self.state.startswith('walk') and not can_walk:
            self.start('idle')
        if self.state.startswith('walk') and surface_moving:
            # Keep the current pose and gait phase while the taskbar carries the
            # pet vertically, then continue the same step when it settles.
            return x
        self.elapsed += dt
        if self.state.startswith('walk'):
            direction = -1 if self.state == 'walk_left' else 1
            x += direction * speed * dt
            if x <= left or x >= right:
                x = max(left, min(x, right))
                self.start('idle')
                return x
        if self.elapsed >= self.duration:
            if self.state != 'idle' or not self.enabled:
                self.start('idle')
            else:
                choices = ['idle', 'groom', 'groom']
                if can_walk and not surface_moving and right - left > 8:
                    if x - left > 8:
                        choices.extend(['walk_left'] * 2)
                    if right - x > 8:
                        choices.extend(['walk_right'] * 2)
                self.start(self.rng.choice(choices))
        return x


class PatrolBehavior(PetBehavior):
    """Walk to alternating screen edges, with one rest/groom stop on long legs."""
    def __init__(self, rng=None, cycle_seconds=None, rest_states=(), rhythm=None):
        super().__init__(rng, cycle_seconds)
        self.rhythm = rhythm
        self.rest_states = tuple(rest_states)
        self.rest_pending = None
        self.direction = -1
        self.stop_x = None
        self.mid_stop = False
        self.leg_rest_done = False
        self.groom_pending = False
        self.rest_reason = 'startup'

    def start(self, state):
        # User actions/dragging deliberately cancel the old intermediate stop.
        super().start(state)
        self.stop_x = None
        self.leg_rest_done = False
        self.groom_pending = False
        self.rest_reason = 'manual'
        self.rest_pending = None
        if self.rhythm and self.enabled and self.rhythm.quiet and not state.startswith('walk'):
            self.duration = self.rhythm.rest_duration()
        if state.startswith('walk'):
            self.direction = -1 if state == 'walk_left' else 1

    def _rest(self, midpoint):
        super().start('idle')
        self.duration = self.rng.uniform(2, 4) if midpoint else self.rng.uniform(3, 6)
        self.rest_reason = 'midpoint' if midpoint else 'edge'
        self.groom_pending = self.enabled and (midpoint or self.rng.random() < .65)
        self.rest_pending = (self.rng.choice(self.rest_states)
                             if self.enabled and self.rest_states and self.rng.random() < .7 else None)
        self.stop_x = None
        if midpoint:
            self.leg_rest_done = True
        else:
            self.direction *= -1
            self.leg_rest_done = False

    def advance(self, dt, x, left, right, speed, can_walk=True, surface_moving=False, stop_filter=None):
        right = max(left, right)
        x = max(left, min(x, right))
        if self.state.startswith('walk') and not can_walk:
            self.start('idle')
        if self.state.startswith('walk') and surface_moving:
            return x
        self.elapsed += dt
        if self.state.startswith('walk'):
            edge = left if self.direction < 0 else right
            if self.stop_x is None:
                remaining = abs(edge - x)
                self.mid_stop = self.enabled and not self.leg_rest_done and remaining > 280
                self.stop_x = x + (edge - x) * self.rng.uniform(.35, .6) if self.mid_stop else edge
                if stop_filter:
                    self.stop_x = stop_filter(self.stop_x, self.direction)
            if not self.mid_stop:
                self.stop_x = edge  # Follow display/size changes while patrolling.
            self.stop_x = max(left, min(self.stop_x, right))
            # Geometry changes may move a waypoint behind the pet.
            if self.direction * (self.stop_x - x) <= 0:
                self._rest(self.mid_stop and abs(x - edge) > 2)
                return x
            distance = min(max(0., speed * dt), abs(self.stop_x - x))
            x += self.direction * distance
            if abs(x - self.stop_x) < 1e-6:
                self._rest(self.mid_stop and abs(x - edge) > 2)
            return x
        if self.elapsed < self.duration:
            return x
        if self.enabled and self.rhythm and self.rhythm.quiet:
            self.start(self.rhythm.rest_pose())
            return x
        if self.state in ('groom','play_kick','play_lick') or self.state in self.rest_states:
            super().start('idle')
            self.duration = self.rng.uniform(1, 2)
        elif not self.enabled:
            self.groom_pending = False
            self.rest_pending = None
            super().start('idle')
        elif self.rest_pending:
            state, self.rest_pending = self.rest_pending, None
            super().start(state)
        elif self.groom_pending:
            self.groom_pending = False
            super().start('groom')
        elif can_walk and not surface_moving and right - left > 4:
            super().start('walk_left' if self.direction < 0 else 'walk_right')
            self.stop_x = None
        else:
            super().start(self.rng.choice(['idle', 'groom', *self.rest_states]))
        return x


def floor_offset(monitor, work, bars, auto_hide):
    """Return physical pixels above monitor bottom for a visible bottom taskbar."""
    left, top, right, bottom = monitor
    floor = bottom if auto_hide else min(bottom, work[3])
    for x1, y1, x2, y2 in bars:
        overlap = min(right, x2) - max(left, x1)
        visible = bottom - max(top, y1)
        if overlap > (right - left) / 2 and y2 >= bottom - 3:
            # Ignore the auto-hide activation strip and non-horizontal windows.
            if 4 < visible < (bottom - top) / 3:
                floor = min(floor, y1)
    return bottom - floor


def blink_at(seconds):
    """Return source index, destination index, blend; exact same resting frame at seam."""
    t = seconds % 4.0
    segments = [(2.6, 0, 0), (.12, 0, 2), (.12, 2, 3),
                (.12, 3, 3), (.12, 3, 2), (.18, 2, 0), (.74, 0, 0)]
    for duration, first, second in segments:
        if t < duration:
            u = t / duration
            return first, second, u * u * (3 - 2 * u)
        t -= duration
    return 0, 0, 0.0
