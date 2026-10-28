"""Actual gaze renderer: distant, near-convergent and vertical targets."""
from PIL import Image, ImageDraw
import preview_interactions as common
app=common.QApplication.instance() or common.QApplication([])
cat=common.DesktopCat(common.MemorySettings());cat.gaze.enabled=True
for timer in (cat.timer,cat.floor_timer,cat.top_timer):timer.stop()
cat.hide();cat.tray.hide()
frames=[];tiles=[]
for name,target in [('far left',(-900,280)),('far right',(1500,280)),('near center',(260,280)),('near below',(260,330)),('far above',(260,-1000))]:
    for _ in range(18):
        cat.gaze.follow(*target,.05)
        sprite=cat.gaze.paint(cat.frames[0],'idle/0',(0,0),512)
        bg=Image.new('RGBA',(512,512),'#eee9e2');bg.alpha_composite(common.pil(sprite))
        face=bg.crop((175,205,335,325)).convert('RGB').resize((480,360),Image.Resampling.LANCZOS)
        ImageDraw.Draw(face).text((10,10),name,fill='black')
        frames.append(face)
    tiles.append(face)
out=common.ROOT/'output/eye-focus';out.mkdir(parents=True,exist_ok=True)
frames[0].save(out/'focus.gif',save_all=True,append_images=frames[1:],duration=50,loop=0)
sheet=Image.new('RGB',(480*len(tiles),360))
for i,im in enumerate(tiles):sheet.paste(im,(480*i,0))
sheet.save(out/'focus.png')
tiles=[]
for state in ('rest_supine','rest_side','play_lick','run_right'):
    source=cat.animations[state][0][0];key=f'{state}/0'
    eyes=cat.gaze.catalog.get(key,[])
    if not eyes:continue
    cx=sum(x+w/2 for x,y,w,h in eyes)/len(eyes)
    cy=sum(y+h/2 for x,y,w,h in eyes)/len(eyes)
    cat.gaze.target=(cx+70,cy-25)
    sprite=cat.gaze.paint(source,key,(0,0),512)
    bg=Image.new('RGBA',(512,512),'#eee9e2');bg.alpha_composite(common.pil(sprite))
    face=bg.crop((round(cx-70),round(cy-70),round(cx+70),round(cy+70))).convert('RGB').resize((420,420),Image.Resampling.LANCZOS)
    ImageDraw.Draw(face).text((8,8),state,fill='black');tiles.append(face)
    print(state,[round(a,1) for _,a in cat.gaze.eye_geometry(source,key,eyes)])
sheet=Image.new('RGB',(420*len(tiles),420))
for i,im in enumerate(tiles):sheet.paste(im,(i*420,0))
sheet.save(out/'tilted-heads.png')
cat.close();cat.tray.hide()
