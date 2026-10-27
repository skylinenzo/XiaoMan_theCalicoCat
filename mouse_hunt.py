"""Bottom-lane mouse hunting. Never controls or clicks the real cursor."""
import math

class MouseHunt:
    def __init__(self):
        self.state = 'off'
        self.elapsed = 0.
        self.cooldown = 0.
        self.direction = 1
        self.age = 0.
        self.height = 0.
        self.caught = False
        self.next_play = 0

    def cancel(self):
        self.state = 'off'
        self.elapsed = self.height = self.age = 0.
        self.cooldown = 2.
        self.caught = False

    def step(self, dt, x, cursor, lane, size):
        self.cooldown = max(0., self.cooldown-dt)
        left, right = lane.x, max(lane.x, lane.x+lane.width-size)
        cx, cy = cursor
        valid = (lane.x <= cx < lane.x+lane.width and lane.floor-180 <= cy <= lane.floor+6
                 and abs(cx-(x+size/2)) <= 380)
        if self.state == 'off':
            if not valid or self.cooldown > 0:return x
            self.state, self.elapsed, self.age = 'watch', 0., 0.
        self.age += dt
        if self.state not in ('pounce', 'recover', 'play_kick', 'play_lick') and (not valid or self.age > 12):
            self.cancel();return x
        self.elapsed += dt
        if self.state in ('watch','stalk'):
            dx=cx-(x+size/2)
            if abs(dx)>12:self.direction=1 if dx>0 else -1
            if self.state=='watch' and self.elapsed>=.65:
                self.state,self.elapsed='stalk',0.
            elif self.state=='stalk':
                if abs(dx)<75:
                    self.state,self.elapsed='crouch',0.
                else:x+=self.direction*min(abs(dx)-65,65*size/220*dt)
        elif self.state=='crouch' and self.elapsed>=.35:
            self.state,self.elapsed='pounce',0.
            self.start=x
            # Aim the directional front-paw contact, not the canvas center.
            self.contact_x = .76 if self.direction > 0 else .24
            self.end=max(left,min(right,cx-size*self.contact_x))
            self.end=x+max(-110,min(110,self.end-x))
        elif self.state=='pounce':
            u=min(1.,self.elapsed/.38)
            x=self.start+(self.end-self.start)*(u*u*(3-2*u))
            self.height=math.sin(math.pi*u)*18*size/220
            if u>=1:
                self.caught = (abs(cx-(x+size*self.contact_x)) <= 32*size/220
                               and abs(cy-lane.floor) <= 48*size/220)
                self.state,self.elapsed,self.height='recover',0.,0.
        elif self.state=='recover' and self.elapsed>=.45:
            if self.caught:
                self.state = ('play_kick','play_lick')[self.next_play%2]
                self.next_play += 1
                self.elapsed = 0.
            else:self.cancel()
        elif self.state in ('play_kick','play_lick'):
            duration = 2.26 if self.state=='play_kick' else 1.62
            if self.elapsed>=duration:self.cancel()
        return max(left,min(right,x))
