#!/usr/bin/env python3
"""macOS menu-bar extra: click to switch locally saved CamillaDSP presets."""

from __future__ import annotations

import sys
from pathlib import Path

_MAX_PRESETS = 24


def is_supported() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSStatusBar  # noqa: F401

        return True
    except Exception:
        return False


def short_preset_label(path: Path) -> str:
    name = path.stem
    if name.startswith("cosplay_"):
        name = name[len("cosplay_") :]
    name = name.replace("_to_", " → ").replace("_", " ")
    if len(name) > 52:
        name = name[:49] + "…"
    return name


def _icon_path() -> Path | None:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "assets" / "icons" / "menubar.png",
        here / "assets" / "icons" / "menubarTemplate.png",
    ]
    try:
        import cosplay as cp

        bundled = cp.get_bundle_dir() / "assets" / "icons"
        candidates.extend(
            [
                bundled / "menubar.png",
                bundled / "menubarTemplate.png",
            ]
        )
    except Exception:
        pass
    for path in candidates:
        if path.is_file():
            return path
    return None


def _make_target_class():
    from Foundation import NSObject  # type: ignore

    class _Target(NSObject):
        controller = None

        def selectPreset_(self, sender) -> None:
            tag = int(sender.tag())
            path = getattr(self, "preset_map", {}).get(tag)
            app = self.controller.app
            if path is None:
                return
            app.root.after(0, lambda p=path: app._load_preset_from_menubar(p))

        def showWindow_(self, _sender) -> None:
            self.controller.app.root.after(0, self.controller.app._show_window)

        def hideWindow_(self, _sender) -> None:
            self.controller.app.root.after(0, self.controller.app._hide_to_menubar)

        def stopEngine_(self, _sender) -> None:
            self.controller.app.root.after(0, self.controller.app._on_stop)

        def refreshPresets_(self, _sender) -> None:
            self.controller.app.root.after(0, self.controller.app._refresh_presets)

        def quitApp_(self, _sender) -> None:
            self.controller.app.root.after(0, self.controller.app._quit_app)

    return _Target


class MenuBarController:
    """Owns an NSStatusItem. Callbacks hop back onto the Tk thread via root.after."""

    def __init__(self, app) -> None:
        self.app = app
        self._item = None
        self._target = None
        self._menu = None
        self._install()

    def _install(self) -> None:
        from AppKit import (  # type: ignore
            NSImage,
            NSMenu,
            NSStatusBar,
            NSVariableStatusItemLength,
        )

        Target = _make_target_class()
        self._target = Target.alloc().init()
        self._target.controller = self
        self._target.preset_map = {}

        bar = NSStatusBar.systemStatusBar()
        self._item = bar.statusItemWithLength_(NSVariableStatusItemLength)
        button = self._item.button()
        icon = _load_template_image(NSImage)
        if icon is not None:
            button.setImage_(icon)
            try:
                button.setToolTip_("EQ Cosplay")
            except Exception:
                pass
        else:
            button.setTitle_("EQ")
        self._menu = NSMenu.alloc().init()
        self._menu.setAutoenablesItems_(False)
        self._item.setMenu_(self._menu)
        self.rebuild()

    def rebuild(self) -> None:
        if self._item is None or self._target is None or self._menu is None:
            return
        try:
            from AppKit import NSMenuItem  # type: ignore
            import cosplay as cp
        except Exception:
            return

        menu = self._menu
        menu.removeAllItems()
        target = self._target
        t = self.app._t
        running = (
            getattr(self.app, "engine_proc", None) is not None
            and getattr(self.app.engine_proc, "poll", lambda: 0)() is None
        )
        active = getattr(self.app, "last_config", None)
        active_path = Path(active).resolve() if active else None
        if running and active_path is not None:
            status_title = t("gui_menubar_running", name=short_preset_label(active_path))
        elif running:
            status_title = t("gui_status_running")
        else:
            status_title = t("gui_menubar_idle")

        status = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            status_title, None, ""
        )
        status.setEnabled_(False)
        menu.addItem_(status)
        menu.addItem_(NSMenuItem.separatorItem())

        header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("gui_menubar_presets"), None, ""
        )
        header.setEnabled_(False)
        menu.addItem_(header)

        try:
            presets = cp.list_saved_presets()
        except Exception:
            presets = []
        target.preset_map = {}
        if not presets:
            empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                t("gui_menubar_no_presets"), None, ""
            )
            empty.setEnabled_(False)
            menu.addItem_(empty)
        else:
            for idx, path in enumerate(presets[:_MAX_PRESETS]):
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    short_preset_label(path), "selectPreset:", ""
                )
                item.setTarget_(target)
                item.setTag_(idx)
                item.setEnabled_(True)
                if active_path is not None and path.resolve() == active_path:
                    item.setState_(1)
                target.preset_map[idx] = path
                menu.addItem_(item)
            extra = len(presets) - _MAX_PRESETS
            if extra > 0:
                more = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    f"… +{extra}", None, ""
                )
                more.setEnabled_(False)
                menu.addItem_(more)

        menu.addItem_(NSMenuItem.separatorItem())

        def add(title: str, action: str, enabled: bool = True) -> None:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, ""
            )
            item.setTarget_(target)
            item.setEnabled_(bool(enabled))
            menu.addItem_(item)

        add(t("gui_menubar_show"), "showWindow:")
        add(t("gui_menubar_hide"), "hideWindow:")
        add(t("gui_menubar_refresh"), "refreshPresets:")
        add(t("gui_menubar_stop"), "stopEngine:", enabled=running)
        menu.addItem_(NSMenuItem.separatorItem())
        add(t("gui_menubar_quit"), "quitApp:")


def _load_template_image(NSImage):
    path = _icon_path()
    if path is None:
        return _draw_fallback_image(NSImage)
    try:
        img = NSImage.alloc().initWithContentsOfFile_(str(path))
        if img is None:
            return _draw_fallback_image(NSImage)
        # Colour artwork for menubar.png; template (black glyph) otherwise.
        img.setTemplate_(path.name.lower().endswith("template.png"))
        img.setSize_((18, 18))
        return img
    except Exception:
        return _draw_fallback_image(NSImage)


def _draw_fallback_image(NSImage):
    """Tiny template glyph so the extra still appears without an icon file."""
    try:
        from AppKit import NSBitmapImageRep, NSColor, NSFont, NSPoint  # type: ignore
        from Foundation import NSString  # type: ignore

        img = NSImage.alloc().initWithSize_((18, 18))
        img.lockFocus()
        NSColor.blackColor().set()
        font = NSFont.boldSystemFontOfSize_(9)
        NSString.stringWithString_("EQ").drawAtPoint_withAttributes_(
            NSPoint(1, 3),
            {"NSFont": font, "NSForegroundColor": NSColor.blackColor()},
        )
        img.unlockFocus()
        img.setTemplate_(True)
        return img
    except Exception:
        return None


def install(app):
    if not is_supported():
        return None
    try:
        return MenuBarController(app)
    except Exception as exc:
        try:
            print(f"[WARN] macOS menu bar extra failed: {exc}", flush=True)
        except Exception:
            pass
        return None
