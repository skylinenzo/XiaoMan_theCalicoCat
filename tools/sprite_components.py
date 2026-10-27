from PIL import Image
from pathlib import Path
from collections import deque

def components(im):
 a=im.getchannel('A');w,h=im.size;data=a.tobytes();seen=bytearray(w*h);result=[]
 for k,v in enumerate(data):
  if v<100 or seen[k]:continue
  q=[k];seen[k]=1;count=0;left=right=k%w;top=bottom=k//w
  while q:
   j=q.pop();x,y=j%w,j//w;count+=1
   left=min(left,x);right=max(right,x);top=min(top,y);bottom=max(bottom,y)
   for n in ((j-1 if x else -1),(j+1 if x<w-1 else -1),j-w,j+w):
    if 0<=n<len(data) and not seen[n] and data[n]>=100:seen[n]=1;q.append(n)
  if count>3000:result.append((count,(left,top,right+1,bottom+1)))
 return sorted(result,reverse=True)
if __name__=='__main__':
 for p in Path('output/imagegen/hunt-actions-v1').glob('*/source-sheet.png'):
  im=Image.open(p);print(p.parent.name,im.size,components(im),flush=True)
