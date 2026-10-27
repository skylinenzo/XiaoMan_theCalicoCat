"""Finite visual transitions; patrol time and movement pause until completion."""


class PoseTransition:
    def __init__(self, frames, segment_seconds=.22, states=None):
        if len(frames) < 2 or segment_seconds <= 0:
            raise ValueError('A transition needs two or more poses and a positive duration')
        self.frames = frames
        if states is not None and len(states) != len(frames):
            raise ValueError('Each transition drawing needs one state label')
        self.states = states
        self.segment_seconds = segment_seconds
        self.elapsed = 0.
        self.duration = (len(frames) - 1) * segment_seconds

    def advance(self, dt):
        self.elapsed = min(self.duration, self.elapsed + max(0., dt))
        return self.elapsed >= self.duration

    def image(self):
        # These are authored turn poses, not opacity layers: a dissolve between
        # them produces two heads/tails. Present each full drawing atomically.
        return self.frames[self.index]

    @property
    def index(self):
        return min(len(self.frames) - 1, int(self.elapsed / self.segment_seconds))

    @property
    def current_state(self):
        return self.states[self.index] if self.states is not None else None
