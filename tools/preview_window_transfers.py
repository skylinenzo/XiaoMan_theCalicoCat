"""Render the actual Qt controller's climb, window hop and gravity descent."""
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
import preview_interactions as common
import preview_window_actions as saving
from desktop_route import Surface
from window_perch import NativeSnapshot, NativeWindow, Rect

OUT = common.ROOT / 'output/window-transfer-preview'

class Windows:
    windows = [NativeWindow(9001, Rect(100,320,650,660), pid=42)]
    def snapshot(self, exclude_hwnds=()):
        return NativeSnapshot({'preview': Rect(0,0,1100,850)}, tuple(self.windows))

def main(style=None):
    global OUT
    if style:
        OUT = common.ROOT / 'output/window-climb-views-preview' / style
    OUT.mkdir(parents=True, exist_ok=True)
    app = common.QApplication.instance() or common.QApplication([])
    cat = common.DesktopCat(settings=common.MemorySettings())
    for timer in (cat.timer, cat.floor_timer, cat.top_timer): timer.stop()
    cat.tray.hide()
    cat.behavior.enabled = False
    if style:
        cat.set_climb_style(style)
    cat.logical_screens = lambda: {'preview': (0,0,1100,850)}
    cat.screen_surfaces = lambda: [Surface('preview',0,0,1100,850,820)]
    cat.window_observer = Windows()
    cat.route = None
    cat.move(300,round(820-cat.height()*490/512))
    cat.refresh_floor()
    cat.rest_y = cat.target_y
    cat.move(round(cat.rest_x),round(cat.rest_y))
    frames, poses = [], {}
    def step():
        cat.refresh_floor()
        with patch('desktop_cat.time.monotonic', return_value=cat.last_tick+.05): cat.tick()
        image = Image.new('RGBA',(1100,850),'#eeeae3')
        draw = ImageDraw.Draw(image)
        draw.text((25,20),'Climb, mantle, window hop and jump down',font=common.font(26),fill='#41382e')
        draw.text((25,60),cat.visible_state(),font=common.font(18),fill='#786a5a')
        for window in reversed(cat.window_observer.windows):
            r = window.rect
            draw.rounded_rectangle((r.left,r.top,r.right,r.bottom),radius=8,fill='#fbfaf8',outline='#9ba9b8',width=2)
            draw.rectangle((r.left+2,r.top+2,r.right-2,r.top+30),fill='#d9e3ee')
        draw.line((15,820,1085,820),fill='#a79d91',width=2)
        image.alpha_composite(common.pil(cat.render_frame(cat.width())),(cat.x(),cat.y()))
        frame = image.convert('RGB').resize((770,595),Image.Resampling.LANCZOS)
        frames.append(frame)
        poses.setdefault(cat.visible_state(),frame)
    def finish():
        for _ in range(200):
            step()
            if cat.transfer is None and cat.jump is None and cat.transition is None: return
        raise AssertionError('Motion did not finish')
    try:
        for _ in range(10): step()
        assert cat.start_transfer(upward_only=True)
        finish()
        for _ in range(14): step()
        cat.window_observer.windows.insert(0,NativeWindow(9002,Rect(690,420,1070,720),pid=42))
        assert cat.start_transfer()
        finish()
        for _ in range(14): step()
        cat.jump_down()
        finish()
        for _ in range(14): step()
        saving.OUT = OUT
        saving.save('climb-hop-down',frames,loop=False)
        selected = ['transfer_prepare','transfer_launch','transfer_climb','transfer_hook','transfer_pull','transfer_rotate','transfer_settle','transfer_flight']
        overview = Image.new('RGB',(770*2,595*4),'#eeeae3')
        for i,state in enumerate(selected): overview.paste(poses[state],(i%2*770,i//2*595))
        overview.save(OUT/'overview.png')
        print(OUT/'climb-hop-down.gif')
    finally:
        cat.close();cat.tray.hide()

if __name__ == '__main__':
    import sys
    main(sys.argv[1] if len(sys.argv)>1 else None)
