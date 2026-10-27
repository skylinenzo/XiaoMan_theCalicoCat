"""Two-bone IK and a distance-driven four-leg walk, independent of Qt."""
import math

STRIDE = 92.0
STANCE = .65
GROUND = 490.0
ANKLE = 476.0


def solve_leg(root, target, upper, lower, bend):
    """Return knee and reachable endpoint for two rigid bone lengths."""
    dx, dy = target[0] - root[0], target[1] - root[1]
    distance = math.hypot(dx, dy)
    distance = max(abs(upper - lower) + 1e-6, min(upper + lower - 1e-6, distance))
    angle = math.atan2(dy, dx)
    cosine = (upper * upper + distance * distance - lower * lower) / (2 * upper * distance)
    joint_angle = angle + bend * math.acos(max(-1., min(1., cosine)))
    knee = (root[0] + upper * math.cos(joint_angle), root[1] + upper * math.sin(joint_angle))
    end = (root[0] + distance * math.cos(angle), root[1] + distance * math.sin(angle))
    return knee, end


def foot_target(phase, center_x, offset=0):
    """Linear backward stance cancels forward body motion; raised forward swing."""
    p = (phase + offset) % 1.
    reach = STRIDE * STANCE / 2
    if p < STANCE:
        return center_x + reach - STRIDE * p, ANKLE
    u = (p - STANCE) / (1 - STANCE)
    smooth = u * u * (3 - 2 * u)
    return center_x - reach + 2 * reach * smooth, ANKLE - 24 * math.sin(math.pi * u) ** 2


def leg_pose(phase, front, far):
    root = (346., 370.) if front else (174., 366.)
    offset = (.25 if front else 0.) + (.5 if far else 0.)
    target = foot_target(phase, root[0] + (0 if front else 4), offset)
    knee, foot = solve_leg(root, target, 58 if front else 65, 64 if front else 65,
                           1 if front else -1)
    return root, knee, foot
