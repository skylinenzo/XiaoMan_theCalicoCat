"""Preview all normalized run frames at runtime scale."""
from PIL import Image, ImageDraw
import preview_interactions as common
app=common.QApplication.instance() or common.QApplication([])
cat=common.DesktopCat(common.MemorySettings())
for timer in (cat.timer,cat.floor_timer,cat.top_timer):timer.stop()
cat.hide();cat.tray.hide()
out=common.ROOT/'output/size-audit';out.mkdir(parents=True,exist_ok=True)
sheet=Image.new('RGB',(1280,4*340),'#eee9e2')
for s,side in enumerate(('left','right')):
    frames=[]
    for i,frame in enumerate(cat.animations['run_'+side][0]):
        sprite=common.pil(frame).resize((320,320),Image.Resampling.LANCZOS)
        bg=Image.new('RGBA',(320,340),'#eee9e2');bg.alpha_composite(sprite,(0,20))
        ImageDraw.Draw(bg).text((5,5),f'{side} {i+1}',fill='black')
        sheet.paste(bg.convert('RGB'),(i%4*320,(s*2+i//4)*340))
        frames.append(bg.convert('RGB'))
    frames[0].save(out/f'run-{side}.gif',save_all=True,append_images=frames[1:],duration=[50,50,60,50,50,60,50,60],loop=0)
sheet.save(out/'run-frames.png')
cat.close();cat.tray.hide()
