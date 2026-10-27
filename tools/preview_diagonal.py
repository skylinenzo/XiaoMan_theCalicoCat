"""Export the same gait and two-pose sit/stand transitions used by the app."""
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from PIL import Image
from anchored_renderer import AnchoredWalk
from pose_transition import PoseTransition
from desktop_cat import WALK_SPEED_MULTIPLIER
from preview_anchored import pil


def main():
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1] / 'output'
    folder = root / 'diagonal-preview'
    folder.mkdir(exist_ok=True)
    art = root / 'imagegen'
    renderer = AnchoredWalk({'left': 'walk-diagonal-left-v1', 'right': 'walk-diagonal-right-v1'})
    idle = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
    idle.fill(Qt.GlobalColor.transparent)
    meta = json.loads((art / 'turn-sit-v1/animation.json').read_text())
    scale = meta['idle_scale']
    painter = QPainter(idle)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRectF(256 * (1 - scale), 490 * (1 - scale), 512 * scale, 512 * scale),
                      QImage(str(art / 'idle-v3/frame-01.png')))
    painter.end()
    for side in ('left', 'right'):
        cycle = renderer.cycles[side]
        frames = [renderer.render(side, i * .05 * WALK_SPEED_MULTIPLIER, 512)
                  for i in range(round(cycle.duration / WALK_SPEED_MULTIPLIER / .05))]
        turns = [QImage(str(art / 'turn-sit-v1' / name)).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                 for name in meta[side]]
        walking = renderer.render(side, cycle.duration, 512)
        sit = PoseTransition([walking, *turns, idle], meta['segment_duration_ms'] / 1000)
        while sit.elapsed < sit.duration:
            frames.append(sit.image())
            sit.advance(.05)
        frames.extend([idle] * 16)
        stand = PoseTransition([idle, *reversed(turns), walking], meta['segment_duration_ms'] / 1000)
        while stand.elapsed < stand.duration:
            frames.append(stand.image())
            stand.advance(.05)
        previews = []
        for image in frames:
            rgba = pil(image)
            bg = Image.new('RGBA', rgba.size, '#eee9e2')
            bg.alpha_composite(rgba)
            previews.append(bg.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS))
        palette_sheet = Image.new('RGB', (320 * 4, 320 * 4))
        for i in range(16):
            palette_sheet.paste(previews[i * len(previews) // 16], (i % 4 * 320, i // 4 * 320))
        palette = palette_sheet.quantize(colors=256)
        indexed = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in previews]
        indexed[0].save(folder / f'walk-sit-{side}.gif', save_all=True, append_images=indexed[1:],
                        duration=50, loop=0, disposal=2, optimize=False)
        palette_sheet.save(folder / f'walk-sit-{side}-contact.png')
    print(folder)


if __name__ == '__main__':
    main()
