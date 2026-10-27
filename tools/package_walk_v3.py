"""Register the eight tail-up drawings on the head, using one common scale.

Only sprite packing/alignment here. Artwork is edited by image_gen; originals
and prompts are retained in each v3 directory.
"""
import json
from pathlib import Path
from PIL import Image
from package_walk_v2 import on_gray, register

ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen'


def main():
    for side in ('left', 'right'):
        folder = ROOT / f'walk-{side}-v3'
        sheet = Image.open(folder / 'source-sheet.png').convert('RGBA')
        cells = [sheet.crop((round(i % 4 * sheet.width / 4), round(i // 4 * sheet.height / 2),
                             round((i % 4 + 1) * sheet.width / 4), round((i // 4 + 1) * sheet.height / 2)))
                 for i in range(8)]
        size = cells[0].width
        # Common cell extent, preserving coordinates rather than individual bounding boxes.
        cells = [cell.crop((0, 0, size, size)) for cell in cells]
        box = ((20, 140, 150, 275) if side == 'left' else (275, 140, 411, 282))
        registrations = [(0, 0, 0, 0)] + [register(on_gray(cells[0]), on_gray(cell), box) for cell in cells[1:]]
        frames = []
        # At this scale the standing cat's head/body match the existing idle asset.
        scale = 1.12
        bounds = [cell.getchannel('A').point(lambda a: 255 if a > 100 else 0).getbbox() for cell in cells]
        bottom = max(b[3] + offset[1] for b, offset in zip(bounds, registrations))
        origin_y = 490 - bottom * scale
        origin_x = (512 - size * scale) / 2
        for i, (cell, (dx, dy, _, _)) in enumerate(zip(cells, registrations)):
            image = Image.new('RGBA', (512, 512))
            image.alpha_composite(cell.resize((round(size * scale), round(size * scale)), Image.Resampling.LANCZOS),
                                  (round(origin_x + dx * scale), round(origin_y + dy * scale)))
            image.save(folder / f'frame-{i + 1:02}.png')
            frames.append(image)
        contact = Image.new('RGBA', (2048, 1024))
        for i, frame in enumerate(frames):
            contact.alpha_composite(frame, (i % 4 * 512, i // 4 * 512))
        contact.save(folder / 'aligned-sheet.png')
        metadata = {'frame_size': [512, 512], 'foot_baseline_y': 490,
                    'frames': [f'frame-{i + 1:02}.png' for i in range(8)],
                    'playback_order_zero_based': list(range(8)), 'duration_ms': [120] * 8,
                    'loop': True, 'mirrored': False, 'registration': registrations}
        # Same named paw in each pair; coordinates measured on the registered drawings.
        if side == 'left':
            order = [0, 1, 2, 3, 4, 7, 5, 6]
            anchors = [(374, 382), (184, 194), (344, 368), (86, 95),
                       (95, 94), (366, 382), (189, 196), (358, 374)]
            names = ['far_hind', 'far_front', 'far_hind', 'near_front',
                     'near_front', 'far_hind', 'far_front', 'far_hind']
        else:
            order = list(range(8))
            anchors = [(428, 386), (281, 268), (211, 192), (150, 110),
                       (278, 270), (270, 270), (116, 130), (321, 306)]
            names = ['near_front', 'far_front', 'far_hind', 'near_hind',
                     'far_front', 'far_front', 'near_hind', 'far_front']
        direction = -1 if side == 'left' else 1
        raw_steps = [-direction * (b - a) for a, b in anchors]
        steps = [min(28, max(6 if side == 'right' else 4, step)) for step in raw_steps]
        factor = sum(raw_steps) / sum(steps)
        steps = [step * factor for step in steps]
        offsets = [0.] * 8
        for i in range(7):
            offsets[order[i + 1]] = offsets[order[i]] + direction * (raw_steps[i] - steps[i])
        # Both outgoing and incoming stance contacts are flattened to the same floor.
        soles = [[] for _ in range(8)]
        for i, (a, b) in enumerate(anchors):
            for frame_index, x in ((order[i], a), (order[(i + 1) % 8], b)):
                alpha = frames[frame_index].getchannel('A')
                y = max(y for y in range(430, 500) if any(
                    alpha.getpixel((xx, y)) > 160 for xx in range(x - 5, x + 6)))
                soles[frame_index].append([x, y])
        metadata.update(direction=side, playback_order_zero_based=order,
                        duration_ms=[round(100 + step * 1.5) for step in steps],
                        step_pixels=steps, support_anchors=anchors, support_paws=names,
                        lower_offsets=offsets, support_soles=soles,
                        stride_pixels=sum(steps), stable_body_y=320)
        (folder / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(side, registrations)


if __name__ == '__main__':
    main()
