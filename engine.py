"""Core engine.

Mechanisms:
  * category rewrite  -> rename / reorder (unregister, set bl_category, register)
  * poll filter       -> hide + group visibility (wrap each panel's poll)

Group switching is poll-only: changing the active group never re-registers a
panel, so it is instant and cannot break the sidebar. Only rename/reorder
touch registration.

Stable identity: a panel's ORIGINAL category is its "home", stamped once.
"""

import bpy

SPACE = 'VIEW_3D'
REGION = 'UI'
PROTECTED = {"Tool", "Item"}
HOME_ATTR = "_nm_home"

# --- state consulted by the poll wrapper ---------------------------------
_hidden = set()        # home categories hidden outright
_group_of = {}         # home -> group name
_active_group = ""     # "" == show all groups
_wrapped = set()


def iter_sidebar_panels():
    for cls in bpy.types.Panel.__subclasses__():
        if cls.__name__.startswith("NM_"):
            continue                      # never manage our own UI
        if (getattr(cls, "bl_space_type", None) == SPACE
                and getattr(cls, "bl_region_type", None) == REGION
                and getattr(cls, "bl_category", "")):
            yield cls


def home_of(cls):
    return getattr(cls, HOME_ATTR, None) or cls.bl_category


def scan():
    groups = {}
    for cls in iter_sidebar_panels():
        if not getattr(cls, HOME_ATTR, None):
            setattr(cls, HOME_ATTR, cls.bl_category)
        groups.setdefault(home_of(cls), []).append(cls)
    return groups


def categories():
    return list(scan().keys())


# --- (un)register helpers -------------------------------------------------

def _unregister(cls):
    try:
        bpy.utils.unregister_class(cls); return True
    except Exception as e:
        print(f"[NManager] unregister {cls.__name__}: {e}"); return False


def _register(cls):
    try:
        bpy.utils.register_class(cls); return True
    except Exception as e:
        print(f"[NManager] register {cls.__name__}: {e}"); return False


def _sort(classes):
    return sorted(classes, key=lambda c: (getattr(c, "bl_parent_id", "") or "",
                                          getattr(c, "bl_order", 0)))


# --- poll filter ----------------------------------------------------------

def _visible(cls):
    home = home_of(cls)
    if home in _hidden:
        return False
    if _active_group and _group_of.get(home, "") != _active_group:
        return False
    return True


def _wrap(cls):
    if cls in _wrapped:
        return
    orig = cls.__dict__.get("poll", None)

    def poll(c, context, _orig=orig):
        if not _visible(c):
            return False
        if _orig is not None:
            return _orig.__func__(c, context)
        return True

    cls._nm_orig_poll = orig
    cls.poll = classmethod(poll)
    _wrapped.add(cls)


def _unwrap(cls):
    if cls not in _wrapped:
        return
    orig = getattr(cls, "_nm_orig_poll", None)
    if orig is not None:
        cls.poll = orig
    else:
        try:
            del cls.poll
        except Exception:
            pass
    _wrapped.discard(cls)


def ensure_filters():
    for cls in iter_sidebar_panels():
        _wrap(cls)


def redraw():
    wm = bpy.context.window_manager
    if not wm:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            area.tag_redraw()


def set_filters(hidden, group_of):
    """Light update: visibility only, no re-registration."""
    global _hidden, _group_of
    _hidden = set(hidden)
    _group_of = dict(group_of)
    ensure_filters()
    redraw()


def set_active_group(name):
    """Light update: just flip which group is shown."""
    global _active_group
    _active_group = name or ""
    redraw()


# --- heavy path: rename + reorder ----------------------------------------

def apply(entries):
    """entries: [{home, name, order, hidden, group}, ...]
    Rewrites categories/order (re-register) then refreshes visibility."""
    groups = scan()
    index = {e["home"]: e for e in entries}

    ordered = sorted(index.values(), key=lambda e: e.get("order", 0))
    seq = [e["home"] for e in ordered] + [h for h in groups if h not in index]

    flat = [c for cs in groups.values() for c in cs]
    for cls in reversed(_sort(flat)):
        _unregister(cls)

    for home in seq:
        e = index.get(home, {})
        target = e.get("name") or home          # rename only
        for cls in _sort(groups.get(home, [])):
            cls.bl_category = target
            _register(cls)
            _wrap(cls)

    set_filters(
        {e["home"] for e in entries if e.get("hidden")},
        {e["home"]: e["group"] for e in entries if e.get("group")},
    )


def reset():
    groups = scan()
    flat = [c for cs in groups.values() for c in cs]
    for cls in reversed(_sort(flat)):
        _unwrap(cls)
        _unregister(cls)
    global _hidden, _group_of, _active_group
    _hidden, _group_of, _active_group = set(), {}, ""
    for home in groups:
        for cls in _sort(groups[home]):
            cls.bl_category = home
            _register(cls)
