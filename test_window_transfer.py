import unittest
import test_interaction_integration as fixtures
from window_perch import NativeWindow, Rect, NativeSnapshot
from window_transfer import canvas_on_screens, choose_transfer

ANCHORS = [490, 490, 482, 490, 104.3, 225.4, 410.9, 490]

class TransferGeometryTests(unittest.TestCase):
    def test_contiguous_monitors_and_gap(self):
        self.assertTrue(canvas_on_screens(-50, 100, 100, 100,
                        {'a': (-800, 0, 0, 800), 'b': (0, 0, 800, 800)}))
        self.assertFalse(canvas_on_screens(-50, 100, 100, 100,
                         {'a': (-800, 0, -10, 800), 'b': (0, 0, 800, 800)}))

    def test_climb_phases_and_hand_anchors(self):
        screens = {'test': (0, 0, 1000, 800)}
        snapshot = NativeSnapshot(screens, (NativeWindow(1, Rect(200, 350, 850, 650), pid=42),))
        motion = choose_transfer(snapshot, screens, (600, 797), 220, ANCHORS)
        self.assertIsNotNone(motion)
        phases = set()
        for i in range(300):
            sample = motion.sample(motion.duration * i / 299)
            phases.add(sample.phase)
            if sample.frame >= 4:
                self.assertAlmostEqual(sample.y + ANCHORS[sample.frame] * 220 / 512, 350)
            if sample.phase != 'climb':
                self.assertEqual(sample.blur, 0)
        self.assertTrue({'prepare','launch','climb','hook','pull','rotate','settle'} <= phases)
        self.assertIsNone(choose_transfer(snapshot, screens, (600, 797), 220, ANCHORS, source_hwnd=1))
        blocker = NativeWindow(2, Rect(100, 300, 900, 700), eligible=False)
        self.assertIsNone(choose_transfer(NativeSnapshot(screens, (blocker, *snapshot.windows)), screens,
                                         (600, 797), 220, ANCHORS))

@unittest.skipUnless(fixtures.HAS_QT, 'PySide6 is required')
class TransferAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.InteractionIntegrationTests.setUpClass()
    make_cat = fixtures.InteractionIntegrationTests.make_cat
    tick = staticmethod(fixtures.InteractionIntegrationTests.tick)
    mouse = staticmethod(fixtures.InteractionIntegrationTests.mouse)

    def setup_transfer(self):
        cat = self.make_cat()
        cat.window_observer = fixtures.WindowSource([NativeWindow(1, Rect(200,350,850,650), pid=42)])
        self.assertTrue(cat.start_transfer(upward_only=True))
        return cat

    def finish(self, cat):
        states = set()
        for i in range(160):
            if i % 2 == 0:
                cat.refresh_floor()
            self.tick(cat)
            states.add(cat.visible_state())
            self.assertFalse(cat.render_frame().isNull())
            if cat.transfer is None and cat.transition is None:
                return states
        self.fail('Transfer did not finish')

    def test_ground_climb_lands_then_hops_other_window(self):
        cat = self.setup_transfer()
        states = self.finish(cat)
        self.assertIn('transfer_climb', states)
        self.assertEqual(cat.perch.hwnd, 1)
        self.assertAlmostEqual(cat.rest_y + cat.perch_baseline(), 350)
        cat.window_observer.windows.insert(0, NativeWindow(2, Rect(680,450,990,750), pid=42))
        self.assertTrue(cat.start_transfer())
        states = self.finish(cat)
        self.assertIn('transfer_flight', states)
        self.assertEqual(cat.perch.hwnd, 2)

    def test_target_disappears_in_air_falls_and_lands(self):
        cat = self.setup_transfer()
        for _ in range(8): self.tick(cat)
        cat.window_observer.windows.clear()
        cat.refresh_floor()
        self.assertIsNone(cat.transfer)
        self.assertIsNotNone(cat.jump)
        for _ in range(100): self.tick(cat)
        self.assertIsNone(cat.jump)
        self.assertIsNone(cat.perch)
        self.assertAlmostEqual(cat.rest_y, cat.target_y)

    def test_drag_interrupts_and_free_mode_cancels_without_fall(self):
        cat = self.setup_transfer()
        self.tick(cat)
        cat.mousePressEvent(self.mouse(cat.x()+100, cat.y()+100))
        self.assertIsNone(cat.transfer)
        self.assertEqual(cat.visible_state(), 'held')
        other = self.setup_transfer()
        for _ in range(8): self.tick(other)
        other.set_mode('free')
        self.assertIsNone(other.transfer)
        self.assertIsNone(other.jump)
        self.assertEqual(other.mode, 'free')

    def test_target_move_before_launch_and_far_move_cancels(self):
        cat = self.setup_transfer()
        cat.window_observer.windows[0] = NativeWindow(1, Rect(220,360,870,660), pid=42)
        cat.refresh_floor()
        self.assertEqual(cat.transfer['target'].floor, 360)
        for _ in range(8): self.tick(cat)
        cat.window_observer.windows[0] = NativeWindow(1, Rect(220,600,870,780), pid=42)
        cat.refresh_floor()
        self.assertIsNone(cat.transfer)
        self.assertIsNotNone(cat.jump)

    def test_autonomy_disabled_and_cooldown(self):
        cat = self.make_cat()
        cat.window_observer = fixtures.WindowSource([NativeWindow(1, Rect(200,350,850,650), pid=42)])
        cat.roam_cooldown = 0
        cat.behavior.elapsed = 2.5
        self.tick(cat)
        self.assertIsNone(cat.transfer)
        cat.rhythm.enter('active')
        cat.behavior.enabled = True
        self.tick(cat)
        self.assertIsNotNone(cat.transfer)

