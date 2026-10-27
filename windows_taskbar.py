"""Read-only Win32 taskbar observation. Coordinates here are physical pixels."""
import ctypes as C
from ctypes import wintypes as W


class MonitorInfo(C.Structure):
    _fields_ = [('size', W.DWORD), ('monitor', W.RECT), ('work', W.RECT),
                ('flags', W.DWORD)]


class MonitorInfoEx(C.Structure):
    _fields_ = MonitorInfo._fields_ + [('device', W.WCHAR * 32)]


class AppBarData(C.Structure):
    _fields_ = [('size', W.DWORD), ('hwnd', W.HWND), ('callback', W.UINT),
                ('edge', W.UINT), ('rect', W.RECT), ('param', W.LPARAM)]


def rect_tuple(rect):
    return rect.left, rect.top, rect.right, rect.bottom


class TaskbarObserver:
    def __init__(self):
        self.user = C.WinDLL('user32', use_last_error=True)
        self.shell = C.WinDLL('shell32', use_last_error=True)
        self.callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.monitor_callback = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
        signatures = {
            'MonitorFromWindow': ([W.HWND, W.DWORD], W.HANDLE),
            'GetMonitorInfoW': ([W.HANDLE, C.c_void_p], W.BOOL),
            'EnumDisplayMonitors': ([W.HDC, C.POINTER(W.RECT), self.monitor_callback, W.LPARAM], W.BOOL),
            'GetWindowRect': ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            'GetClassNameW': ([W.HWND, W.LPWSTR, C.c_int], C.c_int),
            'IsWindowVisible': ([W.HWND], W.BOOL),
            'EnumWindows': ([self.callback_type, W.LPARAM], W.BOOL),
            'SetWindowPos': ([W.HWND, W.HWND, C.c_int, C.c_int,
                              C.c_int, C.c_int, W.UINT], W.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.user, name)
            fn.argtypes, fn.restype = args, result
        self.shell.SHAppBarMessage.argtypes = [W.DWORD, C.POINTER(AppBarData)]
        self.shell.SHAppBarMessage.restype = C.c_size_t

    def snapshot(self, hwnd):
        monitor = self.user.MonitorFromWindow(hwnd, 2)
        return self._snapshot_monitor(monitor, self._taskbars())

    def snapshots(self):
        """Physical monitor/taskbar state keyed by native display device name."""
        result, errors, bars = {}, [], self._taskbars()

        @self.monitor_callback
        def visit(monitor, hdc, rect, data):
            info = MonitorInfoEx()
            info.size = C.sizeof(info)
            if not self.user.GetMonitorInfoW(monitor, C.byref(info)):
                errors.append(C.get_last_error())
                return False
            try:
                result[info.device] = self._snapshot_monitor(monitor, bars)
            except OSError as error:
                errors.append(error.winerror)
                return False
            return True

        if not self.user.EnumDisplayMonitors(None, None, visit, 0) or errors:
            raise C.WinError(errors[0] if errors else C.get_last_error())
        return result

    def _snapshot_monitor(self, monitor, bars):
        info = MonitorInfo()
        info.size = C.sizeof(info)
        if not self.user.GetMonitorInfoW(monitor, C.byref(info)):
            raise C.WinError(C.get_last_error())
        data = AppBarData()
        data.size = C.sizeof(data)
        data.edge = 3  # ABE_BOTTOM
        data.rect = info.monitor
        auto_hide = bool(self.shell.SHAppBarMessage(11, C.byref(data)))
        return rect_tuple(info.monitor), rect_tuple(info.work), bars, auto_hide

    def _taskbars(self):
        bars = []

        @self.callback_type
        def visit(window, _):
            name = C.create_unicode_buffer(128)
            self.user.GetClassNameW(window, name, 128)
            if name.value in ('Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
                rect = W.RECT()
                if (self.user.IsWindowVisible(window)
                        and self.user.GetWindowRect(window, C.byref(rect))):
                    bars.append(rect_tuple(rect))
            return True

        self.user.EnumWindows(visit, 0)
        return bars

    def keep_topmost(self, hwnd):
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        self.user.SetWindowPos(hwnd, W.HWND(-1), 0, 0, 0, 0, 0x13)
