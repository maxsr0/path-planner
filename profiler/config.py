import json
import math
from dataclasses import dataclass, asdict, fields
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

    def validate(self):
        """Raise ValueError with a readable message if any value is unusable."""
        def finite(name, value):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{name} must be a number")

        for name in ("v_max", "a_max", "spacing"):
            finite(name, getattr(self, name))
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than 0")
        finite("track_width", self.track_width)
        if self.track_width < 0:
            raise ValueError("track_width cannot be negative")
        if self.a_lat_max is not None:
            finite("a_lat_max", self.a_lat_max)
            if self.a_lat_max <= 0:
                raise ValueError("a_lat_max must be greater than 0 (leave blank to use a_max)")
        return self

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known}).validate()


def load_config(path):
    """Load a RobotConfig from JSON. Returns (config, error); falls back to defaults on any problem."""
    try:
        with open(path, encoding='utf-8') as f:
            return RobotConfig.from_dict(json.load(f)), None
    except FileNotFoundError:
        return RobotConfig(), None
    except (OSError, ValueError, TypeError) as e:
        return RobotConfig(), f"Could not load {path}: {e}. Using defaults."


def save_config(config, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config.to_dict(), f, indent=2)
        f.write("\n")
