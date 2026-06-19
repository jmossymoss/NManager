"""UI: AddonPreferences (the full management UI lives here, in a resizable
window), the list widgets, the shared group menu, and the top-right viewport
header group switcher. There is intentionally no N-panel tab."""

import bpy
from bpy.props import (CollectionProperty, IntProperty, StringProperty,
                       BoolProperty)
from . import engine, model


# --- list widgets ---------------------------------------------------------

class NM_UL_tabs(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_prop, index):
        prefs = data
        row = layout.row(align=True)
        ic = item.icon if item.icon and item.icon != 'NONE' else 'BLANK1'
        op = row.operator("nm.pick_icon", text="", icon=ic, emboss=False)
        op.target = "tab"
        op.index = index
        row.prop(item, "hidden", text="",
                 icon='HIDE_ON' if item.hidden else 'HIDE_OFF', emboss=False)
        sub = row.row(align=True)
        sub.active = not item.hidden
        sub.label(text=item.name or item.home)
        row.prop_search(item, "group", prefs, "groups", text="",
                        icon='OUTLINER_COLLECTION')
        row.label(text="",
                  icon='LOCKED' if item.home in engine.PROTECTED else 'BLANK1')

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
        ic = item.icon if item.icon and item.icon != 'NONE' else 'BLANK1'
        op2 = row.operator("nm.pick_icon", text="", icon=ic, emboss=False)
        op2.target = "group"
        op2.index = index
        row.label(text=item.name or "(unnamed)")


# --- shared group switcher menu (header + prefs) -------------------------

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
            if g.icon and g.icon != 'NONE':
                ic = g.icon
            else:
                ic = 'CHECKMARK' if cur == g.name else 'BLANK1'
            op = layout.operator("nm.set_active_group",
                                 text=g.name or "(unnamed)", icon=ic)
            op.name = g.name

        layout.separator()
        layout.operator("nm.add_group", text="New Group...", icon='ADD')
        if cur:
            op = layout.operator("nm.remove_group",
                                 text='Remove "%s"' % cur, icon='REMOVE')
            op.name = cur


# --- AddonPreferences: the whole management UI ---------------------------

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

        row = layout.row(align=True)
        row.menu("NM_MT_group_menu",
                 text=self.active_group or "All Tabs",
                 icon='OUTLINER_COLLECTION')
        r = row.row()
        r.enabled = bool(self.active_group)
        r.prop(self, "filter_to_group")

        layout.separator()
        split = layout.split(factor=0.62)

        # Tabs
        col = split.column()
        col.label(text="Tabs", icon='WINDOW')
        trow = col.row()
        trow.template_list("NM_UL_tabs", "", self, "tabs",
                           self, "active", rows=14)
        tcol = trow.column(align=True)
        tcol.operator("nm.move", text="", icon='TRIA_UP').direction = -1
        tcol.operator("nm.move", text="", icon='TRIA_DOWN').direction = 1
        tcol.separator()
        tcol.operator("nm.rename", text="", icon='GREASEPENCIL')
        brow = col.row(align=True)
        brow.operator("nm.apply", icon='CHECKMARK')
        brow.operator("nm.reset", icon='LOOP_BACK')

        # Groups
        gcol = split.column()
        gcol.label(text="Groups", icon='OUTLINER_COLLECTION')
        grow = gcol.row()
        grow.template_list("NM_UL_groups", "", self, "groups",
                           self, "active_group_index", rows=14)
        gccol = grow.column(align=True)
        gccol.operator("nm.group_move", text="", icon='TRIA_UP').direction = -1
        gccol.operator("nm.group_move", text="", icon='TRIA_DOWN').direction = 1
        gccol.separator()
        gccol.operator("nm.group_rename", text="", icon='GREASEPENCIL')
        rm = gccol.operator("nm.remove_group", text="", icon='X')
        idx = self.active_group_index
        rm.name = self.groups[idx].name if 0 <= idx < len(self.groups) else ""
        gcol.operator("nm.add_group", text="New Group", icon='ADD')

        layout.separator()
        iorow = layout.row(align=True)
        iorow.operator("nm.import", icon='IMPORT')
        iorow.operator("nm.export", icon='EXPORT')
        layout.label(text="Switch the active group from the top-right of the "
                          "viewport header.", icon='INFO')


# --- top-right viewport header switcher -----------------------------------

def draw_header(self, context):
    if model.ADDON_ID not in context.preferences.addons:
        return
    prefs = model.get_prefs(context)
    layout = self.layout
    label = prefs.active_group or "All Tabs"
    group_obj = next((g for g in prefs.groups if g.name == prefs.active_group), None)
    icon = (group_obj.icon if group_obj and group_obj.icon and group_obj.icon != 'NONE'
            else 'OUTLINER_COLLECTION')
    layout.separator_spacer()
    row = layout.row(align=True)
    row.ui_units_x = min(12.0, max(4.0, len(label) * 0.55 + 2.0))
    row.menu("NM_MT_group_menu", text=label, icon=icon)
