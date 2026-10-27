import json
import math
import os
from pathlib import Path
import random
import unittest

from anchored_walk import AnchoredCycle
from desktop_route import DesktopRoute, Surface
from pet_logic import PatrolBehavior

ROOT = Path(__file__).resolve().parent / 'output/imagegen'


class FootAnchorTests(unittest.TestCase):
    def test_world_support_foot_is_stationary_and_speed_varies(self):
        for side in ('left', 'right'):
            cycle = AnchoredCycle(json.loads((ROOT / f'walk-{side}-v3/animation.json').read_text()))
            for i, duration in enumerate(cycle.durations):
                world = []
                for step in range(20):
                    sample = cycle.sample(cycle.times[i] + duration * (step + .1) / 21)
                    world.append(cycle.direction * sample[3] + sample[4])
                self.assertLess(max(world) - min(world), 1e-8)
            for boundary in cycle.times[1:]:
                self.assertLess(abs(cycle.sample(boundary + 1e-8)[3] - cycle.sample(boundary - 1e-8)[3]), .0001)
            speeds = [cycle.travel(i * .005, .005) / .005 for i in range(180)]
            self.assertGreater(max(speeds), min(speeds) * 5)
            self.assertTrue(all(s >= 0 for s in speeds))
            self.assertAlmostEqual(cycle.travel(0, cycle.duration * 10), cycle.stride * 10)
            # Clipping a step at a screen edge preserves the same motion curve.
            end = cycle.time_after_distance(.02, .1, cycle.travel(.02, .1) * .4)
            self.assertAlmostEqual(cycle.sample(end)[3] - cycle.sample(.02)[3], cycle.travel(.02, .1) * .4)


