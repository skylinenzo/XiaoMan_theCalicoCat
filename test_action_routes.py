"""Pose routes preserve physical intermediate postures and safe handling exits."""

import itertools
import unittest

from action_routes import ACTION_STATES, TRANSITION_GRAPH, transition_route


class ActionRouteTests(unittest.TestCase):
    def test_rolls_lower_to_prone_before_side_and_supine(self):
        self.assertEqual(transition_route('idle', 'rest_supine'),
                         ('rest_prone', 'rest_side', 'rest_supine'))
        self.assertEqual(transition_route('rest_supine', 'idle'),
                         ('rest_side', 'rest_prone', 'idle'))

    def test_walk_and_groom_use_the_seated_posture(self):
        self.assertEqual(transition_route('walk_left', 'walk_right'),
                         ('idle', 'walk_right'))
        self.assertEqual(transition_route('groom', 'walk_left'),
                         ('idle', 'walk_left'))
        self.assertEqual(transition_route('rest_supine', 'groom'),
                         ('rest_side', 'rest_prone', 'idle', 'groom'))

    def test_window_perch_enters_and_exits_through_prone(self):
        self.assertEqual(transition_route('idle', 'window_perch'),
                         ('rest_prone', 'window_perch'))
        self.assertEqual(transition_route('window_perch', 'walk_right'),
                         ('rest_prone', 'idle', 'walk_right'))
        self.assertEqual(transition_route('window_perch', 'rest_supine'),
                         ('rest_prone', 'rest_side', 'rest_supine'))

    def test_all_normal_pairs_use_legal_symmetric_shortest_routes(self):
        # The graph is a connected tree: any legal path without repeated states
        # is necessarily the unique shortest route. Check all ordered pairs.
        states = tuple(TRANSITION_GRAPH)
        edge_count = sum(map(len, TRANSITION_GRAPH.values()))
        self.assertEqual(edge_count, 2 * (len(states) - 1))
        for source, target in itertools.product(states, repeat=2):
            with self.subTest(source=source, target=target):
                route = transition_route(source, target)
                self.assertIsInstance(route, tuple)
                self.assertEqual(route, transition_route(source, target))
                if source == target:
                    self.assertEqual(route, ())
                    continue
                self.assertEqual(route[-1], target)
                path = (source, *route)
                self.assertEqual(len(path), len(set(path)))
                for first, second in zip(path, path[1:]):
                    self.assertIn(second, TRANSITION_GRAPH[first])
                    self.assertIn(first, TRANSITION_GRAPH[second])
                reverse = (target, *transition_route(target, source))
                self.assertEqual(path, tuple(reversed(reverse)))

    def test_pickup_interrupts_every_pose_immediately(self):
        for source in ACTION_STATES - {'held'}:
            with self.subTest(source=source):
                self.assertEqual(transition_route(source, 'held'), ('held',))
        self.assertEqual(transition_route('held', 'held'), ())

    def test_release_always_starts_at_idle_without_resuming_old_route(self):
        for target in ACTION_STATES - {'held'}:
            with self.subTest(target=target):
                route = transition_route('held', target)
                self.assertEqual(route[0], 'idle')
                self.assertEqual(route[-1], target)
                self.assertEqual(route[1:], transition_route('idle', target))
        self.assertEqual(transition_route('held', 'idle'), ('idle',))

    def test_replanning_from_visible_pose_discards_abandoned_destinations(self):
        pending = transition_route('idle', 'rest_supine')
        visible = pending[0]  # Only prone has been shown when the user asks to walk.
        self.assertEqual(transition_route(visible, 'walk_left'), ('idle', 'walk_left'))
        # A repeated request for the currently displayed pose simply stops there.
        self.assertEqual(transition_route(visible, visible), ())

    def test_unknown_states_fail_even_when_source_and_target_match(self):
        for invalid in ('', 'sleep', 'Idle', None, [], 0):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    transition_route(invalid, 'idle')
                with self.assertRaises(ValueError):
                    transition_route('idle', invalid)
                with self.assertRaises(ValueError):
                    transition_route(invalid, invalid)


if __name__ == '__main__':
    unittest.main()