class OcclusionGeometryTests(unittest.TestCase):
    def test_mixed_dpi_window_coverage_and_pid_reuse(self):
        from window_transfer import window_occlusion_rects
        from window_perch import PerchAttachment
        snapshot = NativeSnapshot({'a': Rect(-1000,0,0,1000), 'b': Rect(0,0,2000,1600)},
                                  (NativeWindow(10,Rect(-100,300,800,900),pid=42),))
        screens={'a':(-1000,0,0,1000),'b':(0,0,1000,800)}
        self.assertEqual(window_occlusion_rects(snapshot,screens,PerchAttachment(10,.5,42)),
                         [Rect(-100,300,0,900),Rect(0,150,400,450)])
        self.assertEqual(window_occlusion_rects(snapshot,screens,PerchAttachment(10,.5,99)),[])

@unittest.skipUnless(fixtures.HAS_QT, 'PySide6 is required')
class ClimbViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.InteractionIntegrationTests.setUpClass()
    make_cat = fixtures.InteractionIntegrationTests.make_cat
    tick = staticmethod(fixtures.InteractionIntegrationTests.tick)

    def test_three_views_and_occlusion_pixels(self):
        for style in ('back','side','front_hidden'):
            with self.subTest(style=style):
                cat=self.make_cat()
                cat.set_climb_style(style)
                cat.window_observer=fixtures.WindowSource([NativeWindow(1,Rect(200,350,850,650),pid=42)])
                self.assertTrue(cat.start_transfer(upward_only=True))
                for _ in range(80):
                    self.tick(cat,.025)
                    if cat.visible_state()=='transfer_hook':break
                self.assertEqual(cat.visible_state(),'transfer_hook')
                image=cat.render_frame(220)
                below=above=0
                for y in range(image.height()):
                    for x in range(image.width()):
                        alpha=image.pixelColor(x,y).alpha()
                        covered=200<=cat.x()+x<850 and 350<=cat.y()+y<650
                        if covered:below+=alpha
                        else:above+=alpha
                if style=='front_hidden':
                    self.assertEqual(below,0)
                    self.assertGreater(above,0)
                else:self.assertGreater(below,10000)
                current=cat.transfer['animation']
                cat.set_climb_style('side' if style!='side' else 'back')
                self.assertEqual(cat.transfer['animation'],current)
                for _ in range(100):
                    self.tick(cat)
                    if cat.transfer is None and cat.transition is None:break
                self.assertIsNone(cat.transfer)
                self.assertEqual(cat.perch.hwnd,1)
                self.assertAlmostEqual(cat.rest_y+cat.perch_baseline(),350)
