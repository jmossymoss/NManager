"""Core engine.

THE KEY FACT this design is built around:
    Blender decides whether a panel has a poll at REGISTRATION time. A panel
    that defined no poll when registered has its internal poll pointer set to
    NULL, and Blender then never calls poll for it -- it always shows.
    Re-assigning `cls.poll` afterwards does nothing for those panels.

    => To hide/group a poll-less panel we must RE-REGISTER it with the wrapper
       already installed, so Blender starts calling the wrapper. Panels that
       already had a poll are picked up dynamically and need no re-register.

Safety properties retained:
  * Wrapper is idempotent, self-tagging, exception-guarded (never recurses,
    never crashes the draw).
  * NManager is inert until you actually use filtering. A fresh/empty layout
    touches nothing.
  * The one-time re-registration (when filtering is first used) is sub-panel
    safe (parent-before-child) and fully defensive (read-only types skipped).
"""

import bpy

SPACE = 'VIEW_3D'
REGION = 'UI'
PROTECTED = {"Tool", "Item", "View"}  # always visible in every group
HOME_ATTR = "_nm_home"
ORIG_ATTR = "_nm_orig_poll"

_hidden = set()         # home categories hidden outright
_group_of = {}          # home -> group name
_active_group = ""      # "" == show all
_wrapped = set()        # classes whose poll we've wrapped
_dispatched = set()     # homes re-registered so the wrapper is actually called


# --- enumeration ----------------------------------------------------------

