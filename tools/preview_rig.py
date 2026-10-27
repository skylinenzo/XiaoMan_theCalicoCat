"""Render the real Qt bone renderer into shareable previews (Pillow dev-only)."""
import io
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication
from PIL import Image
from rig_renderer import CatRig


def main():
    app = QApplication.instance() or QApplication([])
    rig = CatRig()
    output = Path(__file__).resolve().parents[1] / 'output/rig-preview'
    output.mkdir(parents=True, exist_ok=True)
    for side in ('left', 'right'):
        transparent, preview = [], []
        for frame in range(38):
            image = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            rig.draw(painter, side, frame / 38, 320)
            painter.end()
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, 'PNG')
            pil = Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')
            transparent.append(pil)
            background = Image.new('RGBA', pil.size, '#eee9e2')
            background.alpha_composite(pil)
            preview.append(background.convert('RGB'))
        transparent[0].save(output / f'walk-{side}.webp', save_all=True,
                             append_images=transparent[1:], duration=20, loop=0, lossless=True)
        preview[0].save(output / f'walk-{side}.gif', save_all=True,
                       append_images=preview[1:], duration=20, loop=0, disposal=2)
        preview[0].save(output / f'walk-{side}-still.png')
    print(output)


if __name__ == '__main__':
    main()
