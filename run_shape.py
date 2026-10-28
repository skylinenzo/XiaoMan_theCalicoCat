"""Normalize shoulder-to-hip length, keeping head and tail proportions intact."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

# Shoulder/hip landmarks in the original 512px artwork, one pair per frame.
LANDMARKS = {
    'run_left': list(zip([225,230,228,224,233,235,236,220],
                         [365,355,350,353,354,365,375,355])),
    'run_right': list(zip([150,145,153,150,150,145,145,150],
                          [320,305,310,310,310,330,340,315])),
}
TORSO_LENGTH = 175.


def coordinate(x, left, right):
    midpoint = (left+right)/2
    start = midpoint-TORSO_LENGTH/2
    end = midpoint+TORSO_LENGTH/2
    if x <= left:
        return x + start-left
    if x >= right:
        return x + end-right
    return start + (x-left)*TORSO_LENGTH/(right-left)


def normalize_run(state, frames, metadata, scale):
    if state not in LANDMARKS:
        return frames, metadata
    result, eyes, contacts = [], [], []
    for index, (frame, (left, right)) in enumerate(zip(frames, LANDMARKS[state])):
        left, right = 256+(left-256)*scale, 256+(right-256)*scale
        target = QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied)
        target.fill(Qt.GlobalColor.transparent)
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Continuous mapping across three adjoining regions; no detached limbs.
        for a,b in ((0,left),(left,right),(right,512)):
            x1,x2 = coordinate(a,left,right),coordinate(b,left,right)
            painter.drawImage(QRectF(x1,0,x2-x1,512),frame,QRectF(a,0,b-a,512))
        painter.end()
        result.append(target)
        eyes.append([[coordinate(x,left,right),y,
                      coordinate(x+w,left,right)-coordinate(x,left,right),h]
                     for x,y,w,h in metadata.get('eye_rects',[[]]*len(frames))[index]])
        if metadata.get('contact_x'):
            contacts.append(coordinate(metadata['contact_x'][index],left,right))
    meta = dict(metadata, eye_rects=eyes)
    if contacts:
        meta['contact_x'] = contacts
    return result, meta
