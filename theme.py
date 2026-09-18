#!/usr/bin/env python3
"""EchoCR & Liquid Glass visual language for the EQ Cosplay Tk GUI.

Matches the visual style, color palette, and component design of eq_cosplay_swift
(ultra-dark panel UI, Liquid Glass cards, gold/teal/emerald accents, JetBrains Mono logs).
"""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Canvas, Frame, TclError
from tkinter import font as tkfont

# EchoCR & Swift Design Tokens (1:1 with EchoCRTheme.swift)
BG = "#0b0d11"              # Base window background
PANEL = "#12161d"           # Card surface fill
PANEL_GLASS = "#161b24"     # Elevated card surface
BORDER = "#2a3340"          # Base specular rim border
LINE = "#2a3340"            # Separators and table borders
BORDER_SPECULAR = "#3d4b5c" # Highlighted rim border
BORDER_SUBTLE = "#1e2633"   # Subtle inner border
TEXT = "#e8edf4"            # Primary text
MUTED = "#8b97a8"           # Secondary muted text
GOLD = "#d4a24a"            # Target curve accent & gold highlights
TEAL = "#5eead4"            # Source curve accent & teal highlights
EMERALD = "#34d399"         # Simulated curve & success indicators
OK = "#34d399"              # Success indicator
ROSE = "#f87171"            # Delta curve & error/warning indicators
SLOT = "#1a212c"            # Slot and row alternate fill
INPUT = "#0e1319"           # Input and search box background
BTN = "#1c232e"             # Default button background
BTN_HOVER = "#273140"       # Default button hover
PRIMARY_BG = "#12352f"      # Primary prominent action background
PRIMARY_LINE = "#2d6a62"    # Primary prominent action border
PRIMARY_HOVER = "#18453d"   # Primary prominent action hover
GOLD_BG = "#2a210f"         # Gold action background
LOG_BG = "#0a0d11"          # Terminal log background
LOG_FG = "#c5d0dc"          # Terminal log text
GLOW_GOLD = "#d4a24a"

# Plot Specific Tokens (matching FrequencyResponsePlotView.swift)
PLOT_FACE = "#0e1319"       # Canvas face
PLOT_GRID = "#1a222d"       # Grid lines
PLOT_SRC = "#8b97a8"        # Source curve (dim white / secondary)
PLOT_TGT = "#e8edf4"        # Target curve (pure white)
PLOT_SIM = "#34d399"        # Simulated curve (emerald)
PLOT_DELTA = "#f87171"      # Delta curve (rose)

UI_FAMILY_CANDIDATES = (
    ".AppleSystemUIFont",
    "SF Pro Display",
    "PingFang SC",
    "Helvetica Neue",
    "AR FangXinShuH7GBK HV",
    "AR FangXinShuH7GBK",
    "FangXinShu",
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
    """Create a Frame styled with Liquid Glass aesthetics (panel background, subtle rim border)."""
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
    radius: float = 8,
    **kwargs,
) -> int:
    """Draw a smooth rounded polygon on a Tk Canvas."""
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
    return canvas.create_polygon(points, smooth=True, **kwargs)


