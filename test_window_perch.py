import unittest
from types import SimpleNamespace

from window_perch import (NativeSnapshot, NativeWindow, PerchAttachment, Rect,
                          WindowObserver, choose_perch, follow_perch, match_monitors)


class WindowPerchTests(unittest.TestCase):
    screens = {'main': (0, 0, 1920, 1080)}
    size = (200, 200)

    def snapshot(self, *windows):
        return NativeSnapshot(self.screens, windows)

    def window(self, hwnd=1, bounds=(300, 400, 1100, 950), eligible=True, pid=42):
        return NativeWindow(hwnd, Rect(*bounds), eligible, pid)

    def choose(self, snapshot, foot=(700, 420), **kwargs):
        return choose_perch(snapshot, self.screens, foot, self.size, baseline=190, **kwargs)

    def follow(self, attached, snapshot):
        return follow_perch(attached, snapshot, self.screens, self.size, baseline=190)

    def test_drop_snaps_to_top_and_saves_fraction(self):
        placed = self.choose(self.snapshot(self.window()))
        self.assertEqual((placed.x, placed.y, placed.floor, placed.screen), (600, 210, 400, 'main'))
        self.assertEqual(placed.attachment, PerchAttachment(1, .5, 42))

    def test_snap_requires_nearby_edge(self):
        snapshot = self.snapshot(self.window())
        self.assertIsNone(self.choose(snapshot, foot=(700, 500)))
        self.assertIsNone(self.choose(snapshot, foot=(150, 400)))
        self.assertIsNotNone(self.choose(snapshot, foot=(380, 420)))
        self.assertIsNone(self.choose(snapshot, foot=(700, 440)))
        self.assertIsNotNone(self.choose(snapshot, foot=(700, 540), snap_distance=160))

    def test_rejects_no_room_above_or_narrow_window(self):
        self.assertIsNone(self.choose(self.snapshot(self.window(bounds=(300, 100, 1100, 900))), foot=(700, 100)))
        self.assertIsNone(self.choose(self.snapshot(self.window(bounds=(600, 400, 750, 900)))))

    def test_same_height_prefers_foreground_window(self):
        placed = self.choose(self.snapshot(self.window(2), self.window(1)))
        self.assertEqual(placed.attachment.hwnd, 2)

    def test_menu_is_occluder_but_not_a_perch(self):
        menu = self.window(2, (550, 350, 850, 600), eligible=False)
        snapshot = self.snapshot(menu, self.window())
        self.assertIsNone(self.choose(snapshot))
        placed = self.choose(snapshot, foot=(420, 400))
        self.assertEqual(placed.attachment.hwnd, 1)
        self.assertEqual(placed.x, 320)

    def test_occlusion_must_fit_whole_canvas_not_only_center(self):
        front = self.window(2, (780, 250, 950, 600), eligible=False)
        snapshot = self.snapshot(front, self.window())
        placed = self.choose(snapshot, snap_distance=30)
        self.assertEqual(placed.x, 580)  # Center moved to 680 to clear the menu.
        self.assertIsNone(self.follow(PerchAttachment(1, .5, 42), snapshot))

    def test_window_below_top_does_not_hide_ledge(self):
        front = self.window(2, (500, 500, 900, 900), eligible=False)
        self.assertIsNotNone(self.choose(self.snapshot(front, self.window())))

    def test_follows_window_movement_and_resize_without_changing_fraction(self):
        attached = self.choose(self.snapshot(self.window())).attachment
        placed = self.follow(attached, self.snapshot(self.window(bounds=(400, 500, 1600, 1000))))
        self.assertEqual((placed.x, placed.y), (900, 310))
        self.assertEqual(placed.attachment, attached)

    def test_detaches_when_window_gone_ineligible_or_hwnd_reused(self):
        attached = self.choose(self.snapshot(self.window())).attachment
        for snapshot in (self.snapshot(), self.snapshot(self.window(eligible=False)),
                         self.snapshot(self.window(pid=100))):
            self.assertIsNone(self.follow(attached, snapshot))

    def test_detaches_on_covered_anchor_instead_of_jumping_sideways(self):
        attached = self.choose(self.snapshot(self.window())).attachment
        front = self.window(2, (600, 250, 800, 650), eligible=False)
        self.assertIsNone(self.follow(attached, self.snapshot(front, self.window())))

    def test_screen_edge_clamp_retains_fraction_and_recovers(self):
        attached = PerchAttachment(1, .2, 42)
        moved = self.snapshot(self.window(bounds=(-100, 400, 700, 950)))
        placed = self.follow(attached, moved)
        self.assertEqual(placed.x, 0)
        self.assertEqual(placed.attachment.fraction, .2)
        returned = self.follow(attached, self.snapshot(self.window()))
        self.assertEqual(returned.x, 360)

    def test_does_not_jump_across_occluder_when_resize_leaves_tiny_patch(self):
        attached = PerchAttachment(1, .0625, 42)  # Desired center x = 350.
        front = self.window(2, (460, 250, 700, 650), eligible=False)
        # The initial center is uncovered, but the cat no longer fits between
        # the resized left window edge and the foreground window.
        self.assertIsNone(self.follow(attached, self.snapshot(front, self.window())))

    def test_mixed_dpi_negative_origin_uses_monitor_local_mapping(self):
        physical = {'left': (-1920, 0, 0, 1080), 'main': (0, 0, 3840, 2160)}
        logical = {'left': (-1280, 0, 0, 720), 'main': (0, 0, 1920, 1080)}
        window = self.window(bounds=(-1500, 600, -300, 1000))
        snapshot = NativeSnapshot(physical, (window,))
        placed = choose_perch(snapshot, logical, (-600, 410), self.size, baseline=190)
        self.assertEqual((placed.x, placed.y, placed.floor, placed.screen), (-700, 210, 400, 'left'))
        self.assertEqual(placed.attachment.fraction, .5)

    def test_attachment_tracks_window_across_different_dpi_monitors(self):
        physical = {'left': (-1920, 0, 0, 1080), 'main': (0, 0, 3840, 2160)}
        logical = {'left': (-1280, 0, 0, 720), 'main': (0, 0, 1920, 1080)}
        window = self.window(bounds=(400, 800, 2000, 1700))
        snapshot = NativeSnapshot(physical, (window,))
        placed = follow_perch(PerchAttachment(1, .5, 42), snapshot, logical, self.size, baseline=190)
        self.assertEqual((placed.x, placed.y, placed.floor, placed.screen), (500, 210, 400, 'main'))

    def test_spanning_window_cannot_place_cat_in_logical_monitor_gap(self):
        physical = {'left': (0, 0, 1920, 1080), 'right': (1920, 0, 5760, 2160)}
        logical = {'left': (0, 0, 1920, 1080), 'right': (2560, 0, 4480, 1080)}
        window = self.window(bounds=(1500, 800, 3000, 1050))
        snapshot = NativeSnapshot(physical, (window,))
        self.assertIsNone(choose_perch(snapshot, logical, (2250, 400), self.size))
        placed = choose_perch(snapshot, logical, (2570, 400), self.size, snap_distance=100)
        self.assertEqual(placed.screen, 'right')
        self.assertEqual(placed.x, 2560)

    def test_unknown_monitor_mapping_is_not_guessed(self):
        snapshot = self.snapshot(self.window())
        self.assertIsNone(choose_perch(snapshot, {'another': (2000, 0, 3920, 1080)},
                                      (700, 400), self.size))

    def test_real_friendly_screen_name_can_attach_and_follow(self):
        physical = {'DISPLAY1': (0, 0, 1920, 1200), 'DISPLAY2': (-2560, -243, 0, 1197)}
        logical = {'DISPLAY1': (0, 0, 1920, 1200), 'LEN T24h-20': (-2560, -243, 0, 1197)}
        snapshot = NativeSnapshot(physical, (self.window(bounds=(-1912, 150, -710, 951)),))
        placed = choose_perch(snapshot, logical, (-1400, 150), (300, 300), 300 * 477 / 512)
        self.assertIsNotNone(placed)
        self.assertEqual(placed.screen, 'LEN T24h-20')
        self.assertEqual(follow_perch(placed.attachment, snapshot, logical,
                                     (300, 300), 300 * 477 / 512), placed)

    def test_friendly_name_matching_uses_origin_not_scaled_size(self):
        physical = {'DISPLAY1': (0, 0, 3840, 2160), 'DISPLAY2': (-2560, -243, 0, 1197)}
        logical = {'Internal': (0, 0, 1920, 1080), 'LEN': (-2560, -243, -1280, 477)}
        self.assertEqual(match_monitors(physical, logical), {'Internal': 'DISPLAY1', 'LEN': 'DISPLAY2'})
        snapshot = NativeSnapshot(physical, (self.window(bounds=(-2200, 400, -400, 1000)),))
        placed = choose_perch(snapshot, logical, (-1930, 78.5), self.size, 190)
        self.assertAlmostEqual(placed.floor, 78.5)
        self.assertEqual(placed.screen, 'LEN')

    def test_ambiguous_origins_are_not_matched(self):
        self.assertEqual(match_monitors({'a': (0, 0, 1920, 1080), 'b': (0, 0, 1920, 1080)},
                                       {'friendly': (0, 0, 1920, 1080)}), {})
        self.assertEqual(match_monitors({'a': (0, 0, 1920, 1080)},
                                       {'one': (0, 0, 1920, 1080), 'two': (0, 0, 1920, 1080)}), {})

    def test_small_display_or_invalid_size_has_no_ledge(self):
        snapshot = self.snapshot(self.window())
        for size in ((0, 200), (200, -1), (2000, 200)):
            self.assertIsNone(choose_perch(snapshot, self.screens, (700, 400), size))


