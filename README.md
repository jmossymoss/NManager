# NManager

A Blender add-on for managing the 3D viewport sidebar (N-panel) tabs. Rename,
reorder, hide, and group your N-panel tabs — and switch between groups from a
menu in the top-right of the viewport.

If you run a stack of add-ons (HardOps, BoxCutter, MACHIN3, Zen UV, …) and your
sidebar has turned into an unreadable wall of tabs, NManager lets you tidy it
into named groups and show only what you need for the task at hand.

- **Maintainer:** Jordan Moss
- **Blender:** 4.5 or newer (extension format)
- **License:** GPL-3.0-or-later

---

## Features

- **Rename** any sidebar tab.
- **Reorder** tabs, and reorder within a group.
- **Hide** tabs you never use.
- **Icons** — assign a unicode shape symbol to any tab or group. The symbol
  appears as a suffix directly in the N-panel sidebar tab label (e.g.
  `Modelling ●`). 24 symbols available across three categories: Filled,
  Outline, and Special.
- **Groups** — assign tabs to named groups and switch the active group from the
  top-right of the viewport header. The sidebar then shows only that group's
  tabs.
- **Always-visible tabs** — Tool, View, and Item are pinned and always shown
  regardless of the active group.
- **Per-group ordering** — reorder a group's tabs independently.
- **Import / export** your layout as JSON, and automatic persistence between
  sessions.
- **Reset** — restore the original sidebar at any time.

All management lives in **Add-on Preferences**, so it doesn't add clutter to the
very sidebar it's cleaning up. The only in-viewport control is the group
switcher.

---

## Installation

1. Download the latest release `.zip` (or zip the `NManager/` folder yourself).
2. In Blender: **Edit > Preferences > Get Extensions > Install from Disk…**
   (or simply drag the `.zip` into the Blender window).
3. Enable **NManager** if it isn't already.

---

## Usage

**Manage tabs:** open **Edit > Preferences > Add-ons > NManager** and expand it.

- **Tabs** (left): click a row to select it, then use the up/down buttons to
  reorder or the pencil to rename. Toggle the eye to hide a tab, and use the
  group field to assign it to a group. Click the symbol button at the start of
  a row to pick an icon that will appear as a suffix in the sidebar tab label.
- **Groups** (right): create, rename, reorder, and remove groups. The radio
  button activates a group. Click the symbol button next to a group to pick an
  icon for it — the icon appears in the group switcher menu and viewport header.
- **Apply** commits names and order; **Reset** restores the original sidebar.
- Tick **Limit list to active group** to focus the list on one group and
  reorder within it.
- The preferences list scales vertically with the window — resize it and the
  tab/group lists grow to fill the available space.

**Switch groups:** use the **group menu at the top-right of the viewport
header**. Pick *All Tabs* to show everything, or a group to show only its tabs.

### Icon picker

Click the small symbol button (shows `·` when no icon is set) at the left of
any tab or group row to open the picker. Icons are grouped into:

| Group   | Symbols |
|---------|---------|
| Filled  | ● ■ ▲ ▼ ◆ ★ ▶ ◀ |
| Outline | ○ □ △ ▽ ◇ ☆ ▷ ◁ |
| Special | ◉ ◎ ◈ ◐ ♦ ♣ ♠ ♥ |

> **Note:** Blender sidebar tab labels are plain text, so icons are unicode
> characters and render in the theme's text colour. Colour icons are not
> possible.

---

## How it works

NManager uses two mechanisms, kept separate on purpose:

- **Rename / reorder** re-register the affected panels (the only way to change a
  tab's name or strip position in Blender). This happens on Apply or when you
  reorder — never silently.
- **Hide / group** wrap each panel's `poll` to control visibility. Switching
  groups is just a state change and a redraw, so it's instant.

Groups are *visibility filters*, not folded mega-tabs, which keeps switching
cheap and reversible. NManager stays inert until you actually configure
something, and **Reset** always restores the original sidebar.

---

## Known limitations

- Some add-ons inject sidebar content via a draw callback rather than their own
  panel (e.g. certain autoConstraints content). NManager can't gate those by
  visibility, so they may stay visible inside a group.
- A panel that inherits its `poll` from a base class has that inherited check
  bypassed while wrapped (it fails open), so it could appear in a context where
  it would normally be hidden.
- Drag-and-drop tab reordering isn't supported by Blender's UI API; use the
  up/down buttons.

---

## Compatibility note

NManager re-registers third-party panels to apply changes. It does this
defensively (subtree-safe, exception-guarded, and only when you use a feature),
but if you hit an issue with a specific add-on, please open an issue with the
add-on name and a console log.

---

## Contributing

Issues and pull requests welcome. When reporting a bug, include your Blender
version, the add-ons involved, and any `[NManager]` lines from the system
console.
