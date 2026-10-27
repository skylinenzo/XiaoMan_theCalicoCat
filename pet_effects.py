"""Soft grounding shadows and a small, stable spring for a carried cat."""

import math
from numbers import Integral


def contact_shadow(size, state, floor_ratio=490 / 512, opacity=1.0):
    """Return a transparent premultiplied QImage containing a soft contact ellipse.

    ``size`` accepts a square pixel count, ``(width, height)``, or ``QSize``.
    Resting bodies spread the shadow; sitting narrows it. A window perch uses
    its raised contact line at 477/512. Held/free poses have no contact shadow.
    The shadow is procedural and can be cached by the caller for each size/state.
    """
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QRadialGradient

    if isinstance(size, Integral):
        width = height = int(size)
    elif hasattr(size, 'width') and hasattr(size, 'height'):
        width, height = size.width(), size.height()
    else:
        width, height = size
    if (not isinstance(width, Integral) or not isinstance(height, Integral)
            or width <= 0 or height <= 0):
        raise ValueError('Shadow dimensions must be positive integers')
    if not math.isfinite(floor_ratio) or not 0 <= floor_ratio <= 1:
        raise ValueError('Shadow floor ratio must be between zero and one')
    if not math.isfinite(opacity):
        raise ValueError('Shadow opacity must be finite')
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    opacity = max(0., min(1., opacity))
    if state in ('held', 'free', 'jump_air') or opacity == 0:
        return image

    if state == 'window_perch':
        radius_x, radius_y, floor_ratio = .37, .009, 477 / 512
    elif state == 'window_straddle':
        radius_x, radius_y = .34, .009
    elif state.startswith('jump_'):
        radius_x, radius_y = .37, .014
    elif state.startswith('rest_'):
        radius_x, radius_y = .43, .013
    elif state.startswith('walk_'):
        radius_x, radius_y = .37, .018
    else:  # Seated idle and grooming share a compact support area.
        radius_x, radius_y = .245, .022
    center_x, center_y = width / 2., height * floor_ratio
    radius_x *= width
    # Keep the complete fade within the texture, even at custom floor positions.
    radius_y = min(height * radius_y, center_y - .5, height - .5 - center_y)
    if radius_y <= 0:
        return image

    gradient = QRadialGradient(QPointF(0., 0.), 1.)
    for radius, strength in ((0., 1.), (.25, .86), (.5, .52),
                             (.75, .16), (.9, .025), (1., 0.)):
        gradient.setColorAt(radius, QColor(39, 31, 35, round(64 * opacity * strength)))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.translate(center_x, center_y)
    painter.scale(radius_x, radius_y)
    painter.setBrush(gradient)
    painter.drawEllipse(QRectF(-1., -1., 2., 2.))
    painter.end()
    return image


class HeldSway:
    """A damped roll spring that responds to horizontal mouse movement.

    Feed each frame's mouse displacement, not its absolute position. Motion to
    the right makes the lower body lag left (positive Qt degrees). Vertical motion
    deliberately introduces no roll. Exact spring integration stays stable even
    after a slow frame, and zero input naturally settles back to upright.
    """

    def __init__(self, max_angle=10.0):
        if not math.isfinite(max_angle) or max_angle <= 0:
            raise ValueError('Maximum sway angle must be finite and positive')
        self.max_angle = float(max_angle)
        self.angle = 0.
        self.velocity = 0.

    def reset(self):
        self.angle = 0.
        self.velocity = 0.

    def update(self, dt, mouse_dx, mouse_dy=0):
        """Advance by seconds and return degrees, bounded by ``max_angle``."""
        if not all(math.isfinite(value) for value in (dt, mouse_dx, mouse_dy)):
            raise ValueError('Sway time and mouse displacement must be finite')
        if dt <= 0:
            return self.angle
        target = max(-self.max_angle, min(self.max_angle, mouse_dx / dt * .022))
        frequency, damping = 10., .72
        decay = damping * frequency
        oscillation = frequency * math.sqrt(1. - damping * damping)
        displacement = self.angle - target
        sine_coefficient = (self.velocity + decay * displacement) / oscillation
        fade = math.exp(-decay * dt)
        cosine, sine = math.cos(oscillation * dt), math.sin(oscillation * dt)
        motion = displacement * cosine + sine_coefficient * sine
        self.angle = target + fade * motion
        self.velocity = fade * (
            -decay * motion + oscillation * (sine_coefficient * cosine - displacement * sine))
        self.angle = max(-self.max_angle, min(self.max_angle, self.angle))
        # A hard limit may absorb outward velocity, but must allow inward return.
        if abs(self.angle) == self.max_angle and self.angle * self.velocity > 0:
            self.velocity = 0.
        return self.angle
