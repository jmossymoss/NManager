"""Core engine.

Safety model (this file was the cause of hard crashes; these properties matter):

  * The poll wrapper is IDEMPOTENT and SELF-TAGGING. It can never wrap itself,
    so re-enabling the add-on cannot stack wrappers into infinite recursion.
    Every wrapper body is also exception-guarded (fail open / show the panel).

  * NManager is INERT until configured. `apply` only re-registers panels whose
    category actually changes (renames), and only wraps polls for panels that
    are actually hidden, grouped, or hidden by an active group. A fresh/empty
    layout touches nothing.

  * The dangerous global reorder (re-registering every panel to change the tab
    strip order) is opt-in via `reorder=True`, so it only runs on a deliberate
    user action -- never at enable/startup.

  * Re-registration is sub-panel safe: panels are ordered parent-before-child
    by walking bl_parent_id chains, so nested sub-panels don't get orphaned.
"""

import bpy

SPACE = 'VIEW_3D'
REGION = 'UI'
PROTECTED = {"Tool", "Item"}
HOME_ATTR = "_nm_home"
ORIG_ATTR = "_nm_orig_poll"
WRAP_TAG = "_nm_is_wrapper"

_hidden = set()        # home categories hidden outright
_group_of = {}         # home -> group name
_active_group = ""     # "" == show all


# --- enumeration ----------------------------------------------------------

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


def _idname(cls):
    return getattr(cls, "bl_idname", None) or cls.__name__


def _subtree_sorted(cls_list):
    """Parents before children, by walking bl_parent_id within this set."""
    by_id = {_idname(c): c for c in cls_list}

    def depth(c):
        d, pid, seen = 0, getattr(c, "bl_parent_id", ""), set()
        while pid and pid in by_id and pid not in seen:
            seen.add(pid)
            d += 1
            pid = getattr(by_id[pid], "bl_parent_id", "")
        return d

    return sorted(cls_list, key=lambda c: (depth(c), getattr(c, "bl_order", 0)))


def _reregister(cls_list, category):
    ordered = _subtree_sorted(cls_list)
    for c in reversed(ordered):          # children first
        _unregister(c)
    for c in ordered:                    # parents first
        c.bl_category = category
        _register(c)


# --- poll wrapper (idempotent, recursion-proof, exception-safe) ----------

def _is_wrapper(poll_attr):
    fn = getattr(poll_attr, "__func__", poll_attr)
    return getattr(fn, WRAP_TAG, False)


def _visible(cls):
    home = home_of(cls)
    if home in _hidden:
        return False
    if _active_group and _group_of.get(home, "") != _active_group:
        return False
    return True


def _wrap(cls):
    existing = cls.__dict__.get("poll", None)
    if existing is not None and _is_wrapper(existing):
        return                            # already ours -- never re-wrap
    setattr(cls, ORIG_ATTR, existing)     # genuine original (classmethod/None)

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
    cls.poll = classmethod(poll)


def _unwrap(cls):
    existing = cls.__dict__.get("poll", None)
    if existing is None or not _is_wrapper(existing):
        return
    orig = getattr(cls, ORIG_ATTR, None)
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


def _apply_wraps():
    """Wrap only panels that need filtering; unwrap the rest."""
    group_active = bool(_active_group)
    for cls in iter_sidebar_panels():
        home = home_of(cls)
        need = group_active or (home in _hidden) or (home in _group_of)
        if need:
            _wrap(cls)
        else:
            _unwrap(cls)


def redraw():
    wm = bpy.context.window_manager
    if not wm:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            area.tag_redraw()


# --- public: light updates (no re-registration) --------------------------

def set_filters(hidden, group_of):
    global _hidden, _group_of
    _hidden = set(hidden)
    _group_of = dict(group_of)
    _apply_wraps()
    redraw()


def set_active_group(name):
    global _active_group
    _active_group = name or ""
    _apply_wraps()                        # group on/off changes wrap set
    redraw()


# --- public: apply layout -------------------------------------------------

def apply(entries, reorder=False):
    """Rename categories (always, minimal) and optionally reorder the strip.

    reorder=False : only re-register panels whose category actually changes.
                    Safe; used at startup and for renames/filters.
    reorder=True  : re-register every panel in the requested order (the risky
                    path). Only call from a deliberate user action.
    """
    groups = scan()
    index = {e["home"]: e for e in entries}
    targets = {home: (index.get(home, {}).get("name") or home)
               for home in groups}

    if reorder:
        ordered = sorted(index.values(), key=lambda e: e.get("order", 0))
        seq = [e["home"] for e in ordered] + [h for h in groups if h not in index]
        flat = []
        for home in seq:
            flat.extend((c, targets[home]) for c in _subtree_sorted(groups[home]))
        for c, _ in reversed(flat):
            _unregister(c)
        for c, target in flat:
            c.bl_category = target
            _register(c)
    else:
        for home, cls_list in groups.items():
            target = targets[home]
            if any(c.bl_category != target for c in cls_list):
                _reregister(cls_list, target)

    set_filters(
        {e["home"] for e in entries if e.get("hidden")},
        {e["home"]: e["group"] for e in entries if e.get("group")},
    )


def reset():
    groups = scan()
    for cls in iter_sidebar_panels():
        _unwrap(cls)
    for home, cls_list in groups.items():
        if any(c.bl_category != home for c in cls_list):
            _reregister(cls_list, home)
    global _hidden, _group_of, _active_group
    _hidden, _group_of, _active_group = set(), {}, ""
    redraw()
