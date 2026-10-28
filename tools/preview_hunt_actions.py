"""Preview actual app layers and behavior with simulated cursor coordinates."""
from unittest.mock import patch
from PIL import Image,ImageDraw
from PySide6.QtCore import QPoint
import preview_interactions as common
import preview_window_actions as saving
from desktop_route import Surface
OUT=common.ROOT/'output/hunt-actions-preview'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    app=common.QApplication.instance() or common.QApplication([])
    cat=common.DesktopCat(common.MemorySettings());cat.gaze.enabled=True
    for timer in (cat.timer,cat.floor_timer,cat.top_timer):timer.stop()
    cat.tray.hide();cat.behavior.enabled=False
    cat.logical_screens=lambda:{'preview':(0,0,1000,650)}
    cat.screen_surfaces=lambda:[Surface('preview',0,0,1000,650,610)]
    saving.OUT=OUT
    def tick():
        with patch('desktop_cat.time.monotonic',return_value=cat.last_tick+.05):cat.tick()
    def ground():
        cat.hunt.cancel();cat.transition=None;cat.perch=cat.jump=cat.transfer=None
        cat.behavior.start('idle');cat.move(400,399);cat.route=None;cat.refresh_floor()
        cat.rest_y=cat.target_y;cat.move(round(cat.rest_x),round(cat.rest_y))
    def capture(title,cursor=None):
        bg=Image.new('RGBA',(1000,650),'#eee9e2');draw=ImageDraw.Draw(bg)
        draw.text((20,20),title,font=common.font(24),fill='#493b31')
        draw.text((20,56),cat.visible_state(),font=common.font(18),fill='#786a5a')
        draw.line((0,610,1000,610),fill='#958879',width=2)
        if cursor:
            x,y=cursor.x(),cursor.y()
            draw.polygon([(x,y),(x+4,y+20),(x+10,y+12),(x+17,y+11)],fill='white',outline='#333333')
        bg.alpha_composite(common.pil(cat.render_frame(cat.width())),(cat.x(),cat.y()))
        return bg.convert('RGB').resize((800,520),Image.Resampling.LANCZOS)
    try:
        for side in ('left','right'):
            ground();cat.hunt_enabled=True;cat.hunt.cooldown=0
            cursor=QPoint(round(cat.rest_x+cat.width()/2+(-60 if side=='left' else 60)),600)
            cat.cursor_position=lambda:cursor
            cat.hunt.next_play=0 if side=='left' else 1
            frames=[];seen=[]
            for i in range(120):
                tick();frames.append(capture(f'{side}: pounce, catch and play',cursor));seen.append(cat.hunt.state)
            assert any(s.startswith('play') for s in seen),seen
            saving.save('catch-'+side,frames,loop=False)
        for action in ('play_kick','play_lick'):
            ground();cat.hunt_enabled=False;cat.perform(action);frames=[]
            for _ in range(80):tick();frames.append(capture(action))
            saving.save(action,frames,loop=False)
        for side in ('left','right'):
            ground();cat.hunt_enabled=False;cat.perform_run(side);frames=[]
            for _ in range(70):tick();frames.append(capture('Gallop '+side))
            saving.save('run-'+side,frames,loop=False)
        ground();cat.hunt_enabled=False;cat.transition=None
        frames=[]
        for target in ((100,300),(900,300),(500,100),(500,650),(500,400)):
            for _ in range(14):
                cat.gaze.follow(*target,.05)
                sprite=common.pil(cat.gaze_image(cat.frames[0],'idle/0'))
                bg=Image.new('RGBA',(512,512),'#eee9e2');bg.alpha_composite(sprite)
                # Enlarge the face for evaluating the independent eye controls.
                frame=bg.crop((150,175,365,355)).convert('RGB').resize((600,502),Image.Resampling.LANCZOS)
                frames.append(frame)
        saving.save('eyes-follow',frames,loop=True)
        print(OUT)
    finally:cat.close();cat.tray.hide()
if __name__=='__main__':main()
