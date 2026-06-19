"""NManager — package entry point.

Registration order matters: the PropertyGroups register before the
AddonPreferences that holds CollectionProperties of them. The saved layout
is applied on a short timer so other add-ons have registered their tabs.
"""

import bpy
from . import engine, model, store, operators, ui

classes = (
    model.NM_TabEntry,
    model.NM_Group,
    ui.NM_Prefs,
    ui.NM_UL_tabs,
    ui.NM_UL_groups,
    ui.NM_MT_group_menu,
    operators.NM_OT_apply,
    operators.NM_OT_reset,
    operators.NM_OT_move,
    operators.NM_OT_rename,
    operators.NM_OT_add_group,
    operators.NM_OT_set_active_group,
    operators.NM_OT_group_move,
    operators.NM_OT_group_rename,
    operators.NM_OT_remove_group,
    operators.NM_OT_assign_group,
    operators.NM_OT_export,
    operators.NM_OT_import,
)


_enabled = False


def _startup():
    if not _enabled:
        return None                       # add-on was disabled before timer fired
    try:
        prefs = model.get_prefs()
        data = store.load()
        if data:
            model.deserialize(prefs, data)
        model.sync_collection(prefs.tabs)
        model.clamp_active(prefs)
        engine.apply(model.entries_to_list(prefs.tabs))   # reorder=False: safe
        engine.set_active_group(prefs.active_group)
    except Exception as e:
        print(f"[NManager] startup: {e}")
    return None


def register():
    global _enabled
    _enabled = True
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_HT_header.append(ui.draw_header)
    bpy.app.timers.register(_startup, first_interval=1.0)


def unregister():
    global _enabled
    _enabled = False
    try:
        if bpy.app.timers.is_registered(_startup):
            bpy.app.timers.unregister(_startup)
    except Exception:
        pass
    try:
        bpy.types.VIEW3D_HT_header.remove(ui.draw_header)
    except Exception:
        pass
    try:
        engine.reset()
    except Exception as e:
        print(f"[NManager] reset on unregister: {e}")
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
