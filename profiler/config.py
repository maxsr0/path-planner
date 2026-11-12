from dataclasses import dataclass
from typing import Optional


@dataclass
class RobotConfig:
    """Robot and profiling constants. Units: inches, seconds, radians."""
    v_max: float = 100.0               # max linear speed (in/s)
    a_max: float = 20.0                # max longitudinal accel/decel (in/s^2)
    a_lat_max: Optional[float] = None  # max lateral (centripetal) accel; None = use a_max
    track_width: float = 0.0           # wheel-to-wheel width (in); 0 disables the tank wheel-speed limit
    spacing: float = 0.5               # arc-length distance between trajectory points (in)

    @property
    def lateral_accel(self):
        return self.a_max if self.a_lat_max is None else self.a_lat_max
