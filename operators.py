"""Operators: apply/reset, tab reorder (group-aware), rename,
group create/select/reorder/rename/remove, assign, import/export."""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from . import engine, model, store




def _has_active_tab(context):
    prefs = model.get_prefs(context)
    return 0 <= prefs.active < len(prefs.tabs)


def _apply_and_save(context, reorder=False):
    prefs = model.get_prefs(context)
    model.sync_collection(prefs.tabs)
    model.clamp_active(prefs)
    engine.apply(model.entries_to_list(prefs.tabs), reorder=reorder)
    store.save(model.serialize(prefs))


# --- layout-wide ----------------------------------------------------------

class NM_OT_apply(Operator):
    bl_idname = "nm.apply"
    bl_label = "Apply"
    bl_description = "Commit names and order to the sidebar"

    def execute(self, context):
        _apply_and_save(context)
        return {'FINISHED'}


class NM_OT_reset(Operator):
    bl_idname = "nm.reset"
    bl_label = "Reset"
    bl_description = "Restore original names, order, visibility and groups"

    def execute(self, context):
        engine.reset()
        prefs = model.get_prefs(context)
        prefs.tabs.clear()
        prefs.groups.clear()
        prefs.active_group = ""
        prefs.active_group_index = 0
        model.sync_collection(prefs.tabs)
        store.save(model.serialize(prefs))
        return {'FINISHED'}


# --- tab ordering / renaming ---------------------------------------------

class NM_OT_move(Operator):
    bl_idname = "nm.move"
    bl_label = "Move Tab"
    bl_options = {'INTERNAL'}
    direction: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return len(model.get_prefs(context).tabs) > 1

    def execute(self, context):
        prefs = model.get_prefs(context)
        coll = prefs.tabs
        i = prefs.active
        if not (0 <= i < len(coll)):
            return {'CANCELLED'}

        # reorder within the currently shown subset (group filter or all)
        if prefs.filter_to_group and prefs.active_group:
            grp = prefs.active_group
            visible = [k for k, e in enumerate(coll) if e.group == grp]
        else:
            visible = list(range(len(coll)))

        if i not in visible:
            return {'CANCELLED'}
        pos = visible.index(i)
        npos = pos + self.direction
        if 0 <= npos < len(visible):
            j = visible[npos]
            coll.move(i, j)
            prefs.active = j
            _apply_and_save(context, reorder=True)
        return {'FINISHED'}


class NM_OT_rename(Operator):
    bl_idname = "nm.rename"
    bl_label = "Rename Tab"
    new_name: StringProperty(name="Name")

    @classmethod
    def poll(cls, context):
        return _has_active_tab(context)

    def invoke(self, context, event):
        prefs = model.get_prefs(context)
        e = prefs.tabs[prefs.active]
        self.new_name = e.name or e.home
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "new_name")

    def execute(self, context):
        prefs = model.get_prefs(context)
        e = prefs.tabs[prefs.active]
        e.name = self.new_name.strip() or e.home
        _apply_and_save(context)
        return {'FINISHED'}


# --- groups ---------------------------------------------------------------

class NM_OT_add_group(Operator):
    bl_idname = "nm.add_group"
    bl_label = "New Group"
    name: StringProperty(name="Name")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "name")

    def execute(self, context):
        prefs = model.get_prefs(context)
        nm = self.name.strip()
        if not nm:
            self.report({'WARNING'}, "Group name is empty")
            return {'CANCELLED'}
        if not any(g.name == nm for g in prefs.groups):
            prefs.groups.add().name = nm
        prefs.active_group_index = len(prefs.groups) - 1
        prefs.active_group = nm
        store.save(model.serialize(prefs))
        return {'FINISHED'}


class NM_OT_set_active_group(Operator):
    bl_idname = "nm.set_active_group"
    bl_label = "Show Group"
    bl_options = {'INTERNAL'}
    name: StringProperty()

    def execute(self, context):
        prefs = model.get_prefs(context)
        prefs.active_group = self.name          # update cb -> engine
        for i, g in enumerate(prefs.groups):
            if g.name == self.name:
                prefs.active_group_index = i
                break
        store.save(model.serialize(prefs))
        return {'FINISHED'}


class NM_OT_group_move(Operator):
    bl_idname = "nm.group_move"
    bl_label = "Move Group"
    bl_options = {'INTERNAL'}
    direction: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return len(model.get_prefs(context).groups) > 1

    def execute(self, context):
        prefs = model.get_prefs(context)
        coll = prefs.groups
        i = prefs.active_group_index
        j = i + self.direction
        if 0 <= i < len(coll) and 0 <= j < len(coll):
            coll.move(i, j)
            prefs.active_group_index = j
            store.save(model.serialize(prefs))
        return {'FINISHED'}


