"""Independent directional gallop art; distance and cycle share one clock."""
class RunCycle:
    # 1.5x faster than v0.1: increase cadence and translation together.
    duration=.64 / 1.5
    stride=276.  # 15% more ground covered per cycle; cadence is unchanged.
    def travel(self, seconds, dt):return max(0.,dt)*self.stride/self.duration
    def time_after_distance(self, seconds, dt, distance):
        return seconds+min(max(0.,dt),max(0.,distance)*self.duration/self.stride)
    def frame(self, seconds):return int((seconds%self.duration)/self.duration*8)%8
