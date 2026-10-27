"""Verify deformation topology and actual Qt raster output, not just pose math."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import math
import unittest

try:
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
    from deform_renderer import DeformCat, deform_point
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'PySide6 is required for deform rendering')
class DeformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.cat = DeformCat()

    def test_mesh_does_not_fold_and_loop_has_no_jump(self):
        for side in ('left', 'right'):
            for step in range(120):
                points = self.cat.mesh(side, step / 120)
                for a, b, c in self.cat.triangles:
                    x, y = points[a]
                    u, v = points[b]
                    w, z = points[c]
                    self.assertGreater((u - x) * (z - y) - (v - y) * (w - x), 100)
            for x, y in self.cat.vertices:
                self.assertLess(math.dist(deform_point(side, x, y, 1 - 1e-7),
                                          deform_point(side, x, y, 1e-7)), .001)

    def test_coat_stability_transparency_moving_legs_and_exact_loop(self):
        for side in ('left', 'right'):
            initial = self.cat.render(side, 0)
            self.assertEqual(initial, self.cat.render(side, 1))
            for i in range(1, 24):
                frame = self.cat.render(side, i / 24)
                self.assertEqual(frame.copy(0, 0, 512, 352), initial.copy(0, 0, 512, 352))
                self.assertNotEqual(frame.copy(0, 400, 512, 112), initial.copy(0, 400, 512, 112))
                self.assertEqual(frame.pixelColor(0, 0).alpha(), 0)
            self.assertEqual(initial.copy(0, 0, 512, 352), self.cat.textures[side].copy(0, 0, 512, 352))
        self.assertNotEqual(self.cat.textures['left'], self.cat.textures['right'].mirrored(True, False))

    def test_internal_triangle_edges_have_no_cracks_or_alpha_buildup(self):
        cat = DeformCat()
        # Uniform translucent texture makes both gaps and double-painted seams visible.
        texture = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
        texture.fill(QColor(120, 80, 40, 160))
        cat.textures = {'left': texture, 'right': texture}
        for size in (160, 220, 300):
            for side in ('left', 'right'):
                for step in range(12):
                    image = cat.render(side, step / 12, size)
                    for y in range(round(size * 340 / 512), round(size * 485 / 512)):
                        for x in range(round(size * 40 / 512), round(size * 470 / 512)):
                            self.assertEqual(image.pixelColor(x, y).alpha(), 160,
                                             (side, size, step, x, y))


if __name__ == '__main__':
    unittest.main()
