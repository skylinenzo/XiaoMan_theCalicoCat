"""Extract the six disconnected generated rig components. Requires Pillow.

Connected-component packing preserves original artwork and transparency while
preventing neighbouring atlas parts from entering overlapping bounding boxes.
"""
from collections import deque
from pathlib import Path
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / 'assets/rig'
NAMES = ['body', 'front_upper', 'front_lower', 'hind_upper', 'hind_lower', 'tail']


def main():
    for side in ('left', 'right'):
        folder = ROOT / side
        image = Image.open(folder / 'atlas.png').convert('RGBA')
        width, height = image.size
        alpha = image.getchannel('A')
        occupied = bytearray(1 if a > 32 else 0 for a in alpha.tobytes())
        components = []
        for origin in range(width * height):
            if not occupied[origin]:
                continue
            occupied[origin] = 0
            queue, pixels = deque([origin]), []
            while queue:
                p = queue.popleft()
                pixels.append(p)
                x, y = p % width, p // width
                for q in (p - 1 if x else -1, p + 1 if x + 1 < width else -1,
                          p - width if y else -1, p + width if y + 1 < height else -1):
                    if q >= 0 and occupied[q]:
                        occupied[q] = 0
                        queue.append(q)
            if len(pixels) > 10000:
                components.append(pixels)
        assert len(components) == 6, (side, len(components))
        # Atlas uses a larger torso, so identify the two rows by each part's top.
        def bounds(pixels):
            xs, ys = [p % width for p in pixels], [p // width for p in pixels]
            return min(xs), min(ys), max(xs) + 1, max(ys) + 1
        components.sort(key=lambda p: bounds(p)[1])
        components = (sorted(components[:3], key=lambda p: bounds(p)[0])
                      + sorted(components[3:], key=lambda p: bounds(p)[0]))
        for name, pixels in zip(NAMES, components):
            mask_data = bytearray(width * height)
            for p in pixels:
                mask_data[p] = 255
            mask = Image.frombytes('L', image.size, bytes(mask_data)).filter(ImageFilter.MaxFilter(9))
            from PIL import ImageChops
            part = image.copy()
            part.putalpha(ImageChops.darker(alpha, mask))
            box = mask.getbbox()
            part.crop(box).save(folder / f'{name}.png')
            print(side, name, box)


if __name__ == '__main__':
    main()
