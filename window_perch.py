"""Read-only window ledges, with physical-to-Qt mapping for each monitor.

All rectangles use exclusive right/bottom edges. Geometry is independent of Qt
and Windows so mixed-DPI placement and occlusion can be checked on any OS.
"""
from dataclasses import dataclass
import math
import os


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top


@dataclass(frozen=True)
class NativeWindow:
    hwnd: int
    rect: Rect
    eligible: bool = True
    pid: int = 0


@dataclass(frozen=True)
class NativeSnapshot:
    """Windows are in front-to-back Z order; monitors use Win32 device names."""
    monitors: dict
    windows: tuple


@dataclass(frozen=True)
class PerchAttachment:
    hwnd: int
    fraction: float
    pid: int = 0


@dataclass(frozen=True)
class PerchPlacement:
    x: float
    y: float
    floor: float
    screen: str
    attachment: PerchAttachment


@dataclass(frozen=True)
class _Ledge:
    window: NativeWindow
    screen: str
    physical_monitor: Rect
    logical_monitor: Rect
    scale_x: float
    floor: float
    left: float
    right: float
    blockers: tuple
    centers: tuple
    z: int


def _rect(value):
    return value if isinstance(value, Rect) else Rect(*value)


def match_monitors(physical_monitors, logical_screens):
    """Map Qt screen labels to Win32 device names without guessing by size.

    Qt may expose an EDID friendly name (e.g. LEN T24h-20), not DISPLAY2.
    On Windows, Qt scales screen dimensions but retains native screen origins:
    https://doc.qt.io/qt-6.8/highdpi.html#device-independent-screen-geometry
    Use that unique origin only when a device-name match isn't available.
    """
    matched = {name: name for name in logical_screens if name in physical_monitors}
    used = set(matched.values())
    pending = {name: _rect(rect) for name, rect in logical_screens.items() if name not in matched}
    for name, logical in pending.items():
        origin = (logical.left, logical.top)
        if sum((rect.left, rect.top) == origin for rect in pending.values()) != 1:
            continue
        candidates = [device for device, rect in physical_monitors.items()
                      if device not in used and (_rect(rect).left, _rect(rect).top) == origin]
        if len(candidates) == 1:
            matched[name] = candidates[0]
            used.add(candidates[0])
    return matched


def _subtract(intervals, left, right):
    result = []
    for start, end in intervals:
        if right <= start or left >= end:
            result.append((start, end))
        else:
            if left > start:
                result.append((start, left))
            if right < end:
                result.append((right, end))
    return result


def _ledges(snapshot, logical_screens, pet_size, baseline):
    width, height = pet_size
    if not (width > 0 and height > 0 and 0 <= baseline <= height):
        return
    monitor_names = match_monitors(snapshot.monitors, logical_screens)
    for z, window in enumerate(snapshot.windows):
        rect = _rect(window.rect)
        if not window.eligible or rect.width <= 0 or rect.height <= 0:
            continue
        for name, logical in logical_screens.items():
            if name not in monitor_names:
                # Guessing a screen by its dimensions is unsafe with mixed DPI.
                continue
            physical, screen = _rect(snapshot.monitors[monitor_names[name]]), _rect(logical)
            if min(physical.width, physical.height, screen.width, screen.height) <= 0:
                continue
            if not physical.top <= rect.top < physical.bottom:
                continue
            sx, sy = screen.width / physical.width, screen.height / physical.height
            floor = screen.top + (rect.top - physical.top) * sy
            if floor - baseline < screen.top or floor - baseline + height > screen.bottom:
                continue
            left = max(rect.left, physical.left)
            right = min(rect.right, physical.right)
            left = screen.left + (left - physical.left) * sx
            right = screen.left + (right - physical.left) * sx
            if right - left < width:
                continue
            intervals, blockers = [(left, right)], []
            # A higher window covering the ledge makes that portion unusable.
            # Use a narrow strip rather than sampling only a single pixel.
            tolerance = 2 / sy
            for foreground in snapshot.windows[:z]:
                front = _rect(foreground.rect)
                if front.top <= rect.top + tolerance and front.bottom > rect.top - tolerance:
                    a = screen.left + (front.left - physical.left) * sx
                    b = screen.left + (front.right - physical.left) * sx
                    if b > left and a < right:
                        blockers.append((a, b))
                        intervals = _subtract(intervals, a, b)
            centers = tuple((a + width / 2, b - width / 2)
                            for a, b in intervals if b - a >= width)
            if centers:
                yield _Ledge(window, name, physical, screen, sx, floor,
                             left, right, tuple(blockers), centers, z)


