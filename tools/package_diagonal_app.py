"""Register imagegen art and package the approved gait for the desktop app."""
import json
import shutil
from pathlib import Path
from PIL import Image, ImageDraw
from package_walk_v2 import on_gray, score

ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen'


def bounds(image):
    return image.getchannel('A').point(lambda a: 255 if a > 100 else 0).getbbox()


def preview(frames, folder, name='cycle-2fps', duration=500):
    contact = Image.new('RGB', (320 * 4, 340 * ((len(frames) + 3) // 4)), '#eee9e2')
    views = []
    for i, frame in enumerate(frames):
        bg = Image.new('RGBA', frame.size, '#eee9e2')
        bg.alpha_composite(frame)
        view = bg.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS)
        views.append(view)
        contact.paste(view, (i % 4 * 320, i // 4 * 340 + 20))
        ImageDraw.Draw(contact).text((i % 4 * 320 + 10, i // 4 * 340 + 5), str(i + 1), fill='#493b31')
    contact.save(folder / f'{name}-contact.png')
    palette = contact.quantize(colors=256)
    indexed = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in views]
    indexed[0].save(folder / f'{name}.gif', save_all=True, append_images=indexed[1:],
                    duration=duration, loop=0, disposal=2, optimize=False)


def main():
    left = ROOT / 'walk-diagonal-left-v1'
    reference = Image.open(left / 'source-01.png').convert('RGBA').resize((512, 512), Image.Resampling.LANCZOS)
    reference_gray = on_gray(reference)
    for index in range(1, 9):
        source = Image.open(left / f'source-{index:02}.png').convert('RGBA')
        candidates = []
        for step in range(25):
            scale = .96 + step / 300
            extent = round(512 * scale)
            resized = source.resize((extent, extent), Image.Resampling.LANCZOS)
            y = 490 - bounds(resized)[3]
            canvas = Image.new('RGBA', (512, 512))
            canvas.alpha_composite(resized, (0, y))
            error, dx = min((score(reference_gray, on_gray(canvas), (25, 170, 180, 325), x, 0), x)
                            for x in range(-16, 17))
            candidates.append((error, dx, y, resized))
        _, dx, y, resized = min(candidates, key=lambda c: c[0])
        result = Image.new('RGBA', (512, 512))
        result.alpha_composite(resized, (dx, y))
        result.save(left / f'frame-{index:02}.png')
    right = ROOT / 'walk-diagonal-right-v1'
    right.mkdir(exist_ok=True)
    for i in range(1, 9):
        shutil.copy2(ROOT / f'walk-diagonal-cycle-v2/frame-{i:02}.png', right / f'frame-{i:02}.png')

    # Sole centers measured from the approved drawings; first half supports on
    # near front, second half on far front. Never reorder the eight poses.
    for side, folder in [('left', left), ('right', right)]:
        frames = [Image.open(folder / f'frame-{i:02}.png').convert('RGBA') for i in range(1, 9)]
        targets = [450, 450, 350, 330, 310, 450, 450, 350, 310, 300]
        # Find each grounded front paw locally, ignoring the lifted swing paw.
        def sole(frame_index, expected):
            x = 512 - expected if side == 'left' else expected
            alpha = frames[frame_index].getchannel('A')
            points = [(xx, sum(alpha.getpixel((xx, yy)) for yy in range(480, 490)))
                      for xx in range(max(0, x - 28), min(512, x + 29))]
            active = [xx for xx, value in points if value > 700]
            if not active:
                raise ValueError((side, frame_index, 'missing support sole'))
            return (min(active) + max(active)) / 2
        near = [sole(i, targets[i]) for i in range(5)]
        far = [sole(i % 8, targets[5 + j]) for j, i in enumerate(range(4, 9))]
        anchors = list(zip(near, near[1:])) + list(zip(far, far[1:]))
        direction = -1 if side == 'left' else 1
        raw = [-direction * (b - a) for a, b in anchors]
        # Tiny generation/measurement drift can reverse a contact by a few px.
        # Correct this with a small lower-body offset, keeping forward travel.
        steps = [max(2., x) for x in raw]
        factor = sum(raw) / sum(steps)
        steps = [s * factor for s in steps]
        offsets = [0.] * 8
        for i in range(7):
            offsets[i + 1] = offsets[i] + direction * (raw[i] - steps[i])
        metadata = dict(frame_size=[512, 512], foot_baseline_y=490,
                        frames=[f'frame-{i:02}.png' for i in range(1, 9)],
                        playback_order_zero_based=list(range(8)), duration_ms=[500] * 8,
                        direction=side, loop=True, fps=2, normalize_soles=False, blend_poses=False,
                        body_motion='steady',
                        step_pixels=steps, support_anchors=anchors, lower_offsets=offsets,
                        support_paws=['near_front'] * 4 + ['far_front'] * 4,
                        stride_pixels=sum(steps), mirrored=False,
                        artwork_source=('walk-diagonal-cycle-v2' if side == 'right' else 'source-01.png through source-08.png'),
                        prompt_source=('../walk-diagonal-cycle-v2/prompt-*.txt' if side == 'right' else 'prompt.txt'))
        (folder / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
        preview(frames, folder)
        print(side, 'anchors', anchors, 'stride', sum(steps), 'offsets', offsets)

    turns = ROOT / 'turn-sit-v1'
    for side in ('left', 'right'):
        sheet = Image.open(turns / f'source-{side}.png').convert('RGBA')
        # Split in the transparent gutter, including the left-turn tail which
        # slightly extends past the nominal half-cell line.
        split = round(sheet.width * .58)
        cells = [sheet.crop((0, 0, split, sheet.height)), sheet.crop((split, 0, sheet.width, sheet.height))]
        frames = []
        for i, cell in enumerate(cells):
            box = bounds(cell)
            # Common standing/seated head scale; ears at ~180 and soles at490.
            scale = 310 / (box[3] - box[1])
            resized = cell.resize((round(cell.width * scale), round(cell.height * scale)), Image.Resampling.LANCZOS)
            if i:
                x = round(256 - (box[0] + box[2]) / 2 * scale)
            else:
                # Match the turn's head between the side-view and frontal head,
                # not the bounding-box center (the lowering tail skews that).
                head_x = sheet.width * (.418 if side == 'right' else .184)
                x = round((330 if side == 'right' else 182) - head_x * scale)
            y = 490 - bounds(resized)[3]
            out = Image.new('RGBA', (512, 512))
            out.alpha_composite(resized, (x, y))
            out.save(turns / f'{side}-{i + 1:02}.png')
            frames.append(out)
        idle = Image.open(turns / 'idle-size-reference.png').convert('RGBA')
        walking = Image.open(ROOT / f'walk-diagonal-{side}-v1/frame-01.png').convert('RGBA')
        preview([walking, *frames, idle], turns, f'turn-{side}', [500, 220, 220, 1000])
    (turns / 'animation.json').write_text(json.dumps(dict(
        idle_scale=.66, foot_baseline_y=490, segment_duration_ms=220,
        left=['left-01.png', 'left-02.png'], right=['right-01.png', 'right-02.png'],
        notes='Two generated turn/sit poses per direction; reverse these for standing up.'), indent=2) + '\n')


if __name__ == '__main__':
    main()
