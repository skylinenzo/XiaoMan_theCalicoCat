"""Export actual application poses/effects against small illustrative desktops.

Run with PySide6, Pillow and QT_QPA_PLATFORM=offscreen. Native observers and
settings are replaced only inside this preview process; no user settings change.
Cat pixels come exclusively from DesktopCat.render_frame(), without repainting.
"""
import io
import json
import math
import os
from pathlib import Path
import sys
import types

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QBuffer, QIODevice, QPoint
from PySide6.QtWidgets import QApplication


class MemorySettings:
    def __init__(self):
        self.data = {}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def sync(self):
        pass


class FakeTaskbar:
    def snapshot(self, hwnd):
        g = QApplication.primaryScreen().geometry()
        bounds = (g.x(), g.y(), g.x() + g.width(), g.y() + g.height())
        return bounds, bounds, [], True

    def keep_topmost(self, hwnd):
        pass


sys.modules['windows_taskbar'] = types.SimpleNamespace(TaskbarObserver=FakeTaskbar)
from desktop_cat import DesktopCat
from window_perch import NativeSnapshot, NativeWindow, Rect

OUT = ROOT / 'output/interaction-preview'
SIZE, PET, STEP = (480, 320), 256, .05
BG, INK = '#f1eee8', '#454039'
FLOOR = 282


def font(size):
    for name in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


TITLE, SMALL = font(17), font(12)


def pil(qimage):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert qimage.save(buffer, 'PNG')
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')


def background(title, detail, floor=False):
    image = Image.new('RGBA', SIZE, BG)
    drawing = ImageDraw.Draw(image)
    drawing.text((20, 15), title, font=TITLE, fill=INK)
    drawing.text((20, 40), detail, font=SMALL, fill='#81776e')
    if floor:
        drawing.line((16, FLOOR, SIZE[0] - 16, FLOOR), fill='#d5cdc2', width=1)
        drawing.text((20, 300), 'Soft contact shadow / transparent app rendering',
                     font=SMALL, fill='#81776e')
    return image


def validate_sprite(image, position):
    # Ignore sub-visible antialiasing dust, but require all visible artwork and
    # its shadow to fit in both the application texture and preview canvas.
    box = image.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
    assert box is not None
    assert 0 < box[0] < box[2] < PET and 0 < box[1] < box[3] < PET, box
    x, y = position
    assert x + box[0] >= 0 and y + box[1] >= 0, (box, position)
    assert x + box[2] <= SIZE[0] and y + box[3] <= SIZE[1], (box, position)


