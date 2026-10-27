"""Pack a complete two-half-step imagegen cycle without changing approved poses.

Generated drawings are only scaled/registered. No mesh warp, synthesized limbs,
crossfade or reversed half-cycle is used. Pillow is a development dependency.
"""
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageSequence
from package_walk_v2 import on_gray, score

ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / 'output/imagegen/walk-diagonal-four-v1'
OUTPUT = ROOT / 'output/imagegen/walk-diagonal-cycle-v2'
STAGES = [(2, 'a-early'), (3, 'a-middle'), (4, 'a-late'),
          (6, 'b-early'), (7, 'b-middle'), (8, 'b-late')]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reference = Image.open(APPROVED / 'frame-01.png').convert('RGBA')
    reference_gray = on_gray(reference)
    registrations = {}
    for index, stage in STAGES:
        original = Image.open(OUTPUT / f'source-{stage}.png').convert('RGBA')
        candidates = []
        for step in range(31):
            scale = .95 + step / 300
            extent = round(512 * scale)
            resized = original.resize((extent, extent), Image.Resampling.LANCZOS)
            bounds = resized.getchannel('A').point(lambda a: 255 if a > 100 else 0).getbbox()
            y = 490 - bounds[3]
            canvas = Image.new('RGBA', (512, 512))
            canvas.alpha_composite(resized, (0, y))
            gray = on_gray(canvas)
            error, dx = min((score(reference_gray, gray, (340, 170, 478, 320), x, 0), x)
                            for x in range(-24, 25))
            candidates.append((error, scale, dx, y, resized))
        error, scale, dx, y, resized = min(candidates, key=lambda candidate: candidate[0])
        result = Image.new('RGBA', (512, 512))
        result.alpha_composite(resized, (dx, y))
        result.save(OUTPUT / f'frame-{index:02}.png')
        registrations[stage] = {'scale_relative_to_512': scale, 'offset': [dx, y],
                                'head_error': error}
    for source, target in [(1, 1), (2, 5)]:
        shutil.copy2(APPROVED / f'frame-{source:02}.png', OUTPUT / f'frame-{target:02}.png')
    frames = [Image.open(OUTPUT / f'frame-{i:02}.png').convert('RGBA') for i in range(1, 9)]
    sheet = Image.new('RGBA', (2048, 1024))
    contact = Image.new('RGB', (1280, 680), '#eee9e2')
    previews = []
    labels = ['A / contact', 'A / toe-off', 'A / passing', 'A / landing',
              'B / contact', 'B / toe-off', 'B / passing', 'B / landing']
    for i, frame in enumerate(frames):
        sheet.alpha_composite(frame, (i % 4 * 512, i // 4 * 512))
        bg = Image.new('RGBA', frame.size, '#eee9e2')
        bg.alpha_composite(frame)
        preview = bg.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS)
        previews.append(preview)
        contact.paste(preview, (i % 4 * 320, i // 4 * 340 + 20))
    draw = ImageDraw.Draw(contact)
    for i, label in enumerate(labels):
        draw.text((i % 4 * 320 + 12, i // 4 * 340 + 5), f'{i + 1}: {label}', fill='#493b31')
    sheet.save(OUTPUT / 'aligned-sheet.png')
    contact.save(OUTPUT / 'contact-sheet.png')
    # A shared palette keeps unchanged colors stable across GIF frames.
    palette = contact.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in previews]
    indexed[0].save(OUTPUT / 'cycle-2fps.gif', save_all=True, append_images=indexed[1:],
                    duration=500, loop=0, disposal=2, optimize=False)
    frames[0].save(OUTPUT / 'cycle-2fps.webp', save_all=True, append_images=frames[1:],
                   duration=500, loop=0, lossless=True)
    metadata = {'frames': [f'frame-{i:02}.png' for i in range(1, 9)],
                'playback_order_zero_based': list(range(8)), 'duration_ms': [500] * 8,
                'fps': 2, 'loop': True, 'frame_size': [512, 512], 'labels': labels,
                'registration': registrations,
                'notes': 'Two separately drawn diagonal half-steps. Approved A and B untouched. No reverse playback, crossfade, or app changes.'}
    (OUTPUT / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
    with Image.open(OUTPUT / 'cycle-2fps.gif') as gif:
        assert gif.n_frames == 8 and gif.info.get('loop') == 0
        assert all(frame.info['duration'] == 500 for frame in ImageSequence.Iterator(gif))
    for source, target in [(1, 1), (2, 5)]:
        assert (APPROVED / f'frame-{source:02}.png').read_bytes() == (OUTPUT / f'frame-{target:02}.png').read_bytes()
    print(json.dumps(registrations, indent=2))
    print('Verified 8 frames, infinite loop at 2 fps, and byte-identical approved A/B endpoints.')


if __name__ == '__main__':
    main()