def _placement(ledge, center, baseline, attachment=None):
    rect = _rect(ledge.window.rect)
    physical_x = (center - ledge.logical_monitor.left) / ledge.scale_x + ledge.physical_monitor.left
    if attachment is None:
        attachment = PerchAttachment(ledge.window.hwnd,
                                     max(0., min(1., (physical_x - rect.left) / rect.width)),
                                     ledge.window.pid)
    return PerchPlacement(center, ledge.floor - baseline, ledge.floor,
                          ledge.screen, attachment)


def choose_perch(snapshot, logical_screens, foot, pet_size, baseline=None,
                 snap_distance=32.):
    """Snap a released cat to the nearest exposed window top, or return None.

    ``foot`` is the canvas horizontal center and floor Y in Qt coordinates.
    Returned x/y are the canvas top-left, and attachment is retained for follow.
    Use QScreen.geometry() (not availableGeometry) in ``logical_screens``.
    """
    width, height = pet_size
    baseline = height * 490 / 512 if baseline is None else baseline
    if snap_distance < 0:
        return None
    choices = []
    for ledge in _ledges(snapshot, logical_screens, pet_size, baseline):
        for left, right in ledge.centers:
            center = min(max(foot[0], left), right)
            distance = math.hypot(center - foot[0], ledge.floor - foot[1])
            if distance <= snap_distance:
                placed = _placement(ledge, center, baseline)
                choices.append((distance, ledge.z, placed))
    if not choices:
        return None
    placement = min(choices, key=lambda item: item[:2])[2]
    return PerchPlacement(placement.x - width / 2, placement.y, placement.floor,
                          placement.screen, placement.attachment)


def follow_perch(attachment, snapshot, logical_screens, pet_size, baseline=None):
    """Follow a surviving HWND/fraction; detach when its ledge becomes covered.

    Screen-edge clamps retain the original fraction, allowing the cat to resume
    that position when the window returns fully onscreen. Occlusion never causes
    a sideways jump to a different exposed part of the window.
    """
    width, height = pet_size
    baseline = height * 490 / 512 if baseline is None else baseline
    for ledge in _ledges(snapshot, logical_screens, pet_size, baseline):
        if ledge.window.hwnd != attachment.hwnd:
            continue
        if attachment.pid and ledge.window.pid != attachment.pid:
            continue
        rect = _rect(ledge.window.rect)
        physical_x = rect.left + max(0., min(1., attachment.fraction)) * rect.width
        monitor = ledge.physical_monitor
        if not monitor.left <= physical_x < monitor.right:
            continue
        center = ledge.logical_monitor.left + (physical_x - monitor.left) * ledge.scale_x
        if any(center + width / 2 > a and center - width / 2 < b for a, b in ledge.blockers):
            return None
        # Clamp at the display/window ends, but do not cross an occluder.
        choices = [min(max(center, left), right) for left, right in ledge.centers]
        target = min(choices, key=lambda value: abs(value - center))
        if any(max(center, target) + width / 2 > a
               and min(center, target) - width / 2 < b for a, b in ledge.blockers):
            return None
        placed = _placement(ledge, target, baseline, attachment)
        return PerchPlacement(placed.x - width / 2, placed.y, placed.floor,
                              placed.screen, attachment)
    return None


