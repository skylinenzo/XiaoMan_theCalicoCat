"""Pack generated drawings with one scale per set and explicit contact data."""
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter,ImageChops
from eye_annotations import eye_rects
ROOT=Path(__file__).resolve().parents[1]/'output/imagegen/hunt-actions-v1'

def isolate(cell):
    # Extract the largest connected sprite in the crop; neighboring ears/paws
    # can enter its rectangular bounds even though the silhouettes are separate.
    w,h=cell.size;data=cell.getchannel('A').tobytes();seen=bytearray(w*h);largest=[]
    for k,a in enumerate(data):
        if a<80 or seen[k]:continue
        stack=[k];seen[k]=1;group=[]
        while stack:
            j=stack.pop();group.append(j);x=j%w
            for n in (j-1 if x else -1,j+1 if x<w-1 else -1,j-w,j+w):
                if 0<=n<len(data) and not seen[n] and data[n]>=80:seen[n]=1;stack.append(n)
        if len(group)>len(largest):largest=group
    raw=bytearray(w*h)
    for j in largest:raw[j]=255
    mask=Image.frombytes('L',(w,h),bytes(raw)).filter(ImageFilter.MaxFilter(7))
    cell.putalpha(ImageChops.multiply(cell.getchannel('A'),mask))
    return cell

def main():
    boxes=json.loads((ROOT/'components.json').read_text())
    for name,rects in boxes.items():
        folder=ROOT/name
        source=folder/('source-sheet-v2.png' if (folder/'source-sheet-v2.png').exists() else 'source-sheet.png')
        im=Image.open(source).convert('RGBA')
        # Preserve body/head proportions across the whole sequence, never fit
        # each curled/extended pose independently to a common bounding box.
        scale=min(.96,460/max(b[2]-b[0]+8 for b in rects),440/max(b[3]-b[1]+8 for b in rects))
        frames=[];eye_data=[];contact=[]
        for i,b in enumerate(rects):
            box=(max(0,b[0]-3),max(0,b[1]-3),min(im.width,b[2]+3),min(im.height,b[3]+3))
            cell=isolate(im.crop(box))
            # Bounding boxes can overlap at an ear/tail: remove only pixels
            # strictly inside another sprite's opaque bounding region away
            # from this component. Sheets have disjoint actual silhouettes.
            width,height=round(cell.width*scale),round(cell.height*scale)
            x=round(256-width/2);bottom=490
            if name.startswith('run') and i in (3,6,7):bottom-= [0,0,0,22,0,0,34,14][i]
            y=bottom-round((b[3]-box[1])*scale)
            frame=Image.new('RGBA',(512,512))
            frame.alpha_composite(cell.resize((width,height),Image.Resampling.LANCZOS),(x,y))
            frame.save(folder/f'frame-{i+1:02}.png');frames.append(frame)
            eyes=eye_rects(frame)
            if name.startswith(('run','pounce')):
                eyes=sorted(eyes,key=lambda e:e[2]*e[3],reverse=True)[:1]
            eye_data.append(eyes)
            # Forepaw contact at the leading lower silhouette; metadata is
            # consumed by hit testing, not by the cursor itself.
            sign=-1 if name.endswith('left') else 1
            contact.append(256+sign*135)
        durations=([80]*8 if name.startswith('run') else [180,180,90,110,90,100,150,180]
                   if name.startswith('pounce') else [220,220,200,160,160,160,220,280])
        if name=='play_kick':order=[0,1,2,3,4,5,4,5,4,5,6,7];durations=[220,220,200,160,160,160,160,160,160,160,220,280]
        else:order=list(range(8))
        metadata=dict(frame_size=[512,512],ready_for_app=True,frames=[f'frame-{i:02}.png' for i in range(1,9)],
                      playback_order_zero_based=order,duration_ms=durations,contact_baseline_y=490,
                      loop=name.startswith('run'),mirrored=False,eye_rects=eye_data,contact_x=contact,
                      stride_pixels=240 if name.startswith('run') else None,source=source.name,
                      prompts=['prompt.txt']+(['prompt-v2.txt'] if (folder/'prompt-v2.txt').exists() else []),scale=scale)
        (folder/'animation.json').write_text(json.dumps(metadata,indent=2)+'\n')
        sheet=Image.new('RGBA',(1280,680),'#eee9e2')
        for i,f in enumerate(frames):
            sheet.alpha_composite(f.resize((320,320),Image.Resampling.LANCZOS),(i%4*320,i//4*340+20))
            ImageDraw.Draw(sheet).text((i%4*320+8,i//4*340+5),f'{name} {i+1}',fill='#493b31')
        sheet.convert('RGB').save(folder/'contact-sheet.png')
        print(name,'scale',round(scale,3),'eyes',eye_data,flush=True)
if __name__=='__main__':main()
