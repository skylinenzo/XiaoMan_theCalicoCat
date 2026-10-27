"""Ground-contact placement and stable, bounded held sway."""

import math
import unittest

from pet_effects import HeldSway


class HeldSwayTests(unittest.TestCase):
    def test_motion_lags_then_settles_without_spinning(self):
        sway = HeldSway()
        moving = [sway.update(1 / 60, 8) for _ in range(60)]
        self.assertGreater(moving[-1], 8)
        self.assertTrue(all(-10 <= angle <= 10 for angle in moving))
        settled = [sway.update(1 / 60, 0) for _ in range(180)]
        self.assertLess(abs(settled[-1]), .00001)
        self.assertLess(abs(sway.velocity), .0001)
        self.assertLess(max(abs(value) for value in settled[-30:]), .0001)

    def test_pause_does_not_change_state_and_vertical_motion_does_not_roll(self):
        sway = HeldSway()
        sway.update(.1, 20)
        before = sway.angle, sway.velocity
        self.assertEqual(sway.update(0, -100), before[0])
        self.assertEqual((sway.angle, sway.velocity), before)
        sway.reset()
        self.assertEqual((sway.angle, sway.velocity), (0., 0.))
        for _ in range(10):
            self.assertEqual(sway.update(.1, 0, 90), 0.)

    def test_large_motion_and_delayed_frames_stay_bounded(self):
        sway = HeldSway()
        for dt, displacement in ((.001, 100000), (.03, -50000),
                                 (2., 10000), (10., -1000000), (.1, 0)):
            self.assertLessEqual(abs(sway.update(dt, displacement)), 10)
            self.assertTrue(math.isfinite(sway.velocity))
        sway.update(20, 0)
        self.assertLess(abs(sway.angle), .00001)

    def test_constant_mouse_speed_response_does_not_depend_on_frame_rate(self):
        slow, fast = HeldSway(), HeldSway()
        for _ in range(30):
            slow.update(1 / 30, 5)
        for _ in range(120):
            fast.update(1 / 120, 1.25)
        self.assertAlmostEqual(slow.angle, fast.angle, places=10)
        self.assertAlmostEqual(slow.velocity, fast.velocity, places=10)

    def test_invalid_physics_inputs_fail(self):
        for maximum in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                HeldSway(maximum)
        sway = HeldSway()
        for values in ((math.nan, 0, 0), (.1, math.inf, 0), (.1, 0, math.nan)):
            with self.assertRaises(ValueError):
                sway.update(*values)


try:
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage
    from pet_effects import contact_shadow
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'PySide6 is required')
class ContactShadowTests(unittest.TestCase):
    @staticmethod
    def mass(image):
        pixels = [(x, y, image.pixelColor(x, y).alpha())
                  for y in range(image.height()) for x in range(image.width())]
        total = sum(alpha for _, _, alpha in pixels)
        if total == 0:
            return total, 0, 0
        return (total, sum(x * alpha for x, _, alpha in pixels) / total,
                sum(y * alpha for _, y, alpha in pixels) / total)

    def test_profiles_share_ground_line_and_widen_for_walking_and_rest(self):
        widths = []
        for state in ('idle', 'walk_left', 'rest_side'):
            shadow = contact_shadow(160, state)
            self.assertEqual(shadow.format(), QImage.Format.Format_ARGB32_Premultiplied)
            self.assertEqual(shadow.size(), QSize(160, 160))
            total, x, y = self.mass(shadow)
            self.assertGreater(total, 0)
            self.assertAlmostEqual(x, 79.5, delta=.2)
            self.assertAlmostEqual(y, 160 * 490 / 512 - .5, delta=.3)
            occupied = [px for px in range(160)
                        if shadow.pixelColor(px, round(y)).alpha() > 8]
            widths.append(max(occupied) - min(occupied))
            self.assertTrue(all(shadow.pixelColor(px, py).alpha() == 0
                                for px, py in [(0, 0), (80, 159), (0, 153), (159, 153)]))
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])

    def test_window_contact_line_and_custom_ground_are_correct(self):
        window = contact_shadow((180, 160), 'window_perch')
        _, _, y = self.mass(window)
        self.assertAlmostEqual(y, 160 * 477 / 512 - .5, delta=.3)
        custom = contact_shadow(QSize(180, 160), 'idle', floor_ratio=.75)
        self.assertAlmostEqual(self.mass(custom)[2], 119.5, delta=.3)

    def test_hidden_states_and_opacity_have_no_opaque_edges(self):
        for state, opacity in (('held', 1), ('free', 1), ('idle', 0), ('idle', -1)):
            self.assertEqual(self.mass(contact_shadow(80, state, opacity=opacity))[0], 0)
        full = contact_shadow(160, 'idle')
        half = contact_shadow(160, 'idle', opacity=.5)
        self.assertAlmostEqual(self.mass(half)[0] / self.mass(full)[0], .5, delta=.05)
        row = [full.pixelColor(x, 153).alpha() for x in range(80, 160)]
        self.assertLessEqual(max(row), 64)
        self.assertEqual(row[-1], 0)
        self.assertLess(max(abs(a - b) for a, b in zip(row, row[1:])), 5)

    def test_shadow_rejects_invalid_geometry(self):
        for size in (0, -1, (160, 0), (160., 160)):
            with self.assertRaises(ValueError):
                contact_shadow(size, 'idle')
        for ratio in (-.01, 1.01, math.nan):
            with self.assertRaises(ValueError):
                contact_shadow(160, 'idle', floor_ratio=ratio)


if __name__ == '__main__':
    unittest.main()
