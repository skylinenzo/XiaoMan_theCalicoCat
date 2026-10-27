"""Moving previews at the actual app speed, with a ground-contact ruler."""
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from PIL import Image
from anchored_renderer import AnchoredWalk
from desktop_cat import WALK_SPEED_MULTIPLIER
from preview_anchored import pil


def main():
    app = QApplication.instance() or QApplication([])
    folder = Path(__file__).resolve().parents[1] / 'output/steady-walk-preview'
    folder.mkdir(exist_ok=True)
    walker = AnchoredWalk({'left': 'walk-diagonal-left-v1', 'right': 'walk-diagonal-right-v1'})
    started, renders = time.perf_counter(), 0
    for side in ('left', 'right'):
        cycle = walker.cycles[side]
        frames = []
        for i in range(round(cycle.duration * 2 / WALK_SPEED_MULTIPLIER / .04)):
            seconds = i * .04 * WALK_SPEED_MULTIPLIER
            sample = cycle.sample(seconds)
            x = (450 if side == 'left' else 30) + cycle.direction * sample[3] * 220 / 512
            cat = walker.render(side, seconds, 220)
            canvas = QImage(740, 245, QImage.Format.Format_ARGB32_Premultiplied)
            canvas.fill(QColor('#eee9e2'))
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            floor = 490 * 220 / 512
            painter.setPen(QColor('#b8b0a5'))
            painter.drawLine(QPointF(0, floor), QPointF(740, floor))
            for marker in range(0, 740, 20):
                painter.drawLine(QPointF(marker, floor), QPointF(marker, floor + 6))
            painter.drawImage(QPointF(x, 0), cat)
            painter.setPen(QColor('#31885a'))
            painter.setBrush(QColor('#31885a'))
            painter.drawEllipse(QPointF(x + sample[4] * 220 / 512, floor + 12), 3, 3)
            painter.end()
            frames.append(pil(canvas).convert('RGB'))
            renders += 1
        palette = frames[0].quantize(colors=256)
        indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
        indexed[0].save(folder / f'walk-{side}.gif', save_all=True, append_images=indexed[1:],
                        duration=40, loop=0, disposal=2, optimize=False)
        frames[len(frames)//3].save(folder / f'walk-{side}.png')
    print(f'{folder}: {renders} frames, total export {time.perf_counter() - started:.2f}s')


if __name__ == '__main__':
    main()
