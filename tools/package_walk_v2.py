"""Register generated walk key poses on the head and package a cyclic preview.

Only placement, scaling and animation timing are changed; no coat or limbs are
painted here. The two source sheets were generated independently with image_gen.
Run with Python + Pillow. Retains all v1 artifacts for comparison.
"""
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen'


def on_gray(image):
    canvas = Image.new('RGBA', image.size, '#807e7b')
    canvas.alpha_composite(image)
    return canvas.convert('RGB')


def score(reference, candidate, box, dx, dy):
    shifted_box = (box[0] - dx, box[1] - dy, box[2] - dx, box[3] - dy)
    delta = ImageChops.difference(reference.crop(box), candidate.crop(shifted_box))
    return sum(ImageStat.Stat(delta).mean)


def register(reference, candidate, box):
    # Coarse search, then pixel-level refinement. Exclude every moving paw/tail.
    small_ref = reference.resize((160, 160), Image.Resampling.LANCZOS)
    small_target = candidate.resize((160, 160), Image.Resampling.LANCZOS)
    ratio = reference.width / 160
    small_box = tuple(round(value / ratio) for value in box)
    _, sx, sy = min((score(small_ref, small_target, small_box, dx, dy), dx, dy)
                    for dx in range(-16, 17) for dy in range(-24, 25))
    cx, cy = round(sx * ratio), round(sy * ratio)
    error, dx, dy = min((score(reference, candidate, box, x, y), x, y)
                        for x in range(cx - 4, cx + 5) for y in range(cy - 4, cy + 5))
    return dx, dy, score(reference, candidate, box, 0, 0), error


def main():
    for direction in ('left', 'right'):
        output = ROOT / f'walk-{direction}-v2'
        sheet = Image.open(output / 'source-sheet.png').convert('RGBA')
        size = sheet.width // 2
        assert sheet.size == (size * 2, size * 2)
        cells = [sheet.crop(((i % 2) * size, (i // 2) * size,
                             (i % 2 + 1) * size, (i // 2 + 1) * size)) for i in range(4)]
        # Consistent template regions enclosing face/ears, excluding limbs.
        fractions = (.06, .18, .39, .51) if direction == 'left' else (.61, .14, .96, .48)
        head_box = tuple(round(value * size) for value in fractions)
        ref = on_gray(cells[0])
        registrations = [(0, 0, 0., 0.)] + [register(ref, on_gray(cell), head_box) for cell in cells[1:]]
        boxes = []
        for cell, (dx, dy, _, _) in zip(cells, registrations):
            bounds = cell.getchannel('A').point(lambda a: 255 if a > 100 else 0).getbbox()
            boxes.append((bounds[0] + dx, bounds[1] + dy, bounds[2] + dx, bounds[3] + dy))
        # ONE union scale and offset for all poses. Never center by individual paws/tails.
        union = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                 max(b[2] for b in boxes), max(b[3] for b in boxes))
        scale = min(440 / (union[2] - union[0]), 360 / (union[3] - union[1]))
        origin_x = 256 - (union[0] + union[2]) / 2 * scale
        origin_y = 490 - union[3] * scale
        frames = []
        for index, (cell, (dx, dy, _, _)) in enumerate(zip(cells, registrations)):
            result = Image.new('RGBA', (512, 512))
            resized = cell.resize((round(size * scale), round(size * scale)), Image.Resampling.LANCZOS)
            result.alpha_composite(resized, (round(origin_x + dx * scale), round(origin_y + dy * scale)))
            result.save(output / f'frame-{index + 1:02}.png')
            frames.append(result)
        aligned_sheet = Image.new('RGBA', (1024, 1024))
        for index, frame in enumerate(frames):
            aligned_sheet.alpha_composite(frame, ((index % 2) * 512, (index // 2) * 512))
        aligned_sheet.save(output / 'aligned-sheet.png')
        # Matches app rendering: 180ms hold, then a 60ms premultiplied transition.
        animation, durations = [], []
        for index, frame in enumerate(frames):
            animation.append(frame)
            durations.append(180)
            for amount in (0., 1/3, 2/3):
                amount = amount * amount * (3 - 2 * amount)
                mixed = Image.blend(frame.convert('RGBa'), frames[(index + 1) % 4].convert('RGBa'), amount)
                animation.append(mixed.convert('RGBA'))
                durations.append(20)
        animation[0].save(output / 'animation.webp', save_all=True, append_images=animation[1:],
                          duration=durations, loop=0, lossless=True)
        previews = []
        for frame in animation:
            bg = Image.new('RGBA', frame.size, '#eee9e2')
            bg.alpha_composite(frame)
            previews.append(bg.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS))
        previews[0].save(output / 'preview.gif', save_all=True, append_images=previews[1:],
                         duration=durations, loop=0, disposal=2)
        metadata = {'frame_size': [512, 512], 'foot_baseline_y': 490,
                    'frames': [f'frame-{i + 1:02}.png' for i in range(4)],
                    'playback_order_zero_based': [0, 1, 2, 3], 'duration_ms': [240] * 4,
                    'transition_ms': 60, 'stride_pixels': 110, 'loop': True, 'mirrored': False,
                    'registration': {'region': list(head_box), 'scale': scale,
                                     'offsets_and_errors_before_after': registrations},
                    'status': 'four distinct stance/recovery poses; head-registered; cyclic short transitions'}
        (output / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(direction, 'head alignment (dx, dy, error before, after):', registrations)
        print('Ground positions after registration:', [round(origin_y + b[3] * scale) for b in boxes])


if __name__ == '__main__':
    main()
