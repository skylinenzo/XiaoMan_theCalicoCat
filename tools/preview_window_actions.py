"""Show actual app straddling, anchored window strolling and gravity landing."""
from pathlib import Path
import json
from unittest.mock import patch
from PIL import Image, ImageDraw
import preview_interactions as common
from desktop_route import Surface
from window_perch import NativeSnapshot, NativeWindow, Rect

OUT = common.ROOT / 'output/window-actions-preview'
STEP = .05


class Window:
    def snapshot(self, exclude_hwnds=()):
        return NativeSnapshot({'preview': Rect(0, 0, 900, 740)},
                              (NativeWindow(9001, Rect(80, 300, 820, 590), pid=42),))


def save(name, frames, loop=True):
    tiles = Image.new('RGB', (120 * 12, 100 * ((len(frames) + 11) // 12)))
    for i, frame in enumerate(frames):
        tiles.paste(frame.resize((120, 100)), (i % 12 * 120, i // 12 * 100))
    palette = tiles.quantize(colors=256)
    indexed = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    kwargs = {'loop': 0} if loop else {}
    indexed[0].save(OUT / f'{name}.gif', save_all=True, append_images=indexed[1:],
                    duration=50, disposal=2, optimize=False, **kwargs)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = common.QApplication.instance() or common.QApplication([])
    cat = common.DesktopCat(settings=common.MemorySettings())
    for timer in (cat.timer, cat.floor_timer, cat.top_timer):
        timer.stop()
    cat.tray.hide()
    cat.behavior.enabled = False
    cat.logical_screens = lambda: {'preview': (0, 0, 900, 740)}
    cat.screen_surfaces = lambda: [Surface('preview', 0, 0, 900, 740, 690)]
    cat.window_observer = Window()
    cat.move(290, round(300 - cat.height() * 490 / 512))
    assert cat.try_attach_window()
    cat.perform('window_straddle')
    names = {'window_straddle': 'Two paws draped, two resting; tail hangs below the ledge',
             'window_perch': 'Resting on the ledge', 'walk_right': 'Walking along the window; stance paw stays anchored',
             'idle': 'Settled', 'jump_prepare': 'Crouch before jumping',
             'jump_air': 'Gravity accelerates the descent; speed is capped',
             'jump_land': 'Front paws touch down', 'jump_recover': 'Bend the legs to absorb landing'}
    frames, stages = [], []

    def tick():
        with patch('desktop_cat.time.monotonic', return_value=cat.last_tick + STEP):
            cat.tick()

    def capture():
        state = cat.visible_state()
        image = Image.new('RGBA', (900, 740), '#eeeae3')
        draw = ImageDraw.Draw(image)
        draw.text((25, 20), 'Window rest, stroll and jump down', font=common.font(24), fill='#41382e')
        draw.text((25, 60), names.get(state, 'Changing posture'), font=common.font(16), fill='#786a5a')
        draw.rounded_rectangle((80, 300, 820, 590), radius=8, fill='#fbfaf8', outline='#9ba9b8', width=2)
        draw.rounded_rectangle((80, 300, 820, 334), radius=8, fill='#d9e3ee', outline='#9ba9b8', width=2)
        draw.text((95, 310), 'A desktop window', font=common.font(14), fill='#52677d')
        draw.line((15, 690, 885, 690), fill='#a79d91', width=2)
        sprite = common.pil(cat.render_frame(cat.width()))
        box = sprite.getchannel('A').point(lambda a: 255 if a > 10 else 0).getbbox()
        assert cat.x() + box[0] >= 0 and cat.y() + box[1] >= 0
        assert cat.x() + box[2] <= 900 and cat.y() + box[3] <= 740
        image.alpha_composite(sprite, (cat.x(), cat.y()))
        frame = image.convert('RGB').resize((720, 592), Image.Resampling.LANCZOS)
        frames.append(frame)
        stages.append(state)
        return frame

    def transition(capture_frames=True):
        for _ in range(100):
            if cat.transition is None:
                return
            if capture_frames:
                capture()
            tick()
        raise AssertionError('Transition never finished')

    def hold(seconds):
        for _ in range(round(seconds / STEP)):
            capture()
            tick()

    try:
        transition(False)
        hold(3.2)
        save('straddle-loop', frames[:])
        frames[0].save(OUT / 'straddle.png')
        cat.perform('walk_right')
        transition()
        hold(1.2)
        cat.perform('window_straddle')
        transition()
        hold(.8)
        cat.jump_down()
        for _ in range(120):
            capture()
            tick()
            if cat.jump is None and cat.transition is None:
                break
        else:
            raise AssertionError('Jump never landed')
        hold(.5)
        save('window-stroll-jump', frames, loop=False)
        contact = Image.new('RGB', (720 * 3, 592))
        for i, state in enumerate(('window_straddle', 'walk_right', 'jump_air')):
            contact.paste(frames[stages.index(state)], (720 * i, 0))
        contact.save(OUT / 'overview.png')
        (OUT / 'manifest.json').write_text(json.dumps({'frames': len(frames), 'fps': 20,
            'renderer': 'DesktopCat.tick + render_frame', 'jump_stages': sorted(set(s for s in stages if s.startswith('jump_')))}, indent=2))
        print(OUT, len(frames), 'frames')
    finally:
        cat.tray.hide()
        cat.close()
        app.processEvents()


if __name__ == '__main__':
    main()
