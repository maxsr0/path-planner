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


class FieldLibrary:
    """Built-in and user-added field images plus the remembered choice, stored in ui_prefs.json."""

    def __init__(self, prefs_path=None, fields_dir=FIELDS_DIR):
        self.prefs_path = prefs_path
        self.fields_dir = fields_dir

    # ----- prefs file -----

    def _read(self):
        if not self.prefs_path:
            return {}
        try:
            with open(self.prefs_path, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, **changes):
        if not self.prefs_path:
            return
        data = self._read()
        data.update(changes)
        try:
            with open(self.prefs_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass  # preferences are a convenience; never block editing over them

    # ----- listing -----

    def _customs(self):
        prefs = self._read()
        out = []
        for c in prefs.get('custom_fields', []):
            if isinstance(c, dict) and c.get('name') and c.get('path') and os.path.exists(c['path']):
                out.append(custom_field(c['name'], c['path']))
        old = prefs.get('field_image')  # pre-picker preference: one custom image path
        if isinstance(old, str) and os.path.exists(old) and not any(f.path == old for f in out):
            out.append(custom_field(os.path.splitext(os.path.basename(old))[0], old))
        return out

    def options(self):
        return load_builtin_fields(self.fields_dir) + self._customs()

    def names(self):
        return [NO_FIELD] + [f.name for f in self.options()]

    def get(self, name):
        """FieldPreset for name (None for NO_FIELD). Raises KeyError if unknown."""
        if name == NO_FIELD:
            return None
        for f in self.options():
            if f.name == name:
                return f
        raise KeyError(name)

    # ----- selection -----

    def selected_name(self):
        prefs = self._read()
        name = prefs.get('field')
        if name is None and isinstance(prefs.get('field_image'), str):
            name = os.path.splitext(os.path.basename(prefs['field_image']))[0]
        if name is None:
            name = DEFAULT_FIELD
        return name if name in self.names() else NO_FIELD

    def select(self, name):
        if name not in self.names():
            raise KeyError(name)
        self._write(field=name)

    def add_custom(self, image_path, name=None):
        """Remember a user image (cropped to the 144 x 144 in tiles), select it and return its name."""
        image_path = os.path.abspath(image_path)
        name = name or os.path.splitext(os.path.basename(image_path))[0]
        if name == NO_FIELD or any(f.name == name and f.builtin for f in self.options()):
            name += " (custom)"
        customs = [c for c in self._read().get('custom_fields', [])
                   if isinstance(c, dict) and c.get('name') != name]
        self._write(custom_fields=customs + [{"name": name, "path": image_path}], field=name)
        return name

    def remove_custom(self, name):
        prefs = self._read()
        customs = [c for c in prefs.get('custom_fields', []) if isinstance(c, dict) and c.get('name') != name]
        changes = {"custom_fields": customs}
        if prefs.get('field') == name:
            changes["field"] = NO_FIELD
        self._write(**changes)
