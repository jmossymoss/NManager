"""UI: AddonPreferences, tab list (group-filterable), groups list,
settings panels, and the top-right viewport header group switcher."""

import bpy
from bpy.props import (CollectionProperty, IntProperty, StringProperty,
                       BoolProperty)
from . import engine, model


class NM_Prefs(bpy.types.AddonPreferences):
    bl_idname = model.ADDON_ID

    tabs: CollectionProperty(type=model.NM_TabEntry)
    groups: CollectionProperty(type=model.NM_Group)
    active: IntProperty()
    active_group_index: IntProperty()
    active_group: StringProperty(update=model._on_active_group)
    filter_to_group: BoolProperty(
        name="Limit list to active group",
        description="Show only the active group's tabs and reorder within it",
        default=True)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Manage tabs in the 3D viewport sidebar > NManager.",
                     icon='INFO')
        layout.label(text="Switch groups from the top-right of the viewport.",
                     icon='OUTLINER_COLLECTION')
        row = layout.row(align=True)
        row.operator("nm.import", icon='IMPORT')
        row.operator("nm.export", icon='EXPORT')


# --- the tab list ---------------------------------------------------------

class NM_UL_tabs(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_prop, index):
        prefs = data
        row = layout.row(align=True)
        row.prop(item, "hidden", text="",
                 icon='HIDE_ON' if item.hidden else 'HIDE_OFF', emboss=False)
        sub = row.row(align=True)
        sub.active = not item.hidden
        sub.prop(item, "name", text="")
        row.prop_search(item, "group", prefs, "groups", text="",
                        icon='OUTLINER_COLLECTION')
        if item.home in engine.PROTECTED:
            row.label(text="", icon='LOCKED')

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        prefs = model.get_prefs(context)
        shown = self.bitflag_filter_item
        flt = [shown] * len(items)

        if prefs.filter_to_group and prefs.active_group:
            grp = prefs.active_group
            for i, it in enumerate(items):
                if it.group != grp:
                    flt[i] = 0
        if self.filter_name:
            needle = self.filter_name.lower()
            for i, it in enumerate(items):
                if needle not in (it.name or it.home).lower():
                    flt[i] = 0
        return flt, []


# --- the groups list ------------------------------------------------------

class NM_UL_groups(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_prop, index):
        prefs = model.get_prefs(context)
        is_active = prefs.active_group == item.name
        row = layout.row(align=True)
        op = row.operator("nm.set_active_group", text="",
                          icon='RADIOBUT_ON' if is_active else 'RADIOBUT_OFF',
                          emboss=False)
        op.name = item.name
        row.label(text=item.name or "(unnamed)")


# --- shared group switcher menu ------------------------------------------

class NM_MT_group_menu(bpy.types.Menu):
    bl_idname = "NM_MT_group_menu"
    bl_label = "Tab Group"

    def draw(self, context):
        prefs = model.get_prefs(context)
        layout = self.layout
        cur = prefs.active_group

        op = layout.operator("nm.set_active_group", text="All Tabs",
                             icon='CHECKMARK' if not cur else 'BLANK1')
        op.name = ""

        if len(prefs.groups):
            layout.separator()
        for g in prefs.groups:
            op = layout.operator("nm.set_active_group",
                                 text=g.name or "(unnamed)",
                                 icon='CHECKMARK' if cur == g.name else 'BLANK1')
            op.name = g.name

        layout.separator()
        layout.operator("nm.add_group", text="New Group...", icon='ADD')
        if cur:
            op = layout.operator("nm.remove_group",
                                 text='Remove "%s"' % cur, icon='REMOVE')
            op.name = cur


# --- settings panels ------------------------------------------------------

class NM_PT_panel(bpy.types.Panel):
    bl_idname = "NM_PT_panel"
    bl_label = "NManager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "NManager"

    def draw(self, context):
        layout = self.layout
        prefs = model.get_prefs(context)

        row = layout.row(align=True)
        row.menu("NM_MT_group_menu",
                 text=prefs.active_group or "All Tabs",
                 icon='OUTLINER_COLLECTION')
        sub = layout.row()
        sub.enabled = bool(prefs.active_group)
        sub.prop(prefs, "filter_to_group")

        row = layout.row()
        row.template_list("NM_UL_tabs", "", prefs, "tabs",
                          prefs, "active", rows=12)
        col = row.column(align=True)
        col.operator("nm.move", text="", icon='TRIA_UP').direction = -1
        col.operator("nm.move", text="", icon='TRIA_DOWN').direction = 1
        col.separator()
        col.operator("nm.rename", text="", icon='GREASEPENCIL')

        layout.separator()
        row = layout.row(align=True)
        row.operator("nm.apply", icon='CHECKMARK')
        row.operator("nm.reset", icon='LOOP_BACK')


class NM_PT_groups(bpy.types.Panel):
    bl_idname = "NM_PT_groups"
    bl_label = "Groups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "NManager"
    bl_parent_id = "NM_PT_panel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = model.get_prefs(context)

        row = layout.row()
        row.template_list("NM_UL_groups", "", prefs, "groups",
                          prefs, "active_group_index", rows=5)
        col = row.column(align=True)
        col.operator("nm.group_move", text="", icon='TRIA_UP').direction = -1
        col.operator("nm.group_move", text="", icon='TRIA_DOWN').direction = 1
        col.separator()
        col.operator("nm.group_rename", text="", icon='GREASEPENCIL')
        rm = col.operator("nm.remove_group", text="", icon='X')
        idx = prefs.active_group_index
        rm.name = prefs.groups[idx].name if 0 <= idx < len(prefs.groups) else ""

        layout.operator("nm.add_group", text="New Group", icon='ADD')


# --- top-right viewport header switcher -----------------------------------

def draw_header(self, context):
    if model.ADDON_ID not in context.preferences.addons:
        return
    prefs = model.get_prefs(context)
    layout = self.layout
    layout.separator_spacer()
    layout.menu("NM_MT_group_menu",
                text=prefs.active_group or "All Tabs",
                icon='OUTLINER_COLLECTION')
