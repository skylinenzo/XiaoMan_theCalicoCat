"""Pack generated sheets into aligned PNG frames and animated previews.

Requires Pillow. Does not redraw, recolor, mirror or synthesize character poses.
"""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen'
SPECS = [('groom-v1', 3, 6), ('walk-left-v1', 4, 8), ('walk-right-v1', 4, 8)]


def read_cells(name, columns, count):
    image = Image.open(ROOT / name / 'source-sheet.png').convert('RGBA')
    cells = []
    for index in range(count):
        col, row = index % columns, index // columns
        bounds = (round(col * image.width / columns), round(row * image.height / 2),
                  round((col + 1) * image.width / columns), round((row + 1) * image.height / 2))
        cell = image.crop(bounds)
        box = cell.getchannel('A').point(lambda a: 255 if a >= 100 else 0).getbbox()
        assert box is not None
        left, top, right, bottom = box
        assert left > 1 and top > 1 and right < cell.width - 1 and bottom < cell.height - 1
        cells.append((cell, box))
    return cells


def main():
    inputs = {name: read_cells(name, cols, count) for name, cols, count in SPECS}
    # Same target total width for the two independently generated directions.
    for name, cols, count in SPECS:
        cells = inputs[name]
        max_width = max(box[2] - box[0] for _, box in cells)
        max_height = max(box[3] - box[1] for _, box in cells)
        scale = min(440 / max_width, 460 / max_height)
        output = ROOT / name
        frames = []
        for index, (cell, (left, top, right, bottom)) in enumerate(cells):
            size = (round(cell.width * scale), round(cell.height * scale))
            resized = cell.resize(size, Image.Resampling.LANCZOS)
            frame = Image.new('RGBA', (512, 512))
            frame.alpha_composite(resized, (round(256 - (left + right) / 2 * scale),
                                           round(490 - bottom * scale)))
            frame.save(output / f'frame-{index + 1:02}.png')
            frames.append(frame)
        if name == 'groom-v1':
            # Return through the same poses to the exact opening frame.
            order = [0, 1, 2, 3, 2, 1, 0]
            durations = [450, 130, 130, 220, 130, 130, 400]
        else:
            order = list(range(count))
            durations = [120] * count
        playback = [frames[i] for i in order]
        playback[0].save(output / 'animation.webp', save_all=True,
                         append_images=playback[1:], duration=durations, loop=0, lossless=True)
        preview = []
        for frame in playback:
            canvas = Image.new('RGBA', frame.size, '#eee9e2')
            canvas.alpha_composite(frame)
            preview.append(canvas.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS))
        preview[0].save(output / 'preview.gif', save_all=True, append_images=preview[1:],
                        duration=durations, loop=0, disposal=2)
        sheet = Image.new('RGBA', (cols * 512, 1024))
        for index, frame in enumerate(frames):
            sheet.alpha_composite(frame, ((index % cols) * 512, (index // cols) * 512))
        sheet.save(output / 'aligned-sheet.png')
        metadata = {'frame_size': [512, 512], 'foot_baseline_y': 490,
                    'frames': [f'frame-{i + 1:02}.png' for i in range(count)],
                    'playback_order_zero_based': order, 'duration_ms': durations,
                    'loop': True, 'mirrored': False,
                    'status': 'generated animation prototype; minor pose/marking drift possible'}
        (output / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
        with Image.open(output / 'animation.webp') as animation:
            assert animation.n_frames >= 6
            assert animation.size == (512, 512)
        print(f'{name}: {count} source poses, {sum(durations)}ms loop, validated')


if __name__ == '__main__':
    main()
