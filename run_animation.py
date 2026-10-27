"""Independent directional gallop art; distance and cycle share one clock."""
class RunCycle:
    duration=.64
    stride=240.
    def travel(self, seconds, dt):return max(0.,dt)*self.stride/self.duration
    def time_after_distance(self, seconds, dt, distance):
        return seconds+min(max(0.,dt),max(0.,distance)*self.duration/self.stride)
    def frame(self, seconds):return int((seconds%self.duration)/.08)%8