class MultiScreenTests(unittest.TestCase):
    def route(self):
        return DesktopRoute([
            Surface('left', -1280, 0, 1280, 1024, 1021),
            Surface('primary', 0, 0, 1920, 1080, 1032),
            Surface('scaled', 2560, -200, 1280, 720, 517),
            Surface('stacked', 2560, -1280, 1280, 1080, -203),
        ], 220)

    def test_all_displays_visited_without_walking_through_coordinate_gaps(self):
        route = self.route()
        visited = set()
        for step in range(1000):
            x, y, name = route.locate(route.length * step / 999)
            screen = next(s for s in route.lanes if s.name == name)
            visited.add(name)
            self.assertGreaterEqual(x + 110, screen.x)
            self.assertLessEqual(x + 110, screen.x + screen.width)
            self.assertAlmostEqual(y + 490 / 512 * 220, screen.floor)
        self.assertEqual(visited, {'left', 'primary', 'scaled', 'stacked'})
        for screen in route.lanes:
            x = screen.x + 300
            y = screen.floor - 490 / 512 * 220
            mapped_x, mapped_y, name = route.locate(route.project(x, y))
            self.assertEqual(name, screen.name)
            self.assertAlmostEqual(mapped_x, x)
            self.assertAlmostEqual(mapped_y, y)

    def test_contiguous_equal_height_screens_have_continuous_positions(self):
        route = DesktopRoute([Surface('a', 0, 0, 1920, 1080, 1077),
                              Surface('b', 1920, 0, 1920, 1080, 1077)], 220)
        seam = route.spans[0][1]
        self.assertLess(abs(route.locate(seam - .001)[0] - route.locate(seam + .001)[0]), .003)

    def test_drag_projection_prefers_the_display_containing_the_cat(self):
        route = DesktopRoute([Surface('top', 0, -1080, 1920, 1080, -3),
                              Surface('bottom', 0, 0, 1920, 1080, 1077)], 220)
        self.assertEqual(route.locate(route.project(500, 40))[2], 'bottom')

    def test_patrol_crosses_all_screens_and_rests_fully_on_a_screen(self):
        route = self.route()
        pet = PatrolBehavior(random.Random(4))
        position, visited, edges = route.length * .75, set(), []
        for _ in range(30000):
            previous = pet.state
            position = pet.advance(.05, position, 0, route.length, 200, stop_filter=route.safe_stop)
            x, _, name = route.locate(position)
            visited.add(name)
            if previous.startswith('walk') and pet.state == 'idle':
                surface = next(s for s in route.lanes if s.name == name)
                self.assertTrue(surface.x <= x <= surface.x + surface.width - 220)
                if pet.rest_reason == 'edge':
                    edges.append(position)
            if len(edges) == 3:
                break
        self.assertEqual(edges, [0, route.length, 0])
        self.assertEqual(visited, {s.name for s in route.lanes})


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication
    from anchored_renderer import AnchoredWalk, mix
    from PySide6.QtGui import QColor, QImage
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'PySide6 is required')
class AnchoredRenderTests(unittest.TestCase):
    def test_transition_preserves_alpha_and_brightness(self):
        for alpha in (80, 160, 253, 255):
            texture = QImage(8, 8, QImage.Format.Format_ARGB32_Premultiplied)
            texture.fill(QColor(90, 70, 50, alpha))
            original = texture.pixelColor(4, 4)
            for i in range(1, 100):
                pixel = mix(texture, texture, i / 100).pixelColor(4, 4)
                self.assertLessEqual(abs(pixel.alpha() - original.alpha()), 2)
                for actual, expected in zip(pixel.getRgb()[:3], original.getRgb()[:3]):
                    self.assertLessEqual(abs(actual - expected), 4)

    def test_application_crosses_monitors_without_floor_refresh_clamping_it_back(self):
        import tempfile
        import types
        import sys
        from unittest.mock import patch
        from PySide6.QtCore import QSettings
        app = QApplication.instance() or QApplication([])
        class Observer:
            def snapshot(self, hwnd):
                return (0, 0, 800, 800), (0, 0, 800, 800), [], True
            def keep_topmost(self, hwnd):
                pass
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(sys.modules, {'windows_taskbar': types.SimpleNamespace(TaskbarObserver=Observer)}):
                from desktop_cat import DesktopCat
                cat = DesktopCat(QSettings(temp + '/settings.ini', QSettings.Format.IniFormat))
            try:
                for timer in (cat.timer, cat.floor_timer, cat.top_timer):
                    timer.stop()
                surfaces = [Surface('left', -800, 0, 800, 800, 797),
                            Surface('right', 0, 0, 800, 800, 797)]
                with patch.object(cat, 'screen_surfaces', return_value=surfaces):
                    cat.refresh_floor()
                    cat.route_position = 10
                    cat.rest_x, cat.rest_y, cat.route_screen = cat.route.locate(cat.route_position)
                    cat.target_y = cat.rest_y
                    cat.move(round(cat.rest_x), round(cat.rest_y))
                    cat.set_autonomy(False)
                    cat.perform('walk_right')
                    now = 100.
                    cat.last_tick = now
                    visited, increments = set(), []
                    for i in range(1000):
                        now += .05
                        previous = cat.route_position
                        with patch('desktop_cat.time.monotonic', return_value=now):
                            cat.tick()
                        visited.add(cat.route_screen)
                        increments.append(cat.route_position - previous)
                        if i % 2 == 0:
                            cat.refresh_floor()
                        if cat.behavior.state == 'idle':
                            break
                    self.assertEqual(visited, {'left', 'right'})
                    self.assertAlmostEqual(cat.route_position, cat.route.length)
                    self.assertGreater(max(increments), min(v for v in increments if v > 0) * 3)
                    # A removed display must recover onto the remaining visible floor.
                    surfaces[:] = [Surface('left', -800, 0, 800, 800, 797)]
                    cat.refresh_floor()
                    self.assertEqual(cat.route_screen, 'left')
                    self.assertTrue(0 <= cat.route_position <= cat.route.length)
            finally:
                cat.tray.hide()
                cat.close()

    def test_rendered_cycle_has_stable_head_and_tail_and_no_blank_support_foot(self):
        app = QApplication.instance() or QApplication([])
        renderer = AnchoredWalk()
        for side in ('left', 'right'):
            cycle = renderer.cycles[side]
            first = renderer.render(side, 0, 512)
            self.assertEqual(first, renderer.render(side, cycle.duration, 512))
            for i in range(64):
                t = cycle.duration * i / 64
                frame = renderer.render(side, t, 512)
                # Premultiplied interpolation may round a channel by one level;
                # the final opaque upper body should be copied exactly instead.
                a, b = first.copy(0, 0, 512, 320), frame.copy(0, 0, 512, 320)
                self.assertEqual(a, b)
                anchor = round(cycle.sample(t)[4])
                self.assertGreater(max(frame.pixelColor(x, y).alpha()
                                       for x in range(anchor - 8, anchor + 9)
                                       for y in range(480, 492)), 150, (side, t, anchor))


if __name__ == '__main__':
    unittest.main()
