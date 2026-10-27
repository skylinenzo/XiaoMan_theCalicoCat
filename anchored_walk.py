"""Eight drawing walk cycle with measured, fixed-world support-foot anchors."""
import bisect
import math


class AnchoredCycle:
    def __init__(self, metadata):
        self.order = metadata['playback_order_zero_based']
        self.durations = [value / 1000 for value in metadata['duration_ms']]
        self.steps = metadata['step_pixels']
        self.anchors = metadata['support_anchors']
        self.offsets = metadata['lower_offsets']
        self.direction = -1 if metadata['direction'] == 'left' else 1
        self.steady_body = metadata.get('body_motion') == 'steady'
        self.times, self.distances = [0.], [0.]
        for duration, step in zip(self.durations, self.steps):
            self.times.append(self.times[-1] + duration)
            self.distances.append(self.distances[-1] + step)
        self.duration, self.stride = self.times[-1], self.distances[-1]

    def sample(self, seconds):
        loops = math.floor(seconds / self.duration)
        t = seconds - loops * self.duration
        index = min(len(self.steps) - 1, bisect.bisect_right(self.times, t) - 1)
        fraction = (t - self.times[index]) / self.durations[index]
        u = fraction * fraction * (3 - 2 * fraction)
        distance = loops * self.stride + self.distances[index] + self.steps[index] * u
        first = self.order[index]
        second = self.order[(index + 1) % len(self.order)]
        anchor = self.anchors[index][0] + self.offsets[first] - self.direction * self.steps[index] * u
        if self.steady_body:
            # Keep the authored gait clock, but decouple the torso's travel from
            # its uneven step lengths. The small ripple never stops the body.
            phase = t / self.duration
            steady = self.stride * (loops + phase + .08 * math.sin(4 * math.pi * phase) / (4 * math.pi))
            # Equal and opposite leg compensation preserves the original WORLD
            # contact, including when consecutive frames use the same paw.
            anchor += self.direction * (distance - steady)
            distance = steady
        return first, second, u, distance, anchor, index

    def travel(self, start, duration):
        return self.sample(start + duration)[3] - self.sample(start)[3]

    def time_after_distance(self, start, duration, distance):
        """Clip cadence at a waypoint without letting feet keep moving afterwards."""
        low, high = start, start + duration
        for _ in range(40):
            middle = (low + high) / 2
            if self.sample(middle)[3] - self.sample(start)[3] < distance:
                low = middle
            else:
                high = middle
        return (low + high) / 2
