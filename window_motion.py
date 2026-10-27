"""Time-based downward motion in logical pixels, independent of frame rate."""
from dataclasses import dataclass


@dataclass
class GravityDescent:
    foot_y: float
    velocity: float = -55.
    gravity: float = 760.
    terminal_speed: float = 560.
    landed: bool = False

    def advance(self, dt, floor):
        if dt < 0:
            raise ValueError('Time must not run backwards')
        if self.landed:
            self.foot_y = floor
            return True
        # Integrate exactly, including a possible terminal-speed crossing.
        accelerating = min(dt, max(0., (self.terminal_speed - self.velocity) / self.gravity))
        self.foot_y += self.velocity * accelerating + .5 * self.gravity * accelerating ** 2
        self.velocity = min(self.terminal_speed, self.velocity + self.gravity * accelerating)
        self.foot_y += self.velocity * (dt - accelerating)
        if self.foot_y >= floor and self.velocity >= 0:
            self.foot_y, self.velocity, self.landed = floor, 0., True
        return self.landed
