"""Actual renderer preview using a simulated cursor; never moves real mouse."""
import preview_interactions as common
import preview_window_actions as saving
from PIL import Image,ImageDraw
from PySide6.QtCore import QPoint
from unittest.mock import patch
from desktop_route import Surface
OUT=common.ROOT/'output/hunt-preview'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    app=common.QApplication.instance() or common.QApplication([])
    cat=common.DesktopCat(common.MemorySettings())
    for timer in (cat.timer,cat.floor_timer,cat.top_timer):timer.stop()
    cat.tray.hide();cat.behavior.enabled=False
    cat.logical_screens=lambda:{'preview':(0,0,1000,600)}
    cat.screen_surfaces=lambda:[Surface('preview',0,0,1000,600,570)]
    cat.move(300,360);cat.route=None;cat.refresh_floor()
    cat.rest_y=cat.target_y;cat.move(round(cat.rest_x),round(cat.rest_y))
    poses=[('idle',cat.frames[0])]+[(k,v[0][0]) for k,v in cat.animations.items()]
    for style in cat.style_actions:
        cat.set_walk_style(style)
        poses.append((style,cat.walking_image('right',512)))
    for side in ('left','right'):
        poses.extend((f'turn_{side}_{i}',im) for i,im in enumerate(cat.turn_frames[side]))
    sheet=Image.new('RGB',(1200,300*((len(poses)+3)//4)),'#eee9e2')
    for i,(name,im) in enumerate(poses):
        sprite=common.pil(im).resize((300,300));sheet.paste(sprite,(i%4*300,i//4*300),sprite)
        ImageDraw.Draw(sheet).text((i%4*300+5,i//4*300+5),name,fill='black')
    sheet.save(OUT/'size-comparison.png')
    cat.set_walk_style('frames_diagonal');cat.set_hunt_enabled(True)
    cursor=QPoint(570,540);cat.cursor_position=lambda:cursor
    frames=[]
    for i in range(180):
        if i==135:cursor=QPoint(800,100)
        with patch('desktop_cat.time.monotonic',return_value=cat.last_tick+.05):cat.tick()
        bg=Image.new('RGBA',(1000,600),'#eee9e2');draw=ImageDraw.Draw(bg)
        draw.text((20,20),'Bottom mouse hunt: '+cat.hunt.state,font=common.font(24),fill='#493b31')
        draw.line((0,570,1000,570),fill='#958879',width=2)
        draw.polygon([(cursor.x(),cursor.y()),(cursor.x()+4,cursor.y()+20),(cursor.x()+9,cursor.y()+13),
                      (cursor.x()+17,cursor.y()+12)],fill='white',outline='#333333')
        bg.alpha_composite(common.pil(cat.render_frame(cat.width())),(cat.x(),cat.y()))
        frames.append(bg.convert('RGB').resize((800,480),Image.Resampling.LANCZOS))
    saving.OUT=OUT;saving.save('mouse-hunt',frames,loop=False)
    cat.close();cat.tray.hide()
if __name__=='__main__':main()
