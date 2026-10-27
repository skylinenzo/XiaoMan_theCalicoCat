"""A patrol coordinate along actual screen bottoms, excluding virtual gaps.

Qt/Windows mixed-DPI desktops can have empty logical-coordinate islands. Each
lane is mapped independently; contiguous screens meet exactly, islands reconnect
at their edges instead of spending seconds walking through an invisible gap.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Surface:
    name: str
    x: float
    y: float
    width: float
    height: float
    floor: float


class DesktopRoute:
    def __init__(self, surfaces, size):
        self.size = size
        # Stable order also covers stacked displays and negative desktop origins.
        ordered = sorted(surfaces, key=lambda s: (s.x, s.y, s.name))
        seen, self.lanes, self.length = set(), [], 0.
        for surface in ordered:
            key = (surface.x, surface.y, surface.width, surface.height)
            if key not in seen:
                seen.add(key)
                self.lanes.append(surface)
        if not self.lanes:
            raise ValueError('At least one screen is required')
        self.spans = []
        for i, surface in enumerate(self.lanes):
            start_x = surface.x if i == 0 else surface.x - size / 2
            end_x = surface.x + surface.width - (size if i == len(self.lanes) - 1 else size / 2)
            length = max(1., end_x - start_x)
            self.spans.append((self.length, self.length + length, start_x))
            self.length += length
        self.signature = (size, tuple((s.name, s.x, s.y, s.width, s.height) for s in self.lanes))

    def locate(self, distance):
        distance = max(0., min(distance, self.length))
        for i, (start, end, x) in enumerate(self.spans):
            if distance < end or i == len(self.spans) - 1:
                surface = self.lanes[i]
                return x + distance - start, surface.floor - 490 / 512 * self.size, surface.name

    def project(self, x, y):
        choices = []
        for surface, (start, end, start_x) in zip(self.lanes, self.spans):
            local = max(0., min(x - start_x, end - start))
            top = surface.floor - 490 / 512 * self.size
            inside = (surface.x <= x + self.size / 2 < surface.x + surface.width
                      and surface.y <= y + self.size / 2 < surface.y + surface.height)
            choices.append((not inside, (x - start_x - local) ** 2 + (y - top) ** 2, start + local))
        return min(choices)[2]

    def safe_stop(self, distance, direction):
        """Rest fully inside a display, never half-hidden on an internal seam."""
        x, _, name = self.locate(distance)
        i = next(i for i, s in enumerate(self.lanes) if s.name == name)
        surface = self.lanes[i]
        start, end, start_x = self.spans[i]
        if direction > 0 and x > surface.x + surface.width - self.size and i + 1 < len(self.lanes):
            next_start, _, next_x = self.spans[i + 1]
            return next_start + self.lanes[i + 1].x - next_x
        if direction < 0 and x < surface.x and i > 0:
            prev_start, _, prev_x = self.spans[i - 1]
            prev = self.lanes[i - 1]
            return prev_start + prev.x + prev.width - self.size - prev_x
        x = min(max(x, surface.x), max(surface.x, surface.x + surface.width - self.size))
        return min(end, max(start, start + x - start_x))
