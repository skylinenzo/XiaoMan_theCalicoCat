"""Optional real-Qt offscreen checks; native Windows observation is stubbed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QPoint, QSettings
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from rig_renderer import CatRig
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'PySide6 is required for offscreen rendering')
class RigRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.rig = CatRig()

    def render(self, side, phase, size=512):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        self.rig.draw(painter, side, phase, size)
        painter.end()
        return image

    def test_head_and_upper_coat_never_change_during_stride(self):
        for side in ('left', 'right'):
            first = self.render(side, 0)
            stable = first.copy(0, 0, 512, 330)
            changed = False
            for i in range(1, 40):
                rendered = self.render(side, i / 40)
                self.assertEqual(rendered.copy(0, 0, 512, 330), stable)
                self.assertEqual(rendered.pixelColor(0, 0).alpha(), 0)
                changed |= rendered != first
            self.assertTrue(changed, 'legs should actually move')
            self.assertEqual(self.render(side, 1), first)

    def test_real_app_switches_styles_and_pauses_phase(self):
        class Observer:
            def snapshot(self, hwnd):
                return (0, 0, 800, 800), (0, 0, 800, 800), [], True
            def keep_topmost(self, hwnd):
                pass
        preferences = tempfile.TemporaryDirectory()
        self.addCleanup(preferences.cleanup)
        settings_path = preferences.name + '/settings.ini'
        settings = QSettings(settings_path, QSettings.Format.IniFormat)
        with patch.dict(sys.modules, {'windows_taskbar': types.SimpleNamespace(TaskbarObserver=Observer)}):
            from desktop_cat import DesktopCat
            cat = DesktopCat(settings=settings)
        try:
            for timer in (cat.timer, cat.floor_timer, cat.top_timer):
                timer.stop()
            self.app.processEvents()
            self.assertEqual(set(cat.animations), {'groom', 'rest_prone', 'rest_supine',
                                                   'rest_side', 'held', 'window_perch',
                                                   'window_straddle', 'jump_down', 'window_climb', 'window_climb_back', 'window_climb_side', 'run_left', 'run_right', 'pounce_left', 'pounce_right', 'play_kick', 'play_lick'})
            self.assertEqual(cat.walk_style, 'frames_diagonal')
            for style in ('frames_diagonal', 'frames_anchored', 'deform', 'frames_original', 'frames_aligned'):
                # Exercise the actual menu signal and mutual exclusion.
                cat.style_actions[style].trigger()
                self.assertEqual(cat.walk_style, style)
                self.assertEqual(sum(a.isChecked() for a in cat.style_actions.values()), 1)
                for size in (160, 220, 300):
                    cat.change_size(size)
                    for action in ('idle', 'groom', 'walk_left', 'walk_right'):
                        cat.perform(action)
                        if cat.transition:
                            cat.transition.advance(cat.transition.duration)
                            cat.transition = None
                        for i in range(8):
                            cat.gait_phase = i / 8
                            cat.gait_time = i / 8 * cat.active_walker().cycles['left'].duration
                            image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
                            image.fill(QColor(0, 0, 0, 0))
                            cat.render(image)
                            self.assertTrue(any(image.pixelColor(size // 2, y).alpha() > 200
                                                for y in range(size)))
            cat.set_walk_style('frames_original')
            for side in ('left', 'right'):
                for i in range(8):
                    cat.gait_phase = (i + .1) / 8
                    self.assertEqual(cat.walking_image(side), cat.walk_animations['frames_original'][side][0][i])
            cat.change_size(220)
            cat.rest_x = 300
            cat.route_position = cat.route.project(300, cat.target_y)
            cat.rest_y = cat.target_y
            cat.move(300, round(cat.target_y))
            cat.perform('walk_left')
            if cat.transition:
                cat.transition.advance(cat.transition.duration)
                cat.transition = None
            cat.last_tick = time.monotonic() - .05
            cat.tick()
            self.assertLess(cat.rest_x, 300)
            self.assertGreater(cat.gait_phase, 0)
            destination = cat.behavior.stop_x
            before_switch = (cat.behavior.state, cat.behavior.elapsed, cat.rest_x, cat.gait_phase)
            cat.set_walk_style('deform')
            self.assertEqual(before_switch, (cat.behavior.state, cat.behavior.elapsed, cat.rest_x, cat.gait_phase))
            self.assertEqual(destination, cat.behavior.stop_x)
            phase, position = cat.gait_phase, cat.rest_x
            cat.drag_offset = QPoint(0, 0)
            cat.last_tick = time.monotonic() - .05
            cat.tick()
            self.assertEqual((cat.gait_phase, cat.rest_x), (phase, position))
            cat.drag_offset = None
            cat.target_y -= 48
            cat.last_tick = time.monotonic() - .05
            cat.tick()
            self.assertEqual((cat.gait_phase, cat.rest_x), (phase, position))
            self.assertEqual(cat.behavior.state, 'walk_left')
            cat.set_walk_style('frames_aligned')
            saved = QSettings(settings_path, QSettings.Format.IniFormat)
            with patch.dict(sys.modules, {'windows_taskbar': types.SimpleNamespace(TaskbarObserver=Observer)}):
                reopened = DesktopCat(settings=saved)
            try:
                self.assertEqual(reopened.walk_style, 'frames_aligned')
                self.assertTrue(reopened.style_actions['frames_aligned'].isChecked())
            finally:
                for timer in (reopened.timer, reopened.floor_timer, reopened.top_timer):
                    timer.stop()
                reopened.tray.hide()
                reopened.close()
            cat.set_mode('free')
            self.assertEqual(cat.behavior.state, 'idle')
            cat.set_autonomy(False)
            self.assertFalse(cat.behavior.enabled)
        finally:
            cat.tray.hide()
            cat.close()


if __name__ == '__main__':
    unittest.main()
