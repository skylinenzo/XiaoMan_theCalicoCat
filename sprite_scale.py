"""Visual calibration against the preferred eight-frame walk and seated head.

Scale complete poses around contact lines; never equalize crouching/standing
bounding-box height, mirror coats or alter the walking support mesh.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

FACTORS = {'idle':1., 'groom':.96, 'rest_prone':1., 'rest_supine':1., 'rest_side':1.,
           'held':.94, 'window_perch':1., 'window_straddle':1., 'jump_down':1.06,
           'window_climb':1.06, 'window_climb_back':1.16, 'window_climb_side':1.23,
           'turn':1., 'walk':1.}
# Compare head/torso proportions at the same logical canvas, not silhouette
# height: a crouch or a stretched gallop must remain a different shape.
FACTORS.update(run_left=.90, run_right=1.08, pounce_left=.92,
               pounce_right=1., play_kick=.94, play_lick=.94)

def calibrate(image, factor, baseline=490.):
    if factor == 1.:return image
    result=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    painter=QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRectF(256*(1-factor),baseline*(1-factor),512*factor,512*factor),image)
    painter.end()
    return result

def calibrate_animation(state, frames, metadata):
    factor=FACTORS.get(state,1.)
    meta=dict(metadata)
    baseline=meta.get('contact_baseline_y') or 490.
    if 'contact_baselines_y' in meta:
        baseline=490.
        meta['contact_baselines_y']=[baseline+(a-baseline)*factor for a in meta['contact_baselines_y']]
    if meta.get('pivot_px'):
        x,y=meta['pivot_px'];meta['pivot_px']=[256+(x-256)*factor,baseline+(y-baseline)*factor]
    if meta.get('eye_rects'):
        meta['eye_rects'] = [[[256+(x-256)*factor, baseline+(y-baseline)*factor,
                               w*factor, h*factor] for x,y,w,h in eyes]
                             for eyes in meta['eye_rects']]
    if meta.get('contact_x'):
        meta['contact_x'] = [256+(x-256)*factor for x in meta['contact_x']]
    return [calibrate(f,factor,baseline) for f in frames],meta
