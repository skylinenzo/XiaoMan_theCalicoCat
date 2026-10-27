import random
import unittest
from activity_rhythm import ActivityRhythm
from pet_logic import PatrolBehavior, REST_STATES
import test_interaction_integration as fixtures

class RhythmTests(unittest.TestCase):
    def test_rest_dominates_and_bursts_always_recover(self):
        r=ActivityRhythm(random.Random(42))
        totals=dict.fromkeys(r.LABELS,0.)
        for _ in range(1000):
            old=r.state
            totals[old]+=r.duration
            r.advance(r.duration)
            if old=='burst':self.assertEqual(r.state,'settle')
            if old=='settle':self.assertEqual(r.state,'rest')
        self.assertGreater(totals['rest']/sum(totals.values()),.65)
        self.assertGreater(totals['burst'],0)

    def test_quiet_ground_behavior_never_starts_patrol(self):
        rhythm=ActivityRhythm(random.Random(3))
        b=PatrolBehavior(random.Random(1),rest_states=REST_STATES,rhythm=rhythm)
        for _ in range(3000):
            x=b.advance(.1,500,0,1000,100)
            self.assertEqual(x,500)
            self.assertFalse(b.state.startswith('walk'))
        self.assertIn(b.state,('idle','groom',*REST_STATES))

    def test_active_uses_patrol_and_burst_speed_is_bounded(self):
        r=ActivityRhythm(random.Random(2));r.enter('active')
        b=PatrolBehavior(random.Random(1),rest_states=REST_STATES,rhythm=r)
        b.duration=0
        b.advance(.1,500,0,1000,100)
        self.assertTrue(b.state.startswith('walk'))
        r.enter('burst')
        self.assertEqual(r.speed,1.45)
        self.assertLessEqual(r.duration,16)

@unittest.skipUnless(fixtures.HAS_QT,'PySide6 required')
class RhythmAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.InteractionIntegrationTests.setUpClass()
    make_cat=fixtures.InteractionIntegrationTests.make_cat
    finish_transition=fixtures.InteractionIntegrationTests.finish_transition
    attach=fixtures.InteractionIntegrationTests.attach
    tick=staticmethod(fixtures.InteractionIntegrationTests.tick)

    def test_menu_and_disabled_pause_rhythm(self):
        cat=self.make_cat()
        before=cat.rhythm.elapsed
        self.tick(cat)
        self.assertEqual(cat.rhythm.elapsed,before)
        cat.set_activity('burst')
        cat.menu_open=True
        self.tick(cat)
        self.assertEqual(cat.rhythm.elapsed,0)
        cat.menu_open=False
        self.tick(cat)
        self.assertGreater(cat.rhythm.elapsed,0)

    def test_recovery_waits_for_airborne_landing(self):
        cat=self.make_cat();self.attach(cat)
        cat.behavior.enabled=True
        cat.rhythm.enter('burst');cat.rhythm.duration=.01
        cat.jump_down()
        self.tick(cat)
        self.assertEqual(cat.rhythm.state,'settle')
        self.assertIsNotNone(cat.jump)
        self.assertTrue(cat.rhythm_pending)
        for _ in range(160):self.tick(cat)
        self.assertIsNone(cat.jump)
        self.assertFalse(cat.rhythm_pending)
        self.assertFalse(cat.behavior.state.startswith('walk'))

    def test_window_rest_stays_on_support_without_exploring(self):
        cat=self.make_cat();self.attach(cat)
        cat.behavior.enabled=True
        cat.rhythm.enter('rest')
        cat.perch_action_duration=0
        cat.roam_cooldown=0
        for _ in range(300):self.tick(cat)
        self.assertIsNotNone(cat.perch)
        self.assertIsNone(cat.transfer)
        self.assertIsNone(cat.jump)
        self.assertIn(cat.perch_state,('window_perch','window_straddle','groom'))
