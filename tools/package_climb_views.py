"""Pack authored back/side drawings, preserving alpha and asymmetric coats."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
from package_interactions import alpha_bounds
ROOT = Path(__file__).resolve().parents[1] / 'output/imagegen'

def main():
    template = json.loads((ROOT/'window-climb-v1/animation.json').read_text())
    for kind, split, contacts in [('back',470,[530,637,785,None]), ('side',478,[540,660,736,None])]:
        folder = ROOT/f'window-climb-{kind}-v1'
        source = Image.open(folder/'source-sheet.png').convert('RGBA')
        frames, anchors = [], []
        for i in range(8):
            col,row = i%4,i//4
            box = (round(col*source.width/4),0 if row==0 else split,
                   round((col+1)*source.width/4),split if row==0 else source.height)
            cell = source.crop(box)
            b = alpha_bounds(cell)
            scale = .9
            x = 256-(b[0]+b[2])/2*scale
            y = 490-b[3]*scale
            frame = Image.new('RGBA',(512,512))
            frame.alpha_composite(cell.resize((round(cell.width*scale),round(cell.height*scale)),Image.Resampling.LANCZOS),
                                  (round(x),round(y)))
            frame.save(folder/f'frame-{i+1:02}.png')
            frames.append(frame)
            contact = contacts[i-4] if i>=4 else None
            anchors.append(round(y+(contact-box[1])*scale,3) if contact else 490.)
        metadata = dict(template,contact_baselines_y=anchors,sources=['source-sheet.png'],prompts=['prompt.txt'],
                        notes=f'{kind} view, original asymmetric coat; never mirrored.')
        (folder/'animation.json').write_text(json.dumps(metadata,indent=2)+'\n')
        sheet=Image.new('RGBA',(1024,552),'#eee9e2')
        for i,frame in enumerate(frames):
            sheet.alpha_composite(frame.resize((256,256),Image.Resampling.LANCZOS),(i%4*256,i//4*276+20))
            ImageDraw.Draw(sheet).text((i%4*256+8,i//4*276+4),template['poses'][i],fill='#493b31')
        sheet.convert('RGB').save(folder/'contact-sheet.png')
        print(kind,anchors)
if __name__=='__main__':main()