def advance_perch(attachment, snapshot, logical_screens, pet_size, distance, baseline=None):
    """Move along the current exposed ledge, never across a blocker or its ends.

    Return placement and actual logical travel; updating the attachment fraction
    makes later native window movement keep the new position on that window.
    """
    width, height = pet_size
    baseline = height * 490 / 512 if baseline is None else baseline
    current = follow_perch(attachment, snapshot, logical_screens, pet_size, baseline)
    if current is None:
        return None, 0.
    center = current.x + width / 2
    for ledge in _ledges(snapshot, logical_screens, pet_size, baseline):
        if ledge.window.hwnd != attachment.hwnd or ledge.screen != current.screen:
            continue
        for left, right in ledge.centers:
            if left - 1e-6 <= center <= right + 1e-6:
                target = max(left, min(right, center + distance))
                moved = _placement(ledge, target, baseline)
                return PerchPlacement(moved.x - width / 2, moved.y, moved.floor,
                                      moved.screen, moved.attachment), target - center
    return None, 0.


class WindowObserver:
    """Observe app windows without activating, moving or changing other windows."""

    def __init__(self):
        if os.name != 'nt':
            raise OSError('WindowObserver requires Windows')
        import ctypes as C
        from ctypes import wintypes as W
        self.C, self.W = C, W
        self.user = C.WinDLL('user32', use_last_error=True)
        self.dwm = C.WinDLL('dwmapi', use_last_error=True)
        self.window_callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.monitor_callback = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC,
                                              C.POINTER(W.RECT), W.LPARAM)

        class MonitorInfo(C.Structure):
            _fields_ = [('size', W.DWORD), ('monitor', W.RECT), ('work', W.RECT),
                        ('flags', W.DWORD), ('device', W.WCHAR * 32)]

        self.MonitorInfo = MonitorInfo
        signatures = {
            'EnumWindows': ([self.window_callback, W.LPARAM], W.BOOL),
            'GetTopWindow': ([W.HWND], W.HWND),
            'GetWindow': ([W.HWND, W.UINT], W.HWND),
            'IsWindow': ([W.HWND], W.BOOL),
            'IsWindowVisible': ([W.HWND], W.BOOL),
            'IsIconic': ([W.HWND], W.BOOL),
            'GetWindowRect': ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            'GetWindowThreadProcessId': ([W.HWND, C.POINTER(W.DWORD)], W.DWORD),
            'GetClassNameW': ([W.HWND, W.LPWSTR, C.c_int], C.c_int),
            'EnumDisplayMonitors': ([W.HDC, C.POINTER(W.RECT), self.monitor_callback, W.LPARAM], W.BOOL),
            'GetMonitorInfoW': ([W.HANDLE, C.c_void_p], W.BOOL),
            'SetThreadDpiAwarenessContext': ([C.c_void_p], C.c_void_p),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.user, name)
            fn.argtypes, fn.restype = args, result
        self.get_style = getattr(self.user, 'GetWindowLongPtrW', self.user.GetWindowLongW)
        self.get_style.argtypes = [W.HWND, C.c_int]
        self.get_style.restype = C.c_ssize_t
        self.dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
        self.dwm.DwmGetWindowAttribute.restype = C.c_long
        self.pid = os.getpid()

    def snapshot(self, exclude_hwnds=()):
        C = self.C
        # DWM rects are physical. Scope monitor/fallback queries to the same
        # physical coordinate system, then restore the GUI thread's DPI context.
        previous = self.user.SetThreadDpiAwarenessContext(C.c_void_p(-4))
        if not previous:
            raise C.WinError(C.get_last_error())
        try:
            monitors = self._monitors()
            windows = self._windows(set(exclude_hwnds))
            return NativeSnapshot(monitors, tuple(windows))
        finally:
            self.user.SetThreadDpiAwarenessContext(previous)

    def _monitors(self):
        C, result, errors = self.C, {}, []

        @self.monitor_callback
        def visit(handle, hdc, rect, data):
            info = self.MonitorInfo()
            info.size = C.sizeof(info)
            if not self.user.GetMonitorInfoW(handle, C.byref(info)):
                errors.append(C.get_last_error())
                return False
            result[info.device] = Rect(info.monitor.left, info.monitor.top,
                                       info.monitor.right, info.monitor.bottom)
            return True

        if not self.user.EnumDisplayMonitors(None, None, visit, 0) or errors:
            raise C.WinError(errors[0] if errors else C.get_last_error())
        return result

    def _read_window(self, hwnd, excluded):
        C, W = self.C, self.W
        if hwnd in excluded or not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd):
            return None
        pid = W.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd, C.byref(pid)):
            raise OSError('Window disappeared while reading its process')
        if pid.value == self.pid:
            return None
        cloaked = W.DWORD()
        cloak_known = self.dwm.DwmGetWindowAttribute(hwnd, 14, C.byref(cloaked), C.sizeof(cloaked)) == 0
        if cloak_known and cloaked.value:
            return None
        name = C.create_unicode_buffer(256)
        class_known = bool(self.user.GetClassNameW(hwnd, name, len(name)))
        if name.value in ('Progman', 'WorkerW'):
            return None
        rect = W.RECT()
        if self.dwm.DwmGetWindowAttribute(hwnd, 9, C.byref(rect), C.sizeof(rect)) != 0:
            if not self.user.GetWindowRect(hwnd, C.byref(rect)):
                raise OSError('Window bounds changed during the snapshot')
        bounds = Rect(rect.left, rect.top, rect.right, rect.bottom)
        if bounds.width <= 0 or bounds.height <= 0:
            return None
        # A zero extended style is normal; only GetLastError distinguishes it
        # from failure. Unknown windows remain conservative occluders.
        C.set_last_error(0)
        style = self.get_style(hwnd, -16)
        style_known = style != 0 or C.get_last_error() == 0
        C.set_last_error(0)
        extended = self.get_style(hwnd, -20)
        style_known &= extended != 0 or C.get_last_error() == 0
        eligible = cloak_known and class_known and style_known
        eligible &= not (style & 0x40000000 or extended & (0x80 | 0x08000000))
        eligible &= not self.user.GetWindow(hwnd, 4) or bool(extended & 0x40000)
        eligible &= name.value not in ('Shell_TrayWnd', 'Shell_SecondaryTrayWnd', '#32768')
        eligible &= bounds.width >= 80 and bounds.height >= 40
        if not self.user.IsWindow(hwnd):
            raise OSError('Window was destroyed during the snapshot')
        # Tool windows/menus/taskbars can cover a ledge even though they
        # cannot serve as ledges themselves.
        return NativeWindow(hwnd, bounds, bool(eligible), pid.value)

    def _windows(self, excluded):
        C, enumerated = self.C, set()

        @self.window_callback
        def visit(hwnd, data):
            enumerated.add(hwnd)
            return True

        if not self.user.EnumWindows(visit, 0):
            raise C.WinError(C.get_last_error())
        ordered, seen = [], set()
        hwnd = self.user.GetTopWindow(None)
        # Read geometry during the explicit Z traversal. A newly created menu
        # that wasn't present during EnumWindows must still cover lower ledges.
        while hwnd and hwnd not in seen and len(seen) < 16384:
            seen.add(hwnd)
            next_window = self.user.GetWindow(hwnd, 2)
            window = self._read_window(hwnd, excluded)
            if window is not None:
                ordered.append(window)
            hwnd = next_window
        if hwnd or not enumerated.issubset(seen):
            # The caller can retain the last placement for one polling interval
            # on this transient error; no artificial empty snapshot is returned.
            raise OSError('Window Z order changed during the snapshot')
        return ordered
