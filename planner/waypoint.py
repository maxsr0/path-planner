class Waypoint:
    """A path waypoint.

    (dx, dy) is the robot's *heading* tangent here (the direction it faces). The
    segment-level options (reversed, v_cap) apply to the segment leaving this waypoint
    and are ignored on the last waypoint.
    """

    def __init__(self, x, y, dx=1, dy=0, manual_tangent=False, reversed=False, v_cap=None):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.manual_tangent = manual_tangent
        self.reversed = reversed  # drive the next segment backwards
        self.v_cap = v_cap        # max speed (in/s) on the next segment, None = no cap

    def as_tuple(self):
        return self.x, self.y, self.dx, self.dy, self.manual_tangent, self.reversed, self.v_cap

    @classmethod
    def from_tuple(cls, t):
        return cls(*t)

    def __repr__(self):
        return f"({self.x}, {self.y})"
