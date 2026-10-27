"""Continuous, shared-vertex deformation of ONE intact texture per side.

No limb cutouts or replacement drawings: a smooth cage moves the lower mesh,
with the head/upper coat pinned. Modest steps avoid changing limb occlusion,
which a single drawing cannot represent. Qt alone renders the textured mesh.
"""
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPolygonF, QTransform

ROOT = Path(__file__).resolve().parent / 'output/imagegen'
STRIDE = 88.


def smooth(value):
    value = min(1., max(0., value))
    return value * value * (3 - 2 * value)


# Toe x, attachment x, phase, amplitude. Measured independently on each image.
CAGES = {
    'left': ((61, 135, 0., 24), (194, 170, .5, 16),
             (251, 270, .25, 16), (385, 317, .75, 24)),
    'right': ((79, 174, .75, 24), (254, 222, .25, 16),
              (315, 338, .5, 16), (443, 357, 0., 24)),
}


def deform_point(side, x, y, phase):
    """A continuous displacement field, shared by every adjacent triangle."""
    if y <= 352:
        return x, y
    phase %= 1.
    strength = smooth((y - 352) / 112)
    centers, deltas = [], []
    direction = -1 if side == 'left' else 1
    for toe, root, offset, amplitude in CAGES[side]:
        centers.append(root + (toe - root) * strength)
        angle = 2 * math.pi * ((phase + offset) % 1.)
        deltas.append((direction * amplitude * math.cos(angle),
                       -15 * max(0., -math.sin(angle)) ** 2))
    dx, dy = deltas[0]
    if x >= centers[-1]:
        dx, dy = deltas[-1]
    else:
        for index in range(3):
            if centers[index] <= x < centers[index + 1]:
                t = smooth((x - centers[index]) / (centers[index + 1] - centers[index]))
                dx = deltas[index][0] * (1 - t) + deltas[index + 1][0] * t
                dy = deltas[index][1] * (1 - t) + deltas[index + 1][1] * t
                break
    # Keep the original tail in the same surface; fade leg influence away there.
    tail = smooth((x - 345) / 105) if side == 'left' else smooth((155 - x) / 105)
    tail *= smooth((y - 352) / 35) * (1 - smooth((y - 435) / 25))
    return (x + dx * strength * (1 - tail),
            y + dy * strength * (1 - tail) + 5 * tail * math.sin(2 * math.pi * phase))


def triangle_transform(source, target):
    """Affine map through three vertices (QTransform uses row-vector notation)."""
    a, b, c = source
    u, v, w = target
    bx, by, cx, cy = b[0] - a[0], b[1] - a[1], c[0] - a[0], c[1] - a[1]
    det = bx * cy - by * cx
    vx, vy, wx, wy = v[0] - u[0], v[1] - u[1], w[0] - u[0], w[1] - u[1]
    m11, m21 = (vx * cy - wx * by) / det, (wx * bx - vx * cx) / det
    m12, m22 = (vy * cy - wy * by) / det, (wy * bx - vy * cx) / det
    return QTransform(m11, m12, m21, m22,
                      u[0] - m11 * a[0] - m21 * a[1],
                      u[1] - m12 * a[0] - m22 * a[1])


class DeformCat:
    def __init__(self):
        self.textures = {}
        for side in ('left', 'right'):
            path = ROOT / f'walk-{side}-v2/frame-01.png'
            image = QImage(str(path)).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            if image.isNull():
                raise RuntimeError(f'找不到变形素材：{path}')
            self.textures[side] = image
        # A single connected surface; top is rigid, bottom has a 16-pixel grid.
        self.vertices = [(x, y) for y in range(352, 513, 16) for x in range(0, 513, 16)]
        self.triangles = []
        for row in range(10):
            for col in range(32):
                a = row * 33 + col
                self.triangles.extend(((a, a + 1, a + 34), (a, a + 34, a + 33)))

    def mesh(self, side, phase):
        return [deform_point(side, x, y, phase) for x, y in self.vertices]

    def render(self, side, phase, size=512):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(size / 512, size / 512)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Raster clips share exact vertices. Do not antialias triangle boundaries:
        # those are internal edges, not silhouette edges. Source avoids alpha buildup.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        texture = self.textures[side]
        painter.drawImage(QRectF(0, 0, 512, 352), texture, QRectF(0, 0, 512, 352))
        target = self.mesh(side, phase)
        for indices in self.triangles:
            source_tri = [self.vertices[i] for i in indices]
            target_tri = [target[i] for i in indices]
            painter.save()
            # Clip in destination space before applying the texture transform.
            clip = QPainterPath()
            clip.addPolygon(QPolygonF([QPointF(*point) for point in target_tri]))
            clip.closeSubpath()
            painter.setClipPath(clip)
            painter.setWorldTransform(triangle_transform(source_tri, target_tri), True)
            painter.drawImage(0, 0, texture)
            painter.restore()
        painter.end()
        return image

    def draw(self, painter, side, phase, size=512):
        painter.drawImage(0, 0, self.render(side, phase, size))
