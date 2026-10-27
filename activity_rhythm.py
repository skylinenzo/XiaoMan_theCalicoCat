"""Long-lived mood above individual animations; uses active app time only."""
import random

class ActivityRhythm:
    LABELS = {'rest': '休息', 'active': '日常活动', 'burst': '突然活跃', 'settle': '放松恢复'}
    DURATIONS = {'rest': (100, 220), 'active': (25, 55), 'burst': (8, 16), 'settle': (25, 45)}

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.enter('rest')

    def enter(self, state):
        if state not in self.DURATIONS:
            raise ValueError(state)
        self.state = state
        self.elapsed = 0.
        self.duration = self.rng.uniform(*self.DURATIONS[state])

    @property
    def quiet(self):
        return self.state in ('rest', 'settle')

    @property
    def speed(self):
        return {'rest': .8, 'active': 1., 'burst': 1.45, 'settle': .85}[self.state]

    def advance(self, dt):
        self.elapsed += max(0., dt)
        if self.elapsed < self.duration:
            return False
        following = {'burst': 'settle', 'settle': 'rest'}.get(self.state)
        if following is None:
            following = (self.rng.choice(['active', 'burst']) if self.state == 'rest'
                         else self.rng.choice(['settle', 'settle', 'burst']))
        self.enter(following)
        return True

    def rest_duration(self):
        return self.rng.uniform(25, 55) if self.state == 'rest' else self.rng.uniform(10, 20)

    def rest_pose(self, window=False):
        return self.rng.choice(['window_perch'] * 4 + ['window_straddle'] * 3 + ['groom'] if window
                               else ['rest_prone'] * 4 + ['rest_side'] * 3 + ['rest_supine', 'idle', 'groom'])

    def exploration_delay(self):
        return self.rng.uniform(5, 9) if self.state == 'burst' else self.rng.uniform(14, 25)
