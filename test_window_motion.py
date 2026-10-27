"""Window stroll boundaries, shared foot anchors and interruptible gravity jumps."""
import unittest
from window_motion import GravityDescent
from window_perch import NativeSnapshot, NativeWindow, Rect, choose_perch, advance_perch


class DescentTests(unittest.TestCase):
    def test_gravity_accelerates_and_is_frame_rate_independent(self):
        results = []
        for fps in (20, 60, 144):
            descent = GravityDescent(300)
            for _ in range(fps):
                descent.advance(1 / fps, 2000)
            results.append((descent.foot_y, descent.velocity))
        for position, velocity in results:
            self.assertAlmostEqual(position, results[0][0], places=8)
            self.assertAlmostEqual(velocity, 560, places=8)
        descent = GravityDescent(300, velocity=0)
        displacements = []
        for _ in range(5):
            before = descent.foot_y
            descent.advance(.1, 2000)
            displacements.append(descent.foot_y - before)
        self.assertEqual(displacements, sorted(displacements))
        self.assertGreater(displacements[-1], displacements[0] * 5)

    def test_500px_descent_takes_over_one_second_and_never_overshoots(self):
        descent = GravityDescent(300)
        elapsed = 0
        while not descent.landed:
            descent.advance(.025, 800)
            elapsed += .025
            self.assertLessEqual(descent.foot_y, 800)
            self.assertLess(elapsed, 3)
        self.assertGreater(elapsed, 1.2)
        self.assertEqual((descent.foot_y, descent.velocity), (800, 0))
        descent.advance(.1, 760)
        self.assertEqual(descent.foot_y, 760)

    def test_walk_cannot_cross_blocker_and_updates_attachment_fraction(self):
        screens = {'test': (0, 0, 1200, 900)}
        support = NativeWindow(1, Rect(100, 400, 1100, 850), pid=42)
        blocker = NativeWindow(2, Rect(650, 300, 800, 600), eligible=False)
        snapshot = NativeSnapshot(screens, (blocker, support))
        start = choose_perch(snapshot, screens, (350, 400), (200, 200), 190)
        end, distance = advance_perch(start.attachment, snapshot, screens, (200, 200), 1000, 190)
        self.assertEqual(end.x + 200, 650)
        self.assertEqual(distance, 200)
        self.assertGreater(end.attachment.fraction, start.attachment.fraction)
        final, stopped = advance_perch(end.attachment, snapshot, screens, (200, 200), 100, 190)
        self.assertEqual(stopped, 0)
        self.assertEqual(final, end)


import test_interaction_integration as fixtures


