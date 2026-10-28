"""Exercise repeated real Qt screen changes; optional QT_SCREEN_SCALE_FACTORS.

This only moves its own test pet. It does not change Windows display settings.
"""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from desktop_cat import DesktopCat


def main():
    if len(sys.argv) > 1:
        os.environ['QT_SCREEN_SCALE_FACTORS'] = sys.argv[1]
    app = QApplication([])
    cat = DesktopCat(SimpleNamespace(value=lambda k, d=None: d,
                                     setValue=lambda *args: None, sync=lambda: None))
    for timer in (cat.timer, cat.floor_timer, cat.top_timer):
        timer.stop()
    cat.tray.hide()
    samples = []
    try:
        for _ in range(4):
            for screen in app.screens():
                center = screen.geometry().center()
                cat.move(center.x() - 110, center.y() - 110)
                QTest.qWait(120)
                samples.append({'screen': cat.screen().name(),
                                'dpr': cat.devicePixelRatioF(),
                                'width': cat.width(), 'height': cat.height()})
        print(json.dumps(samples), flush=True)
        assert all(s['width'] == 220 and s['height'] == 220 for s in samples), samples
        print('PASS repeated native screen changes retain logical size', flush=True)
    finally:
        cat.close()
        cat.tray.hide()


if __name__ == '__main__':
    main()
