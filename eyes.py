"""Independent, clipped iris/pupil controls, expressed in 512px pose coordinates."""
import json
import math
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF, QRadialGradient

class EyeControl:
    def __init__(self):
        path=Path(__file__).resolve().parent/'assets/eye-catalog.json'
        self.catalog=json.loads(path.read_text()) if path.exists() else {}
        self.enabled=True
        self.target=None
        self.mask_cache={}

    def follow(self, x, y, dt):
        if self.target is None:self.target=(float(x),float(y));return
        amount=1-math.exp(-14*max(0.,dt))
        self.target=(self.target[0]+(x-self.target[0])*amount,self.target[1]+(y-self.target[1])*amount)

    @staticmethod
    def offset(dx,dy,width,height):
        length=max(1.,math.hypot(dx,dy))
        return dx/length*width*.22,dy/length*height*.13

    def gaze_offsets(self, eyes, origin, logical_size, angles=None):
        """Stylized depth: each eye looks from its own center to one target.

        Screen distance is a depth cue, not a measurement of real 3D distance.
        Near the face, vergence increases; distant targets become parallel.
        """
        if not eyes or self.target is None:
            return []
        scale = logical_size / 512
        centers = [(origin[0]+(x+w/2)*scale, origin[1]+(y+h/2)*scale)
                   for x,y,w,h in eyes]
        cx = sum(x for x,y in centers)/len(centers)
        cy = sum(y for x,y in centers)/len(centers)
        distance = math.hypot(self.target[0]-cx, self.target[1]-cy)
        focus = 1/(1+(distance/max(1.,logical_size*.45))**2)
        depth = max(1., logical_size*.18 + distance*.65)
        result = []
        for index, ((sx,sy), (_,_,w,h)) in enumerate(zip(centers,eyes)):
            dx,dy = self.target[0]-sx,self.target[1]-sy
            length = math.sqrt(dx*dx+dy*dy+depth*depth)
            angle = math.radians(angles[index] if angles else 0.)
            local_x = dx*math.cos(angle)+dy*math.sin(angle)
            local_y = -dx*math.sin(angle)+dy*math.cos(angle)
            ox,oy = self.offset(local_x/length,local_y/length,w,h)
            result.append((ox,oy,focus))
        return result

    def eye_geometry(self, image, key, eyes):
        """Conservative aperture from authored iris pixels; never paint fur/lids."""
        cache_key=(image.cacheKey(),key,tuple(tuple(e) for e in eyes))
        if cache_key in self.mask_cache:return self.mask_cache[cache_key]
        ratio=image.width()/512
        pair_angle=None
        if len(eyes)==2:
            ordered=sorted(eyes,key=lambda e:e[0]+e[2]/2)
            a,b=ordered
            pair_angle=math.degrees(math.atan2(b[1]+b[3]/2-a[1]-a[3]/2,
                                               b[0]+b[2]/2-a[0]-a[2]/2))
        geometries=[]
        for x,y,w,h in eyes:
            path=QPainterPath()
            dark=[]
            outline=[]
            for py in range(max(0,math.ceil(y*ratio)),min(image.height(),math.floor((y+h)*ratio))):
                colored=[]
                for px in range(max(0,math.ceil(x*ratio)),min(image.width(),math.floor((x+w)*ratio))):
                    c=image.pixelColor(px,py)
                    r,g,b=c.red(),c.green(),c.blue()
                    if c.alpha()>220 and 65<g<225 and 65<r<245 and -12<r-g<38 and g-b>24:
                        colored.append(px)
                if len(colored)<2:continue
                # Fill the iris interior, including its dark pupil; keep a small
                # inset from the authored edge so antialiasing never eats eyelids.
                lo,hi=min(colored)+.5,max(colored)-.5
                if hi<=lo:continue
                outline.extend(((lo/ratio,py/ratio),(hi/ratio,(py+1)/ratio)))
                for px in range(math.ceil(lo),math.floor(hi)+1):
                    c=image.pixelColor(px,py)
                    if max(c.red(),c.green(),c.blue())<75:
                        dark.append((px/ratio,py/ratio))
            # A convex iris envelope bridges pupil/highlight gaps without the
            # horizontal scan-line seams of a disconnected pixel mask.
            points=sorted(set(outline))
            if len(points)>=3:
                def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
                lower=[];upper=[]
                for p in points:
                    while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
                    lower.append(p)
                for p in reversed(points):
                    while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
                    upper.append(p)
                path.addPolygon(QPolygonF([QPointF(*p) for p in lower[:-1]+upper[:-1]]))
                path.closeSubpath()
            # The color-derived footprint is additionally inset from the annotation
            # boundary, avoiding hard rectangular cuts from imperfect legacy boxes.
            inset=QPainterPath();inset.addEllipse(QRectF(x+1,y+1,max(1,w-2),max(1,h-2)))
            path=path.intersected(inset)
            angle=pair_angle if pair_angle is not None else 0.
            if pair_angle is None and len(dark)>=8:
                cx=sum(p[0] for p in dark)/len(dark);cy=sum(p[1] for p in dark)/len(dark)
                xx=sum((a-cx)**2 for a,b in dark);yy=sum((b-cy)**2 for a,b in dark)
                xy=sum((a-cx)*(b-cy) for a,b in dark)
                # A clearly elongated authored pupil supplies the profile tilt.
                gap=math.hypot(xx-yy,2*xy)
                if gap/max(1.,xx+yy)>.35:
                    axis=math.degrees(.5*math.atan2(2*xy,xx-yy))
                    candidate=(axis-90+90)%180-90
                    if abs(candidate)<=25:angle=candidate
            # Profile run art has deliberately different head pitches per frame.
            # Explicit references avoid mistaking an eyelid for a diagonal pupil.
            profile_angles={
                'run_left': (0,0,5,5,10,10,0,-8),
                'run_right': (0,-5,0,0,-8,-8,0,-12),
            }
            family,_,frame=key.partition('/')
            if family in profile_angles and frame.isdigit():
                angle=profile_angles[family][int(frame)%8]
            geometries.append((path,angle))
        if len(self.mask_cache)>=128:self.mask_cache.clear()
        self.mask_cache[cache_key]=geometries
        return geometries

    def paint(self, image, key, origin, logical_size):
        eyes=self.catalog.get(key,[])
        if not self.enabled or self.target is None or not eyes:return image
        geometry=self.eye_geometry(image,key,eyes)
        offsets=self.gaze_offsets(eyes,origin,logical_size,[angle for _,angle in geometry])
        result=image.copy()
        painter=QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(image.width()/512,image.height()/512)
        for (x,y,w,h), (path,angle), (ox,oy,focus) in zip(eyes,geometry,offsets):
            if path.isEmpty():continue
            painter.save();painter.setClipPath(path)
            # Warm, subdued sclera appears only as a narrow crescent when looking
            # sideways. The original eye contour is the mask, not a new ellipse.
            painter.fillPath(path,QColor('#d4ceb3'))
            painter.translate(x+w/2,y+h/2)
            painter.rotate(angle)
            iris=QRectF(-w*.48+ox,-h*.60+oy,w*.96,h*1.20)
            gradient=QRadialGradient(ox-w*.12,oy-h*.15,max(w,h)*.62)
            gradient.setColorAt(0,QColor('#d5c77d'))
            gradient.setColorAt(.65,QColor('#a69e60'))
            gradient.setColorAt(1,QColor('#706b3f'))
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(gradient)
            painter.drawEllipse(iris)
            pupil_width=w*(.30+.06*focus)
            pupil=QRectF(ox-pupil_width/2,-h*.40+oy,pupil_width,h*.80)
            painter.setBrush(QColor('#202019'));painter.drawEllipse(pupil)
            painter.setBrush(QColor(255,253,220,225))
            painter.drawEllipse(QRectF(pupil.x()+w*.05,pupil.y()+h*.12,
                                       max(1.2,w*.10),max(1.5,h*.13)))
            painter.restore()
        painter.end()
        return result
