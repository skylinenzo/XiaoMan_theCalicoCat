"""Torso speed, actual foot locking and continuous tail deformation."""
import json
import math
import os
from pathlib import Path
import unittest

from anchored_walk import AnchoredCycle

ROOT = Path(__file__).resolve().parent / 'output/imagegen'


class SteadyTimingTests(unittest.TestCase):
    def test_speed_never_stops_between_steps_and_anchor_does_not_slide(self):
        for side in ('left', 'right'):
            data = json.loads((ROOT / f'walk-diagonal-{side}-v1/animation.json').read_text())
            cycle = AnchoredCycle(data)
            average = cycle.stride / cycle.duration
            for i in range(800):
                speed = cycle.travel(i * .005, .005) / .005
                self.assertGreaterEqual(speed, .919 * average)
                self.assertLessEqual(speed, 1.081 * average)
            # Same named support paw must keep ONE world location across all
            # four segments of the half-step, not just inside a single frame.
            for half in (0, 4):
                points = []
                for segment in range(half, half + 4):
                    for u in (.001, .2, .5, .8, .999):
                        s = cycle.sample(cycle.times[segment] + cycle.durations[segment] * u)
                        points.append(cycle.direction * s[3] + s[4])
                self.assertLess(max(points) - min(points), 1e-7)
            for boundary in cycle.times[1:]:
                left = cycle.travel(boundary - .0001, .0001) / .0001
                right = cycle.travel(boundary, .0001) / .0001
                self.assertAlmostEqual(left, right, delta=.01)
            start, dt = 1.12, .16
            requested = cycle.travel(start, dt) * .37
            end = cycle.time_after_distance(start, dt, requested)
            self.assertAlmostEqual(cycle.travel(start, end - start), requested)


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
    from anchored_renderer import AnchoredWalk, walking_point, warp_lower
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'PySide6 is required')
class SteadyRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tail_moves_head_only_bobs_and_soles_are_unchanged(self):
        for side in ('left', 'right'):
            tail_x = 430 if side == 'left' else 82
            tip = []
            for i in range(80):
                phase = i / 80
                tip.append(walking_point(side, phase, tail_x, 120, 0)[0])
                for x in (60, 180, 310, 450):
                    self.assertEqual(walking_point(side, phase, x, 490, 23), (x + 23, 490))
                face_x = 80 if side == 'left' else 430
                x, y = walking_point(side, phase, face_x, 280, 0)
                self.assertEqual(x, face_x)
                self.assertTrue(278.2 <= y <= 280)
            self.assertGreater(max(tip) - min(tip), 15)
            for x, y in ((tail_x, 120), (250, 300), (200, 490)):
                self.assertLess(math.dist(walking_point(side, 1 - 1e-8, x, y, 0),
                                          walking_point(side, 1e-8, x, y, 0)), .00001)

    def test_connected_mesh_does_not_fold_or_change_interior_opacity(self):
        texture = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
        texture.fill(QColor(120, 80, 40, 160))
        for side in ('left', 'right'):
            for phase in (0, .15, .3, .5, .7, .9):
                for dx in (-85, 0, 85):
                    for y in range(0, 480, 24):
                        for x in range(0, 480, 32):
                            a = walking_point(side, phase, x, y, dx)
                            b = walking_point(side, phase, x + 32, y, dx)
                            c = walking_point(side, phase, x + 32, y + 24, dx)
                            self.assertGreater((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]), 500)
                frame = warp_lower(texture, 20, size=220, motion=(side, phase))
                for y in range(8, 206, 3):
                    for x in range(18, 202, 3):
                        self.assertEqual(frame.pixelColor(x, y).alpha(), 160)

    def test_real_art_has_moving_tail_and_exact_repeat(self):
        renderer = AnchoredWalk({'left': 'walk-diagonal-left-v1', 'right': 'walk-diagonal-right-v1'})
        for side in ('left', 'right'):
            cycle = renderer.cycles[side]
            first = renderer.render(side, 0, 512)
            self.assertEqual(first, renderer.render(side, cycle.duration, 512))
            x = 350 if side == 'left' else 0
            a = renderer.render(side, cycle.duration * .25, 512).copy(x, 80, 160, 190)
            b = renderer.render(side, cycle.duration * .75, 512).copy(x, 80, 160, 190)
            self.assertNotEqual(a, b)

    def test_compensation_keeps_contact_pinned_and_all_paws_inside_canvas(self):
        renderer = AnchoredWalk({'left': 'walk-diagonal-left-v1', 'right': 'walk-diagonal-right-v1'})
        for side in ('left', 'right'):
            cycle = renderer.cycles[side]
            for i in range(80):
                seconds = i * cycle.duration / 80
                first, second, u, _, anchor, segment = cycle.sample(seconds)
                index = first if u < .5 else second
                contact = cycle.anchors[segment][0 if u < .5 else 1] + cycle.offsets[index]
                self.assertEqual(walking_point(side, seconds / cycle.duration, contact, 490,
                                                anchor - contact, anchor), (anchor, 490))
                image = renderer.render(side, seconds, 220)
                self.assertFalse(any(image.pixelColor(x, y).alpha() > 100
                                     for x in (0, 219) for y in range(220)), (side, i))


if __name__ == '__main__':
    unittest.main()
