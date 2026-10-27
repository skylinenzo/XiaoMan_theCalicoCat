"""Independent, clipped iris/pupil controls, expressed in 512px pose coordinates."""
import json
import math
from pathlib import Path
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient

class EyeControl:
    def __init__(self):
        path=Path(__file__).resolve().parent/'assets/eye-catalog.json'
        self.catalog=json.loads(path.read_text()) if path.exists() else {}
        self.enabled=True
        self.target=None

    def follow(self, x, y, dt):
        if self.target is None:self.target=(float(x),float(y));return
        amount=1-math.exp(-14*max(0.,dt))
        self.target=(self.target[0]+(x-self.target[0])*amount,self.target[1]+(y-self.target[1])*amount)

    @staticmethod
    def offset(dx,dy,width,height):
        length=max(1.,math.hypot(dx,dy))
        return dx/length*width*.22,dy/length*height*.13

    def paint(self, image, key, origin, logical_size):
        eyes=self.catalog.get(key,[])
        if not self.enabled or self.target is None or not eyes:return image
        result=image.copy()
        painter=QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(image.width()/512,image.height()/512)
        for x,y,w,h in eyes:
            # Coordinates describe the inner iris, leaving authored eyelids intact.
            eye=QRectF(x,y,w,h)
            path=QPainterPath();path.addEllipse(eye)
            painter.save();painter.setClipPath(path)
            gradient=QRadialGradient(x+w*.45,y+h*.4,max(w,h)*.8)
            gradient.setColorAt(0,QColor('#c9ba72'));gradient.setColorAt(.65,QColor('#a69e60'))
            gradient.setColorAt(1,QColor('#706b3f'))
            painter.fillPath(path,gradient)
            sx=origin[0]+(x+w/2)*logical_size/512
            sy=origin[1]+(y+h/2)*logical_size/512
            dx=(self.target[0]-sx)/max(100.,logical_size)
            dy=(self.target[1]-sy)/max(100.,logical_size)
            ox,oy=self.offset(dx,dy,w,h)
            pupil=QRectF(x+w*.32+ox,y+h*.1+oy,w*.36,h*.8)
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#202019'));painter.drawEllipse(pupil)
            painter.setBrush(QColor(255,253,220,225))
            painter.drawEllipse(QRectF(pupil.x()+w*.05,pupil.y()+h*.12,max(1.2,w*.10),max(1.5,h*.13)))
            painter.restore()
        painter.end()
        return result
