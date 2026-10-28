"""Compare actual runtime poses on identical canvases, without resizing poses."""
from PIL import Image, ImageDraw
import preview_interactions as common


def main():
    app = common.QApplication.instance() or common.QApplication([])
    cat = common.DesktopCat(common.MemorySettings())
    for timer in (cat.timer, cat.floor_timer, cat.top_timer):
        timer.stop()
    cat.hide()
    cat.tray.hide()
    cat.gaze.enabled = False
    try:
        poses = [('idle', cat.frames[0])]
        poses.extend((name, frames[0]) for name, (frames, _) in cat.animations.items())
        for style in cat.style_actions:
            cat.walk_style = style
            poses.append((style, cat.walking_image('right', 512)))
        poses.extend((f'turn_{side}_{i}', frame) for side, frames in cat.turn_frames.items()
                     for i, frame in enumerate(frames))
        sheet = Image.new('RGB', (1100, 250 * ((len(poses)+3)//4)), '#eee9e2')
        draw = ImageDraw.Draw(sheet)
        for i, (name, frame) in enumerate(poses):
            x, y = i % 4 * 275, i // 4 * 250
            draw.text((x+8, y+5), name, fill='#493b31')
            draw.line((x+20, y+24+490*220/512, x+240, y+24+490*220/512), fill='#b8b0a7')
            sprite = common.pil(frame).resize((220, 220), Image.Resampling.LANCZOS)
            sheet.paste(sprite, (x+20, y+24), sprite)
        out = common.ROOT / 'output/size-audit'
        out.mkdir(parents=True, exist_ok=True)
        sheet.save(out / 'runtime-poses.png')
    finally:
        cat.close()
        cat.tray.hide()


if __name__ == '__main__':
    main()
