"""Real Qt coverage for pose routes, held overlays, window support and shadows."""

import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from desktop_route import Surface
from window_perch import NativeSnapshot, NativeWindow, Rect


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


class WindowSource:
    def __init__(self, windows=()):
        self.windows = windows
        self.excluded = ()
        self.error = None

    def snapshot(self, exclude_hwnds=()):
        self.excluded = exclude_hwnds
        if self.error:
            raise self.error
        return NativeSnapshot({'test': Rect(0, 0, 1000, 800)}, tuple(self.windows))


@unittest.skipUnless(HAS_QT, 'PySide6 is required')
class InteractionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_cat(self):
        class TaskbarObserver:
            def snapshot(self, hwnd):
                return (0, 0, 800, 800), (0, 0, 800, 800), [], True

            def keep_topmost(self, hwnd):
                pass

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        with patch.dict(sys.modules, {'windows_taskbar': types.SimpleNamespace(TaskbarObserver=TaskbarObserver)}):
            import desktop_cat
            with patch.object(desktop_cat, 'WindowObserver', return_value=None):
                cat = desktop_cat.DesktopCat(QSettings(temp.name + '/settings.ini', QSettings.Format.IniFormat))
        for timer in (cat.timer, cat.floor_timer, cat.top_timer):
            timer.stop()
        self.addCleanup(cat.close)
        self.addCleanup(cat.tray.hide)
        cat.set_autonomy(False)
        cat.logical_screens = lambda: {'test': (0, 0, 1000, 800)}
        cat.screen_surfaces = lambda: [Surface('test', 0, 0, 1000, 800, 797)]
        cat.refresh_floor()
        cat.rest_y = cat.target_y
        cat.move(round(cat.rest_x), round(cat.rest_y))
        return cat

    @staticmethod
    def mouse(x, y):
        return types.SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton,
                                     globalPosition=lambda: QPointF(x, y))

    @staticmethod
    def tick(cat, dt=.05):
        with patch('desktop_cat.time.monotonic', return_value=cat.last_tick + dt):
            cat.tick()

    def finish_transition(self, cat):
        for _ in range(150):
            if cat.transition is None:
                return
            self.tick(cat)
        self.fail('Transition did not finish')

    def attach(self, cat, finish=True):
        observer = WindowSource([NativeWindow(91001, Rect(200, 400, 850, 700), pid=42)])
        cat.window_observer = observer
        cat.move(350, round(400 - cat.height() * 490 / 512))
        self.assertTrue(cat.try_attach_window())
        if finish:
            self.finish_transition(cat)
        return observer

    def test_supine_to_walk_visits_side_prone_and_sit_without_moving(self):
        cat = self.make_cat()
        cat.perform('rest_supine')
        self.finish_transition(cat)
        cat.perform('walk_left')
        labels = list(dict.fromkeys(cat.transition.states))
        self.assertEqual(labels, ['rest_supine', 'rest_side', 'rest_prone', 'idle', 'walk_left'])
        start_position, elapsed = cat.route_position, cat.behavior.elapsed
        seen = {cat.visible_state()}
        while cat.transition:
            self.tick(cat)
            seen.add(cat.visible_state())
            self.assertEqual(cat.route_position, start_position)
            self.assertEqual(cat.behavior.elapsed, elapsed)
        self.assertEqual(seen, set(labels))

    def test_interruption_replans_from_visible_pose_and_same_pose_cancels(self):
        cat = self.make_cat()
        cat.perform('rest_supine')
        cat.transition.advance(cat.transition.segment_seconds + .001)
        self.assertEqual(cat.behavior.state, 'rest_supine')
        self.assertEqual(cat.visible_state(), 'rest_prone')
        before = cat.visible_image()
        cat.perform('walk_right')
        self.assertEqual(cat.transition.states[0], 'rest_prone')
        self.assertEqual(cat.transition.image(), before)
        self.assertNotIn('rest_supine', cat.transition.states)
        self.assertNotIn('rest_side', cat.transition.states)
        cat.perform('rest_prone')
        self.assertIsNone(cat.transition)
        self.assertEqual(cat.behavior.state, 'rest_prone')
        self.assertEqual(cat.visible_image(), before)

    def test_pickup_cancels_pending_route_animates_sway_and_releases_to_idle(self):
        cat = self.make_cat()
        cat.perform('rest_supine')
        press_x, press_y = cat.x() + 110, cat.y() + 70
        cat.mousePressEvent(self.mouse(press_x, press_y))
        self.assertIsNone(cat.transition)
        self.assertEqual(cat.visible_state(), 'held')
        self.assertEqual(cat.behavior.state, 'idle')
        position = cat.route_position
        for index in range(1, 11):
            cat.mouseMoveEvent(self.mouse(press_x + index * 10, press_y + index * 2))
            self.tick(cat)
        self.assertGreater(cat.held_sway.angle, 1.)
        self.assertEqual(cat.route_position, position)
        self.assertEqual(cat.behavior.elapsed, 0.)
        self.assertGreater(cat.overlay_elapsed, .45)
        for _ in range(70):
            self.tick(cat)
        self.assertLess(abs(cat.held_sway.angle), .0001)
        self.assertGreater(cat.overlay_elapsed, 3.9)
        cat.mouseReleaseEvent(self.mouse(press_x + 100, press_y + 20))
        self.assertIsNone(cat.drag_offset)
        self.assertIsNone(cat.perch)
        self.assertEqual(cat.transition.states, ['held', 'idle'])
        self.assertEqual(cat.behavior.state, 'idle')
        self.assertIsNone(cat.behavior.stop_x)
        self.finish_transition(cat)
        self.assertEqual(cat.visible_state(), 'idle')

    def test_window_attach_follows_motion_and_drop_can_attach_again(self):
        cat = self.make_cat()
        observer = self.attach(cat, finish=False)
        self.assertEqual(cat.visible_state(), 'idle')
        self.assertEqual(cat.transition.states, ['idle', 'rest_prone', 'window_perch'])
        self.assertIn(int(cat.winId()), observer.excluded)
        self.assertAlmostEqual(cat.rest_y + cat.perch_baseline(), 400)
        self.assertEqual(cat.perch.hwnd, 91001)
        old_x, old_y = cat.rest_x, cat.rest_y
        observer.windows = [NativeWindow(91001, Rect(240, 460, 890, 760), pid=42)]
        cat.refresh_floor()
        self.assertAlmostEqual(cat.rest_x, old_x + 40)
        self.assertAlmostEqual(cat.rest_y, old_y + 60)
        self.assertEqual(cat.pos(), QPoint(round(cat.rest_x), round(cat.rest_y)))
        self.tick(cat)
        self.assertEqual(cat.overlay_elapsed, 0.)
        self.assertIsNotNone(cat.transition)
        self.finish_transition(cat)
        self.assertEqual(cat.visible_state(), 'window_perch')
        self.tick(cat)
        self.assertGreater(cat.overlay_elapsed, 0.)
        self.assertEqual(cat.behavior.elapsed, 0.)
        # Pickup detaches immediately; releasing near the same ledge reattaches.
        x, y = cat.x() + 100, cat.y() + 80
        cat.mousePressEvent(self.mouse(x, y))
        self.assertIsNone(cat.perch)
        self.assertEqual(cat.visible_state(), 'held')
        cat.mouseReleaseEvent(self.mouse(x, y))
        self.assertEqual(cat.transition.states, ['held', 'idle', 'rest_prone', 'window_perch'])
        self.assertEqual(cat.visible_state(), 'held')
        self.assertEqual(cat.perch.hwnd, 91001)
        self.finish_transition(cat)
        self.assertEqual(cat.visible_state(), 'window_perch')
        self.assertIsNone(cat.transition)
        self.assertEqual(cat.perch.hwnd, 91001)

    def test_release_keeps_the_rotated_held_image_for_floor_and_window_landings(self):
        for attach_window in (False, True):
            with self.subTest(attach_window=attach_window):
                cat = self.make_cat()
                if attach_window:
                    self.attach(cat)
                x, y = cat.x() + 100, cat.y() + 80
                cat.mousePressEvent(self.mouse(x, y))
                cat.mouseMoveEvent(self.mouse(x + 30, y))
                self.tick(cat)
                self.tick(cat)
                self.assertGreater(abs(cat.held_sway.angle), .1)
                before = cat.render_frame(512)
                self.assertNotEqual(before, cat.visible_image())
                cat.mouseReleaseEvent(self.mouse(x + 30, y))
                self.assertEqual(cat.held_sway.angle, 0.)
                self.assertEqual(cat.transition.image(), before)
                self.assertEqual(cat.render_frame(512), before)
                self.assertEqual(cat.transition.states,
                                 ['held', 'idle', 'rest_prone', 'window_perch']
                                 if attach_window else ['held', 'idle'])

    def test_missing_window_returns_to_floor_even_from_free_mode(self):
        cat = self.make_cat()
        cat.set_mode('free')
        observer = self.attach(cat)
        observer.windows = []
        cat.refresh_floor()
        self.assertIsNone(cat.perch)
        self.assertEqual(cat.mode, 'auto')
        self.assertEqual(cat.behavior.state, 'idle')
        self.assertIsNone(cat.transition)
        self.assertEqual(cat.visible_state(), 'jump_air')
        self.assertGreater(cat.target_y, 500)
        self.finish_transition(cat)
        for _ in range(80):
            self.tick(cat)
        self.assertIsNone(cat.jump)
        self.assertAlmostEqual(cat.y(), cat.target_y, delta=1.)

    def test_transient_window_read_failure_preserves_current_attachment(self):
        cat = self.make_cat()
        observer = self.attach(cat)
        old_perch, old_position = cat.perch, cat.pos()
        observer.error = OSError('Transient native enumeration failure')
        cat.refresh_floor()
        self.assertEqual(cat.perch, old_perch)
        self.assertEqual(cat.pos(), old_position)
        self.assertEqual(cat.visible_state(), 'window_perch')

    def test_successful_window_read_resets_errors_and_three_failures_release(self):
        cat = self.make_cat()
        observer = self.attach(cat)
        attachment = cat.perch
        observer.error = OSError('Enumeration unavailable')
        for _ in range(2):
            cat.refresh_floor()
            self.assertEqual(cat.perch, attachment)
        observer.error = None
        cat.refresh_floor()
        self.assertEqual(cat.perch, attachment)
        self.assertEqual(cat.perch_errors, 0)
        observer.error = OSError('Enumeration unavailable again')
        for _ in range(2):
            cat.refresh_floor()
            self.assertEqual(cat.perch, attachment)
        cat.refresh_floor()
        self.assertIsNone(cat.perch)
        self.assertEqual(cat.behavior.state, 'idle')
        self.assertGreater(cat.target_y, 500)

    def test_native_topmost_refresh_pauses_for_visible_tray_or_context_menu(self):
        cat = self.make_cat()
        with patch.object(cat.observer, 'keep_topmost') as native_raise:
            with patch.object(cat.menu, 'isVisible', return_value=True):
                cat.menu_open = False  # Tray menus can show without contextMenuEvent.
                cat.raise_pet()
                native_raise.assert_not_called()
            with patch.object(cat.menu, 'isVisible', return_value=False):
                cat.menu_open = True
                cat.raise_pet()
                native_raise.assert_not_called()
                cat.menu_open = False
                cat.raise_pet()
                native_raise.assert_called_once_with(int(cat.winId()))

    def test_shadow_is_below_cat_and_absent_while_free_or_held(self):
        cat = self.make_cat()
        # The authored seated sprite peaks below alpha255; the prone texture
        # contains opaque pixels that can prove SourceOver preserves cat colors.
        cat.perform('rest_prone')
        self.finish_transition(cat)
        cat.target_y = float(cat.y())
        pose, composed = cat.visible_image(), cat.render_frame(512)
        opaque_checked = shadow_visible = 0
        for y in range(0, 512, 2):
            for x in range(0, 512, 2):
                alpha = pose.pixelColor(x, y).alpha()
                if alpha == 255:
                    self.assertEqual(pose.pixel(x, y), composed.pixel(x, y))
                    opaque_checked += 1
                elif alpha == 0 and composed.pixelColor(x, y).alpha() > 0:
                    shadow_visible += 1
        self.assertGreater(opaque_checked, 50)
        self.assertGreater(shadow_visible, 50)
        cat.mode = 'free'
        self.assertEqual(cat.render_frame(512), cat.visible_image())
        cat.mode = 'auto'
        cat.mousePressEvent(self.mouse(cat.x() + 100, cat.y() + 70))
        self.assertEqual(cat.render_frame(512), cat.visible_image())

    def test_interaction_assets_are_calibrated_once_and_loop(self):
        from sprite_scale import calibrate, FACTORS
        cat = self.make_cat()
        root = Path(__file__).resolve().parent / 'output/imagegen/interactions-v1'
        for state, folder in (('held', 'held'), ('window_perch', 'perch')):
            frames, metadata = cat.animations[state]
            original = QImage(str(root / folder / 'frame-01.png')).convertToFormat(
                QImage.Format.Format_ARGB32_Premultiplied)
            self.assertEqual(frames[0], calibrate(original, FACTORS[state], 490 if state == 'held' else 477))
            self.assertEqual(len(frames), 4)
            self.assertTrue(metadata['ready_for_app'])
            self.assertEqual(sum(metadata['duration_ms']), 3200)
            self.assertEqual(cat.pose_image(state, 0), cat.pose_image(state, 3.2))
            self.assertEqual(cat.pose_image(state, 0), cat.pose_image(state, 3.199))
            self.assertNotEqual(cat.pose_image(state, 0), cat.pose_image(state, 1.75))
        self.assertEqual(cat.animations['held'][1]['pivot_px'], [256, 490+(270-490)*FACTORS['held']])
        self.assertAlmostEqual(cat.perch_baseline(), 477 * cat.height() / 512)

    def test_taskbar_follows_native_monitor_when_qt_uses_friendly_name(self):
        from PySide6.QtCore import QRect
        from desktop_cat import DesktopCat
        cat = self.make_cat()
        screen = types.SimpleNamespace(
            name=lambda: 'LEN T24h-20',
            geometry=lambda: QRect(-2560, -243, 1280, 720),
            availableGeometry=lambda: QRect(-2560, -243, 1280, 720))
        native = (-2560, -243, 0, 1197)
        cat.observer.snapshots = lambda: {
            'DISPLAY2': (native, native, [(-2560, 1097, 0, 1197)], True)}
        cat.logical_screens = lambda: {'LEN T24h-20': (-2560, -243, -1280, 477)}
        with patch('desktop_cat.QApplication.screens', return_value=[screen]):
            surfaces = DesktopCat.screen_surfaces(cat)
        self.assertEqual(surfaces[0].name, 'LEN T24h-20')
        self.assertEqual(surfaces[0].floor, 427)  # 100 physical px -> 50 logical px.


if __name__ == '__main__':
    unittest.main()
