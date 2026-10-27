import math
import random
import unittest

from bones import ANKLE, STANCE, STRIDE, foot_target, leg_pose, solve_leg
from pet_logic import PatrolBehavior


class BoneTests(unittest.TestCase):
    def test_bone_lengths_and_targets_through_entire_walk(self):
        for front in (True, False):
            for far in (True, False):
                for i in range(1000):
                    phase = i / 1000
                    root, knee, foot = leg_pose(phase, front, far)
                    self.assertAlmostEqual(math.dist(root, knee), 58 if front else 65)
                    self.assertAlmostEqual(math.dist(knee, foot), 64 if front else 65)
                    offset = (.25 if front else 0) + (.5 if far else 0)
                    expected = foot_target(phase, root[0] + (0 if front else 4), offset)
                    self.assertLess(math.dist(foot, expected), 1e-5)

    def test_supporting_foot_locks_to_world_ground(self):
        world = []
        for phase in (.02, .12, .25, .4, .6):
            x, y = foot_target(phase, 200)
            world.append(x + phase * STRIDE)
            self.assertEqual(y, ANKLE)
        self.assertLess(max(world) - min(world), 1e-8)

    def test_swing_and_loop_have_no_position_jump(self):
        for boundary in (STANCE, 1):
            before = foot_target(boundary - 1e-8, 200)
            after = foot_target(boundary + 1e-8, 200)
            self.assertLess(math.dist(before, after), 1e-4)
        self.assertLess(foot_target((STANCE + 1) / 2, 200)[1], ANKLE - 20)

    def test_unreachable_target_clamps_without_nan(self):
        knee, foot = solve_leg((0, 0), (1000, 0), 50, 60, 1)
        self.assertAlmostEqual(math.dist((0, 0), knee), 50)
        self.assertLess(foot[0], 110)
        self.assertTrue(all(math.isfinite(v) for p in (knee, foot) for v in p))


class PatrolTests(unittest.TestCase):
    def make_pet(self):
        return PatrolBehavior(random.Random(12), {'groom': 1.59, 'walk_left': 1., 'walk_right': 1.})

    def test_reaches_both_edges_and_rests_and_grooms_midway(self):
        pet = self.make_pet()
        x, edges, middle_groom = 750., [], False
        last = pet.state
        for _ in range(10000):
            old_x = x
            x = pet.advance(.05, x, 0, 1000, 50)
            self.assertLessEqual(abs(x - old_x), 2.50001)
            self.assertTrue(0 <= x <= 1000)
            if last.startswith('walk') and pet.state == 'idle' and pet.rest_reason == 'edge':
                edges.append(x)
            if pet.state == 'groom' and pet.rest_reason == 'midpoint':
                middle_groom = True
            last = pet.state
            if len(edges) >= 3:
                break
        self.assertEqual(edges, [0, 1000, 0])
        self.assertTrue(middle_groom)

    def test_midpoint_rest_keeps_original_direction(self):
        pet = self.make_pet()
        pet.start('walk_right')
        x = 0
        for _ in range(3000):
            x = pet.advance(.05, x, 0, 1000, 60)
            if pet.rest_reason == 'midpoint' and pet.state == 'walk_right':
                break
        self.assertGreater(x, 0)
        self.assertLess(x, 1000)
        self.assertEqual(pet.state, 'walk_right')
        self.assertTrue(pet.leg_rest_done)

    def test_walk_does_not_stop_on_old_random_timer(self):
        pet = self.make_pet()
        pet.enabled = False  # Explicit manual walk still reaches the edge.
        pet.start('walk_left')
        x = 900
        for _ in range(200):
            x = pet.advance(.05, x, 0, 1000, 50)
        self.assertEqual(pet.state, 'walk_left')
        self.assertAlmostEqual(x, 400)

    def test_surface_pause_preserves_destination_and_phase(self):
        pet = self.make_pet()
        pet.start('walk_left')
        x = pet.advance(.1, 800, 0, 1000, 50)
        target, elapsed = pet.stop_x, pet.elapsed
        for _ in range(60):
            self.assertEqual(pet.advance(.016, x, 0, 1000, 50, surface_moving=True), x)
        self.assertEqual(pet.stop_x, target)
        self.assertEqual(pet.elapsed, elapsed)

    def test_disabled_and_free_modes_do_not_patrol(self):
        for enabled, can_walk in ((False, True), (True, False)):
            pet = self.make_pet()
            pet.enabled = enabled
            for _ in range(1000):
                self.assertEqual(pet.advance(.1, 500, 0, 1000, 50, can_walk=can_walk), 500)
                self.assertFalse(pet.state.startswith('walk'))


if __name__ == '__main__':
    unittest.main()
