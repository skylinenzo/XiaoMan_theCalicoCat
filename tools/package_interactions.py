"""Register generated pickup/perch drawings without painting or deforming them.

Splits the original transparent sheets, applies one uniform scale per animation,
and aligns the head before exporting exact-return blink loops and app metadata.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence

from package_walk_v2 import on_gray, score


ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen/interactions-v1'
ORDER = [0, 1, 2, 3, 2, 1, 0]
DURATIONS = [1000, 600, 100, 140, 100, 600, 660]


def register_head(reference, candidate, box):
    """Handle unequal generated sheet gutters, including a 76px held offset."""
    small_ref = reference.resize((160, 160), Image.Resampling.LANCZOS)
    small_candidate = candidate.resize((160, 160), Image.Resampling.LANCZOS)
    ratio = reference.width / 160
    small_box = tuple(round(value / ratio) for value in box)
    _, sx, sy = min((score(small_ref, small_candidate, small_box, dx, dy), dx, dy)
                    for dx in range(-28, 29) for dy in range(-20, 21))
    cx, cy = round(sx * ratio), round(sy * ratio)
    error, dx, dy = min((score(reference, candidate, box, x, y), x, y)
                        for x in range(cx - 4, cx + 5) for y in range(cy - 4, cy + 5))
    return dx, dy, score(reference, candidate, box, 0, 0), error


def alpha_bounds(frame):
    return frame.getchannel('A').point(lambda alpha: 255 if alpha > 100 else 0).getbbox()


def main():
    overview = Image.new('RGB', (1280, 680), '#eee9e2')
    first_frames = []
    for row, name in enumerate(('held', 'perch')):
        folder = ROOT / name
        source = Image.open(folder / 'source-sheet.png').convert('RGBA')
        size = source.width // 2
        assert source.size == (size * 2, size * 2)
        cells = [source.crop((i % 2 * size, i // 2 * size,
                              (i % 2 + 1) * size, (i // 2 + 1) * size)) for i in range(4)]
        # Register the static ears/forehead, excluding the changing eyelids.
        box = (255, 25, 500, 140) if name == 'held' else (360, 205, 610, 330)
        box = tuple(round(value * size / 627) for value in box)
        reference = on_gray(cells[0])
        offsets = [(0, 0, 0., 0.)] + [register_head(reference, on_gray(cell), box)
                                       for cell in cells[1:]]
        bounds = [alpha_bounds(cell) for cell in cells]
        union = (min(b[0] + d[0] for b, d in zip(bounds, offsets)),
                 min(b[1] + d[1] for b, d in zip(bounds, offsets)),
                 max(b[2] + d[0] for b, d in zip(bounds, offsets)),
                 max(b[3] + d[1] for b, d in zip(bounds, offsets)))
        if name == 'held':
            scale = 165 / (235 * size / 627)
            origin_x = 256 - 377 * size / 627 * scale
            bottom = 480
        else:
            scale = 430 / (union[2] - union[0])
            origin_x = 256 - (union[0] + union[2]) / 2 * scale
            bottom = 490
        origin_y = bottom - union[3] * scale
        frames, previews = [], []
        aligned = Image.new('RGBA', (1024, 1024))
        for index, (cell, (dx, dy, _, _)) in enumerate(zip(cells, offsets)):
            frame = Image.new('RGBA', (512, 512))
            scaled = cell.resize((round(size * scale), round(size * scale)), Image.Resampling.LANCZOS)
            frame.alpha_composite(scaled, (round(origin_x + dx * scale), round(origin_y + dy * scale)))
            frame.save(folder / f'frame-{index + 1:02}.png')
            assert frame.getchannel('A').getextrema() == (0, 255)
            b = alpha_bounds(frame)
            assert 8 < b[0] < b[2] < 504 and 8 < b[1] < b[3] <= 491, (name, index, b)
            frames.append(frame)
            aligned.alpha_composite(frame, (index % 2 * 512, index // 2 * 512))
            background = Image.new('RGBA', frame.size, '#eee9e2')
            background.alpha_composite(frame)
            previews.append(background.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS))
            overview.paste(previews[-1], (index * 320, row * 340 + 20))
            ImageDraw.Draw(overview).text((index * 320 + 10, row * 340 + 5),
                                          f'{name} / {index + 1}', fill='#493b31')
        first_frames.append(frames[0])
        aligned.save(folder / 'aligned-sheet.png')
        palette_sheet = Image.new('RGB', (1280, 320))
        for index, preview in enumerate(previews):
            palette_sheet.paste(preview, (index * 320, 0))
        palette = palette_sheet.quantize(colors=256)
        indexed = [previews[index].quantize(palette=palette, dither=Image.Dither.NONE) for index in ORDER]
        indexed[0].save(folder / 'preview.gif', save_all=True, append_images=indexed[1:],
                        duration=DURATIONS, loop=0, disposal=2, optimize=False)
        playback = [frames[index] for index in ORDER]
        playback[0].save(folder / 'animation.webp', save_all=True, append_images=playback[1:],
                         duration=DURATIONS, loop=0, lossless=True)
        metadata = dict(frame_size=[512, 512], foot_baseline_y=bottom,
                        contact_baseline_y=477 if name == 'perch' else None,
                        pivot_px=[256, 270] if name == 'held' else None,
                        ready_for_app=True, frames=[f'frame-{i:02}.png' for i in range(1, 5)],
                        playback_order_zero_based=ORDER, duration_ms=DURATIONS,
                        loop=True, mirrored=False,
                        registration=dict(region=list(box), offsets_and_errors_before_after=offsets),
                        scale=scale, origin=[origin_x, origin_y],
                        source='source-sheet.png', prompt='prompt.txt',
                        notes='Original transparent drawings; shared uniform scale; ears/forehead registration; '
                              'same first/last pose; shared GIF palette; no opacity dissolve or painted edits.')
        (folder / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
        with Image.open(folder / 'preview.gif') as gif:
            assert gif.info['loop'] == 0
            assert sum(frame.info['duration'] for frame in ImageSequence.Iterator(gif)) == 3200
            gif.seek(0)
            first = gif.convert('RGB').tobytes()
            gif.seek(gif.n_frames - 1)
            assert gif.convert('RGB').tobytes() == first
        with Image.open(folder / 'animation.webp') as webp:
            assert webp.info['loop'] == 0
            first = webp.convert('RGBA').tobytes()
            webp.seek(webp.n_frames - 1)
            assert webp.convert('RGBA').tobytes() == first
        print(name, 'scale', scale, 'offsets', offsets,
              'frame bounds', [alpha_bounds(frame) for frame in frames], '3200 ms loop verified')
    overview.save(ROOT / 'contact-sheet.png')
    reference = Image.open(ROOT.parent / 'turn-sit-v1/idle-size-reference.png').convert('RGBA')
    comparison = Image.new('RGBA', (1536, 512), '#eee9e2')
    for index, (label, frame) in enumerate(zip(('seated reference', 'held', 'window perch'),
                                             (reference, *first_frames))):
        comparison.alpha_composite(frame, (index * 512, 0))
        ImageDraw.Draw(comparison).text((index * 512 + 12, 10), label, fill='#493b31')
    comparison.convert('RGB').save(ROOT / 'size-comparison.png')


if __name__ == '__main__':
    main()
