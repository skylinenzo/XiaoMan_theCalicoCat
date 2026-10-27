"""Rest animation seams, app playback and patrol continuation."""
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from pet_logic import REST_STATES, PatrolBehavior, sequence_frame

ROOT = Path(__file__).resolve().parent / 'output/imagegen/rest-idles-v1'


class RestBehaviorTests(unittest.TestCase):
    def test_rest_variants_do_not_interrupt_patrol_direction_or_grooming(self):
        pet = PatrolBehavior(random.Random(19), rest_states=REST_STATES)
        x, seen, edges = 750., set(), []
        for _ in range(20000):
            previous, old_x = pet.state, x
            x = pet.advance(.1, x, 0, 1000, 150)
            seen.add(pet.state)
            if previous in REST_STATES:
                self.assertEqual(x, old_x)
            if previous.startswith('walk') and pet.state == 'idle' and pet.rest_reason == 'edge':
                edges.append(x)
            if len(edges) > 10 and set(REST_STATES).issubset(seen):
                break
        self.assertTrue(set(REST_STATES).issubset(seen), seen)
        self.assertIn('groom', seen)
        self.assertEqual(edges[:6], [0, 1000, 0, 1000, 0, 1000])

    def test_free_mode_uses_rest_variants_without_moving(self):
        pet = PatrolBehavior(random.Random(4), rest_states=REST_STATES)
        seen = set()
        for _ in range(10000):
            self.assertEqual(pet.advance(.1, 500, 0, 1000, 100, can_walk=False), 500)
            self.assertFalse(pet.state.startswith('walk'))
            seen.add(pet.state)
        self.assertTrue(set(REST_STATES).issubset(seen))


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'PySide6 is required')
class RestAppTests(unittest.TestCase):
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

    def tick(self, cat):
        with patch('desktop_cat.time.monotonic', return_value=cat.last_tick + .05):
            cat.tick()

    def finish_transition(self, cat):
        for _ in range(60):
            if cat.transition is None:
                return
            self.tick(cat)
        self.fail('Transition did not finish')

    def test_actual_frames_loop_and_are_not_scaled_twice(self):
        cat = self.make_cat()
        for state, folder in zip(REST_STATES, ('prone', 'supine', 'side')):
            frames, meta = cat.animations[state]
            self.assertEqual(len(frames), 4)
            self.assertEqual(sum(meta['duration_ms']), 3200)
            self.assertEqual(meta['playback_order_zero_based'][0], meta['playback_order_zero_based'][-1])
            original = QImage(str(ROOT / folder / 'frame-01.png')).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            self.assertEqual(frames[0], original)
            self.assertEqual(cat.pose_image(state, elapsed=0), cat.pose_image(state, elapsed=3.2))
            self.assertEqual(cat.pose_image(state, elapsed=0), cat.pose_image(state, elapsed=3.199))
            self.assertNotEqual(cat.pose_image(state, elapsed=0), cat.pose_image(state, elapsed=1.75))
            for frame in frames:
                self.assertEqual(frame.pixelColor(0, 0).alpha(), 0)
                bottom = max(y for y in range(512) if any(frame.pixelColor(x, y).alpha() > 160 for x in range(0, 512, 2)))
                self.assertTrue(482 <= bottom <= 491, (state, bottom))

    def test_rest_stays_in_place_and_returns_through_sit_before_walking(self):
        cat = self.make_cat()
        for state in REST_STATES:
            cat.perform(state)
            self.finish_transition(cat)
            position = cat.route_position
            for _ in range(70):
                self.tick(cat)
            self.assertEqual(cat.route_position, position)
            self.assertEqual(cat.behavior.state, state)
            for size in (160, 220, 300):
                cat.change_size(size)
                self.assertFalse(cat.grab().isNull())
            cat.perform('walk_left')
            self.assertIn('idle', cat.transition.states)
            self.assertIn(cat.gaze_image(cat.frames[0],'idle/0'),cat.transition.frames)
            self.finish_transition(cat)
            self.tick(cat)
            self.assertEqual(cat.behavior.state, 'walk_left')
            cat.perform('idle')
            self.finish_transition(cat)

    def test_automatic_exit_keeps_the_last_displayed_rest_pose(self):
        cat = self.make_cat()
        cat.perform('rest_side')
        self.finish_transition(cat)
        cat.behavior.elapsed = 1.75  # Eyes closed, not the first frame.
        cat.behavior.duration = 1.76
        before = cat.pose_image()
        self.tick(cat)
        self.assertEqual(cat.behavior.state, 'idle')
        self.assertEqual(cat.transition.image(), before)


if __name__ == '__main__':
    unittest.main()
