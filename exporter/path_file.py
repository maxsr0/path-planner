"""Save/load editable path projects (.path.json).

Only the waypoints (with their per-segment reverse / speed-cap options) are stored. Robot constants live in robot_config.json, so
one path can be re-exported for a different robot.
"""
import json
import math

FORMAT = "prism-path"
VERSION = 1
EXTENSION = ".path.json"


def save_path(filepath, waypoints):
    """waypoints: iterable of objects with x, y, dx, dy, manual_tangent."""
    data = {
        "format": FORMAT,
        "version": VERSION,
        "waypoints": [
            {"x": w.x, "y": w.y, "dx": w.dx, "dy": w.dy, "manual_tangent": bool(w.manual_tangent),
             "reversed": bool(getattr(w, "reversed", False)), "v_cap": getattr(w, "v_cap", None)}
            for w in waypoints
        ],
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_path(filepath):
    """Return a list of dicts with x, y, dx, dy, manual_tangent. Raises ValueError on bad files."""
    try:
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"not valid JSON ({e})") from e

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not a PRISM path file")
    if data.get("version") != VERSION:
        raise ValueError(f"unsupported path file version {data.get('version')!r} (expected {VERSION})")
    raw = data.get("waypoints")
    if not isinstance(raw, list):
        raise ValueError("missing waypoint list")

    waypoints = []
    for i, w in enumerate(raw):
        try:
            entry = {k: float(w[k]) for k in ("x", "y", "dx", "dy")}
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"waypoint {i + 1} is missing x, y, dx or dy")
        if not all(math.isfinite(v) for v in entry.values()):
            raise ValueError(f"waypoint {i + 1} has a non-finite value")
        entry["manual_tangent"] = bool(w.get("manual_tangent", False))
        entry["reversed"] = bool(w.get("reversed", False))
        cap = w.get("v_cap")
        if cap is not None:
            try:
                cap = float(cap)
            except (TypeError, ValueError):
                raise ValueError(f"waypoint {i + 1} has an invalid speed cap")
            if not math.isfinite(cap) or cap <= 0:
                raise ValueError(f"waypoint {i + 1} speed cap must be a positive number")
        entry["v_cap"] = cap
        waypoints.append(entry)
    return waypoints
