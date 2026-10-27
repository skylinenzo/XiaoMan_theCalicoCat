"""Register generated resting drawings and export exact-return idle loops.

Only sprite packing, uniform scale, alignment and timing; no painted poses.
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageSequence
from package_walk_v2 import on_gray, register

ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen/rest-idles-v1'
ORDER = [0, 1, 2, 3, 2, 1, 0]
DURATIONS = [1000, 600, 100, 140, 100, 600, 660]


def main():
    overview = Image.new('RGB', (1280, 1020), '#eee9e2')
    for row, name in enumerate(('prone', 'supine', 'side')):
        folder = ROOT / name
        sheet = Image.open(folder / 'source-sheet.png').convert('RGBA')
        size = sheet.width // 2
        assert sheet.size == (size * 2, size * 2)
        cells = [sheet.crop((i % 2 * size, i // 2 * size,
                             (i % 2 + 1) * size, (i // 2 + 1) * size)) for i in range(4)]
        box = tuple(round(v * size / 640) for v in (360, 180, 635, 595))
        reference = on_gray(cells[0])
        offsets = [(0, 0, 0, 0)] + [register(reference, on_gray(cell), box) for cell in cells[1:]]
        bounds = [cell.getchannel('A').point(lambda a: 255 if a > 100 else 0).getbbox() for cell in cells]
        union = (min(b[0] + d[0] for b, d in zip(bounds, offsets)),
                 min(b[1] + d[1] for b, d in zip(bounds, offsets)),
                 max(b[2] + d[0] for b, d in zip(bounds, offsets)),
                 max(b[3] + d[1] for b, d in zip(bounds, offsets)))
        scale = 430 / (union[2] - union[0])
        origin_x = 256 - (union[0] + union[2]) / 2 * scale
        origin_y = 490 - union[3] * scale
        frames, previews = [], []
        aligned = Image.new('RGBA', (1024, 1024))
        for i, (cell, (dx, dy, _, _)) in enumerate(zip(cells, offsets)):
            frame = Image.new('RGBA', (512, 512))
            resized = cell.resize((round(size * scale), round(size * scale)), Image.Resampling.LANCZOS)
            frame.alpha_composite(resized, (round(origin_x + dx * scale), round(origin_y + dy * scale)))
            frame.save(folder / f'frame-{i + 1:02}.png')
            frames.append(frame)
            aligned.alpha_composite(frame, (i % 2 * 512, i // 2 * 512))
            bg = Image.new('RGBA', frame.size, '#eee9e2')
            bg.alpha_composite(frame)
            previews.append(bg.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS))
            overview.paste(previews[-1], (i * 320, row * 340 + 20))
            ImageDraw.Draw(overview).text((i * 320 + 10, row * 340 + 5), f'{name} / {i + 1}', fill='#493b31')
        aligned.save(folder / 'aligned-sheet.png')
        palette_sheet = Image.new('RGB', (1280, 320))
        for i, preview in enumerate(previews):
            palette_sheet.paste(preview, (i * 320, 0))
        palette = palette_sheet.quantize(colors=256)
        indexed = [previews[i].quantize(palette=palette, dither=Image.Dither.NONE) for i in ORDER]
        indexed[0].save(folder / 'preview.gif', save_all=True, append_images=indexed[1:],
                        duration=DURATIONS, loop=0, disposal=2, optimize=False)
        playback = [frames[i] for i in ORDER]
        playback[0].save(folder / 'animation.webp', save_all=True, append_images=playback[1:],
                         duration=DURATIONS, loop=0, lossless=True)
        metadata = dict(frame_size=[512, 512], foot_baseline_y=490, ready_for_app=True,
                        frames=[f'frame-{i:02}.png' for i in range(1, 5)],
                        playback_order_zero_based=ORDER, duration_ms=DURATIONS,
                        loop=True, mirrored=False, registration=offsets, scale=scale,
                        source='source-sheet.png', prompt='prompt.txt',
                        notes='Same start/end image, shared palette, head registration; no opacity dissolve.')
        (folder / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
        with Image.open(folder / 'preview.gif') as gif:
            assert gif.info['loop'] == 0
            assert sum(f.info['duration'] for f in ImageSequence.Iterator(gif)) == sum(DURATIONS)
            gif.seek(0)
            first = gif.convert('RGB').tobytes()
            gif.seek(gif.n_frames - 1)
            assert gif.convert('RGB').tobytes() == first
        assert frames[0].getchannel('A').getextrema() == (0, 255)
        print(name, 'scale', scale, 'offsets', offsets, '3200 ms loop verified')
    overview.save(ROOT / 'contact-sheet.png')


if __name__ == '__main__':
    main()
