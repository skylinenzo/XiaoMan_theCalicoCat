"""Logical sizing is independent of native resize/DPR and action selection."""
import unittest
from unittest.mock import patch
import test_interaction_integration as fixtures
from run_animation import RunCycle


class RunCadenceTests(unittest.TestCase):
    def test_faster_cycle_visits_all_frames_and_preserves_stride(self):
        cycle = RunCycle()
        self.assertAlmostEqual(cycle.travel(0, 1), 1.5 * 240 * 1.15 / .64)
        self.assertEqual([cycle.frame(cycle.duration*(i+.5)/8) for i in range(8)], list(range(8)))
        self.assertEqual(cycle.frame(cycle.duration), 0)
        self.assertAlmostEqual(cycle.travel(0, cycle.duration), cycle.stride)


@unittest.skipUnless(fixtures.HAS_QT, 'Qt required')
class DpiSizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.InteractionIntegrationTests.setUpClass()

    make_cat = fixtures.InteractionIntegrationTests.make_cat

    def test_gaze_starts_off_and_menu_can_enable_it(self):
        cat=self.make_cat()
        self.assertFalse(cat.gaze.enabled)
        self.assertFalse(cat.gaze_action.isChecked())
        cat.gaze_action.setChecked(True)
        self.assertTrue(cat.gaze.enabled)
        cat.gaze_action.setChecked(False)
        self.assertFalse(cat.gaze.enabled)

    def test_run_body_length_and_rigid_head_tail_for_every_frame(self):
        from run_shape import coordinate, LANDMARKS, TORSO_LENGTH
        from sprite_scale import FACTORS
        for state, landmarks in LANDMARKS.items():
            for left, right in landmarks:
                left = 256+(left-256)*FACTORS[state]
                right = 256+(right-256)*FACTORS[state]
                self.assertAlmostEqual(coordinate(right,left,right)-coordinate(left,left,right), TORSO_LENGTH)
                self.assertAlmostEqual(coordinate(left-10,left,right)-coordinate(left-30,left,right), 20)
                self.assertAlmostEqual(coordinate(right+30,left,right)-coordinate(right+10,left,right), 20)
        cat = self.make_cat()
        for state in LANDMARKS:
            frames, meta = cat.animations[state]
            self.assertEqual(len(frames), 8)
            for i, frame in enumerate(frames):
                for y in range(512):
                    self.assertLess(frame.pixelColor(0,y).alpha(), 16)
                    self.assertLess(frame.pixelColor(511,y).alpha(), 16)
                self.assertEqual(cat.gaze.catalog[f'{state}/{i}'], meta['eye_rects'][i])

    def test_repeated_native_size_proposals_cannot_change_selected_size(self):
        cat = self.make_cat()
        for size in (220, 160, 300, 220):
            cat.change_size(size)
            for ratio in (1.5, 1., 2., 1.25, 1., 1.5, 1.):
                cat.resize(round(cat.width()/ratio), round(cat.height()/ratio))
                self.assertEqual((cat.width(), cat.height()), (size, size))
                with patch.object(cat, 'devicePixelRatioF', return_value=ratio):
                    image = cat.render_frame()
                self.assertEqual(image.width(), round(size*ratio))

    def test_animation_sources_remain_unchanged_across_dpr_changes(self):
        cat = self.make_cat()
        original = {name: frames[0].copy() for name, (frames, _) in cat.animations.items()}
        cat.mode = 'free'
        cat.gaze.enabled = False
        for ratio in (1., 1.5, 2., 1.25, 1.):
            for state in cat.animations:
                if state.startswith(('run_', 'pounce_', 'window_climb')):
                    continue  # These are rendered by their movement state machines.
                if state == 'jump_down':
                    continue
                cat.behavior.start(state)
                with patch.object(cat, 'devicePixelRatioF', return_value=ratio):
                    self.assertFalse(cat.render_frame().isNull())
        for name, (frames, _) in cat.animations.items():
            self.assertEqual(frames[0], original[name])
            self.assertEqual((frames[0].width(), frames[0].height()), (512, 512))

    def test_calibrated_eye_and_contact_coordinates_match_pose_scale(self):
        from sprite_scale import calibrate_animation, FACTORS
        from PySide6.QtGui import QImage
        image = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
        metadata = {'contact_baseline_y': 490, 'eye_rects': [[[120, 250, 20, 18]]],
                    'contact_x': [100]}
        _, adjusted = calibrate_animation('run_left', [image], metadata)
        factor = FACTORS['run_left']
        self.assertEqual(adjusted['eye_rects'][0][0],
                         [256+(120-256)*factor, 490+(250-490)*factor, 20*factor, 18*factor])
        self.assertEqual(adjusted['contact_x'], [256+(100-256)*factor])
        self.assertEqual(metadata['contact_x'], [100])


if __name__ == '__main__':
    unittest.main()
