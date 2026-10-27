import math
import unittest
from desktop_route import Surface
from mouse_hunt import MouseHunt
from run_animation import RunCycle
import test_interaction_integration as fixtures

class CatchTests(unittest.TestCase):
    def run_hunt(self,hunt,escape=False):
        lane=Surface('a',0,0,1000,800,797);x=400;states=set()
        for _ in range(130):
            cursor=(550,770)
            if escape and hunt.state=='pounce':cursor=(900,100)
            x=hunt.step(.05,x,cursor,lane,220);states.add(hunt.state)
            if hunt.state.startswith('play'):return hunt.state
            if hunt.state=='off' and 'pounce' in states:return 'miss'
        self.fail('Hunt did not terminate')

    def test_catches_alternate_play_groups_and_misses_do_not_play(self):
        h=MouseHunt()
        self.assertEqual(self.run_hunt(h),'play_kick')
        h.cancel();h.cooldown=0
        self.assertEqual(self.run_hunt(h),'play_lick')
        self.assertEqual(self.run_hunt(MouseHunt(),True),'miss')

    def test_direction_locked_and_short_run_cycle_distance(self):
        h=MouseHunt();lane=Surface('a',0,0,1000,800,797);x=400
        for _ in range(50):
            x=h.step(.05,x,(550,770),lane,220)
            if h.state=='pounce':break
        direction=h.direction
        h.step(.1,x,(100,770),lane,220)
        self.assertEqual(h.direction,direction)
        cycle=RunCycle()
        self.assertAlmostEqual(cycle.travel(0,cycle.duration),cycle.stride)
        self.assertEqual(cycle.frame(0),cycle.frame(cycle.duration))

@unittest.skipUnless(fixtures.HAS_QT,'Qt required')
class HuntActionAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.InteractionIntegrationTests.setUpClass()
    make_cat=fixtures.InteractionIntegrationTests.make_cat
    tick=staticmethod(fixtures.InteractionIntegrationTests.tick)
    finish_transition=fixtures.InteractionIntegrationTests.finish_transition

    def test_directional_pounce_is_not_shared_or_mirrored(self):
        cat=self.make_cat()
        left=cat.animations['pounce_left'][0]
        right=cat.animations['pounce_right'][0]
        for a,b in zip(left,right):
            self.assertNotEqual(a,b)
            self.assertNotEqual(a,b.mirrored(True,False))
        cat.hunt.state='pounce';cat.hunt.elapsed=.12
        cat.hunt.direction=-1;first=cat.visible_image()
        cat.hunt.direction=1;self.assertNotEqual(first,cat.visible_image())

    def test_running_uses_own_cycle_and_manual_play_finishes(self):
        cat=self.make_cat();cat.perform_run('left');self.finish_transition(cat)
        self.assertTrue(cat.is_running())
        x=cat.rest_x;t=cat.gait_time
        for _ in range(4):self.tick(cat)
        distance=abs(cat.rest_x-x)
        self.assertAlmostEqual(distance,(cat.gait_time-t)*cat.run_cycle.stride/cat.run_cycle.duration*cat.width()/512,places=4)
        cat.perform('play_lick');self.finish_transition(cat)
        self.assertFalse(cat.is_running())
        for _ in range(45):self.tick(cat)
        self.assertEqual(cat.behavior.state,'idle')

    def test_eye_component_changes_only_iris_regions_and_respects_blinks(self):
        cat=self.make_cat();image=cat.frames[0];cat.gaze.target=(cat.x()+700,cat.y()-200)
        painted=cat.gaze_image(image,'idle/0');self.assertNotEqual(image,painted)
        rects=cat.gaze.catalog['idle/0']
        changed=0
        for y in range(512):
            for x in range(512):
                if image.pixel(x,y)!=painted.pixel(x,y):
                    changed+=1
                    self.assertTrue(any(a-1<=x<=a+w+1 and b-1<=y<=b+h+1 for a,b,w,h in rects))
        self.assertGreater(changed,30)
        for key in ('idle/3','held/3','window_climb_back/2','play_lick/2'):
            self.assertEqual(cat.gaze_image(image,key),image)
        dx,dy=cat.gaze.offset(1000,1000,30,20)
        self.assertLessEqual((dx/(30*.22))**2+(dy/(20*.13))**2,1.00001)