def _gather_panel_classes():
    classes = []
    seen = set()
    stack = list(bpy.types.Panel.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
        classes.append(cls)
    panel_base = bpy.types.Panel
    for name in dir(bpy.types):
        try:
            cls = getattr(bpy.types, name)
        except Exception:
            continue
        if cls in seen:
            continue
        try:
            if isinstance(cls, type) and issubclass(cls, panel_base):
                seen.add(cls)
                classes.append(cls)
        except Exception:
            continue
    return classes


def iter_sidebar_panels():
    for cls in _gather_panel_classes():
        if cls.__name__.startswith("NM_"):
            continue
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


def _idname(cls):
    return getattr(cls, "bl_idname", None) or cls.__name__


def _subtree_sorted(cls_list):
    by_id = {_idname(c): c for c in cls_list}

    def depth(c):
        d, pid, seen = 0, getattr(c, "bl_parent_id", ""), set()
        while pid and pid in by_id and pid not in seen:
            seen.add(pid)
            d += 1
            pid = getattr(by_id[pid], "bl_parent_id", "")
        return d

    return sorted(cls_list, key=lambda c: (depth(c), getattr(c, "bl_order", 0)))


def _all_ui_panels():
    for cls in _gather_panel_classes():
        if cls.__name__.startswith("NM_"):
            continue
        if (getattr(cls, "bl_space_type", None) == SPACE
                and getattr(cls, "bl_region_type", None) == REGION):
            yield cls                     # include children (no bl_category)


def _with_descendants(cls_list):
    """cls_list plus every sub-panel descending from them. Re-registering a
    parent without its children orphans the children, which then render as
    loose panels in the viewport -- so the whole subtree moves together."""
    children_of = {}
    for c in _all_ui_panels():
        pid = getattr(c, "bl_parent_id", "")
        if pid:
            children_of.setdefault(pid, []).append(c)
    result, seen, stack = [], set(), list(cls_list)
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        result.append(c)
        stack.extend(children_of.get(_idname(c), []))
    return result


def _reregister(cls_list, category):
    recat = set(cls_list)                 # ONLY these get the new category
    ordered = _subtree_sorted(_with_descendants(cls_list))
    for c in reversed(ordered):           # children first
        _unregister(c)
    for c in ordered:                     # parents first
        if c in recat:                    # never set a category on a child
            try:
                c.bl_category = category
            except Exception as e:
                print(f"[NManager] cannot set category on {c.__name__}: {e}")
        _register(c)


# --- poll wrapper ---------------------------------------------------------

def _is_wrapper(poll_attr):
    fn = getattr(poll_attr, "__func__", poll_attr)
    return getattr(fn, "_nm_is_wrapper", False)


def _visible(cls):
    home = home_of(cls)
    if home in _hidden:
        return False
    if _active_group and home not in PROTECTED and _group_of.get(home, "") != _active_group:
        return False
    return True


def _wrap(cls):
    """Install the visibility wrapper. Returns True if this panel had NO poll
    at registration (so it needs a re-register before Blender will call us)."""
    own = cls.__dict__.get("poll", None)
    if own is not None and _is_wrapper(own):
        return False                      # already ours
    had_dispatcher = getattr(cls, "poll", None) is not None  # own OR inherited

    def poll(c, context):
        try:
            if not _visible(c):
                return False
            orig = getattr(c, ORIG_ATTR, None)
            if orig is not None:
                return orig.__func__(c, context)
            return True
        except Exception as e:
            print(f"[NManager] poll error {getattr(c, '__name__', '?')}: {e}")
            return True                   # fail open; never crash the draw

    poll._nm_is_wrapper = True
    try:
        setattr(cls, ORIG_ATTR, own)      # own poll only (None if inherited/none)
        cls.poll = classmethod(poll)
        _wrapped.add(cls)
    except Exception as e:
        print(f"[NManager] cannot wrap {cls.__name__}: {e}")
        return False
    return not had_dispatcher


def _unwrap(cls):
    existing = cls.__dict__.get("poll", None)
    if existing is None or not _is_wrapper(existing):
        _wrapped.discard(cls)
        return
    orig = getattr(cls, ORIG_ATTR, None)
    try:
        if orig is not None:
            cls.poll = orig
        else:
            try:
                del cls.poll
            except Exception:
                pass
        try:
            delattr(cls, ORIG_ATTR)
        except Exception:
            pass
    except Exception as e:
        print(f"[NManager] cannot unwrap {cls.__name__}: {e}")
    _wrapped.discard(cls)


def redraw():
    wm = bpy.context.window_manager
    if not wm:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            area.tag_redraw()


def _filtering_active():
    return bool(_active_group) or bool(_hidden)


def _ensure_filtering():
    """Wrap managed panels and, for any category containing poll-less panels,
    re-register it ONCE so Blender actually calls the wrapper. Idempotent."""
    groups = scan()
    for home, cls_list in groups.items():
        if home in _dispatched:
            for c in cls_list:
                _wrap(c)                  # keep wrappers fresh (cheap, idempotent)
            continue
        needs_reregister = False
        for c in cls_list:
            if _wrap(c):
                needs_reregister = True
        if needs_reregister:
            _reregister(cls_list, cls_list[0].bl_category)
        _dispatched.add(home)


# --- public: light state changes -----------------------------------------

def set_filters(hidden, group_of):
    global _hidden, _group_of
    _hidden = set(hidden)
    _group_of = dict(group_of)
    if _filtering_active():
        _ensure_filtering()
    redraw()


def set_active_group(name):
    global _active_group
    _active_group = name or ""
    if _filtering_active():
        _ensure_filtering()
    redraw()


# --- public: apply layout (rename / reorder) -----------------------------

def apply(entries, reorder=False):
    groups = scan()
    index = {e["home"]: e for e in entries}
    targets = {}
    for home in groups:
        entry = index.get(home, {})
        name = entry.get("name") or home
        suffix = entry.get("icon", "")
        targets[home] = f"{name} {suffix}" if suffix else name

    global _hidden, _group_of
    _hidden = {e["home"] for e in entries if e.get("hidden")}
    _group_of = {e["home"]: e["group"] for e in entries if e.get("group")}
    filtering = _filtering_active()

    if filtering:                         # wrap first so re-registration sticks
        for cls_list in groups.values():
            for c in cls_list:
                _wrap(c)

    if reorder:
        ordered = sorted(index.values(), key=lambda e: e.get("order", 0))
        seq = [e["home"] for e in ordered] + [h for h in groups if h not in index]
        for home in seq:
            _reregister(groups[home], targets[home])
        if filtering:
            _dispatched.update(groups.keys())
    else:
        for home, cls_list in groups.items():
            if any(c.bl_category != targets[home] for c in cls_list):
                _reregister(cls_list, targets[home])
                if filtering:
                    _dispatched.add(home)
        if filtering:
            _ensure_filtering()

    redraw()


def reset():
    global _hidden, _group_of, _active_group, _dispatched, _wrapped
    groups = scan()
    for cls in iter_sidebar_panels():
        _unwrap(cls)
    for home, cls_list in groups.items():
        if home in _dispatched or any(c.bl_category != home for c in cls_list):
            _reregister(cls_list, home)
    _hidden, _group_of, _active_group = set(), {}, ""
    _dispatched = set()
    _wrapped = set()
    redraw()