def apply(root) -> dict:
    """Paint the EchoCR Liquid Glass dark theme onto a Tk root."""
    from tkinter import ttk

    resolve_families(root)
    ui = ui_family()
    mono = mono_family()

    ui14 = (ui, 14)
    ui13 = (ui, 13)
    ui12 = (ui, 12)
    ui11 = (ui, 11)
    ui10 = (ui, 10)
    ui9 = (ui, 9)
    title = (ui, 13, "bold")
    mark_font = (ui, 13, "bold")
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
        root.option_add("*TCombobox*Listbox.selectBackground", GOLD_BG)
        root.option_add("*TCombobox*Listbox.selectForeground", GOLD)
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
    style.configure("Section.TLabel", background=BG, foreground=MUTED, font=ui11)
    style.configure("Gold.TLabel", background=BG, foreground=GOLD, font=ui11)
    style.configure("Teal.TLabel", background=BG, foreground=TEAL, font=ui11)
    style.configure("Ok.TLabel", background=BG, foreground=OK, font=ui11)
    style.configure("Rose.TLabel", background=BG, foreground=ROSE, font=ui11)

    # Status pills (matching Liquid Glass status badge)
    style.configure(
        "Pill.TLabel",
        background=SLOT,
        foreground=MUTED,
        font=ui10,
        padding=(10, 4),
        bordercolor=BORDER,
        relief="solid",
    )
    style.configure(
        "PillOn.TLabel",
        background="#0c231c",
        foreground=OK,
        font=ui10,
        padding=(10, 4),
        bordercolor="#1b4d3e",
        relief="solid",
    )
    style.configure(
        "PillOff.TLabel",
        background="#1c1111",
        foreground=ROSE,
        font=ui10,
        padding=(10, 4),
        bordercolor="#4a1f1f",
        relief="solid",
    )

    style.configure(
        "TLabelframe",
        background=PANEL,
        foreground=TEXT,
        bordercolor=BORDER,
        relief="solid",
        padding=8,
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
        padding=(12, 6),
        font=ui11,
        relief="flat",
        wraplength=0,
        justify="center",
    )
    style.map(
        "TButton",
        background=[("disabled", PANEL), ("pressed", SLOT), ("active", BTN_HOVER)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("disabled", BORDER_SUBTLE), ("active", BORDER_SPECULAR), ("pressed", BORDER_SPECULAR)],
    )

    # Primary Prominent Button (e.g. Deploy to CamillaDSP)
    style.configure(
        "Primary.TButton",
        background=PRIMARY_BG,
        foreground=TEAL,
        bordercolor=PRIMARY_LINE,
        darkcolor=PRIMARY_BG,
        lightcolor=PRIMARY_BG,
        padding=(14, 6),
        font=ui11,
        wraplength=0,
        justify="center",
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", PANEL), ("pressed", "#0b2420"), ("active", PRIMARY_HOVER)],
        foreground=[("disabled", MUTED), ("active", TEAL)],
        bordercolor=[("disabled", BORDER_SUBTLE), ("active", TEAL)],
    )

    # Gold Button
    style.configure(
        "Gold.TButton",
        background=GOLD_BG,
        foreground=GOLD,
        bordercolor=GOLD,
        darkcolor=GOLD_BG,
        lightcolor=GOLD_BG,
        padding=(12, 6),
        font=ui11,
        wraplength=0,
        justify="center",
    )
    style.map(
        "Gold.TButton",
        background=[("disabled", PANEL), ("pressed", "#1c160a"), ("active", "#3a2d14")],
        foreground=[("disabled", MUTED), ("active", GOLD)],
        bordercolor=[("disabled", BORDER_SUBTLE), ("active", GOLD)],
    )

    # Ghost Button
    style.configure(
        "Ghost.TButton",
        background=BG,
        foreground=TEXT,
        bordercolor=BORDER,
        darkcolor=BG,
        lightcolor=BG,
        padding=(10, 5),
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
        bordercolor=[("focus", TEAL), ("active", BORDER_SPECULAR)],
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
        bordercolor=[("focus", TEAL), ("active", BORDER_SPECULAR)],
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
    style.map(
        "Treeview",
        background=[("selected", "#222d3d")],
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
        "mark": mark_font,
        "mono11": mono11,
        "mono10": mono10,
        "mono9": mono9,
        "style": style,
    }


def make_mark(parent, text: str = "EQ", size: int = 32) -> Canvas:
    """Gold-bordered square mark, matching EchoCR `.mark`."""
    cv = Canvas(
        parent,
        width=size,
        height=size,
        bg=BG,
        highlightthickness=0,
        bd=0,
    )
    inset = 1
    cv.create_rectangle(
        inset,
        inset,
        size - inset,
        size - inset,
        outline=GOLD,
        width=1,
    )
    cv.create_text(
        size / 2,
        size / 2,
        text=text,
        fill=GOLD,
        font=(ui_family(), max(10, size // 3), "bold"),
    )
    return cv


def style_log_widget(widget, mono_font) -> None:
    try:
        widget.configure(
            background=LOG_BG,
            foreground=LOG_FG,
            insertbackground=TEXT,
            selectbackground="#1e2c3d",
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
