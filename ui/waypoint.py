class Waypoint:
    def __init__(self, x, y, dx=1, dy=0):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.manual_tangent = False

    def __str__(self):
        return f"({self.x}, {self.y})"

    def __repr__(self):
        return f"({self.x}, {self.y})"

    def auto_tangent(self, prev, nxt):  # Catmull-Rom
        self.dx = (nxt.x - prev.x) * 0.5
        self.dy = (nxt.y - prev.y) * 0.5
        # 0.5 represents curve tension, lower is tighter with less overshoot, higher is mores sweeping curves (0-1)
