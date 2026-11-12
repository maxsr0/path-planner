"""Field background presets: built-in images listed in fields/fields.json plus user-added images."""
import json
import os
from typing import List, NamedTuple

MM_PER_IN = 25.4
FIELD_IN = 144.0
NO_FIELD = "None (grid)"
DEFAULT_FIELD = "VURC 2027 - Override"
FIELDS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fields")


class FieldPreset(NamedTuple):
    name: str
    path: str
    size_in: float      # real-world width/height the image covers
    builtin: bool

    @property
    def extent(self):
        """(left, right, bottom, top) in field inches, centered on the 144 x 144 in field."""
        lo = (FIELD_IN - self.size_in) / 2
        hi = lo + self.size_in
        return lo, hi, lo, hi


def load_builtin_fields(fields_dir=FIELDS_DIR) -> List[FieldPreset]:
    """Presets from fields/fields.json whose image file exists."""
    try:
        with open(os.path.join(fields_dir, "fields.json"), encoding='utf-8') as f:
            entries = json.load(f).get("fields", [])
    except (OSError, ValueError, AttributeError):
        return []
    presets = []
    for e in entries:
        try:
            path = os.path.join(fields_dir, e["file"])
            size_in = float(e.get("size_mm", FIELD_IN * MM_PER_IN)) / MM_PER_IN
        except (KeyError, TypeError, ValueError):
            continue
        if os.path.exists(path):
            presets.append(FieldPreset(e["name"], path, size_in, True))
    return presets


def custom_field(name, path):
    """A user image, assumed cropped to the 144 x 144 in field (tiles only, no wall)."""
    return FieldPreset(name, path, FIELD_IN, False)
