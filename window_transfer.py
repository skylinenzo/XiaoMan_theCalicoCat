"""Reachable window destinations and authored jump/climb/mantle trajectories."""
from dataclasses import dataclass
import math
from window_perch import _ledges, _placement, _rect, PerchPlacement


def canvas_on_screens(x, y, width, height, screens):
    """Require the canvas to be covered by the union, including at screen seams."""
    right, bottom = x + width, y + height
    rectangles = [_rect(r) for r in screens.values()]
    cuts = sorted({x, right, *(max(x, min(right, r.left)) for r in rectangles),
                   *(max(x, min(right, r.right)) for r in rectangles)})
    for left, end in zip(cuts, cuts[1:]):
        if end - left < 1e-6:
            continue
        mid = (left + end) / 2
        intervals = sorted((max(y, r.top), min(bottom, r.bottom)) for r in rectangles
                           if r.left <= mid < r.right and r.bottom > y and r.top < bottom)
        covered = y
        for top, low in intervals:
            if top > covered + 1e-5:
                return False
            covered = max(covered, low)
        if covered < bottom - 1e-5:
            return False
    return True


def smooth(value):
    return value * value * (3 - 2 * value)


@dataclass(frozen=True)
class TransferSample:
    x: float
    y: float
    phase: str
    frame: int
    blur: float = 0.


class TransferMotion:
    """Keep full authored drawings; only the moving climb has a short trail."""
    def __init__(self, origin, destination, size, anchors):
        self.origin = origin  # canvas horizontal center, support line Y
        self.destination = destination
        self.size = size
        self.anchors = anchors
        self.elapsed = 0.
        rise = origin[1] - destination.floor
        self.climbing = rise > size * 1.05
        start_y = origin[1] - 490 * size / 512
        hook_y = destination.floor - anchors[4] * size / 512
        self.arc = max(25., min(85., abs(destination.x + size / 2 - origin[0]) * .16 + 25))
        flight = max(.42, math.sqrt(8 * self.arc / 760),
                     abs(destination.x + size / 2 - origin[0]) / 600,
                     (max(0., hook_y - start_y) + 4 * self.arc) / 560)
        climb = max(.18, min(.65, abs(hook_y - start_y) * .75 / 950))
        self.phases = ([('prepare', .18), ('launch', .24), ('climb', climb)] if self.climbing
                       else [('prepare', .18), ('flight', flight)])
        self.phases += [('hook', .10), ('pull', .16), ('rotate', .18), ('settle', .20)]
        self.duration = sum(duration for _, duration in self.phases)

    def sample(self, elapsed=None, destination=None):
        t = self.elapsed if elapsed is None else max(0., elapsed)
        target = destination or self.destination
        local = t
        for phase, duration in self.phases:
            if local < duration:
                break
            local -= duration
        else:
            phase, duration, local = 'settle', .20, .20
        u = min(1., local / duration)
        start_x, start_y = self.origin[0] - self.size / 2, self.origin[1] - 490 * self.size / 512
        hook_y = target.floor - self.anchors[4] * self.size / 512
        if phase == 'prepare':
            return TransferSample(start_x, start_y, phase, 0)
        if phase == 'launch':
            return TransferSample(start_x + (target.x - start_x) * smooth(u),
                                  start_y + (hook_y - start_y) * .25 * smooth(u) - 8 * math.sin(math.pi * u), phase, 1)
        if phase == 'flight':
            return TransferSample(start_x + (target.x - start_x) * smooth(u),
                                  start_y + (hook_y - start_y) * u - 4 * self.arc * u * (1-u), phase, 1)
        if phase == 'climb':
            return TransferSample(target.x, start_y + (hook_y-start_y) * (.25 + .75 * (1-(1-u)**2)),
                                  phase, 2 + int(local * 20) % 2, math.sin(math.pi * u))
        frame = {'hook': 4, 'pull': 5, 'rotate': 6, 'settle': 7}[phase]
        return TransferSample(target.x, target.floor - self.anchors[frame] * self.size / 512, phase, frame)

    def fits(self, screens):
        times = {self.duration * i / 50 for i in range(51)}
        start = 0.
        for _, duration in self.phases:
            times.update((start, start + duration / 2, max(start, start + duration - 1e-6)))
            start += duration
        return all(canvas_on_screens(sample.x, sample.y, self.size, self.size * 490 / 512, screens)
                   for sample in (self.sample(t) for t in times))


def choose_transfer(snapshot, screens, origin, size, anchors, source_hwnd=None, upward_only=False):
    """Choose an exposed ledge within reach; reject display gaps and same window."""
    choices = []
    for ledge in _ledges(snapshot, screens, (size, size), 490 * size / 512):
        if ledge.window.hwnd == source_hwnd:
            continue
        rise = origin[1] - ledge.floor
        if upward_only and rise < 35:
            continue
        if not -min(650, size * 3) <= rise <= min(900, size * 4):
            continue
        for left, right in ledge.centers:
            center = min(max(origin[0], left), right)
            if abs(center - origin[0]) > min(600, size * 3):
                continue
            raw = _placement(ledge, center, 490 * size / 512)
            placement = PerchPlacement(raw.x - size / 2, raw.y, raw.floor, raw.screen, raw.attachment)
            motion = TransferMotion(origin, placement, size, anchors)
            if motion.fits(screens):
                score = abs(center-origin[0]) + abs(rise) * .55 + ledge.z * 2
                choices.append((score, motion))
    return min(choices, key=lambda item: item[0])[1] if choices else None


def window_occlusion_rects(snapshot, screens, attachment):
    """Map target window coverage separately on each monitor (mixed DPI safe)."""
    from window_perch import match_monitors, Rect
    if snapshot is None:
        return []
    window = next((w for w in snapshot.windows if w.hwnd == attachment.hwnd
                   and (not attachment.pid or w.pid == attachment.pid)), None)
    if window is None:
        return []
    rect = _rect(window.rect)
    result = []
    for name, device in match_monitors(snapshot.monitors, screens).items():
        physical, logical = _rect(snapshot.monitors[device]), _rect(screens[name])
        left, top = max(rect.left, physical.left), max(rect.top, physical.top)
        right, bottom = min(rect.right, physical.right), min(rect.bottom, physical.bottom)
        if right <= left or bottom <= top:
            continue
        sx, sy = logical.width / physical.width, logical.height / physical.height
        result.append(Rect(logical.left+(left-physical.left)*sx, logical.top+(top-physical.top)*sy,
                           logical.left+(right-physical.left)*sx, logical.top+(bottom-physical.top)*sy))
    return result
