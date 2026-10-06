#!/usr/bin/env python3
"""Neutral industrial visual language for the EQ Cosplay Tk GUI.

Tk widgets use solid graphite surfaces with fine borders. Source, target, and
simulated response use restrained cool gray, steel blue, and sage gray. Legacy
``make_glass_frame`` naming remains for callers, although Tk does not blur widgets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Canvas, Frame, TclError
from tkinter import font as tkfont

# Neutral surfaces and semantic response roles. Older names remain aliases so
# existing callers can migrate without preserving the former warm palette.
BG = "#111418"              # Main window
PANEL = "#191e23"           # Card surface
PANEL_GLASS = "#20262c"     # Elevated surface (legacy name)
BORDER = "#343d45"          # Structural border
LINE = "#2c343b"            # Separators and table rules
BORDER_SPECULAR = "#72808a" # Focus and hover rim
BORDER_SUBTLE = "#283038"   # Quiet inner border
TEXT = "#e4e9ec"            # Primary text
MUTED = "#9ca8b0"           # Secondary text
PLOT_SRC = "#b5c0c8"         # Source response: cool light gray
PLOT_TGT = "#879aa8"         # Target response: muted steel blue
PLOT_SIM = "#9eaaa2"         # Simulated response: muted sage gray
PLOT_DELTA = "#aa9695"       # Residual: low-saturation warm gray
SILVER = PLOT_SRC
CHAMPAGNE = PLOT_TGT
GOLD = PLOT_TGT              # Compatibility alias; value is cool steel blue
TEAL = "#aab5bd"             # Neutral legacy accent
EMERALD = "#9eaaa2"          # Compatibility alias; subdued success/simulation
OK = "#9eaaa2"
ROSE = "#aa9695"
SLOT = "#222930"             # Slot and alternate row fill
INPUT = "#14191d"            # Input surface
BTN = "#252d33"              # Default button
BTN_HOVER = "#303a42"        # Clearly visible hover state
PRIMARY_BG = "#cbd3d8"       # High-contrast neutral action
PRIMARY_FG = "#111519"
PRIMARY_LINE = "#e1e7ea"
PRIMARY_HOVER = "#e2e7ea"
GOLD_BG = "#2a3035"          # Neutral compatibility surface
LOG_BG = "#12171b"
LOG_FG = "#c6cdd1"
GLOW_GOLD = GOLD

# Plot role colors follow the same semantic order across views.
PLOT_FACE = "#151a1e"       # Plot face
PLOT_GRID = "#2b343b"       # Quiet grid lines

FOCUS = "#aab8c1"
SUCCESS = OK
WARNING = "#a9aaa3"
ERROR = ROSE

UI_FAMILY_CANDIDATES = (
    ".AppleSystemUIFont",
    "Segoe UI",
    "Microsoft YaHei UI",
    "PingFang SC",
    "Yu Gothic UI",
    "Meiryo",
    "Helvetica Neue",
    "Arial",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "sans-serif",
)
MONO_FAMILY_CANDIDATES = (
    "JetBrains Mono",
    "JetBrains Mono Regular",
    "JetBrainsMono-Regular",
    "Menlo",
    "SF Mono",
)

_FONTS_REGISTERED = False
_UI_FAMILY = ""
_MONO_FAMILY = ""


def assets_dir() -> Path:
    here = Path(__file__).resolve().parent
    bundled = None
    try:
        import cosplay as cp

        bundled = cp.get_bundle_dir() / "assets"
    except Exception:
        bundled = None
    if bundled is not None and bundled.is_dir():
        return bundled
    return here / "assets"


def fonts_dir() -> Path:
    return assets_dir() / "fonts"


def _register_font_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if sys.platform == "darwin":
        return _register_font_macos(path)
    if sys.platform == "win32":
        return _register_font_windows(path)
    return _register_font_fontconfig(path)


def _register_font_macos(path: Path) -> bool:
    try:
        from ctypes import c_bool, c_char_p, c_int32, c_void_p, cdll
        from ctypes.util import find_library

        ct_name = find_library("CoreText")
        cf_name = find_library("CoreFoundation")
        if not ct_name or not cf_name:
            return False
        ct = cdll.LoadLibrary(ct_name)
        cf = cdll.LoadLibrary(cf_name)
        cf.CFURLCreateFromFileSystemRepresentation.restype = c_void_p
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
            c_void_p,
            c_char_p,
            c_int32,
            c_bool,
        ]
        raw = str(path.resolve()).encode("utf-8")
        url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
        if not url:
            return False
        ct.CTFontManagerRegisterFontsForURL.restype = c_bool
        ct.CTFontManagerRegisterFontsForURL.argtypes = [c_void_p, c_int32, c_void_p]
        ok = bool(ct.CTFontManagerRegisterFontsForURL(url, 1, None))
        try:
            cf.CFRelease.argtypes = [c_void_p]
            cf.CFRelease(url)
        except Exception:
            pass
        return ok
    except Exception:
        return False


def _register_font_windows(path: Path) -> bool:
    try:
        import ctypes

        FR_PRIVATE = 0x10
        AddFontResourceExW = ctypes.windll.gdi32.AddFontResourceExW
        AddFontResourceExW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_void_p,
        ]
        AddFontResourceExW.restype = ctypes.c_int
        return AddFontResourceExW(str(path.resolve()), FR_PRIVATE, None) > 0
    except Exception:
        return False


def _register_font_fontconfig(path: Path) -> bool:
    try:
        import os
        import subprocess

        os.environ.setdefault("FONTCONFIG_PATH", "/etc/fonts")
        dest_dir = Path.home() / ".local" / "share" / "fonts" / "eq-cosplay"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        if not dest.exists():
            dest.write_bytes(path.read_bytes())
        subprocess.run(["fc-cache", "-f", str(dest_dir)], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def register_bundled_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    folder = fonts_dir()
    for name in ("fang-xin-shu.ttf", "JetBrainsMono-Regular.ttf"):
        _register_font_file(folder / name)
    _FONTS_REGISTERED = True


def _pick_family(root, candidates: tuple[str, ...], fallback: str) -> str:
    try:
        available = set(tkfont.families(root))
    except Exception:
        available = set()
    for name in candidates:
        if name in available:
            return name
    lower = {n.lower(): n for n in available}
    for name in candidates:
        hit = lower.get(name.lower())
        if hit:
            return hit
        for actual, orig in lower.items():
            if name.lower() in actual:
                return orig
    return fallback


def resolve_families(root) -> tuple[str, str]:
    global _UI_FAMILY, _MONO_FAMILY
    register_bundled_fonts()
    ui_fallback = "PingFang SC" if sys.platform == "darwin" else (
        "Microsoft YaHei UI" if sys.platform == "win32" else "sans-serif"
    )
    mono_fallback = "Menlo" if sys.platform == "darwin" else (
        "Consolas" if sys.platform == "win32" else "monospace"
    )
    _UI_FAMILY = _pick_family(root, UI_FAMILY_CANDIDATES, ui_fallback)
    _MONO_FAMILY = _pick_family(root, MONO_FAMILY_CANDIDATES, mono_fallback)
    return _UI_FAMILY, _MONO_FAMILY


def ui_family() -> str:
    return _UI_FAMILY or UI_FAMILY_CANDIDATES[0]


def mono_family() -> str:
    return _MONO_FAMILY or MONO_FAMILY_CANDIDATES[0]


def make_glass_frame(parent, padding: int = 10, **kwargs) -> Frame:
    """Create a solid graphite card with a quiet border (legacy function name)."""
    frame = Frame(
        parent,
        bg=PANEL,
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=BORDER_SPECULAR,
        padx=padding,
        pady=padding,
        **kwargs,
    )
    return frame


def draw_rounded_rect(
    canvas: Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float = 0,
    **kwargs,
) -> int:
    """Draw a square polygon by default, with optional softened corners."""
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=bool(r), **kwargs)


def apply(root) -> dict:
    """Apply the shared graphite material and semantic response palette."""
    from tkinter import ttk

    resolve_families(root)
    ui = ui_family()
    mono = mono_family()

    ui24 = (ui, 22, "bold")
    ui14 = (ui, 14)
    ui13 = (ui, 13)
    ui12 = (ui, 12)
    ui11 = (ui, 11)
    ui10 = (ui, 10)
    ui9 = (ui, 9)
    title = (ui, 15)
    hero = (ui, 18)
    subhead = (ui, 13)
    caption = (ui, 9)
    metric = (mono, 16)
    mark_font = (ui, 12, "bold")
    mono11 = (mono, 11)
    mono10 = (mono, 10)
    mono9 = (mono, 9)

    try:
        root.configure(bg=BG)
    except Exception:
        pass
    try:
        root.option_add("*tearOff", False)
        root.option_add("*Font", ui12)
        root.option_add("*Background", BG)
        root.option_add("*Foreground", TEXT)
        root.option_add("*TCombobox*Listbox.background", INPUT)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", SLOT)
        root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        root.option_add("*TCombobox*Listbox.font", ui11)
        root.option_add("*Entry.background", INPUT)
        root.option_add("*Entry.foreground", TEXT)
        root.option_add("*Entry.insertBackground", TEXT)
        root.option_add("*Text.background", LOG_BG)
        root.option_add("*Text.foreground", LOG_FG)
        root.option_add("*Text.font", mono10)
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except TclError:
        pass

    style.configure(".", background=BG, foreground=TEXT, font=ui12, bordercolor=BORDER)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Glass.TFrame", background=PANEL)
    style.configure("Top.TFrame", background=BG)

    style.configure("TLabel", background=BG, foreground=TEXT, font=ui12)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=ui12)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=ui10)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=ui10)
    style.configure("Title.TLabel", background=BG, foreground=TEXT, font=title)
    style.configure("Hero.TLabel", background=BG, foreground=TEXT, font=hero)
    style.configure("Subhead.TLabel", background=BG, foreground=TEXT, font=subhead)
    style.configure("Caption.TLabel", background=BG, foreground=MUTED, font=caption)
    style.configure("Metric.TLabel", background=PANEL, foreground=CHAMPAGNE, font=metric)
    style.configure("Section.TLabel", background=BG, foreground=MUTED, font=ui11)
    style.configure("Gold.TLabel", background=BG, foreground=GOLD, font=ui11)
    style.configure("Teal.TLabel", background=BG, foreground=TEAL, font=ui11)
    style.configure("Ok.TLabel", background=BG, foreground=OK, font=ui11)
    style.configure("Rose.TLabel", background=BG, foreground=ROSE, font=ui11)

    # Compact status pills use the same surface and border hierarchy.
    style.configure(
        "Pill.TLabel",
        background=SLOT,
        foreground=MUTED,
        font=ui10,
        padding=(9, 4),
        bordercolor=BORDER,
        relief="solid",
    )
    style.configure(
        "PillOn.TLabel",
        background="#202a2f",
        foreground=OK,
        font=ui10,
        padding=(9, 4),
        bordercolor="#405059",
        relief="solid",
    )
    style.configure(
        "PillOff.TLabel",
        background="#2c2828",
        foreground=ROSE,
        font=ui10,
        padding=(9, 4),
        bordercolor="#514747",
        relief="solid",
    )

    style.configure(
        "TLabelframe",
        background=PANEL,
        foreground=TEXT,
        bordercolor=BORDER,
        relief="solid",
        padding=9,
    )
    style.configure(
        "TLabelframe.Label",
        background=PANEL,
        foreground=TEXT,
        font=ui11,
    )

    # Buttons
    style.configure(
        "TButton",
        background=BTN,
        foreground=TEXT,
        bordercolor=BORDER,
        darkcolor=BTN,
        lightcolor=BTN,
        focusthickness=0,
        padding=(10, 5),
        font=ui11,
        relief="flat",
        wraplength=0,
        justify="center",
    )
    style.map(
        "TButton",
        background=[("disabled", PANEL), ("pressed", SLOT), ("active", BTN_HOVER)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("disabled", BORDER_SUBTLE), ("focus", FOCUS), ("active", BORDER_SPECULAR), ("pressed", BORDER_SPECULAR)],
    )

    # Compact tabs share the same neutral system; selection is a fine border
    # and a slight surface lift so persistent footer actions retain hierarchy.
    style.configure("Tab.TButton", background=PANEL, foreground=MUTED,
                    bordercolor=BORDER_SUBTLE, darkcolor=PANEL, lightcolor=PANEL,
                    padding=(9, 4), font=ui10, relief="flat")
    style.map("Tab.TButton",
              background=[("pressed", SLOT), ("active", SLOT)],
              foreground=[("disabled", MUTED), ("active", TEXT)],
              bordercolor=[("focus", BORDER_SPECULAR), ("active", BORDER)])
    style.configure("Selected.Tab.TButton", background=SLOT, foreground=TEXT,
                    bordercolor=BORDER_SPECULAR, darkcolor=SLOT, lightcolor=SLOT,
                    padding=(9, 4), font=ui10, relief="solid")
    style.map("Selected.Tab.TButton",
              background=[("pressed", BTN_HOVER), ("active", SLOT)],
              foreground=[("disabled", MUTED)],
              bordercolor=[("focus", TEXT), ("active", BORDER_SPECULAR)])

    # Primary Prominent Button (e.g. Deploy to CamillaDSP)
    style.configure(
        "Primary.TButton",
        background=PRIMARY_BG,
        foreground=PRIMARY_FG,
        bordercolor=PRIMARY_LINE,
        darkcolor=PRIMARY_BG,
        lightcolor=PRIMARY_BG,
        padding=(12, 5),
        font=ui11,
        wraplength=0,
        justify="center",
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", PANEL), ("pressed", "#b4bec4"), ("active", PRIMARY_HOVER)],
        foreground=[("disabled", MUTED), ("active", PRIMARY_FG)],
        bordercolor=[("disabled", BORDER_SUBTLE), ("active", PRIMARY_LINE)],
    )

    # Legacy gold-button style maps to the neutral secondary action.
    style.configure(
        "Gold.TButton",
        background=BTN,
        foreground=TEXT,
        bordercolor=BORDER_SPECULAR,
        darkcolor=BTN,
        lightcolor=BTN,
        padding=(10, 5),
        font=ui11,
        wraplength=0,
        justify="center",
    )
    style.map(
        "Gold.TButton",
        background=[("disabled", PANEL), ("pressed", SLOT), ("active", BTN_HOVER)],
        foreground=[("disabled", MUTED), ("active", TEXT)],
        bordercolor=[("disabled", BORDER_SUBTLE), ("active", BORDER_SPECULAR)],
    )

    # Ghost Button
    style.configure(
        "Ghost.TButton",
        background=BG,
        foreground=TEXT,
        bordercolor=BORDER,
        darkcolor=BG,
        lightcolor=BG,
        padding=(8, 4),
        font=ui11,
        wraplength=0,
        justify="center",
    )
    style.map(
        "Ghost.TButton",
        background=[("disabled", BG), ("pressed", SLOT), ("active", SLOT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("active", BORDER_SPECULAR)],
    )

    # Entry & Combobox
    style.configure(
        "TEntry",
        fieldbackground=INPUT,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        insertcolor=TEXT,
        padding=5,
        font=ui11,
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", SLOT), ("readonly", INPUT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("focus", FOCUS), ("active", BORDER_SPECULAR)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=INPUT,
        background=INPUT,
        foreground=TEXT,
        bordercolor=BORDER,
        arrowcolor=MUTED,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=5,
        font=ui11,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", INPUT), ("disabled", SLOT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("focus", FOCUS), ("active", BORDER_SPECULAR)],
        arrowcolor=[("active", TEXT)],
    )

    # Treeview
    style.configure(
        "Treeview",
        background=SLOT,
        fieldbackground=SLOT,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        rowheight=24,
        font=mono10,
    )
    style.configure(
        "Treeview.Heading",
        background=PANEL,
        foreground=MUTED,
        bordercolor=BORDER,
        relief="flat",
        font=ui10,
        padding=4,
    )
    style.configure("Numeric.Treeview", background=SLOT, fieldbackground=SLOT,
                    foreground=TEXT, bordercolor=BORDER, rowheight=25, font=mono10)
    style.configure("Numeric.Treeview.Heading", background=PANEL, foreground=MUTED,
                    bordercolor=BORDER, relief="flat", font=ui10, padding=4)
    style.map(
        "Treeview",
        background=[("selected", "#303a42")],
        foreground=[("selected", TEXT)],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", SLOT)],
        foreground=[("active", TEXT)],
    )

    # Scrollbar
    style.configure(
        "TScrollbar",
        background=SLOT,
        troughcolor=BG,
        bordercolor=BORDER,
        arrowcolor=MUTED,
        darkcolor=SLOT,
        lightcolor=SLOT,
    )
    style.map(
        "TScrollbar",
        background=[("active", BORDER)],
        arrowcolor=[("active", TEXT)],
    )

    return {
        "ui": ui,
        "mono": mono,
        "ui14": ui14,
        "ui13": ui13,
        "ui12": ui12,
        "ui11": ui11,
        "ui10": ui10,
        "ui9": ui9,
        "title": title,
        "ui24": ui24,
        "hero": hero,
        "subhead": subhead,
        "caption": caption,
        "metric": metric,
        "mark": mark_font,
        "mono11": mono11,
        "mono10": mono10,
        "mono9": mono9,
        "style": style,
    }


def make_mark(parent, text: str = "EQ", size: int = 32) -> Canvas:
    """Create the compact sound-transformation emblem used in the header."""
    from vector_icons import draw_brand_mark

    cv = Canvas(
        parent,
        width=size,
        height=size,
        bg=BG,
        highlightthickness=0,
        bd=0,
    )
    draw_brand_mark(cv, 1, 1, size - 2, color=PLOT_SRC, secondary=PLOT_TGT, tag="brand-mark")
    if text and text != "EQ":
        cv.create_text(size / 2, size / 2, text=text, fill=TEXT,
                       font=(ui_family(), max(9, size // 4)),
                       tags=("brand-mark-label",))
    return cv


def style_log_widget(widget, mono_font) -> None:
    try:
        widget.configure(
            background=LOG_BG,
            foreground=LOG_FG,
            insertbackground=TEXT,
            selectbackground="#303a42",
            selectforeground=TEXT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER_SPECULAR,
            relief="flat",
            borderwidth=0,
            font=mono_font,
        )
    except Exception:
        pass


def pill_style_for_status(status_key: str) -> str:
    running = {"gui_status_running", "gui_status_preset", "gui_status_deploy"}
    fail = {
        "gui_status_db_fail",
        "gui_status_calc_fail",
        "gui_status_deploy_fail",
        "gui_status_engine_fail",
        "gui_status_exited",
    }
    if status_key in running:
        return "PillOn.TLabel"
    if status_key in fail:
        return "PillOff.TLabel"
    return "Pill.TLabel"
