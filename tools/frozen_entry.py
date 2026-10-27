"""Release entry point, including a native frozen-bundle smoke check."""
import json
from pathlib import Path
import sys

from desktop_cat import main


def smoke_check(report):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from desktop_cat import DesktopCat

    app = QApplication([])
    cat = DesktopCat(SimpleNamespace(value=lambda key, default=None: default,
                                     setValue=lambda *args: None, sync=lambda: None))
    try:
        for timer in (cat.timer, cat.floor_timer, cat.top_timer):
            timer.stop()
        cat.hide()
        cat.tray.hide()
        checked = 0
        for frames, metadata in cat.animations.values():
            for frame in frames:
                if frame.isNull():
                    raise RuntimeError('Empty animation frame')
                checked += 1
        for style in ('frames_diagonal', 'frames_anchored', 'deform',
                      'frames_original', 'frames_aligned'):
            cat.walk_style = style
            for side in ('left', 'right'):
                for phase in (0., .25, .5, .75):
                    cat.gait_time = phase
                    cat.gait_phase = phase
                    if cat.walking_image(side, 220).isNull():
                        raise RuntimeError(f'Empty walk: {style}/{side}')
        if cat.render_frame().isNull():
            raise RuntimeError('Empty rendered pet')
        if not cat.gaze.catalog:
            raise RuntimeError('Missing eye annotations')
        app.processEvents()
        Path(report).write_text(json.dumps({
            'ok': True, 'frozen': bool(getattr(sys, 'frozen', False)),
            'animation_sets': len(cat.animations), 'frames': checked,
            'walk_styles': 5, 'eye_annotations': len(cat.gaze.catalog),
        }, indent=2), encoding='utf-8')
    finally:
        cat.close()
        cat.tray.hide()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        smoke_check(sys.argv[2])
    else:
        sys.exit(main())
