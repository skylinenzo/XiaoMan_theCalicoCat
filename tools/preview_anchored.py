"""Export actual application rendering and a ground-marked foot-lock preview."""
import io
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QBuffer, QIODevice, QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from PIL import Image
from anchored_renderer import AnchoredWalk


def pil(image):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')


def main():
    app = QApplication.instance() or QApplication([])
    renderer = AnchoredWalk()
    folder = Path(__file__).resolve().parents[1] / 'output/anchored-preview'
    folder.mkdir(parents=True, exist_ok=True)
    for side in ('left', 'right'):
        cycle = renderer.cycles[side]
        count = round(cycle.duration / .02)
        frames, transparent = [], []
        for i in range(count):
            image = renderer.render(side, i / count * cycle.duration, 320)
            rgba = pil(image)
            transparent.append(rgba)
            background = Image.new('RGBA', rgba.size, '#eee9e2')
            background.alpha_composite(rgba)
            frames.append(background.convert('RGB'))
        frames[0].save(folder / f'walk-{side}.gif', save_all=True, append_images=frames[1:],
                       duration=20, loop=0, disposal=2)
        transparent[0].save(folder / f'walk-{side}.webp', save_all=True, append_images=transparent[1:],
                            duration=20, loop=0, lossless=True)
        poses = Image.new('RGB', (1280, 320), '#eee9e2')
        for i in range(4):
            poses.paste(frames[i * count // 4], (i * 320, 0))
        poses.save(folder / f'poses-{side}.png')
        moving = []
        for i in range(count * 3):
            t = i / count * cycle.duration
            frame = renderer.render(side, t, 220)
            sample = cycle.sample(t)
            x = (440 if side == 'left' else 20) + cycle.direction * sample[3] * 220 / 512
            canvas = QImage(700, 245, QImage.Format.Format_ARGB32_Premultiplied)
            canvas.fill(QColor('#eee9e2'))
            p = QPainter(canvas)
            p.setPen(QColor('#c5beb5'))
            floor = 490 * 220 / 512
            p.drawLine(QPointF(0, floor), QPointF(700, floor))
            for marker in range(0, 700, 20):
                p.drawLine(QPointF(marker, floor), QPointF(marker, floor + 6))
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(QPointF(x, 0), frame)
            p.setPen(QColor('#31885a'))
            # This marker remains fixed throughout each stance-transfer interval.
            contact = x + sample[4] * 220 / 512
            p.drawEllipse(QPointF(contact, floor + 10), 3, 3)
            p.end()
            moving.append(pil(canvas).convert('RGB'))
        moving[0].save(folder / f'foot-anchor-{side}.gif', save_all=True,
                       append_images=moving[1:], duration=20, disposal=2)
    print(folder)


if __name__ == '__main__':
    main()
