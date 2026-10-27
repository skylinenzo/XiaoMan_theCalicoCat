import unittest
from desktop_route import Surface
from mouse_hunt import MouseHunt
import test_interaction_integration as fixtures

class HuntTests(unittest.TestCase):
    def test_short_pounce_lands_and_cools_down(self):
        hunt=MouseHunt();lane=Surface('a',0,0,1000,800,797);x=400;seen=set()
        for _ in range(110):
            x=hunt.step(.05,x,(550,760),lane,220);seen.add(hunt.state)
            self.assertGreaterEqual(x,0);self.assertLessEqual(x,780)
        self.assertTrue({'watch','stalk','crouch','pounce','recover','off'}<=seen)
        self.assertEqual(hunt.height,0)

    def test_other_screen_high_cursor_and_escape(self):
        h=MouseHunt();lane=Surface('a',-1000,0,1000,800,797)
        for cursor in ((100,760),(-500,100),(-990,760)):
            h.step(.1,-300,cursor,lane,220);self.assertEqual(h.state,'off')
        h.step(.1,-300,(-180,760),lane,220);self.assertEqual(h.state,'watch')
        h.step(.1,-300,(-180,200),lane,220);self.assertEqual(h.state,'off')

@unittest.skipUnless(fixtures.HAS_QT,'Qt required')
class HuntAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.InteractionIntegrationTests.setUpClass()
    make_cat=fixtures.InteractionIntegrationTests.make_cat
    tick=staticmethod(fixtures.InteractionIntegrationTests.tick)
    mouse=staticmethod(fixtures.InteractionIntegrationTests.mouse)
    def test_bottom_hunt_and_drag_cancel(self):
        from PySide6.QtCore import QPoint
        cat=self.make_cat();cat.set_hunt_enabled(True)
        cat.cursor_position=lambda:QPoint(round(cat.rest_x+cat.width()/2+30),770)
        states=set()
        for _ in range(65):
            self.tick(cat);states.add(cat.hunt.state)
            self.assertIsNone(cat.perch);self.assertIsNone(cat.transfer)
            self.assertFalse(cat.render_frame().isNull())
        self.assertIn('pounce',states)
        cat.mousePressEvent(self.mouse(cat.x()+50,cat.y()+50))
        self.assertEqual(cat.hunt.state,'off')

    def test_calibration_preserves_ledge_and_has_no_clipped_opaque_pixels(self):
        cat=self.make_cat()
        for state,(frames,metadata) in cat.animations.items():
            for frame in frames:
                for n in range(512):
                    for x,y in ((0,n),(511,n),(n,0),(n,511)):
                        self.assertLess(frame.pixelColor(x,y).alpha(),100,(state,x,y))
        self.assertEqual(cat.animations['window_climb_side'][1]['contact_baselines_y'][-1],490)
