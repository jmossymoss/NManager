"""Data model: per-tab entry, group entry, (de)serialisation, live filters."""

import bpy
from bpy.props import (StringProperty, IntProperty, BoolProperty,
                       CollectionProperty)
from . import engine

ADDON_ID = __package__

# Suspend live update callbacks during bulk loads.
_suspend = False

# Each entry: (unicode_suffix, blender_icon_id, label)
# The unicode suffix is stored on the property and appended to bl_category so
# it appears directly in the N-panel sidebar tab label.
ICON_OPTIONS = (
    ("",  'BLANK1',        "None"),
    ("●", 'MESH_UVSPHERE', "Dot"),
    ("○", 'MESH_CIRCLE',   "Circle"),
    ("■", 'MESH_CUBE',     "Square"),
    ("□", 'MESH_PLANE',    "Square (outline)"),
    ("▲", 'MESH_CONE',     "Triangle"),
    ("△", 'MESH_ICOSPHERE',"Triangle (outline)"),
    ("◆", 'KEYFRAME_HLT',  "Diamond"),
    ("◇", 'KEYFRAME',      "Diamond (outline)"),
    ("★", 'MODIFIER',      "Star"),
    ("☆", 'LATTICE_DATA',  "Star (outline)"),
    ("▶", 'TRIA_RIGHT',    "Arrow"),
)

_VALID_SYMS = {sym for sym, _, _ in ICON_OPTIONS if sym}
_ICON_LOOKUP = {sym: bi for sym, bi, _ in ICON_OPTIONS}


def icon_to_blender(sym):
    """Return the Blender icon ID for a unicode symbol, for use in layout calls."""
    return _ICON_LOOKUP.get(sym, 'BLANK1')


def _clean_icon(raw):
    """Normalise a stored icon value; discard legacy Blender icon-ID strings."""
    return raw if raw in _VALID_SYMS else ""


def get_prefs(context=None):
    context = context or bpy.context
    return context.preferences.addons[ADDON_ID].preferences


def _refresh_live(self, context):
    """Re-push hidden/group filters to the engine (no re-registration)."""
    if _suspend:
        return
    prefs = get_prefs(context)
    engine.set_filters(
        {e.home for e in prefs.tabs if e.hidden},
        {e.home: e.group for e in prefs.tabs if e.group},
    )


def _on_active_group(self, context):
    if _suspend:
        return
    engine.set_active_group(self.active_group)


class NM_TabEntry(bpy.types.PropertyGroup):
    home: StringProperty()                                  # stable key
    name: StringProperty(name="Name")                       # rename (Apply)
    order: IntProperty()
    hidden: BoolProperty(name="Hidden", update=_refresh_live)   # live
    group: StringProperty(name="Group", update=_refresh_live)   # live
    icon: StringProperty(name="Icon", default='')


class NM_Group(bpy.types.PropertyGroup):
    name: StringProperty(name="Name")
    icon: StringProperty(name="Icon", default='')


# --- collection <-> list (for engine.apply) ------------------------------

def entries_to_list(coll):
    return [{"home": e.home, "name": e.name or e.home, "order": e.order,
             "hidden": e.hidden, "group": e.group, "icon": e.icon} for e in coll]


def sync_collection(coll):
    known = {e.home for e in coll}
    for home in engine.categories():
        if home not in known:
            e = coll.add()
            e.home = home
            e.name = home
    for i, e in enumerate(coll):
        e.order = i


def clamp_active(prefs):
    n = len(prefs.tabs)
    prefs.active = 0 if n == 0 else max(0, min(prefs.active, n - 1))


# --- JSON (de)serialisation ----------------------------------------------

def serialize(prefs):
    return {
        "version": 1,
        "active_group": prefs.active_group,
        "groups": [{"name": g.name, "icon": g.icon} for g in prefs.groups],
        "tabs": entries_to_list(prefs.tabs),
    }


def deserialize(prefs, data):
    global _suspend
    if isinstance(data, list):          # legacy bare-list layouts
        data = {"tabs": data}
    _suspend = True
    try:
        prefs.groups.clear()
        for gdata in data.get("groups", []):
            g = prefs.groups.add()
            if isinstance(gdata, str):  # backward compat: plain name list
                g.name = gdata
            else:
                g.name = gdata.get("name", "")
                g.icon = _clean_icon(gdata.get("icon", ""))
        prefs.tabs.clear()
        for d in data.get("tabs", []):
            e = prefs.tabs.add()
            e.home = d["home"]
            e.name = d.get("name", d["home"])
            e.order = d.get("order", 0)
            e.hidden = d.get("hidden", False)
            e.group = d.get("group", "")
            e.icon = _clean_icon(d.get("icon", ""))
        prefs.active_group = data.get("active_group", "")
    finally:
        _suspend = False