@unittest.skipUnless(fixtures.HAS_QT, 'PySide6 is required')
class WindowMotionAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.InteractionIntegrationTests.setUpClass()

    make_cat = fixtures.InteractionIntegrationTests.make_cat
    attach = fixtures.InteractionIntegrationTests.attach
    finish_transition = fixtures.InteractionIntegrationTests.finish_transition
    tick = staticmethod(fixtures.InteractionIntegrationTests.tick)
    mouse = staticmethod(fixtures.InteractionIntegrationTests.mouse)

    def finish_jump(self, cat):
        seen = set()
        for _ in range(120):
            seen.add(cat.visible_state())
            self.tick(cat)
            if cat.jump is None and cat.transition is None:
                return seen
        self.fail('Jump failed to finish')

    def test_straddle_support_and_existing_walk_anchor_stay_on_window(self):
        cat = self.make_cat()
        self.attach(cat)
        cat.perform('window_straddle')
        self.finish_transition(cat)
        self.assertEqual(cat.visible_state(), 'window_straddle')
        self.assertAlmostEqual(cat.rest_y + cat.perch_baseline(), 400)
        self.assertAlmostEqual(cat.perch_baseline(), 340 * cat.height() / 512)
        cat.perform('walk_right')
        self.finish_transition(cat)
        self.assertIsNotNone(cat.perch)
        self.assertAlmostEqual(cat.rest_y + cat.perch_baseline(), 400)
        x, start_time = cat.rest_x, cat.gait_time
        cycle = cat.active_walker().cycles['right']
        self.tick(cat)
        self.assertGreater(cat.rest_x, x)
        expected = cycle.travel(start_time, cat.gait_time - start_time) * cat.width() / 512
        self.assertAlmostEqual(cat.rest_x - x, expected, places=6)

    def test_window_edge_stops_stroll_and_keeps_cat_supported(self):
        cat = self.make_cat()
        self.attach(cat)
        cat.perform('walk_right')
        self.finish_transition(cat)
        for _ in range(200):
            self.tick(cat)
            self.assertIsNotNone(cat.perch)
            self.assertGreaterEqual(cat.rest_x, 200)
            self.assertLessEqual(cat.rest_x + cat.width(), 850.00001)
            if cat.perch_state == 'window_straddle':
                break
        self.assertEqual(cat.perch_state, 'window_straddle')
        self.finish_transition(cat)
        self.assertEqual(cat.visible_state(), 'window_straddle')

    def test_autonomy_strolls_after_lazy_rest_and_pause_keeps_perch(self):
        cat = self.make_cat()
        self.attach(cat)
        cat.rhythm.enter('active')
        cat.set_autonomy(True)
        cat.perch_action_duration = 0
        self.tick(cat)
        self.assertEqual(cat.perch_state, 'window_straddle')
        self.finish_transition(cat)
        cat.perch_action_duration = 0
        self.tick(cat)
        self.assertTrue(cat.perch_state.startswith('walk'))
        cat.set_autonomy(False)
        self.finish_transition(cat)
        position = cat.pos()
        for _ in range(100):
            self.tick(cat)
        self.assertEqual(cat.pos(), position)
        self.assertIsNotNone(cat.perch)

    def test_all_retained_walk_styles_can_move_both_ways_on_window(self):
        cat = self.make_cat()
        self.attach(cat)
        for style in cat.style_actions:
            for direction, sign in (('left', -1), ('right', 1)):
                cat.perform('walk_' + direction)
                cat.set_walk_style(style)
                self.finish_transition(cat)
                start = cat.rest_x
                for _ in range(3):
                    self.tick(cat)
                self.assertGreater((cat.rest_x - start) * sign, 0, (style, direction))
                self.assertIsNotNone(cat.perch)

    def test_low_window_uses_prone_rest_when_hanging_tail_would_clip(self):
        cat = self.make_cat()
        observer = self.attach(cat)
        observer.windows = [NativeWindow(91001, Rect(200, 750, 850, 790), pid=42)]
        cat.refresh_floor()
        cat.perform('walk_right')
        self.finish_transition(cat)
        cat.perch_action_duration = 0
        self.tick(cat)
        self.assertEqual(cat.perch_state, 'window_perch')
        self.finish_transition(cat)
        self.assertIsNotNone(cat.perch)
        self.assertIsNone(cat.jump)

    def test_jump_has_preparation_gravity_contact_and_recovery(self):
        cat = self.make_cat()
        self.attach(cat)
        cat.perform('window_straddle')
        self.finish_transition(cat)
        cat.jump_down()
        self.assertEqual(cat.visible_state(), 'jump_prepare')
        self.assertAlmostEqual(cat.rest_y + cat.height() * 490 / 512, 400)
        seen = self.finish_jump(cat)
        self.assertTrue({'jump_prepare', 'jump_air', 'jump_land', 'jump_recover'}.issubset(seen), seen)
        self.assertIsNone(cat.perch)
        self.assertEqual(cat.visible_state(), 'idle')
        self.assertAlmostEqual(cat.y(), cat.target_y, delta=1.)

    def test_support_disappearing_during_preparation_does_not_leave_stale_perch(self):
        cat = self.make_cat()
        observer = self.attach(cat)
        cat.jump_down()
        observer.windows = []
        cat.refresh_floor()
        self.assertIsNone(cat.perch)
        self.assertEqual(cat.visible_state(), 'jump_air')
        self.finish_jump(cat)

    def test_window_movement_before_launch_updates_takeoff_height(self):
        cat = self.make_cat()
        observer = self.attach(cat)
        cat.jump_down()
        observer.windows = [NativeWindow(91001, Rect(240, 460, 890, 760), pid=42)]
        cat.refresh_floor()
        self.tick(cat)
        self.assertAlmostEqual(cat.jump['motion'].foot_y, 460)
        self.assertAlmostEqual(cat.rest_y + cat.height() * 490 / 512, 460)

    def test_pickup_interrupts_jump_and_air_has_no_contact_shadow(self):
        cat = self.make_cat()
        observer = self.attach(cat)
        observer.windows = []
        cat.refresh_floor()
        self.assertEqual(cat.visible_state(), 'jump_air')
        self.assertEqual(cat.render_frame(512), cat.visible_image())
        self.tick(cat)
        cat.mousePressEvent(self.mouse(cat.x() + 100, cat.y() + 90))
        self.assertIsNone(cat.jump)
        self.assertEqual(cat.visible_state(), 'held')
        cat.mouseReleaseEvent(self.mouse(cat.x() + 100, cat.y() + 90))
        self.assertEqual(cat.visible_state(), 'jump_air')
        self.finish_jump(cat)


if __name__ == '__main__':
    unittest.main()
