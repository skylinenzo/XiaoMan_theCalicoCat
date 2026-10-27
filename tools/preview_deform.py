"""Export the application's actual continuous mesh renderer (Pillow dev-only)."""
import io
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication
from PIL import Image
from deform_renderer import DeformCat, STRIDE


def main():
    app = QApplication.instance() or QApplication([])
    cat = DeformCat()
    output = Path(__file__).resolve().parents[1] / 'output/deform-preview'
    output.mkdir(parents=True, exist_ok=True)
    count = round(STRIDE / 120 / .02)  # Match the application's travel speed.
    for side in ('left', 'right'):
        transparent, preview = [], []
        for frame in range(count):
            image = cat.render(side, frame / count, 320)
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
        contact = Image.new('RGB', (320 * 4, 320), '#eee9e2')
        for i in range(4):
            contact.paste(preview[i * count // 4], (i * 320, 0))
        contact.save(output / f'walk-{side}-poses.png')
    print(output)


if __name__ == '__main__':
    main()
