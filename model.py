"""Data model: per-tab entry, group entry, (de)serialisation, live filters."""

import bpy
from bpy.props import (StringProperty, IntProperty, BoolProperty,
                       CollectionProperty)
from . import engine

ADDON_ID = __package__

# Suspend live update callbacks during bulk loads.
_suspend = False


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


class NM_Group(bpy.types.PropertyGroup):
    name: StringProperty(name="Name")


# --- collection <-> list (for engine.apply) ------------------------------

def entries_to_list(coll):
    return [{"home": e.home, "name": e.name or e.home, "order": e.order,
             "hidden": e.hidden, "group": e.group} for e in coll]


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
        "groups": [g.name for g in prefs.groups],
        "tabs": entries_to_list(prefs.tabs),
    }


def deserialize(prefs, data):
    global _suspend
    if isinstance(data, list):          # legacy bare-list layouts
        data = {"tabs": data}
    _suspend = True
    try:
        prefs.groups.clear()
        for gn in data.get("groups", []):
            prefs.groups.add().name = gn
        prefs.tabs.clear()
        for d in data.get("tabs", []):
            e = prefs.tabs.add()
            e.home = d["home"]
            e.name = d.get("name", d["home"])
            e.order = d.get("order", 0)
            e.hidden = d.get("hidden", False)
            e.group = d.get("group", "")
        prefs.active_group = data.get("active_group", "")
    finally:
        _suspend = False
