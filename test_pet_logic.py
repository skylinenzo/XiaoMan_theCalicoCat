import unittest
import random
from pet_logic import (PetBehavior, blink_at, floor_offset, sequence_blend,
                       sequence_frame, stride_speed)


class LogicTests(unittest.TestCase):
    def test_hidden_activation_strip(self):
        self.assertEqual(floor_offset((0, 0, 1920, 1080), (0, 0, 1920, 1078),
                                     [(0, 1078, 1920, 1126)], True), 0)

    def test_revealed_auto_hide_bar(self):
        self.assertEqual(floor_offset((0, 0, 1920, 1080), (0, 0, 1920, 1080),
                                     [(0, 1032, 1920, 1080)], True), 48)

    def test_other_monitor_ignored(self):
        self.assertEqual(floor_offset((-1920, 0, 0, 1080), (-1920, 0, 0, 1080),
                                     [(0, 1032, 1920, 1080)], True), 0)

    def test_fixed_taskbar_work_area(self):
        self.assertEqual(floor_offset((0, 0, 2560, 1440), (0, 0, 2560, 1368),
                                     [], False), 72)

    def test_loop_returns_identical_frame(self):
        for t in (0, 3.99999, 4, 8):
            self.assertEqual(blink_at(t)[:2], (0, 0))
        self.assertEqual(blink_at(2.88)[:2], (3, 3))

    def test_groom_playback_and_wrap(self):
        order = [0, 1, 2, 3, 2, 1, 0]
        times = [450, 130, 130, 220, 130, 130, 400]
        self.assertEqual(sequence_frame(.8, order, times), 3)
        self.assertEqual(sequence_frame(1.589, order, times), 0)
        self.assertEqual(sequence_frame(1.59, order, times), 0)

    def test_walk_holds_then_blends_through_loop_seam(self):
        order, times = [0, 1, 2, 3], [240] * 4
        self.assertEqual(sequence_blend(.15, order, times, 60), (0, 0, 0))
        first, second, blend = sequence_blend(.21, order, times, 60)
        self.assertEqual((first, second), (0, 1))
        self.assertAlmostEqual(blend, .5)
        first, second, blend = sequence_blend(.93, order, times, 60)
        self.assertEqual((first, second), (3, 0))
        self.assertAlmostEqual(blend, .5)
        self.assertGreater(sequence_blend(.959999, order, times, 60)[2], .999)
        for boundary in (0, .96, 1.92):
            self.assertEqual(sequence_blend(boundary, order, times, 60), (0, 0, 0))

    def test_blend_respects_custom_order_and_unequal_hold_times(self):
        order, times = [2, 0], [100, 300]
        self.assertEqual(sequence_blend(.15, order, times, 20), (0, 0, 0))
        for elapsed, pair in ((.09, (2, 0)), (.39, (0, 2))):
            first, second, blend = sequence_blend(elapsed, order, times, 20)
            self.assertEqual((first, second), pair)
            self.assertAlmostEqual(blend, .5)
        self.assertEqual(sequence_blend(.39, order, times, 0), (0, 0, 0))

    def test_action_lengths_follow_configured_asset_cycles(self):
        cycles = {'groom': 1.2, 'walk_left': .8, 'walk_right': 1.6}
        pet = PetBehavior(random.Random(5), cycle_seconds=cycles)
        for state, cycle in cycles.items():
            for _ in range(20):
                pet.start(state)
                repeats = pet.duration / cycle
                self.assertAlmostEqual(repeats, round(repeats))
                low, high = (2, 4) if state == 'groom' else (3, 7)
                self.assertTrue(low <= round(repeats) <= high)

    def test_each_walk_cycle_covers_one_scaled_stride(self):
        for width in (160, 220, 300):
            for cycle in (.72, .96, 1.2):
                for state, direction in (('walk_left', -1), ('walk_right', 1)):
                    cycles = {'groom': 1, 'walk_left': cycle, 'walk_right': cycle}
                    pet = PetBehavior(random.Random(6), cycle_seconds=cycles)
                    pet.start(state)
                    x = 500
                    speed = stride_speed(110, width, 512, cycle)
                    for _ in range(60):
                        x = pet.advance(cycle / 60, x, 0, 1000, speed)
                    self.assertAlmostEqual(x - 500, direction * 110 * width / 512)

    def test_taskbar_motion_preserves_walk_phase_and_resumes(self):
        pet = PetBehavior(random.Random(7))
        pet.start('walk_right')
        x = pet.advance(.21, 500, 0, 1000, 50)
        phase = pet.elapsed
        for _ in range(40):
            self.assertEqual(pet.advance(.016, x, 0, 1000, 50,
                                         surface_moving=True), x)
            self.assertEqual(pet.state, 'walk_right')
            self.assertEqual(pet.elapsed, phase)
        self.assertAlmostEqual(pet.advance(.02, x, 0, 1000, 50), x + 1)
        self.assertAlmostEqual(pet.elapsed, phase + .02)
        pet.advance(.02, x, 0, 1000, 50, can_walk=False, surface_moving=True)
        self.assertEqual(pet.state, 'idle')

    def test_moving_surface_does_not_start_a_new_walk(self):
        pet = PetBehavior(random.Random(8))
        for _ in range(500):
            pet.advance(1, 500, 0, 1000, 48, surface_moving=True)
            self.assertIn(pet.state, ('idle', 'groom'))

    def test_walking_stops_at_both_edges(self):
        pet = PetBehavior(random.Random(1))
        for state, start, end in [('walk_left', -1919, -1920), ('walk_right', -221, -220)]:
            pet.start(state)
            self.assertEqual(pet.advance(.1, start, -1920, -220, 48), end)
            self.assertEqual(pet.state, 'idle')

    def test_free_mode_never_selects_walk(self):
        pet = PetBehavior(random.Random(2))
        for _ in range(500):
            pet.advance(1, 500, 0, 1000, 48, can_walk=False)
            self.assertIn(pet.state, ('idle', 'groom'))

    def test_disabled_autonomy_stays_idle(self):
        pet = PetBehavior(random.Random(3))
        pet.enabled = False
        for _ in range(500):
            self.assertEqual(pet.advance(1, 500, 0, 1000, 48), 500)
            self.assertEqual(pet.state, 'idle')

    def test_seeded_random_actions_and_bounds(self):
        pet = PetBehavior(random.Random(4))
        x, seen = 500, set()
        for _ in range(20000):
            x = pet.advance(.05, x, 0, 1000, 48)
            self.assertTrue(0 <= x <= 1000)
            seen.add(pet.state)
        self.assertEqual(seen, {'idle', 'groom', 'walk_left', 'walk_right'})


if __name__ == '__main__':
    unittest.main()
