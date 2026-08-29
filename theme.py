#!/usr/bin/env python3
"""EchoCR visual language for the EQ Cosplay Tk GUI.

Colors, type, and component chrome are taken from EchoCR's `web/app.css`
(dark panel UI, gold mark, teal primary, JetBrains Mono logs).
"""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Canvas, TclError
from tkinter import font as tkfont

# EchoCR :root tokens
BG = "#0b0d11"
PANEL = "#12161d"
LINE = "#2a3340"
TEXT = "#e8edf4"
MUTED = "#8b97a8"
GOLD = "#d4a24a"
TEAL = "#5eead4"
ROSE = "#f87171"
OK = "#34d399"
SLOT = "#1a212c"
INPUT = "#0e1319"
BTN = "#1c232e"
PRIMARY_BG = "#12352f"
PRIMARY_LINE = "#2d6a62"
GOLD_BG = "#2a210f"
LOG_BG = "#0a0d11"
LOG_FG = "#c5d0dc"
GLOW_GOLD = "#d4a24a"
PLOT_SRC = "#5eead4"
PLOT_TGT = "#d4a24a"
PLOT_SIM = "#34d399"
PLOT_GRID = "#2a3340"
PLOT_FACE = "#0e1319"

UI_FAMILY_CANDIDATES = (
    "AR FangXinShuH7GBK HV",
    "AR FangXinShuH7GBK",
    "FangXinShu",
)
MONO_FAMILY_CANDIDATES = (
    "JetBrains Mono",
    "JetBrains Mono Regular",
    "JetBrainsMono-Regular",
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
    # Tk on some platforms reports slightly different names
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


def apply(root) -> dict:
    """Paint the EchoCR dark theme onto a Tk root. Returns font/color handles."""
    from tkinter import ttk

    resolve_families(root)
    ui = ui_family()
    mono = mono_family()
    ui14 = (ui, 14)
    ui13 = (ui, 13)
    ui12 = (ui, 12)
    ui11 = (ui, 11)
    title = (ui, 20)
    mark_font = (ui, 16, "bold")
    mono12 = (mono, 12)

    try:
        root.configure(bg=BG)
    except Exception:
        pass
    try:
        root.option_add("*tearOff", False)
        root.option_add("*Font", ui14)
        root.option_add("*Background", BG)
        root.option_add("*Foreground", TEXT)
        root.option_add("*TCombobox*Listbox.background", INPUT)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", GOLD_BG)
        root.option_add("*TCombobox*Listbox.selectForeground", GOLD)
        root.option_add("*TCombobox*Listbox.font", ui13)
        root.option_add("*Entry.background", INPUT)
        root.option_add("*Entry.foreground", TEXT)
        root.option_add("*Entry.insertBackground", TEXT)
        root.option_add("*Text.background", LOG_BG)
        root.option_add("*Text.foreground", LOG_FG)
        root.option_add("*Text.font", mono12)
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except TclError:
        pass

    style.configure(".", background=BG, foreground=TEXT, font=ui14, bordercolor=LINE)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Top.TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT, font=ui14)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=ui12)
    style.configure("Title.TLabel", background=BG, foreground=TEXT, font=title)
    style.configure("Gold.TLabel", background=BG, foreground=GOLD, font=ui13)
    style.configure("Teal.TLabel", background=BG, foreground=TEAL, font=ui13)
    style.configure("Ok.TLabel", background=BG, foreground=OK, font=ui13)
    style.configure("Rose.TLabel", background=BG, foreground=ROSE, font=ui13)
    style.configure(
        "Pill.TLabel",
        background=SLOT,
        foreground=MUTED,
        font=ui12,
        padding=(10, 4),
        bordercolor=LINE,
        relief="solid",
    )
    style.configure(
        "PillOn.TLabel",
        background="#0f1f16",
        foreground=OK,
        font=ui12,
        padding=(10, 4),
        bordercolor="#14532d",
        relief="solid",
    )
    style.configure(
        "PillOff.TLabel",
        background="#1a1010",
        foreground=ROSE,
        font=ui12,
        padding=(10, 4),
        bordercolor="#4a1f1f",
        relief="solid",
    )

    style.configure(
        "TLabelframe",
        background=PANEL,
        foreground=TEXT,
        bordercolor=LINE,
        relief="solid",
        padding=10,
    )
    style.configure(
        "TLabelframe.Label",
        background=PANEL,
        foreground=GOLD,
        font=ui13,
    )

    style.configure(
        "TButton",
        background=BTN,
        foreground=TEXT,
        bordercolor=LINE,
        darkcolor=BTN,
        lightcolor=BTN,
        focusthickness=0,
        padding=(12, 7),
        font=ui13,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("disabled", PANEL), ("pressed", SLOT), ("active", "#252d3a")],
        foreground=[("disabled", MUTED)],
        bordercolor=[("disabled", LINE), ("active", "#4b5870"), ("pressed", "#4b5870")],
    )
    style.configure(
        "Primary.TButton",
        background=PRIMARY_BG,
        foreground=TEAL,
        bordercolor=PRIMARY_LINE,
        darkcolor=PRIMARY_BG,
        lightcolor=PRIMARY_BG,
        padding=(12, 8),
        font=ui13,
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", PANEL), ("pressed", "#0c2924"), ("active", "#16443c")],
        foreground=[("disabled", MUTED), ("active", TEAL)],
        bordercolor=[("disabled", LINE), ("active", TEAL)],
    )
    style.configure(
        "Gold.TButton",
        background=GOLD_BG,
        foreground=GOLD,
        bordercolor=GOLD,
        darkcolor=GOLD_BG,
        lightcolor=GOLD_BG,
        padding=(12, 8),
        font=ui13,
    )
    style.map(
        "Gold.TButton",
        background=[("disabled", PANEL), ("pressed", "#1c160a"), ("active", "#3a2d14")],
        foreground=[("disabled", MUTED), ("active", GOLD)],
        bordercolor=[("disabled", LINE), ("active", GOLD)],
    )
    style.configure(
        "Ghost.TButton",
        background=BG,
        foreground=TEXT,
        bordercolor=LINE,
        darkcolor=BG,
        lightcolor=BG,
        padding=(10, 6),
        font=ui13,
    )
    style.map(
        "Ghost.TButton",
        background=[("disabled", BG), ("pressed", SLOT), ("active", SLOT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("active", "#4b5870")],
    )

    style.configure(
        "TEntry",
        fieldbackground=INPUT,
        foreground=TEXT,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
        insertcolor=TEXT,
        padding=6,
        font=ui13,
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", SLOT), ("readonly", INPUT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("focus", TEAL)],
    )
    style.configure(
        "TCombobox",
        fieldbackground=INPUT,
        background=INPUT,
        foreground=TEXT,
        bordercolor=LINE,
        arrowcolor=MUTED,
        lightcolor=LINE,
        darkcolor=LINE,
        padding=5,
        font=ui13,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", INPUT), ("disabled", SLOT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("focus", TEAL), ("active", "#4b5870")],
        arrowcolor=[("active", GOLD)],
    )
    style.configure(
        "TCheckbutton",
        background=BG,
        foreground=TEXT,
        font=ui13,
        indicatorcolor=INPUT,
        indicatorbackground=INPUT,
        padding=4,
    )
    style.map(
        "TCheckbutton",
        background=[("active", BG)],
        foreground=[("disabled", MUTED)],
        indicatorcolor=[("selected", TEAL), ("!selected", INPUT)],
    )
    style.configure(
        "TRadiobutton",
        background=PANEL,
        foreground=TEXT,
        font=ui13,
        indicatorcolor=INPUT,
        padding=3,
    )
    style.map(
        "TRadiobutton",
        background=[("active", PANEL)],
        foreground=[("disabled", MUTED)],
        indicatorcolor=[("selected", GOLD), ("!selected", INPUT)],
    )
    style.configure(
        "Treeview",
        background=SLOT,
        fieldbackground=SLOT,
        foreground=TEXT,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
        rowheight=26,
        font=ui12,
    )
    style.configure(
        "Treeview.Heading",
        background=PANEL,
        foreground=GOLD,
        bordercolor=LINE,
        relief="flat",
        font=ui12,
        padding=4,
    )
    style.map(
        "Treeview",
        background=[("selected", GOLD_BG)],
        foreground=[("selected", GOLD)],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", SLOT)],
        foreground=[("active", GOLD)],
    )
    style.configure(
        "TScrollbar",
        background=SLOT,
        troughcolor=BG,
        bordercolor=LINE,
        arrowcolor=MUTED,
        darkcolor=SLOT,
        lightcolor=SLOT,
    )
    style.map(
        "TScrollbar",
        background=[("active", "#2a3340")],
        arrowcolor=[("active", GOLD)],
    )
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=6, background=LINE)

    return {
        "ui": ui,
        "mono": mono,
        "ui14": ui14,
        "ui13": ui13,
        "ui12": ui12,
        "ui11": ui11,
        "title": title,
        "mark": mark_font,
        "mono12": mono12,
        "style": style,
    }


def make_mark(parent, text: str = "EQ", size: int = 44) -> Canvas:
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
        font=(ui_family(), max(11, size // 3), "bold"),
    )
    return cv


def style_log_widget(widget, mono_font) -> None:
    try:
        widget.configure(
            background=LOG_BG,
            foreground=LOG_FG,
            insertbackground=TEXT,
            selectbackground=GOLD_BG,
            selectforeground=GOLD,
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=LINE,
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
