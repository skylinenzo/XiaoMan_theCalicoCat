import unittest
from eyes import EyeControl


class EyeFocusTests(unittest.TestCase):
    eyes = [[200,250,30,20], [280,250,30,20]]

    def test_near_center_converges_and_far_target_reduces_vergence(self):
        gaze = EyeControl()
        gaze.target = (255,260)
        near = gaze.gaze_offsets(self.eyes,(0,0),512)
        self.assertGreater(near[0][0],0)
        self.assertLess(near[1][0],0)
        gaze.target = (255,-2000)
        far = gaze.gaze_offsets(self.eyes,(0,0),512)
        self.assertGreater(near[0][2],far[0][2])
        self.assertLess(abs(far[0][0]-far[1][0]),abs(near[0][0]-near[1][0]))

    def test_single_profile_eye_and_extreme_targets_stay_bounded(self):
        gaze = EyeControl()
        for target in ((-100000,0),(100000,100000),(215,260)):
            gaze.target=target
            ox,oy,focus=gaze.gaze_offsets(self.eyes[:1],(0,0),512)[0]
            self.assertLessEqual((ox/(30*.22))**2+(oy/(20*.13))**2,1.00001)
            self.assertTrue(0<=focus<=1)

    def test_focus_is_invariant_under_logical_scale_and_origin(self):
        gaze = EyeControl();gaze.target=(255,270)
        original=gaze.gaze_offsets(self.eyes,(0,0),512)
        gaze.target=(100+255*.5,200+270*.5)
        scaled=gaze.gaze_offsets(self.eyes,(100,200),256)
        for a,b in zip(original,scaled):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y)

    def test_world_direction_is_rotated_into_head_coordinates(self):
        gaze=EyeControl();gaze.target=(1000,260)
        ox,oy,_=gaze.gaze_offsets(self.eyes[:1],(0,0),512,[90])[0]
        self.assertAlmostEqual(ox,0,places=6)
        self.assertLess(oy,0)

    def test_tilted_aperture_preserves_lids_and_fur(self):
        import math
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QImage,QPainter,QColor
        image=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor('#77503d'))
        eyes=[[100,100,40,28],[180,140,40,28]]
        painter=QPainter(image)
        painter.setBrush(QColor('#b9ac65'))
        for x,y,w,h in eyes:painter.drawEllipse(QRectF(x+3,y+3,w-6,h-6))
        painter.end()
        gaze=EyeControl();gaze.catalog={'tilt':eyes};gaze.target=(350,160)
        geometry=gaze.eye_geometry(image,'tilt',eyes)
        for _,angle in geometry:self.assertAlmostEqual(angle,math.degrees(math.atan2(40,80)))
        changed=gaze.paint(image,'tilt',(0,0),512)
        self.assertNotEqual(image,changed)
        # Warm fur inside the annotation box is not part of the aperture.
        for x,y,w,h in eyes:
            for px,py in ((x,y),(x+1,y+1),(x+w-1,y+h-1)):
                self.assertEqual(image.pixel(px,py),changed.pixel(px,py))

    def test_no_iris_pixels_means_no_repaint(self):
        from PySide6.QtGui import QImage,QColor
        image=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor('#50352b'))
        gaze=EyeControl();gaze.catalog={'closed':self.eyes};gaze.target=(100,200)
        self.assertEqual(image,gaze.paint(image,'closed',(0,0),512))