class NM_OT_group_rename(Operator):
    bl_idname = "nm.group_rename"
    bl_label = "Rename Group"
    new_name: StringProperty(name="Name")

    @classmethod
    def poll(cls, context):
        p = model.get_prefs(context)
        return 0 <= p.active_group_index < len(p.groups)

    def invoke(self, context, event):
        p = model.get_prefs(context)
        self.new_name = p.groups[p.active_group_index].name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "new_name")

    def execute(self, context):
        p = model.get_prefs(context)
        g = p.groups[p.active_group_index]
        old, new = g.name, self.new_name.strip()
        if not new:
            self.report({'WARNING'}, "Group name is empty")
            return {'CANCELLED'}
        if new != old and any(x.name == new for x in p.groups):
            self.report({'WARNING'}, "Group already exists")
            return {'CANCELLED'}
        g.name = new
        for e in p.tabs:                         # keep memberships in sync
            if e.group == old:
                e.group = new
        if p.active_group == old:
            p.active_group = new                 # update cb -> engine
        store.save(model.serialize(p))
        return {'FINISHED'}


class NM_OT_remove_group(Operator):
    bl_idname = "nm.remove_group"
    bl_label = "Remove Group"
    name: StringProperty()

    def execute(self, context):
        prefs = model.get_prefs(context)
        target = self.name or prefs.active_group
        for i, g in enumerate(prefs.groups):
            if g.name == target:
                prefs.groups.remove(i)
                break
        for e in prefs.tabs:
            if e.group == target:
                e.group = ""
        if prefs.active_group == target:
            prefs.active_group = ""
        prefs.active_group_index = min(prefs.active_group_index,
                                       max(0, len(prefs.groups) - 1))
        store.save(model.serialize(prefs))
        return {'FINISHED'}


class NM_OT_assign_group(Operator):
    bl_idname = "nm.assign_group"
    bl_label = "Assign Active Tab To Group"
    name: StringProperty()

    @classmethod
    def poll(cls, context):
        return _has_active_tab(context)

    def execute(self, context):
        prefs = model.get_prefs(context)
        prefs.tabs[prefs.active].group = self.name   # update cb -> engine
        store.save(model.serialize(prefs))
        return {'FINISHED'}


# --- icon picker ----------------------------------------------------------

class NM_OT_pick_icon(Operator):
    bl_idname = "nm.pick_icon"
    bl_label = "Pick Icon"
    bl_description = "Choose an icon for this item"
    bl_options = {'INTERNAL'}
    target: StringProperty()  # "tab" or "group"
    index: IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Choose Icon:")
        col = layout.column(align=True)
        for sym, bi, label in model.ICON_OPTIONS:
            row = col.row(align=True)
            op = row.operator("nm.set_icon", text=label or "None", icon=bi,
                              emboss=bool(sym))
            op.target = self.target
            op.index = self.index
            op.icon_id = sym

    def execute(self, context):
        return {'FINISHED'}


class NM_OT_set_icon(Operator):
    bl_idname = "nm.set_icon"
    bl_label = "Set Icon"
    bl_options = {'INTERNAL'}
    target: StringProperty()
    index: IntProperty()
    icon_id: StringProperty()

    def execute(self, context):
        prefs = model.get_prefs(context)
        if self.target == "tab" and 0 <= self.index < len(prefs.tabs):
            prefs.tabs[self.index].icon = self.icon_id
            _apply_and_save(context)
        elif self.target == "group" and 0 <= self.index < len(prefs.groups):
            prefs.groups[self.index].icon = self.icon_id
            store.save(model.serialize(prefs))
        return {'FINISHED'}


# --- import / export ------------------------------------------------------

class NM_OT_export(Operator, ExportHelper):
    bl_idname = "nm.export"
    bl_label = "Export Layout"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        store.export_to(self.filepath, model.serialize(model.get_prefs(context)))
        return {'FINISHED'}


class NM_OT_import(Operator, ImportHelper):
    bl_idname = "nm.import"
    bl_label = "Import Layout"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        prefs = model.get_prefs(context)
        try:
            data = store.import_from(self.filepath)
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}")
            return {'CANCELLED'}
        model.deserialize(prefs, data)
        _apply_and_save(context, reorder=True)
        engine.set_active_group(prefs.active_group)
        return {'FINISHED'}
