"""Create inspectable eye rectangles for authored, calibrated application poses."""
import json
from PIL import Image,ImageDraw
import preview_interactions as common
from eye_annotations import eye_rects

def main():
    app=common.QApplication.instance() or common.QApplication([])
    cat=common.DesktopCat(common.MemorySettings())
    for t in (cat.timer,cat.floor_timer,cat.top_timer):t.stop()
    cat.tray.hide()
    cat.gaze.enabled=False
    catalog={};tiles=[]
    def add(key,image,profile=False,back=False,explicit=None):
        pil=common.pil(image)
        eyes=eye_rects(pil) if explicit is None else explicit
        if back:eyes=[]
        if profile:eyes=sorted(eyes,key=lambda e:e[2]*e[3],reverse=True)[:1]
        elif len(eyes)>2:
            eyes=sorted(eyes,key=lambda e:e[2]*e[3],reverse=True)[:2]
        overrides = {
            'idle/0': [[207,269,35,23],[280,269,33,23]],
            'idle/2': [], 'idle/3': [], 'idle/4': [], 'groom/3': [],
            'window_climb_side/6': [[400,218,20,21]],
            'walk/frames_original/right': [[415,268,22,23]],
        }
        if key in overrides:eyes=overrides[key]
        if key.split('/')[0] in ('rest_prone','rest_side','rest_supine','held','window_perch','window_straddle') and key.endswith(('/2','/3')):
            eyes=[]
        catalog[key]=eyes
        draw=ImageDraw.Draw(pil)
        for x,y,w,h in eyes:draw.ellipse((x,y,x+w,y+h),outline='red',width=2)
        bg=Image.new('RGBA',(512,512),'#eee9e2');bg.alpha_composite(pil)
        tile=bg.convert('RGB').resize((256,256));ImageDraw.Draw(tile).text((4,4),key,fill='black')
        tiles.append(tile)
    for i,im in enumerate(cat.frames):add(f'idle/{i}',im)
    for state,(frames,metadata) in cat.animations.items():
        for i,im in enumerate(frames):
            add(f'{state}/{i}',im,profile=state.startswith(('run_','pounce_')),
                back=state=='window_climb_back' and i<7,
                explicit=metadata.get('eye_rects',[None]*len(frames))[i])
    for style in cat.style_actions:
        cat.walk_style=style
        for side in ('left','right'):add(f'walk/{style}/{side}',cat.walking_image(side,512),profile=True)
    (common.ROOT/'assets/eye-catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    out=common.ROOT/'output/hunt-actions-preview';out.mkdir(parents=True,exist_ok=True)
    # Separate audit pages to inspect all open/closed frames at useful resolution.
    for page in range((len(tiles)+23)//24):
        portion=tiles[page*24:(page+1)*24];sheet=Image.new('RGB',(1536,256*((len(portion)+5)//6)),'#eee9e2')
        for i,tile in enumerate(portion):sheet.paste(tile,(i%6*256,i//6*256))
        sheet.save(out/f'eye-audit-{page+1}.png')
    cat.close();cat.tray.hide()
    print(len(catalog),'eye annotation entries')
if __name__=='__main__':main()
