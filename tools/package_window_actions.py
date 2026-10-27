"""Pack authored straddle/blink and jump drawings, preserving source artwork."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
from package_interactions import register_head, alpha_bounds
from package_walk_v2 import on_gray

ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen/window-actions-v1'


def main():
    overview = Image.new('RGB', (1280, 680), '#eee9e2')
    for row, name in enumerate(('straddle', 'jump')):
        folder = ROOT / name
        sheet = Image.open(folder / 'source-sheet.png').convert('RGBA')
        half = sheet.width // 2
        # The airborne paws extend below the nominal middle of the jump sheet.
        # Its actual empty row is 680; crop authored poses there, not through paws.
        split = half if name == 'straddle' else 680
        boxes = [(0, 0, half, split), (half, 0, half * 2, split),
                 (0, split, half, sheet.height), (half, split, half * 2, sheet.height)]
        cells = [sheet.crop(box) for box in boxes]
        if name == 'jump':
            # The adjacent crouch's whiskers cross the nominal center gutter.
            # Extract this sprite from two rectangles, keeping its tail above
            # that gutter but excluding the neighboring sprite below it.
            cell = cells[1]
            isolated = Image.new('RGBA', cell.size)
            isolated.paste(cell.crop((0, 0, cell.width, 260)), (0, 0))
            isolated.paste(cell.crop((32, 260, cell.width, cell.height)), (32, 260))
            cells[1] = isolated
        offsets = [(0, 0, 0., 0.)] * 4
        if name == 'straddle':
            reference = on_gray(cells[0])
            offsets = [offsets[0]] + [register_head(reference, on_gray(cell), (375, 75, 600, 175))
                                       for cell in cells[1:]]
            scale = 430 / (alpha_bounds(cells[0])[2] - alpha_bounds(cells[0])[0])
            origin_x = 256 - sum(alpha_bounds(cells[0])[::2]) / 2 * scale
            origin_y = 340 - 377 * scale
        else:
            scale = .76
        frames, previews = [], []
        for i, (cell, offset) in enumerate(zip(cells, offsets)):
            if name == 'jump':
                box = alpha_bounds(cell)
                origin_x = 256 - (box[0] + box[2]) / 2 * scale
                origin_y = 490 - box[3] * scale
            frame = Image.new('RGBA', (512, 512))
            frame.alpha_composite(cell.resize((round(cell.width * scale), round(cell.height * scale)),
                                              Image.Resampling.LANCZOS),
                                  (round(origin_x + offset[0] * scale), round(origin_y + offset[1] * scale)))
            frame.save(folder / f'frame-{i + 1:02}.png')
            bounds = alpha_bounds(frame)
            assert bounds and 0 < bounds[0] < bounds[2] < 512 and 0 < bounds[1] < bounds[3] < 512, bounds
            frames.append(frame)
            preview = Image.new('RGBA', (512, 512), '#eee9e2')
            preview.alpha_composite(frame)
            preview = preview.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS)
            previews.append(preview)
            overview.paste(preview, (i * 320, row * 340 + 20))
            ImageDraw.Draw(overview).text((i * 320 + 10, row * 340 + 5), f'{name} / {i + 1}', fill='#493b31')
        order = [0, 1, 2, 3, 2, 1, 0] if name == 'straddle' else [0, 1, 2, 3]
        durations = [1000, 600, 100, 140, 100, 600, 660] if name == 'straddle' else [280, 1000, 160, 260]
        palette_sheet = Image.new('RGB', (1280, 320))
        for i, preview in enumerate(previews):
            palette_sheet.paste(preview, (i * 320, 0))
        palette = palette_sheet.quantize(colors=256)
        indexed = [previews[i].quantize(palette=palette, dither=Image.Dither.NONE) for i in order]
        indexed[0].save(folder / 'preview.gif', save_all=True, append_images=indexed[1:],
                        duration=durations, loop=0, disposal=2, optimize=False)
        metadata = dict(frame_size=[512, 512], ready_for_app=True,
                        frames=[f'frame-{i:02}.png' for i in range(1, 5)],
                        playback_order_zero_based=order, duration_ms=durations,
                        loop=name == 'straddle', contact_baseline_y=340 if name == 'straddle' else 490,
                        source='source-sheet.png', prompt='prompt.txt', scale=scale,
                        registration=offsets, source_boxes=boxes,
                        notes='Jump air time is driven by gravity, not this preview duration; no mirroring.')
        (folder / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(name, [alpha_bounds(frame) for frame in frames])
    overview.save(ROOT / 'contact-sheet.png')


if __name__ == '__main__':
    main()
