"""Offline iris annotation only; eye movement is a clipped Qt component."""
def eye_rects(image):
    im=image.convert('RGBA');w,h=im.size
    pixels=im.load(); points=set()
    for y in range(h):
        for x in range(w):
            r,g,b,a=pixels[x,y]
            if a>220 and 65<g<210 and 65<r<230 and -12<r-g<38 and g-b>24 and b<150:
                points.add((x,y))
    groups=[]
    while points:
        point=points.pop();stack=[point];group=[point]
        while stack:
            x,y=stack.pop()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                p=(x+dx,y+dy)
                if p in points:points.remove(p);stack.append(p);group.append(p)
        if len(group)>=6:
            xs,ys=zip(*group);groups.append([min(xs),min(ys),max(xs)+1,max(ys)+1,len(group)])
    # Iris halves can be disconnected by the dark pupil. Merge only neighboring
    # compact components; orange fur is excluded by the near-olive color gate.
    changed=True
    while changed:
        changed=False
        for i,a in enumerate(groups):
            for j in range(i+1,len(groups)):
                b=groups[j]
                if (abs((a[1]+a[3]-b[1]-b[3])/2)<9 and max(a[0],b[0])-min(a[2],b[2])<12
                    and max(a[2],b[2])-min(a[0],b[0])<42 and max(a[3],b[3])-min(a[1],b[1])<40):
                    groups[i]=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3]),a[4]+b[4]]
                    groups.pop(j);changed=True;break
            if changed:break
    result=[]
    for x1,y1,x2,y2,count in groups:
        ew,eh=x2-x1,y2-y1
        if 7<=ew<=40 and 8<=eh<=40 and .4<ew/eh<2.4 and count>=18:
            result.append([x1,y1,ew,eh])
    return result
