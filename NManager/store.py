"""Persistence: layout.json in Blender's user CONFIG dir."""

import os
import json
import bpy

_SUBDIR = "nmanager"
_FILE = "layout.json"


def _path(create=False):
    base = bpy.utils.user_resource('CONFIG', path=_SUBDIR, create=create)
    return os.path.join(base, _FILE)


def load():
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(data):
    try:
        with open(_path(create=True), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[NManager] save failed: {e}")
        return False


def export_to(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def import_from(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