class WindowObserverOrderTests(unittest.TestCase):
    """Exercise native scan races with handles, without loading Win32 on Linux."""

    def observer(self, enumerated, chain, windows=None):
        observer = object.__new__(WindowObserver)
        observer.C = SimpleNamespace(WinError=lambda error: OSError(error), get_last_error=lambda: 5)
        observer.window_callback = lambda callback: callback

        def enumerate_windows(callback, data):
            for handle in enumerated:
                callback(handle, data)
            return True

        observer.user = SimpleNamespace(
            EnumWindows=enumerate_windows,
            GetTopWindow=lambda parent: next(iter(chain), None),
            GetWindow=lambda hwnd, relation: chain[hwnd],
        )
        observer._read_window = lambda handle, excluded: (
            None if handle in excluded else
            windows[handle] if windows else NativeWindow(handle, Rect(0, 400, 1000, 800)))
        return observer

    def test_native_order_is_z_order_not_enumeration_order(self):
        observer = self.observer([2, 1, 3], {1: 2, 2: 3, 3: None})
        self.assertEqual([window.hwnd for window in observer._windows(set())], [1, 2, 3])

    def test_new_menu_is_queried_even_if_created_after_enumeration(self):
        windows = {1: NativeWindow(1, Rect(300, 400, 1100, 900)),
                   2: NativeWindow(2, Rect(550, 350, 850, 600), eligible=False)}
        observer = self.observer([1], {2: 1, 1: None}, windows)
        ordered = observer._windows(set())
        self.assertEqual([window.hwnd for window in ordered], [2, 1])
        snapshot = NativeSnapshot({'main': (0, 0, 1920, 1080)}, tuple(ordered))
        self.assertIsNone(choose_perch(snapshot, snapshot.monitors, (700, 400), (200, 200)))

    def test_missing_or_reordered_handle_raises_instead_of_inventing_empty_desktop(self):
        observer = self.observer([1, 2], {1: None})
        with self.assertRaises(OSError):
            observer._windows(set())

    def test_z_order_cycle_terminates_with_error(self):
        observer = self.observer([1, 2], {1: 2, 2: 1})
        with self.assertRaises(OSError):
            observer._windows(set())

    def test_explicit_excluded_handle_does_not_break_order_scan(self):
        observer = self.observer([1, 2], {1: 2, 2: None})
        self.assertEqual([window.hwnd for window in observer._windows({1})], [2])

    def test_native_enumeration_failure_propagates(self):
        observer = self.observer([], {})
        observer.user.EnumWindows = lambda callback, data: False
        with self.assertRaises(OSError):
            observer._windows(set())


if __name__ == '__main__':
    unittest.main()
