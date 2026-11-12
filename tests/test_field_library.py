"""FieldLibrary: built-in + custom field images and the remembered choice (no GUI)."""
import json

import numpy as np
import pytest

from planner.fields import DEFAULT_FIELD, FIELDS_DIR, NO_FIELD, FieldLibrary


@pytest.fixture
def image(tmp_path):
    import PIL.Image
    path = tmp_path / "practice field.png"
    PIL.Image.fromarray((np.random.rand(16, 16, 3) * 255).astype("uint8")).save(path)
    return str(path)


@pytest.fixture
def lib(tmp_path):
    return FieldLibrary(str(tmp_path / "prefs.json"), FIELDS_DIR)


def test_names_start_with_none_then_builtins(lib):
    names = lib.names()
    assert names[0] == NO_FIELD
    assert names[1:6] == ["VURC 2027 - Override", "VURC 2027 - Override (Skills)", "V5RC 2027 - Override",
                          "V5RC 2027 - Override (Skills)", "V5RC Field Perimeter"]


def test_default_selection(lib):
    assert lib.selected_name() == DEFAULT_FIELD


def test_default_falls_back_to_none_without_images(tmp_path):
    lib = FieldLibrary(str(tmp_path / "p.json"), str(tmp_path / "no-fields"))
    assert lib.selected_name() == NO_FIELD
    assert lib.names() == [NO_FIELD]


def test_select_persists_and_keeps_other_prefs(lib, tmp_path):
    prefs = tmp_path / "prefs.json"
    prefs.write_text(json.dumps({"theme": "light"}))
    lib.select("V5RC 2027 - Override (Skills)")
    data = json.loads(prefs.read_text())
    assert data["field"] == "V5RC 2027 - Override (Skills)" and data["theme"] == "light"
    assert FieldLibrary(str(prefs), FIELDS_DIR).selected_name() == "V5RC 2027 - Override (Skills)"


def test_select_unknown_raises(lib):
    with pytest.raises(KeyError):
        lib.select("VEX IQ 1999")


def test_get(lib):
    assert lib.get(NO_FIELD) is None
    assert lib.get("VURC 2027 - Override").builtin


def test_add_and_remove_custom(lib, image):
    name = lib.add_custom(image)
    assert name == "practice field"
    preset = lib.get(name)
    assert not preset.builtin and preset.extent == (0, 144, 0, 144)
    assert lib.selected_name() == name
    lib.remove_custom(name)
    assert name not in lib.names() and lib.selected_name() == NO_FIELD


def test_custom_name_cannot_shadow_builtin(lib, image, tmp_path):
    import shutil
    copy = tmp_path / "VURC 2027 - Override.png"
    shutil.copy(image, copy)
    assert lib.add_custom(str(copy)) == "VURC 2027 - Override (custom)"


def test_missing_custom_file_is_dropped(lib, image, tmp_path):
    name = lib.add_custom(image)
    import os
    os.remove(image)
    assert name not in lib.names()


def test_old_single_image_pref_migrates(tmp_path, image):
    prefs = tmp_path / "prefs.json"
    prefs.write_text(json.dumps({"field_image": image}))
    lib = FieldLibrary(str(prefs), FIELDS_DIR)
    assert lib.selected_name() == "practice field"