def save_animation(name, frames):
    # Train ONE palette over the entire sequence. Per-frame quantization makes
    # stationary fur and background colors flicker even when source PNGs agree.
    thumbs = [image.convert('RGB').resize((120, 80)) for image in frames]
    columns = 12
    rows = math.ceil(len(thumbs) / columns)
    palette_source = Image.new('RGB', (columns * 120, rows * 80), BG)
    for i, thumb in enumerate(thumbs):
        palette_source.paste(thumb, ((i % columns) * 120, (i // columns) * 80))
    palette = palette_source.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    indexed = [frame.convert('RGB').quantize(palette=palette, dither=Image.Dither.NONE)
               for frame in frames]
    path = OUT / f'{name}.gif'
    indexed[0].save(path, save_all=True, append_images=indexed[1:],
                    duration=round(STEP * 1000), loop=0, disposal=2, optimize=False)
    with Image.open(path) as animation:
        total = 0
        for i in range(animation.n_frames):
            animation.seek(i)
            assert animation.size == SIZE
            total += animation.info['duration']
        assert total == len(frames) * round(STEP * 1000)
    return {'samples': len(frames), 'duration_ms': len(frames) * 50,
            'size': list(SIZE), 'shared_palette': True, 'file': path.name}


def reset(pet, state='idle'):
    pet.drag_offset = None
    pet.perch = None
    pet.transition = None
    pet.mode = 'auto'
    pet.behavior.enabled = False
    pet.behavior.start(state)
    pet.overlay_elapsed = 0.
    pet.gait_time = pet.gait_phase = 0.
    pet.rest_x = pet.rest_y = pet.target_y = 0.
    pet.move(0, 0)


def action_preview(pet):
    reset(pet, 'rest_supine')
    frames, x = [], (SIZE[0] - PET) / 2
    names = {'rest_supine': 'Lying on back', 'rest_side': 'Side rest',
             'rest_prone': 'Prone rest', 'idle': 'Sitting',
             'walk_right': 'Walk right', 'walk_left': 'Walk left'}

    def capture():
        state = pet.visible_state()
        frame = background('Rest, stand and turn', names.get(state, state), floor=True)
        sprite = pil(pet.render_frame(PET))
        position = (round(x), round(FLOOR - 490 * PET / 512))
        validate_sprite(sprite, position)
        frame.alpha_composite(sprite, position)
        frames.append(frame)
        if not pet.transition and state in ('idle', 'rest_supine', 'walk_right'):
            path = OUT / f'{state}-transparent.png'
            if not path.exists():
                sprite.save(path)

    def advance():
        nonlocal x
        if pet.transition:
            if pet.transition.advance(STEP):
                pet.transition = None
        else:
            pet.behavior.elapsed += STEP
            if pet.behavior.state.startswith('walk'):
                side = pet.behavior.state[5:]
                cycle = pet.active_walker().cycles[side]
                distance = cycle.travel(pet.gait_time, STEP * 2) * PET / 512
                x += (-1 if side == 'left' else 1) * distance
                pet.gait_time += STEP * 2
                pet.gait_phase = (pet.gait_time / cycle.duration) % 1.
        # The local canvas uses the same fractional offset as the app window.
        pet.rest_x = x - math.floor(x)

    def hold(seconds):
        for _ in range(round(seconds / STEP)):
            capture()
            advance()

    def transition(state):
        pet.perform(state)
        # perform() normally refreshes desktop placement; the preview has a
        # local floor, so preserve the real renderer but reset display geometry.
        pet.target_y = pet.rest_y = 0.
        pet.move(0, 0)
        while pet.transition:
            capture()
            advance()

    hold(.5)
    transition('idle')  # Actual route: supine -> side -> prone -> sitting.
    hold(.65)
    transition('walk_right')
    hold(.6)
    transition('walk_left')  # Uses the app's sit and turn drawings in between.
    hold(.6)
    transition('rest_supine')
    # Small asymmetric stride totals must not become a moving GIF seam.
    # Keep the final resting drawing at the original preview position.
    if abs(x - (SIZE[0] - PET) / 2) > 2:
        raise AssertionError(f'Walk directions did not return near their start: {x}')
    x = (SIZE[0] - PET) / 2
    hold(.5)
    return frames


def held_preview(pet):
    reset(pet)
    pet.drag_offset = QPoint(0, 0)
    pet.held_sway.reset()
    frames, previous = [], 0.
    max_angle = 0.
    for i in range(128):
        t = i * STEP
        displacement = 64 * math.sin(math.pi * t / 1.2) ** 2 if t < 1.2 else 0.
        pet.overlay_elapsed = t
        pet.held_sway.update(STEP, displacement - previous)
        previous = displacement
        max_angle = max(max_angle, abs(pet.held_sway.angle))
        status = 'Moving with the cursor' if t < 1.2 else 'At rest: sway settles, eyes blink'
        frame = background('Picked up', status)
        sprite = pil(pet.render_frame(PET))
        position = (round((SIZE[0] - PET) / 2 + displacement), 42)
        validate_sprite(sprite, position)
        frame.alpha_composite(sprite, position)
        frames.append(frame)
        if i == 0:
            sprite.save(OUT / 'held-transparent.png')
    assert max_angle > 1 and abs(pet.held_sway.angle) < .01
    return frames


class FakeWindow:
    def __init__(self):
        self.dx = self.dy = 0.

    def snapshot(self, exclude_hwnds=()):
        screen = QApplication.primaryScreen()
        g = screen.geometry()
        monitor = Rect(g.x(), g.y(), g.x() + g.width(), g.y() + g.height())
        window = NativeWindow(12345, Rect(80 + self.dx, 430 + self.dy,
                                          720 + self.dx, 700 + self.dy), pid=123)
        return NativeSnapshot({screen.name(): monitor}, (window,))


def perch_preview(pet):
    reset(pet)
    observer = FakeWindow()
    pet.window_observer = observer
    pet.move(round(400 - PET / 2), round(430 - PET * 490 / 512))
    assert pet.try_attach_window(10)
    # This loop demonstrates the settled perch; finish the app's landing route
    # before sampling the blink animation and window-follow geometry.
    if pet.transition:
        pet.transition.advance(pet.transition.duration)
        pet.transition = None
    origin = (pet.rest_x, pet.rest_y)
    frames = []
    for i in range(64):
        t = i * STEP
        observer.dx = 16 * math.sin(2 * math.pi * t / 3.2)
        observer.dy = 7 * math.sin(2 * math.pi * t / 3.2)
        pet.overlay_elapsed = t
        pet.refresh_floor()  # Actual follow_perch geometry integration.
        assert pet.perch is not None
        dx, dy = pet.rest_x - origin[0], pet.rest_y - origin[1]
        frame = background('Window ledge', 'Paws on the edge; follows the window')
        drawing = ImageDraw.Draw(frame)
        left, top, right, bottom = 50 + dx, 210 + dy, 430 + dx, 303 + dy
        drawing.rounded_rectangle((left + 3, top + 4, right + 3, bottom + 4),
                                  radius=7, fill='#ddd7ce')
        drawing.rounded_rectangle((left, top, right, bottom), radius=7,
                                  fill='#fbfaf7', outline='#b9c1cb', width=1)
        drawing.rounded_rectangle((left, top, right, top + 27), radius=7,
                                  fill='#dce5ef', outline='#b9c1cb', width=1)
        drawing.text((left + 12, top + 7), 'A desktop window', font=SMALL, fill='#536376')
        drawing.text((right - 48, top + 5), '-  []  x', font=SMALL, fill='#536376')
        drawing.line((left + 14, top + 48, right - 100, top + 48), fill='#e1e5e9', width=3)
        drawing.line((left + 14, top + 64, right - 50, top + 64), fill='#e1e5e9', width=3)
        sprite = pil(pet.render_frame(PET))
        position = (round((SIZE[0] - PET) / 2 + dx), round(top - pet.perch_baseline()))
        validate_sprite(sprite, position)
        frame.alpha_composite(sprite, position)
        frames.append(frame)
        if i == 0:
            sprite.save(OUT / 'perch-transparent.png')
    return frames


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Deterministic reruns refresh the representative PNGs as well as GIFs.
    for name in ('idle', 'rest_supine', 'walk_right'):
        (OUT / f'{name}-transparent.png').unlink(missing_ok=True)
    app = QApplication.instance() or QApplication([])
    pet = DesktopCat(settings=MemorySettings())
    pet.resize(PET, PET)
    for timer in (pet.timer, pet.floor_timer, pet.top_timer):
        timer.stop()
    pet.tray.hide()
    try:
        actions = action_preview(pet)
        held = held_preview(pet)
        perch = perch_preview(pet)
        manifest = {name: save_animation(name, frames) for name, frames in (
            ('actions-and-shadow', actions), ('held-sway', held), ('window-perch', perch))}
        showcase = Image.new('RGB', (SIZE[0] * 3, SIZE[1]), BG)
        for i, frame in enumerate((actions[26], held[60], perch[0])):
            showcase.paste(frame.convert('RGB'), (SIZE[0] * i, 0))
        showcase.save(OUT / 'showcase.png')
        manifest['renderer'] = 'DesktopCat.render_frame (actual app composition)'
        manifest['validated'] = 'Visible cat/shadow bounds, output duration and dimensions, sway settles'
        (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(manifest, indent=2))
    finally:
        pet.tray.hide()
        pet.close()
        app.processEvents()


if __name__ == '__main__':
    main()
