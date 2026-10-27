"""Fixed texture parts driven by articulated bones; no walking frame swaps."""
import math
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from bones import leg_pose

ROOT = Path(__file__).resolve().parent / 'assets/rig'


class CatRig:
    def __init__(self):
        self.parts = {}
        for side in ('left', 'right'):
            textures = {}
            for name in ('body', 'tail', 'front_upper', 'front_lower', 'hind_upper', 'hind_lower'):
                image = QImage(str(ROOT / side / f'{name}.png'))
                if image.isNull():
                    raise RuntimeError(f'找不到骨骼素材：{ROOT / side / name}')
                textures[name] = image
            for limb in ('front', 'hind'):
                lower = textures[f'{limb}_lower']
                textures[f'{limb}_shin'] = lower.copy(0, 0, lower.width(), round(lower.height() * .76))
                start = round(lower.height() * .66)
                textures[f'{limb}_paw'] = lower.copy(0, start, lower.width(), lower.height() - start)
                for part in ('upper', 'shin', 'paw'):
                    image = textures[f'{limb}_{part}'].convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                    painter = QPainter(image)
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                    painter.fillRect(image.rect(), QColor(51, 43, 39, 48))
                    painter.end()
                    textures[f'{limb}_{part}_far'] = image
            self.parts[side] = textures

    @staticmethod
    def bone(painter, image, start, end, width):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        painter.save()
        painter.translate(*start)
        painter.rotate(math.degrees(math.atan2(dy, dx)) - 90)
        painter.drawImage(QRectF(-width / 2, -9, width, length + 18), image)
        painter.restore()

    def draw(self, painter, side, phase, size=512):
        textures = self.parts[side]
        left = side == 'left'
        def point(p):
            return (512 - p[0], p[1]) if left else p
        painter.save()
        painter.scale(size / 512, size / 512)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        def leg(front, far):
            limb = 'front' if front else 'hind'
            suffix = '_far' if far else ''
            root, knee, foot = [point(p) for p in leg_pose(phase, front, far)]
            # Constant foot orientation avoids rotating toes through the floor.
            foot_width = 40 if front else 44
            shin_end = (foot[0] + (knee[0] - foot[0]) * .14,
                        foot[1] + (knee[1] - foot[1]) * .14)
            self.bone(painter, textures[f'{limb}_shin{suffix}'], knee, shin_end, 32 if front else 34)
            painter.drawImage(QRectF(foot[0] - foot_width / 2, foot[1] - 16, foot_width, 30),
                              textures[f'{limb}_paw{suffix}'])
            self.bone(painter, textures[f'{limb}_upper{suffix}'], root, knee, 48 if front else 64)

        leg(False, True)
        leg(True, True)
        # Tail bone shares the rump root; the two side textures are independent.
        tail_root = point((155, 357))
        painter.save()
        painter.translate(*tail_root)
        painter.rotate((1 if left else -1) * (3 + 4 * math.sin(2 * math.pi * phase)))
        painter.drawImage(QRectF(-5 if left else -100, -12, 105, 58), textures['tail'])
        painter.restore()
        leg(False, False)
        leg(True, False)
        # Torso hides the shoulder/hip attachment caps; no gaps at bone roots.
        painter.drawImage(QRectF(77 if left else 105, 155, 330, 260), textures['body'])
        painter.restore()
