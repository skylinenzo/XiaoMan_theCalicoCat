"""Eight registered drawings, support-aligned in-betweens, one opaque coat.

Premultiplied interpolation never shows an empty frame. Both drawings are warped
to the same stance contact before blending; head/torso/tail pixels stay fixed.
"""
import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPolygonF

from anchored_walk import AnchoredCycle
from deform_renderer import smooth, triangle_transform

ROOT = Path(__file__).resolve().parent / 'output/imagegen'


def mix(first, second, amount):
    if amount <= 0:
        return first
    if amount >= 1:
        return second
    result = QImage(first.size(), QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.setOpacity(1 - amount)
    painter.drawImage(0, 0, first)
    painter.end()
    weighted = QImage(first.size(), QImage.Format.Format_ARGB32_Premultiplied)
    weighted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(weighted)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.setOpacity(amount)
    painter.drawImage(0, 0, second)
    painter.end()
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    # Weight BEFORE Plus: Qt otherwise saturates src+dst before applying opacity,
    # causing a large alpha dip and bright flashes midway through every transition.
    painter.drawImage(0, 0, weighted)
    painter.end()
    return result


def walking_point(side, phase, x, y, foot_dx, contact_anchor=None):
    """Connected body/tail motion, fading to exactly zero at grounded soles."""
    phase %= 1.
    angle = 2 * math.pi * phase
    leg_weight = smooth((y - 380) / 80)
    body_weight = 1 - smooth((y - 360) / 120)
    bob = -1.8 * (1 - math.cos(2 * angle)) / 2
    tail_x = (1 - smooth((x - 140) / 45) if side == 'right'
              else smooth((x - 327) / 45))
    tail_weight = tail_x * (1 - smooth((y - 130) / 170))
    sway = 10 * (math.sin(angle) + .25 * math.sin(2 * angle)) / 1.25
    shifted = x + foot_dx * leg_weight + sway * tail_weight
    if contact_anchor is not None and leg_weight > 0:
        # Torso compensation can push the farthest swing toe past the canvas.
        # Compress only that outer margin, outside the pinned contact. A shared
        # monotone map keeps the limb connected and never shifts the anchor.
        edge_shift = foot_dx * leg_weight
        if edge_shift > 0:
            start = max(440., contact_anchor + 16)
            if shifted > start and start < 512:
                shifted = start + (shifted - start) * (512 - start) / (512 + edge_shift - start)
        elif edge_shift < 0:
            start = min(72., contact_anchor - 16)
            if shifted < start and start > 0:
                shifted = start + (shifted - start) * start / (start - edge_shift)
    return shifted, y + bob * body_weight


def warp_lower(texture, dx, soles=(), size=512, motion=None, contact_anchor=None):
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.scale(size / 512, size / 512)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if motion is None:
        painter.drawImage(QRectF(0, 0, 512, 380), texture, QRectF(0, 0, 512, 380))
    soles = sorted(soles)
    xs = sorted(set(list(range(0, 513, 32 if motion else 64)) + [p[0] for p in soles]))
    if motion is not None and contact_anchor is not None:
        # Put the measured source contact on a mesh vertex so interpolation
        # across the outer-margin correction cannot pull it off its anchor.
        source_contact = contact_anchor - dx
        if 0 < source_contact < 512:
            xs = sorted(set(xs + [source_contact]))
    ys = (tuple(range(0, 361, 24)) + (380, 400, 420, 440, 460, 480, 490, 512)
          if motion else (380, 400, 420, 440, 460, 512))
    def target(x, y):
        if motion is not None:
            return walking_point(*motion, x, y, dx, contact_anchor)
        strength = smooth((y - 380) / 80)
        floor = 490.
        if soles:
            a, b = soles[0], soles[-1]
            t = min(1., max(0., (x - a[0]) / max(1., b[0] - a[0])))
            floor = a[1] * (1 - t) + b[1] * t
        return x + dx * strength, y + (490 - floor) * strength
    for top, bottom in zip(ys, ys[1:]):
        for left, right in zip(xs, xs[1:]):
            corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
            for indices in ((0, 1, 2), (0, 2, 3)):
                source = [corners[i] for i in indices]
                destination = [target(*p) for p in source]
                painter.save()
                clip = QPainterPath()
                clip.addPolygon(QPolygonF([QPointF(*p) for p in destination]))
                clip.closeSubpath()
                painter.setClipPath(clip)
                painter.setWorldTransform(triangle_transform(source, destination), True)
                painter.drawImage(0, 0, texture)
                painter.restore()
    painter.end()
    return image


def stabilize_coat(frame, reference):
    mask = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
    # Fade inside the torso, ABOVE the moving leg attachments. This avoids both
    # a horizontal silhouette seam and remnants of the reference frame's legs.
    gradient = QLinearGradient(0, 320, 0, 380)
    gradient.setColorAt(0, QColor(255, 255, 255, 255))
    gradient.setColorAt(1, QColor(255, 255, 255, 0))
    mask.fill(Qt.GlobalColor.transparent)
    p = QPainter(mask)
    p.fillRect(mask.rect(), gradient)
    p.end()
    fixed = reference.copy()
    p = QPainter(fixed)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.drawImage(0, 0, mask)
    p.end()
    result = frame.copy()
    p = QPainter(result)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    p.drawImage(0, 0, mask)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.drawImage(0, 0, fixed)
    p.end()
    return result


class AnchoredWalk:
    def __init__(self, folders=None):
        self.frames, self.cycles, self.blend_poses = {}, {}, {}
        for side in ('left', 'right'):
            folder = ROOT / (folders[side] if folders else f'walk-{side}-v3')
            metadata = json.loads((folder / 'animation.json').read_text())
            self.cycles[side] = AnchoredCycle(metadata)
            self.blend_poses[side] = metadata.get('blend_poses', True)
            frames = [QImage(str(folder / name)).convertToFormat(
                QImage.Format.Format_ARGB32_Premultiplied) for name in metadata['frames']]
            if any(frame.isNull() for frame in frames):
                raise RuntimeError(f'找不到走路素材：{folder}')
            normalized = ([warp_lower(frame, metadata['lower_offsets'][i], metadata['support_soles'][i])
                           for i, frame in enumerate(frames)]
                          if metadata.get('normalize_soles', True) else
                          [warp_lower(frame, metadata['lower_offsets'][i])
                           for i, frame in enumerate(frames)])
            self.frames[side] = [stabilize_coat(frame, normalized[0]) for frame in normalized]

    def render(self, side, seconds, size):
        cycle = self.cycles[side]
        first, second, u, _, anchor, segment = cycle.sample(seconds)
        a, b = cycle.anchors[segment]
        a += cycle.offsets[first]
        b += cycle.offsets[second]
        if self.blend_poses[side]:
            left = warp_lower(self.frames[side][first], anchor - a, size=size)
            right = warp_lower(self.frames[side][second], anchor - b, size=size)
            result = mix(left, right, u)
        else:
            # The new drawings have deliberately different swing silhouettes.
            # Select one whole pose; blending would show translucent extra legs.
            # Both poses meet at the same grounded contact at the switch.
            index, contact = (first, a) if u < .5 else (second, b)
            motion = (side, seconds / cycle.duration) if cycle.steady_body else None
            result = warp_lower(self.frames[side][index], anchor - contact, size=size,
                                motion=motion, contact_anchor=anchor)
        if cycle.steady_body:
            return result
        # Do not repeatedly quantize the unchanged coat through two alpha weights.
        # Copy its pixels once, so even translucent whiskers have constant opacity.
        p = QPainter(result)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(0, 0, size, 320 * size / 512), self.frames[side][0], QRectF(0, 0, 512, 320))
        p.end()
        return result
