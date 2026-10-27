"""Extract eight authored climbing poses and record ledge contact anchors."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
from package_interactions import alpha_bounds

ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen/window-climb-v1'


def main():
    frames, anchors = [], []
    # Split at actual transparent gutters: climbing paws cross nominal midlines.
    specs = [('launch', [(0, 0, 627, 574), (627, 0, 1254, 590),
                         (0, 574, 627, 1254), (627, 590, 1254, 1254)],
              [418, 918, 424, 893], [554, 571, 1183, 1208]),
             ('mantle', [(0, 0, 627, 700), (627, 0, 1254, 730),
                         (0, 700, 627, 1254), (627, 730, 1254, 1254)],
              [375, 944, None, None], [100, 300, 1080, 1093])]
    for name, boxes, centers, contacts in specs:
        source = Image.open(ROOT / name / 'source-sheet.png').convert('RGBA')
        for i, box in enumerate(boxes):
            cell = source.crop(box)
            bounds = alpha_bounds(cell)
            scale = .70
            center = centers[i] - box[0] if centers[i] is not None else (bounds[0] + bounds[2]) / 2
            x = 256 - center * scale
            y = 490 - bounds[3] * scale
            if name == 'launch' and i == 2:
                y -= 8  # Match A/B head height, rather than their raised foot.
            frame = Image.new('RGBA', (512, 512))
            frame.alpha_composite(cell.resize((round(cell.width * scale), round(cell.height * scale)),
                                              Image.Resampling.LANCZOS), (round(x), round(y)))
            b = alpha_bounds(frame)
            assert b and 8 < b[0] < b[2] < 504 and 8 < b[1] < b[3] < 504, (name, i, b)
            frames.append(frame)
            anchors.append(round(y + (contacts[i] - box[1]) * scale, 3))
            frame.save(ROOT / f'frame-{len(frames):02}.png')
    metadata = dict(frame_size=[512, 512], ready_for_app=True,
                    frames=[f'frame-{i:02}.png' for i in range(1, 9)],
                    playback_order_zero_based=list(range(8)), duration_ms=[180, 240, 100, 100, 100, 160, 180, 200],
                    contact_baselines_y=anchors, loop=False, mirrored=False,
                    poses=['crouch', 'launch', 'climb_a', 'climb_b', 'hook', 'pull_up', 'rotate', 'settle'],
                    sources=['launch/source-sheet.png', 'mantle/source-sheet.png'],
                    prompts=['launch/prompt.txt', 'mantle/prompt.txt'],
                    notes='Climb A/B repeat at runtime; geometry controls transit time. Front-view coat is never mirrored.')
    (ROOT / 'animation.json').write_text(json.dumps(metadata, indent=2) + '\n')
    sheet = Image.new('RGB', (1280, 680), '#eee9e2')
    previews = []
    for i, frame in enumerate(frames):
        bg = Image.new('RGBA', (512, 512), '#eee9e2')
        bg.alpha_composite(frame)
        preview = bg.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS)
        previews.append(preview)
        sheet.paste(preview, (i % 4 * 320, i // 4 * 340 + 20))
        ImageDraw.Draw(sheet).text((i % 4 * 320 + 10, i // 4 * 340 + 5), metadata['poses'][i], fill='#493b31')
    sheet.save(ROOT / 'contact-sheet.png')
    palette = sheet.quantize(colors=256)
    indexed = [p.quantize(palette=palette, dither=Image.Dither.NONE) for p in previews]
    indexed[0].save(ROOT / 'key-poses.gif', save_all=True, append_images=indexed[1:],
                    duration=metadata['duration_ms'], disposal=2, optimize=False)
    print('contact anchors', anchors)


if __name__ == '__main__':
    main()
