"""Exercise new gait, finite turn/sit transitions and the real Qt application."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from anchored_renderer import AnchoredWalk
    HAS_QT = True
except ImportError:
    HAS_QT = False

ROOT = Path(__file__).resolve().parent / 'output/imagegen'


@unittest.skipUnless(HAS_QT, 'PySide6 is required')
class DiagonalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_cat(self):
        class Observer:
            def snapshot(self, hwnd):
                return (0, 0, 800, 800), (0, 0, 800, 800), [], True
            def keep_topmost(self, hwnd):
                pass
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        with patch.dict(sys.modules, {'windows_taskbar': types.SimpleNamespace(TaskbarObserver=Observer)}):
            from desktop_cat import DesktopCat
            cat = DesktopCat(QSettings(temp.name + '/settings.ini', QSettings.Format.IniFormat))
        for timer in (cat.timer, cat.floor_timer, cat.top_timer):
            timer.stop()
        self.addCleanup(cat.close)
        self.addCleanup(cat.tray.hide)
        cat.set_autonomy(False)
        return cat

    def tick(self, cat, dt=.05):
        with patch('desktop_cat.time.monotonic', return_value=cat.last_tick + dt):
            cat.tick()

    def finish_transition(self, cat):
        for _ in range(60):
            if cat.transition is None:
                return
            self.tick(cat)
        self.fail('Transition did not finish')

    def test_both_coats_loop_and_support_anchor_matches_world_motion(self):
        walker = AnchoredWalk({'left': 'walk-diagonal-left-v1', 'right': 'walk-diagonal-right-v1'})
        for side in ('left', 'right'):
            cycle = walker.cycles[side]
            self.assertEqual(cycle.order, list(range(8)))
            self.assertEqual(cycle.duration, 4)
            start = walker.render(side, 0, 512)
            self.assertEqual(start, walker.render(side, cycle.duration, 512))
            for i in range(8):
                world = []
                for u in (.05, .35, .65, .95):
                    t = cycle.times[i] + cycle.durations[i] * u
                    sample = cycle.sample(t)
                    world.append(cycle.direction * sample[3] + sample[4])
                    frame = walker.render(side, t, 512)
                    # Body and tail now move gently; the support sole still stays
                    # opaque at its measured location throughout the segment.
                    anchor = round(sample[4])
                    self.assertGreater(max(frame.pixelColor(x, y).alpha()
                                           for x in range(max(0, anchor - 8), min(512, anchor + 9))
                                           for y in range(480, 492)), 150)
                self.assertLess(max(world) - min(world), 1e-7)
        self.assertNotEqual(walker.frames['left'][0], walker.frames['right'][0].mirrored(True, False))
        for i in range(1, 9):
            self.assertEqual((ROOT / f'walk-diagonal-cycle-v2/frame-{i:02}.png').read_bytes(),
                             (ROOT / f'walk-diagonal-right-v1/frame-{i:02}.png').read_bytes())

    def test_sit_transition_freezes_motion_and_rest_clock_and_is_interruptible(self):
        cat = self.make_cat()
        cat.perform('walk_left')
        position = cat.route_position
        while cat.transition:
            self.tick(cat)
            self.assertEqual(cat.route_position, position)
            self.assertEqual(cat.behavior.elapsed, 0)
        self.tick(cat)
        self.assertLess(cat.route_position, position)
        before = cat.pose_image()
        cat.perform('idle')
        self.assertEqual(cat.transition.image(), before)
        self.assertEqual(len(cat.transition.frames), 4)  # walk + two poses + sit
        position = cat.route_position
        self.tick(cat)
        current = cat.transition.image()
        cat.perform('walk_right')  # New action begins at the currently displayed pose.
        self.assertEqual(cat.transition.image(), current)
        self.finish_transition(cat)
        self.assertEqual(cat.route_position, position)
        cat.perform('idle')
        self.finish_transition(cat)
        self.assertEqual(cat.pose_image(), cat.gaze_image(cat.frames[0],'idle/0'))
        self.assertEqual(cat.behavior.elapsed, 0)

    def test_edge_stop_runs_turn_poses_then_idle_without_extra_distance(self):
        cat = self.make_cat()
        cat.route_position = cat.route.length - 2
        cat.rest_x, cat.rest_y, cat.route_screen = cat.route.locate(cat.route_position)
        cat.target_y = cat.rest_y
        cat.move(round(cat.rest_x), round(cat.rest_y))
        cat.perform('walk_right')
        self.finish_transition(cat)
        for _ in range(60):
            self.tick(cat)
            if cat.behavior.state == 'idle':
                break
        self.assertEqual(cat.route_position, cat.route.length)
        self.assertIsNotNone(cat.transition)
        self.assertEqual(len(cat.transition.frames), 4)
        cat.menu_open = True
        elapsed = cat.transition.elapsed
        self.tick(cat)
        self.assertEqual(cat.transition.elapsed, elapsed)
        cat.menu_open = False
        self.finish_transition(cat)
        self.assertEqual(cat.route_position, cat.route.length)
        self.assertEqual(cat.behavior.elapsed, 0)

    def test_sizes_keep_shared_floor_and_near_matching_head_height(self):
        cat = self.make_cat()
        # Frontal sitting and the two turn poses share ears near180, soles490.
        for image in [cat.frames[0], *cat.turn_frames['left'], *cat.turn_frames['right']]:
            rows = [y for y in range(512) if any(image.pixelColor(x, y).alpha() > 160 for x in range(0, 512, 2))]
            self.assertTrue(170 <= min(rows) <= 190)
            self.assertTrue(487 <= max(rows) <= 492)
        for size in (160, 220, 300):
            cat.change_size(size)
            cat.perform('walk_left')
            self.tick(cat)
            self.assertFalse(cat.grab().isNull())


if __name__ == '__main__':
    unittest.main()
