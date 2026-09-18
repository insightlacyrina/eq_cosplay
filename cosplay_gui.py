#!/usr/bin/env python3
"""EQ Cosplay — Modern macOS Unified UI.

Matches the visual style, component hierarchy, and layout of eq_cosplay_swift:
- Native macOS hidden titlebar & integrated header (80px traffic-light margin, drag anywhere).
- Step 1: Headphone Picker (dual-column interactive fuzzy search with ranked suggestions & badges).
- Step 2: Settings Bar (preamp mode, sample rate, audio output device & action buttons).
- Step 3: Main Display (Frequency Response Plot with live hover frequency tracking + 10-Band PEQ Table).
- Step 4: Bottom Row (Presets Library cards with quick-load/delete + Live colored Log Console).
- Runtime dynamic language switching (en / zh / ja).
"""

from __future__ import annotations

import difflib
import math
import queue
import re
import sys
import tempfile
import threading
import traceback
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    DISABLED,
    END,
    HORIZONTAL,
    LEFT,
    NONE,
    NORMAL,
    RIGHT,
    TOP,
    VERTICAL,
    WORD,
    X,
    Y,
    BooleanVar,
    Canvas,
    DoubleVar,
    Entry,
    Frame,
    Label,
    Scrollbar,
    StringVar,
    Tk,
    Toplevel,
    messagebox,
    ttk,
)
from tkinter.scrolledtext import ScrolledText

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import numpy as np
import cosplay as cp
import theme as ui_theme


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _configure_macos_window(tk_root: Tk) -> bool:
    """Configures macOS unified titlebar and fullSizeContentView via Cocoa/PyObjC."""
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSApplication, NSWindowStyleMaskFullSizeContentView

        tk_root.update_idletasks()
        app = NSApplication.sharedApplication()
        windows = app.windows()
        if not windows:
            return False
        nswin = windows[0]
        nswin.setTitlebarAppearsTransparent_(True)
        nswin.setTitleVisibility_(1)  # NSWindowTitleHidden = 1
        mask = nswin.styleMask() | NSWindowStyleMaskFullSizeContentView
        nswin.setStyleMask_(mask)
        nswin.setMovableByWindowBackground_(False)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# UI Localized String Dictionary (Aligned with I18n.swift & cosplay.py)
# ---------------------------------------------------------------------------

UI_STRINGS = {
    "zh": {
        "app_title": "EQ Cosplay",
        "source_headphone": "使用中耳机 (Source)",
        "target_headphone": "期望目标音色 (Target)",
        "search_placeholder": "输入型号 (如 WH-1000XM4, Q701)...",
        "preamp_label": "前级增益防削波",
        "preamp_safe": "安全模式 (-(峰值+0.2) dB)",
        "preamp_moderate": "折中模式 (-峰值/2 dB)",
        "preamp_custom": "自定义",
        "preamp_none": "不调整 (0 dB)",
        "sample_rate": "采样率",
        "output_device": "物理输出声卡",
        "calculate_button": "拟合频响",
        "deploy_button": "▶ 启动滤波",
        "stop_button": "■ 停止滤波",
        "fir_enable": "开启 FIR",
        "fir_stop": "停止 FIR",
        "peq_table_title": "参数均衡器 (10-Band PEQ)",
        "peq_empty_hint": "尚未生成均衡器参数",
        "col_index": "#",
        "col_type": "类型",
        "col_freq": "频率 (Hz)",
        "col_gain": "增益 (dB)",
        "col_q": "Q值",
        "plot_source": "当前耳机",
        "plot_target": "目标耳机",
        "plot_simulated": "模拟后",
        "plot_mode_eq": "EQ曲线",
        "plot_mode_comp": "补偿曲线",
        "plot_empty_hint": "选择耳机并点击「拟合频响」生成周波数响应曲线",
        "presets_library": "本地方案库",
        "no_presets": "暂无已保存预设",
        "log_console": "运行日志",
        "clear_log": "清空日志",
        "blackhole_warning": "未检测到 BlackHole 2ch 虚拟音频驱动，CamillaDSP 系统捕获需要虚拟声卡支持。",
        "install_blackhole": "一键安装驱动",
        "installing_blackhole": "正在安装驱动...",
        "delete_confirm": "确定要删除预设方案「{name}」吗？",
    },
    "en": {
        "app_title": "EQ Cosplay",
        "source_headphone": "Physical Headphone (Source)",
        "target_headphone": "Desired Sound (Target)",
        "search_placeholder": "Type model name (e.g. WH-1000XM4, Q701)...",
        "preamp_label": "Preamp Gain (Anti-clipping)",
        "preamp_safe": "Safe (-(peak+0.2) dB)",
        "preamp_moderate": "Moderate (-peak/2 dB)",
        "preamp_custom": "Custom",
        "preamp_none": "None (0 dB)",
        "sample_rate": "Sample Rate",
        "output_device": "Audio Output Device",
        "calculate_button": "Fit Curves",
        "deploy_button": "▶ Deploy DSP",
        "stop_button": "■ Stop Engine",
        "fir_enable": "Enable FIR",
        "fir_stop": "Stop FIR",
        "peq_table_title": "10-Band Parametric EQ (IIR)",
        "peq_empty_hint": "No equalizer parameters generated yet",
        "col_index": "#",
        "col_type": "Type",
        "col_freq": "Freq (Hz)",
        "col_gain": "Gain (dB)",
        "col_q": "Q",
        "plot_source": "Current Headphone",
        "plot_target": "Target Headphone",
        "plot_simulated": "Simulated",
        "plot_mode_eq": "EQ Curve",
        "plot_mode_comp": "Compensation Curve",
        "plot_empty_hint": "Select headphones and click 'Fit Curves' to generate frequency response",
        "presets_library": "Presets Library",
        "no_presets": "No saved presets found",
        "log_console": "Live Logs",
        "clear_log": "Clear",
        "blackhole_warning": "BlackHole 2ch was not found. System-wide routing requires a virtual audio device.",
        "install_blackhole": "Install Driver",
        "installing_blackhole": "Installing...",
        "delete_confirm": "Are you sure you want to delete preset '{name}'?",
    },
    "ja": {
        "app_title": "EQ Cosplay",
        "source_headphone": "使用中ヘッドホン (Source)",
        "target_headphone": "目標ヘッドホン (Target)",
        "search_placeholder": "型番を入力 (例: WH-1000XM4, Q701)...",
        "preamp_label": "プリアンプゲイン (クリッピング防止)",
        "preamp_safe": "安全 (-(ピーク+0.2) dB)",
        "preamp_moderate": "中庸 (-ピーク/2 dB)",
        "preamp_custom": "カスタム",
        "preamp_none": "なし (0 dB)",
        "sample_rate": "サンプリング周波数",
        "output_device": "オーディオ出力デバイス",
        "calculate_button": "補正曲線を計算",
        "deploy_button": "▶ CamillaDSP を起動",
        "stop_button": "■ 停止",
        "fir_enable": "FIR 有効化",
        "fir_stop": "FIR 停止",
        "peq_table_title": "10バンド パラメトリックEQ (IIR)",
        "peq_empty_hint": "イコライザーパラメータはまだ生成されていません",
        "col_index": "No",
        "col_type": "タイプ",
        "col_freq": "周波数 (Hz)",
        "col_gain": "ゲイン (dB)",
        "col_q": "Q値",
        "plot_source": "現在のヘッドホン",
        "plot_target": "目標ヘッドホン",
        "plot_simulated": "模擬後",
        "plot_mode_eq": "EQ曲線",
        "plot_mode_comp": "補正曲線",
        "plot_empty_hint": "ヘッドホンを選択し「補正曲線を計算」をクリックして周波数応答を生成",
        "presets_library": "保存済みプリセット",
        "no_presets": "保存されたプリセットはありません",
        "log_console": "動作ログ",
        "clear_log": "クリア",
        "blackhole_warning": "BlackHole 2ch が検出されませんでした。システム全体のEQには仮想オーディオデバイスが必要です。",
        "install_blackhole": "ドライバを導入",
        "installing_blackhole": "導入処理中...",
        "delete_confirm": "プリセット「{name}」を削除してもよろしいですか？",
    },
}


class _QueueWriter:
    def __init__(self, q: queue.Queue, file_path: Path | None = None):
        self._q = q
        self._buf = ""
        self._fh = None
        if file_path is not None:
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = open(file_path, "a", encoding="utf-8", errors="replace")
            except Exception:
                self._fh = None

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self._fh is not None:
            try:
                self._fh.write(s)
                self._fh.flush()
            except Exception:
                pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._q.put(line + "\n")
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self._q.put(self._buf)
            self._buf = ""

    def close(self) -> None:
        self.flush()
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None


# ---------------------------------------------------------------------------
# 耳机智能模糊搜索算法（1:1 对齐 HeadphoneMatcher.swift）
# ---------------------------------------------------------------------------

def search_headphones(query: str, limit: int = 25) -> list[dict]:
    if not cp.AUTOEQ_DATABASE:
        return []
    trimmed = query.strip()
    if not trimmed:
        return []

    q_lower = trimmed.lower()
    q_compact = q_lower.replace(" ", "").replace("-", "").replace("_", "")
    q_tokens = q_lower.split()

    scored = []
    for _key, entries in cp.AUTOEQ_DATABASE.items():
        for entry in entries:
            name = entry.get("display_name") or entry.get("name") or ""
            name_lower = name.lower()
            name_compact = name_lower.replace(" ", "").replace("-", "").replace("_", "")

            score = 0
            if name == trimmed:
                score = 10000
            elif name_lower == q_lower:
                score = 9000
            elif name_compact == q_compact:
                score = 8000
            elif name_lower.startswith(q_lower):
                score = 6000 - min(len(name) - len(trimmed), 200)
            elif name_compact.startswith(q_compact):
                score = 5000 - min(len(name_compact) - len(q_compact), 200)
            elif q_lower in name_lower:
                score = 4000 - min(len(name) - len(trimmed), 200)
            elif q_compact in name_compact:
                score = 3000 - min(len(name_compact) - len(q_compact), 200)
            else:
                if q_tokens and all(t in name_lower or t in name_compact for t in q_tokens):
                    score = 2500 - min(len(name) - len(trimmed), 300)
                else:
                    ratio = difflib.SequenceMatcher(None, q_lower, name_lower[: len(q_lower) + 8]).ratio()
                    if ratio > 0.65:
                        score = int(1400 * ratio)

            if score > 0:
                provider = (entry.get("provider") or "").lower()
                if "oratory" in provider:
                    score += 15
                elif "crinacle" in provider:
                    score += 10
                elif "rtings" in provider:
                    score += 5
                scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    seen = set()
    for _score, entry in scored:
        uid = entry.get("relative_path") or (entry.get("display_name", "") + "_" + entry.get("provider", ""))
        if uid not in seen:
            seen.add(uid)
            results.append(entry)
            if len(results) >= limit:
                break
    return results


def _match_preset_headphone_entries(preset_path: Path) -> tuple[dict | None, dict | None]:
    """从预设文件名（如 cosplay_Sony_WH-1000XM4_oratory1990_to_Sony_MDR-1000X_oratory1990.yml）
    精准解析并匹配出源耳机与目标耳机在 AutoEq 数据库中的条目。
    """
    stem = preset_path.stem
    if stem.startswith("cosplay_"):
        stem = stem[len("cosplay_") :]
    if "_to_" not in stem:
        return None, None
    src_part, tgt_part = stem.split("_to_", 1)

    db = getattr(cp, "AUTOEQ_DATABASE", None)
    if not db:
        try:
            db = cp.load_autoeq_database()
            cp.AUTOEQ_DATABASE = db
        except Exception:
            return None, None
    if not db:
        return None, None

    known_providers = [
        "oratory1990", "crinacle", "rtings", "innerfidelity",
        "headphonecomlegacy", "kuulokenurkka", "rikudougoku", "superreview",
    ]

    def _match(part: str) -> dict | None:
        prov = None
        m_part = part
        for kp in known_providers:
            if part.lower().endswith("_" + kp.lower()):
                prov = kp
                m_part = part[: -len(kp) - 1]
                break
        norm_tgt = re.sub(r"[\W_]", "", m_part).lower()
        if not norm_tgt:
            return None

        best_e = None
        best_s = 0
        for _k, entries in db.items():
            for e in entries:
                norm_n = re.sub(r"[\W_]", "", e.get("display_name", "")).lower()
                s = 0
                if norm_n == norm_tgt:
                    s = 100
                elif norm_n.startswith(norm_tgt) or norm_tgt.startswith(norm_n):
                    s = 70
                elif norm_tgt in norm_n:
                    s = 50
                if s > 0 and prov:
                    if re.sub(r"[\W_]", "", e.get("provider", "").lower()) == re.sub(r"[\W_]", "", prov.lower()):
                        s += 50
                if s > best_s:
                    best_s = s
                    best_e = e
        return best_e

    return _match(src_part), _match(tgt_part)


# ---------------------------------------------------------------------------
# 耳机选择搜索框组件（匹配 HeadphonePickerView.swift）
# ---------------------------------------------------------------------------

class HeadphoneSearchBox(Frame):
    """Liquid Glass Search & Selection Box with floating suggestion list."""

    def __init__(self, parent, fonts: dict | None = None, placeholder: str = "", on_change=None):
        super().__init__(
            parent,
            bg=ui_theme.PANEL,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.TEAL,
            height=34,
        )
        self.pack_propagate(False)
        self.placeholder = placeholder
        self.on_change = on_change
        self.fonts = fonts or {
            "ui11": (ui_theme.ui_family(), 11),
            "mono9": (ui_theme.mono_family(), 9),
        }
        self.selected_entry: dict | None = None
        self._popup: Toplevel | None = None
        self._items: list[dict] = []
        self._hover_idx = -1

        self.var_query = StringVar()
        self._build()

    def _build(self) -> None:
        # Search icon
        self.lbl_icon = Label(
            self,
            text="🔍",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=("Arial", 10),
        )
        self.lbl_icon.pack(side=LEFT, padx=(8, 4))

        # Selected Badge label (hidden initially)
        self.lbl_selected = Label(
            self,
            text="",
            bg=ui_theme.PANEL,
            fg=ui_theme.TEXT,
            font=self.fonts["ui11"],
            anchor="w",
            cursor="hand2",
        )

        # Clear button
        self.btn_clear = Label(
            self,
            text="✕",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=("Arial", 10, "bold"),
            cursor="hand2",
        )
        self.btn_clear.bind("<Button-1>", lambda _e: self.clear_selection())
        self.btn_clear.bind("<Enter>", lambda _e: self.btn_clear.configure(fg=ui_theme.TEXT))
        self.btn_clear.bind("<Leave>", lambda _e: self.btn_clear.configure(fg=ui_theme.MUTED))

        # Search text input
        self.entry = Entry(
            self,
            textvariable=self.var_query,
            bg=ui_theme.PANEL,
            fg=ui_theme.TEXT,
            insertbackground=ui_theme.TEXT,
            font=self.fonts["ui11"],
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.entry.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 6))

        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Down>", self._on_arrow_down)
        self.entry.bind("<Up>", self._on_arrow_up)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Escape>", lambda _e: self._hide_popup())
        self.lbl_selected.bind("<Button-1>", lambda _e: self._edit_selection())

    def set_placeholder(self, text: str) -> None:
        self.placeholder = text

    def set_entry(self, entry: dict | None) -> None:
        self.selected_entry = entry
        self._hide_popup()
        if entry:
            name = entry.get("display_name") or entry.get("name") or ""
            provider = entry.get("provider") or ""
            label_text = f"{name} ({provider})" if provider else name
            self.lbl_selected.configure(text=label_text)
            self.entry.pack_forget()
            self.lbl_selected.pack(side=LEFT, fill=X, expand=True, padx=(2, 6))
            self.btn_clear.pack(side=RIGHT, padx=(0, 8))
        else:
            self.lbl_selected.pack_forget()
            self.btn_clear.pack_forget()
            self.var_query.set("")
            self.entry.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 6))

        if self.on_change:
            self.on_change(self.selected_entry)

    def clear_selection(self) -> None:
        self.set_entry(None)
        self.entry.focus_set()

    def _edit_selection(self) -> None:
        if self.selected_entry:
            name = self.selected_entry.get("display_name") or self.selected_entry.get("name") or ""
            self.set_entry(None)
            self.var_query.set(name)
            self.entry.focus_set()
            self.entry.icursor(END)
            self._trigger_search()

    def _on_key_release(self, event=None) -> None:
        if event and event.keysym in ("Down", "Up", "Return", "Escape"):
            return
        self._trigger_search()

    def _trigger_search(self) -> None:
        query = self.var_query.get().strip()
        if not query:
            self._hide_popup()
            return
        results = search_headphones(query, limit=16)
        if not results:
            self._hide_popup()
            return
        self._show_popup(results)

    def _show_popup(self, items: list[dict]) -> None:
        self._items = items
        self._hover_idx = -1
        root = self.winfo_toplevel()

        if self._popup is None or not self._popup.winfo_exists():
            self._popup = Toplevel(root)
            self._popup.overrideredirect(True)
            self._popup.configure(bg=ui_theme.BORDER)

            # Container with thin border
            self._popup_inner = Frame(self._popup, bg=ui_theme.PANEL_GLASS, padx=2, pady=2)
            self._popup_inner.pack(fill=BOTH, expand=True, padx=1, pady=1)

        for w in self._popup_inner.winfo_children():
            w.destroy()

        for idx, item in enumerate(items):
            row = Frame(self._popup_inner, bg=ui_theme.PANEL_GLASS, cursor="hand2")
            row.pack(fill=X, pady=1)

            name = item.get("display_name") or item.get("name") or ""
            provider = item.get("provider") or ""

            lbl_name = Label(
                row,
                text=name,
                bg=ui_theme.PANEL_GLASS,
                fg=ui_theme.TEXT,
                font=self.fonts["ui11"],
                anchor="w",
            )
            lbl_name.pack(side=LEFT, padx=(6, 4), pady=3)

            lbl_prov = Label(
                row,
                text=provider,
                bg=ui_theme.PANEL_GLASS,
                fg=ui_theme.MUTED,
                font=self.fonts["mono9"],
                anchor="e",
            )
            lbl_prov.pack(side=RIGHT, padx=(4, 6), pady=3)

            def _on_click(_e, it=item):
                self.set_entry(it)

            def _on_enter(_e, r=row, ln=lbl_name, lp=lbl_prov, i=idx):
                self._highlight_row(i)

            row.bind("<Button-1>", _on_click)
            lbl_name.bind("<Button-1>", _on_click)
            lbl_prov.bind("<Button-1>", _on_click)
            row.bind("<Enter>", _on_enter)
            lbl_name.bind("<Enter>", _on_enter)
            lbl_prov.bind("<Enter>", _on_enter)

        self.update_idletasks()
        rx = self.winfo_rootx()
        ry = self.winfo_rooty() + self.winfo_height() + 2
        rw = max(self.winfo_width(), 320)
        rh = min(len(items) * 28 + 6, 240)
        self._popup.geometry(f"{rw}x{rh}+{rx}+{ry}")
        self._popup.lift()

    def _highlight_row(self, index: int) -> None:
        self._hover_idx = index
        children = self._popup_inner.winfo_children()
        for idx, row in enumerate(children):
            bg = "#222d3d" if idx == index else ui_theme.PANEL_GLASS
            row.configure(bg=bg)
            for c in row.winfo_children():
                c.configure(bg=bg)

    def _on_arrow_down(self, _e) -> str:
        if self._popup and self._popup.winfo_exists() and self._items:
            self._hover_idx = min(self._hover_idx + 1, len(self._items) - 1)
            self._highlight_row(self._hover_idx)
        return "break"

    def _on_arrow_up(self, _e) -> str:
        if self._popup and self._popup.winfo_exists() and self._items:
            self._hover_idx = max(self._hover_idx - 1, 0)
            self._highlight_row(self._hover_idx)
        return "break"

    def _on_return(self, _e) -> str:
        if self._popup and self._popup.winfo_exists() and self._items:
            idx = max(self._hover_idx, 0)
            if idx < len(self._items):
                self.set_entry(self._items[idx])
        return "break"

    def _on_focus_out(self, _e) -> None:
        # Delay hiding slightly to register click on popup row
        self.after(200, self._hide_popup)

    def _hide_popup(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None


# ---------------------------------------------------------------------------
# 频响曲线绘制组件（匹配 FrequencyResponsePlotView.swift）
# ---------------------------------------------------------------------------

class FrequencyResponsePlot(Frame):
    """Dynamic logarithmic frequency response curve canvas (read-only presentation)."""

    def __init__(self, parent, fonts: dict):
        super().__init__(
            parent,
            bg=ui_theme.PANEL,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.BORDER,
        )
        self.fonts = fonts
        self.result_data: dict | None = None
        self.mode = "eq"  # "eq" (EQ曲线) or "comp" (补偿曲线)

        self.f_min = 20.0
        self.f_max = 20000.0
        self.log_min = math.log10(self.f_min)
        self.log_max = math.log10(self.f_max)

        self._build()

    def _build(self) -> None:
        # Header with mode title, toggle button & fixed legends
        self.header = Frame(self, bg=ui_theme.PANEL)
        self.header.pack(fill=X, padx=12, pady=(10, 6))

        # Left: Mode Title & Toggle Button (照搬物理输出声卡刷新小按钮)
        self.title_box = Frame(self.header, bg=ui_theme.PANEL)
        self.title_box.pack(side=LEFT, padx=(0, 16))

        self.lbl_mode_title = Label(
            self.title_box,
            text="EQ曲线",
            bg=ui_theme.PANEL,
            fg=ui_theme.TEXT,
            font=self.fonts["ui11"],
        )
        self.lbl_mode_title.pack(side=LEFT)

        self.btn_toggle_mode = Label(
            self.title_box,
            text="↻",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=("Arial", 10, "bold"),
            cursor="hand2",
        )
        self.btn_toggle_mode.pack(side=LEFT, padx=(4, 0))
        self.btn_toggle_mode.bind("<Button-1>", lambda _e: self.toggle_mode())
        self.btn_toggle_mode.bind("<Enter>", lambda _e: self.btn_toggle_mode.configure(fg=ui_theme.TEXT))
        self.btn_toggle_mode.bind("<Leave>", lambda _e: self.btn_toggle_mode.configure(fg=ui_theme.MUTED))

        # Legends: 固定的“当前耳机”“目标耳机”“模拟后”
        self.legend_box = Frame(self.header, bg=ui_theme.PANEL)
        self.legend_box.pack(side=LEFT)

        self.lbl_src = self._make_legend_item(self.legend_box, ui_theme.PLOT_SRC, "当前耳机")
        self.lbl_tgt = self._make_legend_item(self.legend_box, ui_theme.PLOT_TGT, "目标耳机")
        self.lbl_sim = self._make_legend_item(self.legend_box, ui_theme.PLOT_SIM, "模拟后")

        # Plot Canvas (纯展示，不响应鼠标交互)
        self.canvas = Canvas(
            self,
            bg=ui_theme.PLOT_FACE,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _e: self.redraw())

    def _make_legend_item(self, parent, color: str, text: str) -> Label:
        item = Frame(parent, bg=ui_theme.PANEL)
        item.pack(side=LEFT, padx=(0, 14))
        bar = Frame(item, bg=color, width=12, height=3)
        bar.pack(side=LEFT, padx=(0, 5))
        lbl = Label(item, text=text, bg=ui_theme.PANEL, fg=ui_theme.TEXT, font=self.fonts["ui11"])
        lbl.pack(side=LEFT)
        return lbl

    def toggle_mode(self) -> None:
        self.mode = "comp" if self.mode == "eq" else "eq"
        self._update_mode_label()
        self.redraw()

    def set_mode(self, mode: str) -> None:
        if mode in ("eq", "comp"):
            self.mode = mode
            self._update_mode_label()
            self.redraw()

    def _update_mode_label(self) -> None:
        t_fn = getattr(self, "_t_fn", None)
        if self.mode == "comp":
            txt = t_fn("plot_mode_comp") if t_fn else "补偿曲线"
            self.lbl_mode_title.configure(text=txt)
        else:
            txt = t_fn("plot_mode_eq") if t_fn else "EQ曲线"
            self.lbl_mode_title.configure(text=txt)

    def set_data(self, correction: dict | None) -> None:
        self.result_data = correction
        self.redraw()

    def update_labels(self, src_text: str = "当前耳机", tgt_text: str = "目标耳机", sim_text: str = "模拟后") -> None:
        # 固定保持“当前耳机”“目标耳机”“模拟后”
        self.lbl_src.configure(text=src_text or "当前耳机")
        self.lbl_tgt.configure(text=tgt_text or "目标耳机")
        self.lbl_sim.configure(text=sim_text or "模拟后")

    def redraw(self) -> None:
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 80:
            return

        pad_l, pad_r = 44, 16
        pad_t, pad_b = 10, 24
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        # Grid border box
        self.canvas.create_rectangle(
            pad_l,
            pad_t,
            pad_l + plot_w,
            pad_t + plot_h,
            outline=ui_theme.BORDER,
            width=1,
        )

        # Vertical Grid Lines (Logarithmic)
        x_ticks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
        x_labels = {
            20: "20", 50: "50", 100: "100", 200: "200", 500: "500",
            1000: "1k", 2000: "2k", 5000: "5k", 10000: "10k", 20000: "20k"
        }

        for freq in x_ticks:
            x = pad_l + ((math.log10(freq) - self.log_min) / (self.log_max - self.log_min)) * plot_w
            self.canvas.create_line(x, pad_t, x, pad_t + plot_h, fill=ui_theme.PLOT_GRID, width=1)
            lbl = x_labels.get(freq, "")
            self.canvas.create_text(
                x,
                pad_t + plot_h + 12,
                text=lbl,
                fill=ui_theme.MUTED,
                font=self.fonts["mono9"],
                anchor="center",
            )

        # Prepare curves according to mode
        freqs = []
        src = []
        tgt = []
        sim = []
        y_min, y_max = -15.0, 15.0

        if self.result_data and "grid_freqs" in self.result_data:
            freqs = self.result_data.get("grid_freqs") or []
            use_fir = bool(self.result_data.get("use_fir", False))
            resp = self.result_data.get("combined_resp") if use_fir else self.result_data.get("peq_resp")
            if resp is None:
                resp = self.result_data.get("combined_resp") or self.result_data.get("peq_resp")

            s_fr = self.result_data.get("source_fr") or self.result_data.get("source_curve")
            t_fr = self.result_data.get("target_fr") or self.result_data.get("target_curve")
            sim_fr = self.result_data.get("simulated_curve")

            has_real_acoustic = bool(s_fr and t_fr and any(s_fr))

            if self.mode == "comp":
                # 补偿曲线模式: 当前耳机为 0 dB 参考基线，模拟后为滤波器实际拟合补偿增益
                src = [0.0] * len(freqs)
                if has_real_acoustic:
                    tgt = list(np.array(t_fr) - np.array(s_fr))
                else:
                    tgt = []
                sim = list(resp) if resp is not None else [0.0] * len(freqs)

                all_vals = [0.0] + list(tgt) + list(sim)
                min_v = min(all_vals)
                max_v = max(all_vals)
                y_min = min(0.0, min_v) - 3.0
                y_max = max(0.0, max_v) + 3.0
                if y_max - y_min < 8.0:
                    y_min = -5.0
                    y_max = 5.0
            else:
                # EQ曲线模式: 绝对频响对比 (当前耳机、目标耳机、模拟后)
                if has_real_acoustic:
                    src = list(s_fr)
                    tgt = list(t_fr)
                    if sim_fr:
                        sim = list(sim_fr)
                    elif resp is not None:
                        sim = list(np.array(s_fr) + np.array(resp))
                    else:
                        sim = list(s_fr)

                    all_vals = []
                    for vals in (src, tgt, sim):
                        if vals:
                            all_vals.extend(vals)
                    if all_vals:
                        min_v, max_v = min(all_vals), max(all_vals)
                        y_min = min_v - 3.0
                        y_max = max_v + 3.0
                        if y_max - y_min < 8.0:
                            mid = 0.5 * (y_min + y_max)
                            y_min = mid - 4.0
                            y_max = mid + 4.0
                else:
                    # 尚未加载或无实测数据时的 EQ 响应呈现 (以 0 dB 参考输入叠加滤波响应)
                    src = [0.0] * len(freqs)
                    tgt = []
                    sim = list(resp) if resp is not None else [0.0] * len(freqs)
                    # 使用明显的 EQ 频响展示量程 (-25dB 到 +25dB)
                    y_min = -25.0
                    y_max = 25.0

        # Horizontal dB Grid Lines
        step = 5.0
        if (y_max - y_min) > 40:
            step = 10.0
        elif (y_max - y_min) < 16:
            step = 2.0

        db = math.floor(y_min / step) * step
        while db <= y_max + 0.1:
            y = pad_t + ((y_max - db) / (y_max - y_min)) * plot_h
            if pad_t <= y <= pad_t + plot_h:
                self.canvas.create_line(pad_l, y, pad_l + plot_w, y, fill=ui_theme.PLOT_GRID, width=1)
                self.canvas.create_text(
                    pad_l - 6,
                    y,
                    text=f"{db:.0f}",
                    fill=ui_theme.MUTED,
                    font=self.fonts["mono9"],
                    anchor="e",
                )
            db += step

        # Draw Curves
        if freqs and (src or tgt or sim):
            self._draw_curve(freqs, src, ui_theme.PLOT_SRC, 1.8, pad_l, pad_t, plot_w, plot_h, y_min, y_max)
            self._draw_curve(freqs, tgt, ui_theme.PLOT_TGT, 1.8, pad_l, pad_t, plot_w, plot_h, y_min, y_max)
            self._draw_curve(freqs, sim, ui_theme.PLOT_SIM, 2.2, pad_l, pad_t, plot_w, plot_h, y_min, y_max)
        else:
            hint = cp.translate("gui_fr_empty")
            self.canvas.create_text(
                pad_l + plot_w / 2,
                pad_t + plot_h / 2,
                text=hint,
                fill=ui_theme.MUTED,
                font=self.fonts["ui12"],
                anchor="center",
            )

    def _draw_curve(self, freqs, mags, color: str, width: float, pad_l, pad_t, plot_w, plot_h, y_min, y_max) -> None:
        if not freqs or not mags or len(freqs) != len(mags):
            return
        points = []
        for f, m in zip(freqs, mags):
            if f < self.f_min - 1e-4 or f > self.f_max + 1e-4 or not math.isfinite(m):
                continue
            f_clamped = min(max(float(f), self.f_min), self.f_max)
            x = pad_l + ((math.log10(f_clamped) - self.log_min) / (self.log_max - self.log_min)) * plot_w
            y = pad_t + ((y_max - m) / (y_max - y_min)) * plot_h
            points.extend((x, y))

        if len(points) >= 4:
            self.canvas.create_line(*points, fill=color, width=width)


# ---------------------------------------------------------------------------
# PEQ 参数表格组件（匹配 PEQTableView.swift）
# ---------------------------------------------------------------------------

class PEQTableView(Frame):
    """10-Band PEQ filter table with metrics summary header."""

    def __init__(self, parent, fonts: dict):
        super().__init__(
            parent,
            bg=ui_theme.PANEL,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.BORDER,
            width=385,
        )
        self.pack_propagate(False)
        self.fonts = fonts
        self._build()

    def _build(self) -> None:
        # Header with Metrics
        self.header = Frame(self, bg=ui_theme.PANEL)
        self.header.pack(fill=X, padx=10, pady=(10, 8))

        self.lbl_title = Label(
            self.header,
            text="参数均衡器 (10-Band PEQ)",
            bg=ui_theme.PANEL,
            fg=ui_theme.TEXT,
            font=self.fonts["ui12"],
            anchor="w",
        )
        self.lbl_title.pack(side=LEFT)

        # 3-row compact metrics on the right
        self.metrics_box = Frame(self.header, bg=ui_theme.PANEL)
        self.metrics_box.pack(side=RIGHT)

        self.lbl_iir_rmse = Label(
            self.metrics_box,
            text="IIR RMSE: —",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self.fonts["mono9"],
            anchor="e",
        )
        self.lbl_iir_rmse.pack(anchor="e")

        self.lbl_fir_rmse = Label(
            self.metrics_box,
            text="FIR RMSE: —",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self.fonts["mono9"],
            anchor="e",
        )
        self.lbl_fir_rmse.pack(anchor="e")

        self.lbl_fir_taps = Label(
            self.metrics_box,
            text="FIR Taps: —",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self.fonts["mono9"],
            anchor="e",
        )
        self.lbl_fir_taps.pack(anchor="e")

        # Treeview Box
        tree_frame = Frame(self, bg=ui_theme.PANEL)
        tree_frame.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        cols = ("idx", "type", "freq", "gain", "q")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=10)
        self.vsb = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.vsb.set)

        self.tree.column("idx", width=26, anchor="center")
        self.tree.column("type", width=62, anchor="center")
        self.tree.column("freq", width=95, anchor="e")
        self.tree.column("gain", width=70, anchor="e")
        self.tree.column("q", width=55, anchor="e")

        self.tree.heading("idx", text="#")
        self.tree.heading("type", text="类型")
        self.tree.heading("freq", text="频率 (Hz)")
        self.tree.heading("gain", text="增益 (dB)")
        self.tree.heading("q", text="Q值")

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.vsb.pack(side=RIGHT, fill=Y)

    def set_metrics(self, iir_rmse: float | None, fir_rmse: float | None, fir_taps: int | None, use_fir: bool = False) -> None:
        iir_str = f"{iir_rmse:.2f} dB" if iir_rmse is not None else "—"
        fir_str = f"{fir_rmse:.2f} dB" if (use_fir and fir_rmse is not None) else "—"
        taps_str = f"{fir_taps}" if (use_fir and fir_taps and fir_taps > 0) else "—"

        self.lbl_iir_rmse.configure(text=f"IIR RMSE: {iir_str}")
        self.lbl_fir_rmse.configure(text=f"FIR RMSE: {fir_str}")
        self.lbl_fir_taps.configure(text=f"FIR Taps: {taps_str}")

    def populate(self, bands: list[dict]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, band in enumerate(bands, start=1):
            f_val = float(band.get("frequency", 0))
            freq_str = f"{f_val:.0f}" if f_val >= 100 else f"{f_val:.1f}"
            gain_val = float(band.get("gain", 0))
            gain_str = f"{gain_val:+.2f}"
            q_val = float(band.get("Q", 0))
            q_str = f"{q_val:.2f}"
            raw_type = str(band.get("filter_type") or band.get("type") or "PK")
            low = raw_type.lower()
            if "low" in low:
                b_type = "LS"
            elif "high" in low:
                b_type = "HS"
            elif "peak" in low:
                b_type = "PK"
            else:
                b_type = raw_type

            self.tree.insert("", END, values=(f"{i:02d}", b_type, freq_str, gain_str, q_str))


# ---------------------------------------------------------------------------
# 本地方案库组件（匹配 PresetSidebarView.swift）
# ---------------------------------------------------------------------------

class PresetsLibraryView(Frame):
    """Presets Library with card list, left-side control slider, trackpad scroll,
    and Swift-style morphing/scaling expanded card design."""

    def __init__(self, parent, fonts: dict, on_load=None, on_delete=None, on_refresh=None):
        super().__init__(
            parent,
            bg=ui_theme.PANEL,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.BORDER,
            width=280,
            height=150,
        )
        self.pack_propagate(False)
        self.fonts = fonts
        self.on_load = on_load
        self.on_delete = on_delete
        self.on_refresh = on_refresh
        self.presets: list[Path] = []
        self._active_path: Path | None = None
        self._active_expanded_path: Path | None = None
        self._expanded_card: Frame | None = None
        self._anim_job = None
        self._first: float = 0.0
        self._last: float = 1.0
        self._slider_hover: bool = False
        self._slider_dragging: bool = False
        self._root_click_bind_id = None
        self._build()

    def _build(self) -> None:
        header = Frame(self, bg=ui_theme.PANEL)
        header.pack(fill=X, padx=10, pady=(8, 4))

        self.lbl_title = Label(
            header,
            text="本地方案库",
            bg=ui_theme.PANEL,
            fg=ui_theme.TEXT,
            font=self.fonts["ui11"],
            anchor="w",
        )
        self.lbl_title.pack(side=LEFT)

        self.btn_refresh = Label(
            header,
            text="↻",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=("Arial", 12, "bold"),
            cursor="hand2",
        )
        self.btn_refresh.pack(side=RIGHT)
        self.btn_refresh.bind("<Button-1>", lambda _e: self.on_refresh and self.on_refresh())
        self.btn_refresh.bind("<Enter>", lambda _e: self.btn_refresh.configure(fg=ui_theme.TEXT))
        self.btn_refresh.bind("<Leave>", lambda _e: self.btn_refresh.configure(fg=ui_theme.MUTED))

        # Body container
        body = Frame(self, bg=ui_theme.PANEL)
        body.pack(fill=BOTH, expand=True, padx=4, pady=(0, 6))

        # Left control slider track (左侧控制滑块)
        self.slider_canvas = Canvas(
            body,
            width=8,
            bg=ui_theme.PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.slider_canvas.pack(side=LEFT, fill=Y, padx=(2, 4))
        self.slider_canvas.bind("<Configure>", lambda _e: self._draw_slider())
        self.slider_canvas.bind("<Button-1>", self._on_slider_click)
        self.slider_canvas.bind("<B1-Motion>", self._on_slider_drag)
        self.slider_canvas.bind("<ButtonRelease-1>", self._on_slider_release)
        self.slider_canvas.bind("<Enter>", self._on_slider_enter)
        self.slider_canvas.bind("<Leave>", self._on_slider_leave)

        # Scrollable list container (Right of the slider)
        self.scroll_canvas = Canvas(body, bg=ui_theme.PANEL, highlightthickness=0, bd=0)
        self.scroll_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.scroll_canvas.configure(yscrollcommand=self._on_scroll_sync)

        self.cards_frame = Frame(self.scroll_canvas, bg=ui_theme.PANEL)
        self.scroll_win = self.scroll_canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")

        self.cards_frame.bind("<Configure>", lambda _e: self._on_cards_configure())
        self.scroll_canvas.bind("<Configure>", lambda e: self.scroll_canvas.itemconfig(self.scroll_win, width=e.width))

        # Trackpad and mousewheel support (触控板与滚轮滑动)
        self.bind("<Enter>", lambda _e: self._bind_mousewheel())
        self.bind("<Leave>", lambda _e: self._unbind_mousewheel())
        self.scroll_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.cards_frame.bind("<MouseWheel>", self._on_mousewheel)
        self.slider_canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _bind_mousewheel(self) -> None:
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", lambda _e: self.scroll_canvas.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda _e: self.scroll_canvas.yview_scroll(1, "units"))

    def _unbind_mousewheel(self) -> None:
        try:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except Exception:
            pass

    def _on_mousewheel(self, event) -> str:
        if not self.presets:
            return "break"
        delta = getattr(event, "delta", 0)
        if not delta:
            return "break"
        if sys.platform == "darwin":
            if abs(delta) >= 120:
                units = -int(delta / 120)
            else:
                units = -1 if delta > 0 else 1
            self.scroll_canvas.yview_scroll(units, "units")
        else:
            units = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            self.scroll_canvas.yview_scroll(units, "units")
        return "break"

    def _bind_children_mousewheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_children_mousewheel(child)

    def _on_cards_configure(self) -> None:
        bbox = self.scroll_canvas.bbox("all")
        self.scroll_canvas.configure(scrollregion=bbox)
        self._draw_slider()

    def _on_scroll_sync(self, first, last) -> None:
        try:
            self._first = float(first)
            self._last = float(last)
        except Exception:
            pass
        self._draw_slider()

    def _draw_slider(self) -> None:
        self.slider_canvas.delete("all")
        h = self.slider_canvas.winfo_height()
        if h <= 10:
            return

        # Hide thumb if all cards fit completely
        if self._first <= 0.001 and self._last >= 0.999:
            return

        thumb_h = max(20, int((self._last - self._first) * h))
        thumb_y1 = int(self._first * h)
        thumb_y2 = min(h - 2, thumb_y1 + thumb_h)
        thumb_y1 = max(2, min(thumb_y1, h - 22))

        if self._slider_dragging:
            fill_col = ui_theme.TEAL
            w = 5
        elif self._slider_hover:
            fill_col = "#7CE8FF"
            w = 5
        else:
            fill_col = "#3E495B"
            w = 4

        self.slider_canvas.create_line(4, thumb_y1 + w // 2, 4, thumb_y2 - w // 2, width=w, capstyle="round", fill=fill_col)

    def _on_slider_enter(self, _event) -> None:
        self._slider_hover = True
        self._draw_slider()

    def _on_slider_leave(self, _event) -> None:
        self._slider_hover = False
        if not self._slider_dragging:
            self._draw_slider()

    def _on_slider_click(self, event) -> str:
        self._slider_dragging = True
        h = self.slider_canvas.winfo_height()
        if h > 0:
            frac = max(0.0, min(1.0, event.y / float(h)))
            span = self._last - self._first
            target = max(0.0, min(1.0, frac - span / 2.0))
            self.scroll_canvas.yview_moveto(target)
        self._draw_slider()
        return "break"

    def _on_slider_drag(self, event) -> str:
        h = self.slider_canvas.winfo_height()
        if h > 0:
            frac = max(0.0, min(1.0, event.y / float(h)))
            span = self._last - self._first
            target = max(0.0, min(1.0, frac - span / 2.0))
            self.scroll_canvas.yview_moveto(target)
        return "break"

    def _on_slider_release(self, _event) -> str:
        self._slider_dragging = False
        self._draw_slider()
        return "break"

    def set_presets(self, presets: list[Path], active_path: Path | None = None) -> None:
        self.presets = presets
        self._active_path = active_path
        self._collapse_expanded(immediate=True)

        for w in self.cards_frame.winfo_children():
            w.destroy()

        if not presets:
            lbl_empty = Label(
                self.cards_frame,
                text=cp.translate("gui_presets_empty") if hasattr(cp, "translate") else "暂无已保存预设",
                bg=ui_theme.PANEL,
                fg=ui_theme.MUTED,
                font=self.fonts["ui10"],
            )
            lbl_empty.pack(pady=28)
            return

        for p in presets:
            is_active = active_path is not None and p.resolve() == active_path.resolve()
            self._make_preset_card(p, is_active)

        self._bind_children_mousewheel(self.cards_frame)

    def _make_preset_card(self, path: Path, is_active: bool) -> None:
        name = path.stem
        if name.startswith("cosplay_"):
            name = name[len("cosplay_") :]
        name = name.replace("_to_", " → ").replace("_", " ")

        metrics = cp.load_config_metrics(path)
        has_fir = cp.config_uses_fir_conv(path) or cp.config_has_companion_fir_wavs(path)
        peq_rmse = metrics.get("peq_rmse")

        card = Frame(
            self.cards_frame,
            bg=ui_theme.SLOT if is_active else ui_theme.PANEL_GLASS,
            highlightthickness=1,
            highlightbackground=ui_theme.TEAL if is_active else ui_theme.BORDER_SUBTLE,
            cursor="hand2",
        )
        card.pack(fill=X, pady=2, padx=2)

        left_col = Frame(card, bg=card["bg"])
        left_col.pack(side=LEFT, fill=X, expand=True, padx=6, pady=4)

        lbl_name = Label(
            left_col,
            text=name,
            bg=card["bg"],
            fg=ui_theme.TEXT,
            font=self.fonts["ui11"],
            anchor="w",
        )
        lbl_name.pack(anchor="w")

        meta_row = Frame(left_col, bg=card["bg"])
        meta_row.pack(anchor="w", pady=(2, 0))

        if has_fir:
            lbl_fir = Label(
                meta_row,
                text="FIR",
                bg=ui_theme.PRIMARY_BG,
                fg=ui_theme.TEAL,
                font=self.fonts["mono9"],
                padx=3,
                pady=0,
            )
            lbl_fir.pack(side=LEFT, padx=(0, 4))
            lbl_fir.bind("<Button-1>", lambda _e, pt=path, cd=card: self._toggle_expand(pt, cd))

        if peq_rmse is not None:
            lbl_rmse = Label(
                meta_row,
                text=f"PEQ: {float(peq_rmse):.2f} dB",
                bg=card["bg"],
                fg=ui_theme.MUTED,
                font=self.fonts["mono9"],
            )
            lbl_rmse.pack(side=LEFT)
            lbl_rmse.bind("<Button-1>", lambda _e, pt=path, cd=card: self._toggle_expand(pt, cd))

        # Quick action buttons
        actions = Frame(card, bg=card["bg"])
        actions.pack(side=RIGHT, padx=(0, 6))

        btn_play = Label(
            actions,
            text="▶",
            bg=card["bg"],
            fg=ui_theme.TEAL if is_active else ui_theme.TEXT,
            font=("Arial", 10),
            cursor="hand2",
        )
        btn_play.pack(side=LEFT, padx=(0, 4))
        btn_play.bind("<Button-1>", lambda _e, pt=path: self._on_card_play(pt))

        btn_del = Label(
            actions,
            text="🗑",
            bg=card["bg"],
            fg=ui_theme.MUTED,
            font=("Arial", 9),
            cursor="hand2",
        )
        btn_del.pack(side=LEFT)
        btn_del.bind("<Button-1>", lambda _e, pt=path: self._on_card_delete(pt))
        btn_del.bind("<Enter>", lambda _e, b=btn_del: b.configure(fg=ui_theme.ROSE))
        btn_del.bind("<Leave>", lambda _e, b=btn_del: b.configure(fg=ui_theme.MUTED))

        # Clicking card row triggers scale/morph expansion (Swift-style)
        card.bind("<Button-1>", lambda _e, pt=path, cd=card: self._toggle_expand(pt, cd))
        left_col.bind("<Button-1>", lambda _e, pt=path, cd=card: self._toggle_expand(pt, cd))
        lbl_name.bind("<Button-1>", lambda _e, pt=path, cd=card: self._toggle_expand(pt, cd))
        meta_row.bind("<Button-1>", lambda _e, pt=path, cd=card: self._toggle_expand(pt, cd))

    def _on_card_play(self, path: Path) -> None:
        self._collapse_expanded(immediate=True)
        if self.on_load:
            self.on_load(path)

    def _on_card_delete(self, path: Path) -> None:
        self._collapse_expanded(immediate=True)
        if self.on_delete:
            self.on_delete(path)

    def _toggle_expand(self, path: Path, card: Frame) -> None:
        if self._active_expanded_path == path:
            self._collapse_expanded()
        elif self._active_expanded_path is not None:
            self._collapse_expanded(immediate=True)
            self.after(50, lambda: self._show_expanded(path, card))
        else:
            self._show_expanded(path, card)

    def _show_expanded(self, path: Path, card: Frame) -> None:
        self._active_expanded_path = path

        try:
            card_y = card.winfo_rooty()
            parent_y = self.master.winfo_rooty()
            row_y = card_y - parent_y
        except Exception:
            row_y = 40
        row_y = max(32, min(row_y, 104))

        name = path.stem
        if name.startswith("cosplay_"):
            name = name[len("cosplay_") :]
        name = name.replace("_to_", " → ").replace("_", " ")

        metrics = cp.load_config_metrics(path)
        has_fir = cp.config_uses_fir_conv(path) or cp.config_has_companion_fir_wavs(path)
        peq_rmse = metrics.get("peq_rmse")
        comb_rmse = metrics.get("combined_rmse")
        is_active = self._active_path is not None and path.resolve() == self._active_path.resolve()

        needed = len(name) * 7.2 + 180
        target_w = int(min(max(needed, 460), 640))
        start_w = 260

        if self._expanded_card is not None:
            try:
                self._expanded_card.destroy()
            except Exception:
                pass

        # Floating Liquid Glass Card overlay
        self._expanded_card = Frame(
            self.master,
            bg="#18202C",
            highlightthickness=1,
            highlightbackground=ui_theme.TEAL if is_active else ui_theme.BORDER_SPECULAR,
            cursor="hand2",
        )
        self._expanded_card.place(x=10, y=row_y, width=start_w, height=38)
        self._expanded_card.lift()

        inner = Frame(self._expanded_card, bg="#18202C")
        inner.pack(fill=BOTH, expand=True, padx=8, pady=4)

        info_col = Frame(inner, bg="#18202C")
        info_col.pack(side=LEFT, fill=BOTH, expand=True)

        lbl_title = Label(
            info_col,
            text=name,
            bg="#18202C",
            fg="#FFFFFF",
            font=(self.fonts["ui11"][0], 11, "bold"),
            anchor="w",
        )
        lbl_title.pack(anchor="w")

        sub_row = Frame(info_col, bg="#18202C")
        sub_row.pack(anchor="w", pady=(1, 0))

        if has_fir:
            fir_badge = Label(
                sub_row,
                text="● FIR (1024)",
                bg=ui_theme.PRIMARY_BG,
                fg=ui_theme.TEAL,
                font=self.fonts["mono9"],
                padx=4,
                pady=1,
            )
            fir_badge.pack(side=LEFT, padx=(0, 6))

        if peq_rmse is not None:
            peq_lbl = Label(
                sub_row,
                text=f"PEQ: {float(peq_rmse):.2f} dB",
                bg="#18202C",
                fg=ui_theme.MUTED,
                font=self.fonts["mono9"],
            )
            peq_lbl.pack(side=LEFT, padx=(0, 6))

        if comb_rmse is not None and has_fir and abs(comb_rmse - (peq_rmse or 0)) > 1e-4:
            comb_lbl = Label(
                sub_row,
                text=f"Comb: {float(comb_rmse):.2f} dB",
                bg="#18202C",
                fg=ui_theme.MUTED,
                font=self.fonts["mono9"],
            )
            comb_lbl.pack(side=LEFT)

        actions = Frame(inner, bg="#18202C")
        actions.pack(side=RIGHT, padx=(4, 0))

        btn_apply = Label(
            actions,
            text="✔ 已激活" if is_active else "▶ 载入",
            bg=ui_theme.PRIMARY_BG if is_active else ui_theme.BTN,
            fg=ui_theme.TEAL if is_active else "#FFFFFF",
            font=self.fonts["ui11"],
            padx=8,
            pady=2,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=ui_theme.TEAL if is_active else ui_theme.BORDER,
        )
        btn_apply.pack(side=LEFT, padx=(0, 4))
        btn_apply.bind("<Button-1>", lambda _e: self._on_card_play(path))

        btn_del = Label(
            actions,
            text="🗑",
            bg=ui_theme.BTN,
            fg=ui_theme.MUTED,
            font=("Arial", 10),
            padx=6,
            pady=2,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
        )
        btn_del.pack(side=LEFT, padx=(0, 4))
        btn_del.bind("<Button-1>", lambda _e: self._on_card_delete(path))
        btn_del.bind("<Enter>", lambda _e: btn_del.configure(fg=ui_theme.ROSE, highlightbackground=ui_theme.ROSE))
        btn_del.bind("<Leave>", lambda _e: btn_del.configure(fg=ui_theme.MUTED, highlightbackground=ui_theme.BORDER))

        btn_close = Label(
            actions,
            text="✕",
            bg="#18202C",
            fg=ui_theme.MUTED,
            font=("Arial", 9),
            padx=4,
            cursor="hand2",
        )
        btn_close.pack(side=LEFT)
        btn_close.bind("<Button-1>", lambda _e: self._collapse_expanded())

        # Click inside card body to collapse
        self._expanded_card.bind("<Button-1>", lambda _e: self._collapse_expanded())
        inner.bind("<Button-1>", lambda _e: self._collapse_expanded())
        info_col.bind("<Button-1>", lambda _e: self._collapse_expanded())
        lbl_title.bind("<Button-1>", lambda _e: self._collapse_expanded())
        sub_row.bind("<Button-1>", lambda _e: self._collapse_expanded())

        # Start spring expansion animation
        self._animate_expand(start_w, target_w, frame=0, total_frames=12)

        # Bind click outside to collapse
        top = self.winfo_toplevel()
        if self._root_click_bind_id is not None:
            try:
                top.unbind("<Button-1>", self._root_click_bind_id)
            except Exception:
                pass
        self._root_click_bind_id = top.bind("<Button-1>", self._on_outside_click, add="+")

    def _on_outside_click(self, event) -> None:
        card = self._expanded_card
        if card is None or not card.winfo_exists():
            return
        try:
            rx, ry = event.x_root, event.y_root
            cx, cy = card.winfo_rootx(), card.winfo_rooty()
            cw, ch = card.winfo_width(), card.winfo_height()
            if not (cx <= rx <= cx + cw and cy <= ry <= cy + ch):
                self._collapse_expanded()
        except Exception:
            pass

    def _animate_expand(self, start_w: int, target_w: int, frame: int, total_frames: int) -> None:
        if self._expanded_card is None or not self._expanded_card.winfo_exists():
            return
        t = frame / float(total_frames)
        ease = 1.0 - (1.0 - t) ** 3  # cubic ease-out
        cur_w = int(start_w + (target_w - start_w) * ease)
        try:
            self._expanded_card.place_configure(width=cur_w)
        except Exception:
            return

        if frame < total_frames:
            self._anim_job = self.after(16, lambda: self._animate_expand(start_w, target_w, frame + 1, total_frames))

    def _collapse_expanded(self, immediate: bool = False) -> None:
        if self._root_click_bind_id is not None:
            try:
                self.winfo_toplevel().unbind("<Button-1>", self._root_click_bind_id)
            except Exception:
                pass
            self._root_click_bind_id = None

        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

        self._active_expanded_path = None
        card = self._expanded_card
        if card is None or not card.winfo_exists():
            self._expanded_card = None
            return

        if immediate:
            try:
                card.place_forget()
                card.destroy()
            except Exception:
                pass
            self._expanded_card = None
            return

        try:
            cur_w = card.winfo_width()
        except Exception:
            cur_w = 460
        self._animate_collapse(cur_w, 260, frame=0, total_frames=8)

    def _animate_collapse(self, start_w: int, target_w: int, frame: int, total_frames: int) -> None:
        card = self._expanded_card
        if card is None or not card.winfo_exists():
            self._expanded_card = None
            return

        t = frame / float(total_frames)
        ease = 1.0 - (1.0 - t) ** 2
        cur_w = int(start_w - (start_w - target_w) * ease)
        try:
            card.place_configure(width=cur_w)
        except Exception:
            pass

        if frame < total_frames:
            self._anim_job = self.after(16, lambda: self._animate_collapse(start_w, target_w, frame + 1, total_frames))
        else:
            try:
                card.place_forget()
                card.destroy()
            except Exception:
                pass
            self._expanded_card = None


# ---------------------------------------------------------------------------
# 主应用程序窗口 (CosplayApp)
# ---------------------------------------------------------------------------

class CosplayApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("EQ Cosplay")
        self.root.geometry("1040x740")
        self.root.minsize(940, 680)

        self._theme = ui_theme.apply(self.root)
        self.fonts = self._theme
        self._menubar = None
        self._window_icon = None
        self._apply_window_icon()

        # macOS transparent titlebar & fullSizeContentView
        self._is_macos_integrated = _configure_macos_window(self.root)

        # Logging stream & thread dispatch setup
        self.log_q: queue.Queue = queue.Queue()
        self._bg_queue: queue.Queue = queue.Queue()
        self._stdout_backup = sys.stdout
        self._stderr_backup = sys.stderr
        self.session_log_path = cp.make_log_path("gui_session")
        self._io_writer = _QueueWriter(self.log_q, self.session_log_path)
        sys.stdout = self._io_writer  # type: ignore[assignment]
        sys.stderr = self._io_writer  # type: ignore[assignment]

        self.system_name, self.system_arch = cp.get_platform_info()
        self.backend_type, self.default_capture = cp.get_default_audio_backend(self.system_name)

        self.db_ready = False
        self.busy = False
        self.correction: dict | None = None
        self.peq_list: list[dict] = []
        self.source_entry: dict | None = None
        self.target_entry: dict | None = None
        self.last_config: Path | None = None
        self.engine_proc = None
        self.engine_log: Path | None = None
        self._status_key = "gui_status_loading"
        self._status_kwargs: dict = {}
        self._saved_presets: list[Path] = []
        self._active_preset_path: Path | None = None

        # Variables
        self.var_sr = StringVar(value=str(cp.DEFAULT_SAMPLE_RATE))
        self.var_output = StringVar()
        self.var_preamp_mode = StringVar(value="safe")
        self.var_preamp_custom = DoubleVar(value=-3.0)
        self.var_status = StringVar(value="…")
        self.var_lang = StringVar(value=cp.LANG if cp.LANG in ("en", "zh", "ja") else "zh")

        self._init_output_default()
        self._build_ui()
        self._apply_language()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._poll_log)
        self.root.after(150, self._bootstrap)

    def _t(self, key: str, **kwargs) -> str:
        lang = self.var_lang.get()
        if lang in UI_STRINGS and key in UI_STRINGS[lang]:
            msg = UI_STRINGS[lang][key]
            return msg.format(**kwargs) if kwargs else msg
        if hasattr(cp, "translate"):
            res = cp.translate(key, **kwargs)
            if res:
                return res
        return key

    def _apply_window_icon(self) -> None:
        try:
            icon_dir = ui_theme.assets_dir() / "icons"
        except Exception:
            icon_dir = Path(__file__).resolve().parent / "assets" / "icons"
        for name in ("window.png", "app.png"):
            path = icon_dir / name
            if path.is_file():
                try:
                    from tkinter import PhotoImage

                    self._window_icon = PhotoImage(file=str(path))
                    self.root.iconphoto(True, self._window_icon)
                    return
                except Exception:
                    continue

    def _init_output_default(self) -> None:
        detected = None
        if self.system_name == "Darwin":
            detected = cp.detect_macos_default_playback_device()
        if detected:
            self.var_output.set(detected)
        else:
            self.var_output.set(cp.localized_default_playback_label("speakers"))

    def _resolved_output_device(self) -> str:
        user = (self.var_output.get() or "").strip()
        detected = None
        available: list[str] = []
        if self.system_name == "Darwin":
            available = cp.list_macos_playback_devices()
            detected = cp.detect_macos_default_playback_device()
        resolved = cp.resolve_playback_device_name(user, detected, available)
        if resolved and resolved != user:
            self.var_output.set(resolved)
        return resolved or user

    # -----------------------------------------------------------------------
    # 界面构建 (1:1 对齐 MainView.swift)
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Outer container
        self.outer = Frame(self.root, bg=ui_theme.BG)
        self.outer.pack(fill=BOTH, expand=True)

        # Header Bar / Custom Top Bar (Unified with macOS Window Traffic Light Controls)
        top_left_pad = 80 if (sys.platform == "darwin" and self._is_macos_integrated) else 14
        self.top_bar = Frame(self.outer, bg=ui_theme.BG, height=44)
        self.top_bar.pack(fill=X, padx=(top_left_pad, 14), pady=(8, 4))
        self.top_bar.pack_propagate(False)

        self.brand_box = Frame(self.top_bar, bg=ui_theme.BG)
        self.brand_box.pack(side=LEFT)
        self.lbl_app_title = Label(
            self.brand_box,
            text="EQ Cosplay",
            bg=ui_theme.BG,
            fg=ui_theme.TEXT,
            font=self._theme["title"],
        )
        self.lbl_app_title.pack(side=LEFT)

        def _start_win_drag(event):
            self._win_drag_start_x = event.x_root - self.root.winfo_x()
            self._win_drag_start_y = event.y_root - self.root.winfo_y()

        def _on_win_drag(event):
            if hasattr(self, "_win_drag_start_x"):
                nx = event.x_root - self._win_drag_start_x
                ny = event.y_root - self._win_drag_start_y
                self.root.geometry(f"+{nx}+{ny}")

        for w in (self.top_bar, self.brand_box, self.lbl_app_title):
            w.bind("<Button-1>", _start_win_drag)
            w.bind("<B1-Motion>", _on_win_drag)

        # Right side: Status Indicator Pill & Language Dropdown
        self.top_right = Frame(self.top_bar, bg=ui_theme.BG)
        self.top_right.pack(side=RIGHT)

        # Status Pill
        self.status_pill = Frame(
            self.top_right,
            bg=ui_theme.SLOT,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.BORDER,
            padx=8,
            pady=3,
        )
        self.status_pill.pack(side=LEFT, padx=(0, 10))

        self.status_dot = Canvas(self.status_pill, width=8, height=8, bg=ui_theme.SLOT, highlightthickness=0, bd=0)
        self.status_dot.pack(side=LEFT, padx=(0, 6))
        self._dot_id = self.status_dot.create_oval(1, 1, 7, 7, fill=ui_theme.MUTED, outline="")

        self.lbl_status = Label(
            self.status_pill,
            textvariable=self.var_status,
            bg=ui_theme.SLOT,
            fg=ui_theme.MUTED,
            font=self._theme["ui10"],
        )
        self.lbl_status.pack(side=LEFT)

        # Language dropdown
        self.cmb_lang = ttk.Combobox(
            self.top_right,
            textvariable=self.var_lang,
            values=["zh", "en", "ja"],
            state="readonly",
            width=7,
        )
        self.cmb_lang.pack(side=LEFT)
        self.cmb_lang.bind("<<ComboboxSelected>>", self._on_lang_change)

        # Step 1: Headphone Picker (Dual-column interactive search)
        self.picker_frame = Frame(self.outer, bg=ui_theme.BG)
        self.picker_frame.pack(fill=X, padx=14, pady=(2, 8))

        # Source column
        self.col_source = Frame(self.picker_frame, bg=ui_theme.BG)
        self.col_source.pack(side=LEFT, fill=X, expand=True, padx=(0, 7))

        self.lbl_source_title = Label(
            self.col_source,
            text=self._t("source_headphone"),
            bg=ui_theme.BG,
            fg=ui_theme.MUTED,
            font=self._theme["ui11"],
            anchor="w",
        )
        self.lbl_source_title.pack(fill=X, pady=(0, 4))

        self.source_box = HeadphoneSearchBox(
            self.col_source,
            self.fonts,
            placeholder=self._t("search_placeholder"),
            on_change=self._on_source_selected,
        )
        self.source_box.pack(fill=X)

        # Target column
        self.col_target = Frame(self.picker_frame, bg=ui_theme.BG)
        self.col_target.pack(side=RIGHT, fill=X, expand=True, padx=(7, 0))

        self.lbl_target_title = Label(
            self.col_target,
            text=self._t("target_headphone"),
            bg=ui_theme.BG,
            fg=ui_theme.MUTED,
            font=self._theme["ui11"],
            anchor="w",
        )
        self.lbl_target_title.pack(fill=X, pady=(0, 4))

        self.target_box = HeadphoneSearchBox(
            self.col_target,
            self.fonts,
            placeholder=self._t("search_placeholder"),
            on_change=self._on_target_selected,
        )
        self.target_box.pack(fill=X)

        # Step 2: Settings & Actions Bar
        self.settings_bar = ui_theme.make_glass_frame(self.outer, padding=10)
        self.settings_bar.pack(fill=X, padx=14, pady=(0, 10))

        # Settings Left HStack
        s_left = Frame(self.settings_bar, bg=ui_theme.PANEL)
        s_left.pack(side=LEFT)

        # Preamp Mode
        preamp_box = Frame(s_left, bg=ui_theme.PANEL)
        preamp_box.pack(side=LEFT, padx=(0, 14))
        self.lbl_preamp = Label(
            preamp_box,
            text=self._t("preamp_label"),
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self._theme["ui10"],
        )
        self.lbl_preamp.pack(anchor="w", pady=(0, 2))

        self.preamp_values = ["safe", "moderate", "custom", "none"]
        self.cmb_preamp = ttk.Combobox(
            preamp_box,
            state="readonly",
            width=22,
        )
        self.cmb_preamp.pack(anchor="w")
        self.cmb_preamp.bind("<<ComboboxSelected>>", self._on_preamp_change)

        # Sample Rate
        sr_box = Frame(s_left, bg=ui_theme.PANEL)
        sr_box.pack(side=LEFT, padx=(0, 14))
        self.lbl_sr = Label(
            sr_box,
            text=self._t("sample_rate"),
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self._theme["ui10"],
        )
        self.lbl_sr.pack(anchor="w", pady=(0, 2))

        self.cmb_sr = ttk.Combobox(
            sr_box,
            textvariable=self.var_sr,
            values=["44100", "48000", "88200", "96000", "192000"],
            state="readonly",
            width=10,
        )
        self.cmb_sr.pack(anchor="w")

        # Playback Device
        dev_box = Frame(s_left, bg=ui_theme.PANEL)
        dev_box.pack(side=LEFT)

        dev_title_box = Frame(dev_box, bg=ui_theme.PANEL)
        dev_title_box.pack(fill=X, pady=(0, 2))

        self.lbl_playback = Label(
            dev_title_box,
            text=self._t("output_device"),
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self._theme["ui10"],
        )
        self.lbl_playback.pack(side=LEFT)

        self.btn_refresh_dev = Label(
            dev_title_box,
            text="↻",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=("Arial", 10, "bold"),
            cursor="hand2",
        )
        self.btn_refresh_dev.pack(side=LEFT, padx=(4, 0))
        self.btn_refresh_dev.bind("<Button-1>", lambda _e: self._refresh_output_devices())

        self.cmb_output = ttk.Combobox(
            dev_box,
            textvariable=self.var_output,
            state="readonly",
            width=24,
        )
        self.cmb_output.pack(anchor="w")
        self.cmb_output.bind("<<ComboboxSelected>>", self._on_output_device_change)

        # Settings Right Action Buttons
        self.actions_box = Frame(self.settings_bar, bg=ui_theme.PANEL)
        self.actions_box.pack(side=RIGHT)

        self.btn_toggle_fir = ttk.Button(
            self.actions_box,
            text=self._t("fir_enable"),
            command=self._on_toggle_fir,
            style="TButton",
        )

        self.btn_calc = ttk.Button(
            self.actions_box,
            text=self._t("calculate_button"),
            command=self._on_calculate,
            style="TButton",
        )
        self.btn_calc.pack(side=LEFT, padx=(0, 8))

        self.btn_deploy = ttk.Button(
            self.actions_box,
            text=self._t("deploy_button"),
            command=self._on_deploy,
            style="Primary.TButton",
        )
        self.btn_deploy.pack(side=LEFT, padx=(0, 8))

        self.btn_stop = ttk.Button(
            self.actions_box,
            text=self._t("stop_button"),
            command=self._on_stop,
            style="TButton",
        )

        # BlackHole missing banner
        self.bh_banner = Frame(
            self.outer,
            bg="#2a1b10",
            highlightthickness=1,
            highlightbackground="#593414",
            highlightcolor="#593414",
            padx=10,
            pady=6,
        )
        lbl_warn_icon = Label(self.bh_banner, text="⚠️", bg="#2a1b10", font=("Arial", 11))
        lbl_warn_icon.pack(side=LEFT, padx=(0, 6))
        self.lbl_bh_warn = Label(
            self.bh_banner,
            text=self._t("blackhole_warning"),
            bg="#2a1b10",
            fg=ui_theme.TEXT,
            font=self._theme["ui10"],
        )
        self.lbl_bh_warn.pack(side=LEFT)

        self.btn_install_bh = ttk.Button(
            self.bh_banner,
            text=self._t("install_blackhole"),
            command=self._on_install_blackhole,
            style="Gold.TButton",
        )
        self.btn_install_bh.pack(side=RIGHT)

        # Step 3: Main Display (Frequency Plot + PEQ Table)
        self.display_row = Frame(self.outer, bg=ui_theme.BG)
        self.display_row.pack(fill=BOTH, expand=True, padx=14, pady=(0, 10))

        self.plot_view = FrequencyResponsePlot(self.display_row, self._theme)
        self.plot_view._t_fn = self._t
        self.plot_view.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))

        self.peq_view = PEQTableView(self.display_row, self._theme)
        self.peq_view.pack(side=RIGHT, fill=Y)

        # Step 4: Bottom Row (Presets Library + Live Logs)
        self.bottom_row = Frame(self.outer, bg=ui_theme.BG, height=150)
        self.bottom_row.pack(fill=X, padx=14, pady=(0, 12))
        self.bottom_row.pack_propagate(False)

        # Presets library
        self.presets_view = PresetsLibraryView(
            self.bottom_row,
            self._theme,
            on_load=self._load_preset_from_card,
            on_delete=self._delete_preset_from_card,
            on_refresh=self._refresh_presets,
        )
        self.presets_view.pack(side=LEFT, padx=(0, 8))

        # Log console
        self.log_card = ui_theme.make_glass_frame(self.bottom_row, padding=8)
        self.log_card.pack(side=RIGHT, fill=BOTH, expand=True)

        log_hdr = Frame(self.log_card, bg=ui_theme.PANEL)
        log_hdr.pack(fill=X, pady=(0, 4))

        self.lbl_log_title = Label(
            log_hdr,
            text=self._t("log_console"),
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self._theme["mono10"],
        )
        self.lbl_log_title.pack(side=LEFT)

        self.btn_clear_log = Label(
            log_hdr,
            text=self._t("clear_log"),
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self._theme["ui10"],
            cursor="hand2",
        )
        self.btn_clear_log.pack(side=RIGHT)
        self.btn_clear_log.bind("<Button-1>", lambda _e: self._clear_logs())
        self.btn_clear_log.bind("<Enter>", lambda _e: self.btn_clear_log.configure(fg=ui_theme.TEXT))
        self.btn_clear_log.bind("<Leave>", lambda _e: self.btn_clear_log.configure(fg=ui_theme.MUTED))

        self.log_text = ScrolledText(
            self.log_card,
            wrap=WORD,
            font=self._theme["mono10"],
            bg=ui_theme.LOG_BG,
            fg=ui_theme.LOG_FG,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.log_text.pack(fill=BOTH, expand=True)
        ui_theme.style_log_widget(self.log_text, self._theme["mono10"])
        self.log_text.configure(state=DISABLED)

        self.log_text.tag_configure("ok", foreground=ui_theme.EMERALD)
        self.log_text.tag_configure("wait", foreground=ui_theme.TEAL)
        self.log_text.tag_configure("err", foreground=ui_theme.ROSE)
        self.log_text.tag_configure("tip", foreground=ui_theme.GOLD)
        self.log_text.tag_configure("warn", foreground="#fbbf24")
        self.log_text.tag_configure("comment", foreground="#64748b")

    # -----------------------------------------------------------------------
    # 状态与语言更新
    # -----------------------------------------------------------------------

    def _set_status_key(self, key: str, **kwargs) -> None:
        self._status_key = key
        self._status_kwargs = dict(kwargs)
        self._refresh_status_pill()

    def _refresh_status_pill(self) -> None:
        text = self._t(self._status_key, **self._status_kwargs)
        self.var_status.set(text)

        running = {"gui_status_running", "gui_status_preset", "gui_status_deploy"}
        calculating = {"gui_status_calc", "gui_status_download", "gui_status_loading"}
        fail = {"gui_status_db_fail", "gui_status_calc_fail", "gui_status_deploy_fail", "gui_status_engine_fail"}

        if self._status_key in running or self.engine_proc is not None:
            self.status_dot.itemconfig(self._dot_id, fill=ui_theme.EMERALD)
            self.lbl_status.configure(fg=ui_theme.TEXT)
        elif self._status_key in calculating or self.busy:
            self.status_dot.itemconfig(self._dot_id, fill=ui_theme.TEAL)
            self.lbl_status.configure(fg=ui_theme.TEAL)
        elif self._status_key in fail:
            self.status_dot.itemconfig(self._dot_id, fill=ui_theme.ROSE)
            self.lbl_status.configure(fg=ui_theme.ROSE)
        else:
            self.status_dot.itemconfig(self._dot_id, fill=ui_theme.MUTED)
            self.lbl_status.configure(fg=ui_theme.MUTED)

    def _on_lang_change(self, _event=None) -> None:
        code = self.var_lang.get()
        if hasattr(cp, "set_language"):
            cp.set_language(code)
        self._apply_language()

    def _apply_language(self) -> None:
        self.lbl_source_title.configure(text=self._t("source_headphone"))
        self.lbl_target_title.configure(text=self._t("target_headphone"))
        self.source_box.set_placeholder(self._t("search_placeholder"))
        self.target_box.set_placeholder(self._t("search_placeholder"))

        self.lbl_preamp.configure(text=self._t("preamp_label"))
        self.lbl_sr.configure(text=self._t("sample_rate"))
        self.lbl_playback.configure(text=self._t("output_device"))

        self.btn_calc.configure(text=self._t("calculate_button"))
        self.btn_deploy.configure(text=self._t("deploy_button"))
        self.btn_stop.configure(text=self._t("stop_button"))
        self.btn_toggle_fir.configure(text=self._t("fir_enable"))

        self.lbl_bh_warn.configure(text=self._t("blackhole_warning"))
        self.btn_install_bh.configure(text=self._t("install_blackhole"))

        self.peq_view.lbl_title.configure(text=self._t("peq_table_title"))
        self.peq_view.tree.heading("idx", text=self._t("col_index"))
        self.peq_view.tree.heading("type", text=self._t("col_type"))
        self.peq_view.tree.heading("freq", text=self._t("col_freq"))
        self.peq_view.tree.heading("gain", text=self._t("col_gain"))
        self.peq_view.tree.heading("q", text=self._t("col_q"))

        self.plot_view.update_labels(
            self._t("plot_source"),
            self._t("plot_target"),
            self._t("plot_simulated"),
        )
        self.plot_view._update_mode_label()

        self.presets_view.lbl_title.configure(text=self._t("presets_library"))
        self.lbl_log_title.configure(text=self._t("log_console"))
        self.btn_clear_log.configure(text=self._t("clear_log"))

        # Update preamp labels in combobox
        mode_labels = [
            self._t("preamp_safe"),
            self._t("preamp_moderate"),
            self._t("preamp_custom"),
            self._t("preamp_none"),
        ]
        self.cmb_preamp["values"] = mode_labels
        cur_mode = self.var_preamp_mode.get()
        idx_map = {"safe": 0, "moderate": 1, "custom": 2, "none": 3}
        self.cmb_preamp.current(idx_map.get(cur_mode, 0))

        self._refresh_status_pill()

    def _on_preamp_change(self, _event=None) -> None:
        idx = self.cmb_preamp.current()
        modes = ["safe", "moderate", "custom", "none"]
        if 0 <= idx < len(modes):
            chosen = modes[idx]
            self.var_preamp_mode.set(chosen)
            if chosen == "custom":
                # Prompt custom gain value if needed
                pass

    def _on_source_selected(self, entry: dict | None) -> None:
        self.source_entry = entry
        self._update_action_states()

    def _on_target_selected(self, entry: dict | None) -> None:
        self.target_entry = entry
        self._update_action_states()

    def _update_action_states(self) -> None:
        can_calc = bool(self.source_entry and self.target_entry and not self.busy)
        self.btn_calc.configure(state=NORMAL if can_calc else DISABLED)

        can_deploy = bool(self.correction and not self.busy)
        self.btn_deploy.configure(state=NORMAL if can_deploy else DISABLED)

        is_running = self.engine_proc is not None
        if is_running:
            self.btn_stop.pack(side=LEFT, padx=(0, 4))
        else:
            self.btn_stop.pack_forget()

        # Check FIR button
        has_fir = bool(self.correction and self.correction.get("fir_ir") is not None)
        if has_fir:
            use_fir = bool(self.correction.get("use_fir", False))
            self.btn_toggle_fir.configure(text=self._t("fir_stop" if use_fir else "fir_enable"))
            self.btn_toggle_fir.pack(side=LEFT, padx=(0, 8), before=self.btn_calc)
        else:
            self.btn_toggle_fir.pack_forget()

    # -----------------------------------------------------------------------
    # 后台异步启动与数据加载
    # -----------------------------------------------------------------------

    def _bootstrap(self) -> None:
        self._check_blackhole()
        self._refresh_output_devices()
        self._refresh_presets()
        self._install_menubar()

        def db_worker():
            return cp.load_autoeq_database()

        self._run_bg(db_worker, self._on_db_loaded)

    def _check_blackhole(self) -> None:
        if self.system_name == "Darwin":
            installed = cp.is_blackhole_installed()
            if not installed:
                self.bh_banner.pack(fill=X, padx=14, pady=(0, 10), before=self.display_row)
            else:
                self.bh_banner.pack_forget()
        else:
            self.bh_banner.pack_forget()

    def _on_install_blackhole(self) -> None:
        self.btn_install_bh.configure(state=DISABLED, text=self._t("installing_blackhole"))

        def worker():
            return cp.install_blackhole()

        def on_done(ok, _err):
            self.btn_install_bh.configure(state=NORMAL, text=self._t("install_blackhole"))
            if ok:
                self._log("[OK] BlackHole 2ch 驱动安装成功。")
                self.bh_banner.pack_forget()
            else:
                self._log("[ERR] BlackHole 安装失败，请检查网络或通过终端 brew install blackhole-2ch 手动安装。")

        self._run_bg(worker, on_done)

    def _on_db_loaded(self, result, err) -> None:
        if err:
            self._set_status_key("gui_status_db_fail")
            self._log(f"[ERR] Failed to load AutoEq index: {err}")
            return
        cp.AUTOEQ_DATABASE = result or {}
        self.db_ready = bool(cp.AUTOEQ_DATABASE)
        n = len(cp.AUTOEQ_DATABASE) if cp.AUTOEQ_DATABASE else 0
        self._set_status_key("gui_status_ready", count=n)
        self._log(f"[OK] AutoEq 数据库已就绪，已索引 {n} 款耳机。")
        self._update_action_states()

    def _refresh_output_devices(self) -> None:
        if self.system_name == "Darwin":
            devices = cp.list_macos_playback_devices()
            def_dev = cp.detect_macos_default_playback_device()
        else:
            devices = []
            def_dev = None

        self.cmb_output["values"] = devices
        if def_dev and (not self.var_output.get() or self.var_output.get() not in devices):
            self.var_output.set(def_dev)
        elif devices and not self.var_output.get():
            self.var_output.set(devices[0])

    def _on_output_device_change(self, _event=None) -> None:
        device = self.var_output.get()
        if self.engine_proc is not None and self.last_config:
            self._log(f"[..] 重新定向输出声卡至: {device}...")
            cp.set_config_playback_device(self.last_config, device)
            # Re-launch
            proc, log_path = cp.run_camilladsp(self.last_config, debug=False)
            self.engine_proc = proc
            self.engine_log = log_path
            self._log(f"[OK] 引擎已重新定向至: {device}")

    def _refresh_presets(self) -> None:
        try:
            self._saved_presets = cp.list_saved_presets()
        except Exception:
            self._saved_presets = []
        self.presets_view.set_presets(self._saved_presets, self._active_preset_path)
        self._rebuild_menubar()

    # -----------------------------------------------------------------------
    # 计算与拟合
    # -----------------------------------------------------------------------

    def _on_calculate(self) -> None:
        if not self.db_ready:
            messagebox.showwarning("EQ Cosplay", cp.translate("gui_msg_db_not_ready"))
            return
        if not self.source_entry or not self.target_entry:
            messagebox.showwarning("EQ Cosplay", self._t("search_placeholder"))
            return

        try:
            fs = int(self.var_sr.get())
        except ValueError:
            fs = cp.DEFAULT_SAMPLE_RATE

        source_entry = self.source_entry
        target_entry = self.target_entry

        def worker():
            temp_dir = Path(tempfile.mkdtemp(prefix="autoeq_gui_"))
            sp = cp.download_headphone_csv(source_entry, temp_dir)
            tp = cp.download_headphone_csv(target_entry, temp_dir)
            if not sp or not tp:
                raise RuntimeError("Failed to download headphone measurement curves.")
            correction = cp.calculate_correction(sp, tp, fs=fs)
            return {"correction": correction, "fs": fs}

        self._set_busy(True)
        self._set_status_key("gui_status_calc")
        self._run_bg(worker, self._on_calc_done)

    def _on_calc_done(self, result, err) -> None:
        self._set_busy(False)
        if err:
            self._set_status_key("gui_status_calc_fail")
            messagebox.showerror("EQ Cosplay", f"Calculation failed:\n{err}")
            return

        self.correction = result["correction"]
        self.peq_list = list(self.correction.get("peq") or [])

        # Ensure curve fields for plotting
        src = self.correction.get("source_fr")
        if src is not None:
            self.correction["source_curve"] = list(src)
        tgt = self.correction.get("target_fr")
        if tgt is not None:
            self.correction["target_curve"] = list(tgt)
        use_fir = bool(self.correction.get("use_fir", False))
        resp = self.correction.get("combined_resp") if use_fir else self.correction.get("peq_resp")
        if resp is None:
            resp = self.correction.get("combined_resp") or self.correction.get("peq_resp")
        if src is not None and resp is not None:
            self.correction["simulated_curve"] = list(np.array(src) + np.array(resp))

        # Update PEQ Table
        self.peq_view.populate(self.peq_list)
        peq_rmse = float(self.correction.get("peq_rmse") or 0.0)
        comb_rmse = float(self.correction.get("combined_rmse") or peq_rmse)
        fir_taps = self.correction.get("fir_n_taps")
        self.peq_view.set_metrics(peq_rmse, comb_rmse, fir_taps, use_fir)

        # Update Plot View
        self.plot_view.set_mode("eq")
        self.plot_view.update_labels("当前耳机", "目标耳机", "模拟后")
        self.plot_view.set_data(self.correction)

        self._set_status_key("gui_status_calc_done")
        self._update_action_states()
        self._log(f"[OK] 频响拟合完成: IIR RMSE: {peq_rmse:.2f} dB, 联合 RMSE: {comb_rmse:.2f} dB")

    # -----------------------------------------------------------------------
    # 部署与启动 CamillaDSP
    # -----------------------------------------------------------------------

    def _compute_preamp(self, peak: float) -> float:
        mode = self.var_preamp_mode.get()
        if peak <= 0 or mode == "none":
            return 0.0
        if mode == "safe":
            return -(peak + 0.2)
        if mode == "moderate":
            return -(peak / 2.0)
        try:
            return float(self.var_preamp_custom.get())
        except Exception:
            return -(peak + 0.2)

    def _on_deploy(self) -> None:
        if not self.correction or not self.source_entry or not self.target_entry:
            return

        device = self._resolved_output_device()
        try:
            fs = int(self.var_sr.get())
        except ValueError:
            fs = cp.DEFAULT_SAMPLE_RATE

        use_fir = bool(self.correction.get("use_fir", False))
        peak = float(self.correction.get("response_peak") or 0.0)
        preamp_gain = self._compute_preamp(peak)

        def worker():
            cfg_path = cp.build_config_path(self.source_entry, self.target_entry)
            fir_ir = self.correction.get("fir_ir") if use_fir else None
            metrics = cp.metrics_from_correction(self.correction)
            cp.generate_camilladsp_config(
                peq_list=self.peq_list,
                output_device=device,
                config_path=cfg_path,
                pre_amp=preamp_gain,
                samplerate=fs,
                fir_ir=fir_ir,
                metrics=metrics,
            )
            proc, log_path = cp.run_camilladsp(cfg_path, debug=False)
            return {"config": cfg_path, "proc": proc, "log": log_path}

        self._set_busy(True)
        self._set_status_key("gui_status_deploy")
        self._run_bg(worker, self._on_deploy_done)

    def _on_deploy_done(self, res, err) -> None:
        self._set_busy(False)
        if err:
            self._set_status_key("gui_status_deploy_fail")
            messagebox.showerror("EQ Cosplay", f"Deploy failed:\n{err}")
            return

        self.last_config = res["config"]
        self.engine_proc = res["proc"]
        self.engine_log = res["log"]
        self._engine_log_pos = 0
        self._active_preset_path = self.last_config

        self._set_status_key("gui_status_running")
        self._update_action_states()
        self._refresh_presets()

        device = self.var_output.get()
        src_name = self.source_entry.get("display_name") if self.source_entry else ""
        tgt_name = self.target_entry.get("display_name") if self.target_entry else ""
        self._log(f"[OK] CamillaDSP 已启动 ({src_name} → {tgt_name})，输出至: {device}")
        self._log(f"[TIP] 若无声，请确认系统默认输出设备已选 BlackHole 2ch。")

    def _on_stop(self) -> None:
        if self.engine_proc is not None:
            try:
                cp.terminate_camilladsp(self.engine_proc, self.engine_log)
            except Exception:
                pass
            self.engine_proc = None
            self.engine_log = None
        try:
            cp.stop_existing_camilladsp_instances(announce=False)
        except Exception:
            pass

        self.last_config = None
        self._active_preset_path = None
        self._set_status_key("gui_status_stopped")
        self._update_action_states()
        self._refresh_presets()
        self._log("[OK] CamillaDSP 滤波引擎已停止。")

    def _on_toggle_fir(self) -> None:
        if not self.correction:
            return
        cur = bool(self.correction.get("use_fir", False))
        new_state = not cur
        self.correction["use_fir"] = new_state

        peq_rmse = self.correction.get("peq_rmse")
        comb_rmse = self.correction.get("combined_rmse")
        fir_taps = self.correction.get("fir_n_taps")
        self.peq_view.set_metrics(peq_rmse, comb_rmse, fir_taps, new_state)
        self.plot_view.set_data(self.correction)
        self._update_action_states()

        # If engine running, redeploy
        if self.engine_proc is not None:
            self._on_deploy()

    # -----------------------------------------------------------------------
    # 预设加载与管理
    # -----------------------------------------------------------------------

    def _load_preset_from_card(self, path: Path) -> None:
        if not path.is_file():
            return
        device = self._resolved_output_device()

        def worker():
            cp.set_config_playback_device(path, device)
            proc, log_path = cp.run_camilladsp(path, debug=False)
            basics = cp.parse_camilladsp_config_for_regen(path)
            metrics = cp.load_config_metrics(path)
            return {"config": path, "proc": proc, "log": log_path, "basics": basics, "metrics": metrics}

        self._set_busy(True)
        self._set_status_key("gui_status_preset")

        def on_done(res, err):
            self._set_busy(False)
            if err:
                self._set_status_key("gui_status_engine_fail")
                messagebox.showerror("EQ Cosplay", f"Failed to load preset:\n{err}")
                return

            self.last_config = res["config"]
            self.engine_proc = res["proc"]
            self.engine_log = res["log"]
            self._engine_log_pos = 0
            self._active_preset_path = res["config"]

            # Load bands into PEQ Table
            basics = res.get("basics") or {}
            metrics = res.get("metrics") or {}
            bands = list(basics.get("peq") or [])
            if bands:
                self.peq_view.populate(bands)
                peq_rmse = metrics.get("peq_rmse")
                comb_rmse = metrics.get("combined_rmse")
                fir_taps = metrics.get("fir_n_taps")
                has_fir = cp.config_uses_fir_conv(res["config"])
                self.peq_view.set_metrics(peq_rmse, comb_rmse, fir_taps, has_fir)

                # Calculate and draw preset curve on plot
                try:
                    fs = float(basics.get("samplerate") or 48000)
                    grid = cp.make_log_freqs(512)
                    b_obj = cp._bands_from_peq_list(bands)
                    peq_resp = cp.peq_response_db(grid, b_obj, fs=fs)
                    comb_resp = np.array(peq_resp, copy=True)
                    if has_fir:
                        try:
                            fir_ir, fir_sr = cp.load_fir_ir_from_companion_wavs(res["config"])
                            if fir_ir is not None and getattr(fir_ir, "size", 0) > 0:
                                fir_resp = cp.fir_response_db(grid, fir_ir, fs=float(fir_sr or fs))
                                comb_resp = peq_resp + fir_resp
                        except Exception as fir_exc:
                            self._log(f"[WARN] 伴生 FIR 频响计算异常: {fir_exc}")

                    stem = res["config"].stem
                    if stem.startswith("cosplay_"):
                        stem = stem[len("cosplay_") :]
                    if "_to_" in stem:
                        parts = stem.split("_to_")
                        src_name = parts[0].replace("_", " ")
                        tgt_name = parts[1].replace("_", " ")
                    else:
                        src_name = stem.replace("_", " ")
                        tgt_name = "Target"

                    corr = {
                        "peq": bands,
                        "grid_freqs": list(grid),
                        "combined_resp": comb_resp,
                        "peq_resp": peq_resp,
                        "peq_rmse": metrics.get("peq_rmse", 0.0),
                        "combined_rmse": metrics.get("combined_rmse", metrics.get("peq_rmse", 0.0)),
                        "fir_n_taps": metrics.get("fir_n_taps", 0),
                        "use_fir": has_fir,
                        "source_fr": None,
                        "target_fr": None,
                        "simulated_curve": None,
                    }
                    self.correction = corr
                    self.plot_view.set_mode("comp")
                    self.plot_view.update_labels("当前耳机", "目标耳机", "模拟后")
                    self.plot_view.set_data(corr)

                    # Update search boxes with preset headphone names initially
                    self.source_box.set_entry({"display_name": src_name})
                    self.target_box.set_entry({"display_name": tgt_name})

                    # 异步从 AutoEq 匹配并加载源耳机与目标耳机的真实声学测量曲线
                    cfg_path = res["config"]
                    def _fetch_preset_measurement():
                        try:
                            e1, e2 = _match_preset_headphone_entries(cfg_path)
                            if e1 and e2:
                                cache_dir = cp.get_writable_dir() / ".csv_cache"
                                cache_dir.mkdir(parents=True, exist_ok=True)
                                sp = cp.download_headphone_csv(e1, cache_dir)
                                tp = cp.download_headphone_csv(e2, cache_dir)
                                if sp and tp and sp.is_file() and tp.is_file():
                                    sf, sm = cp.parse_csv_response(sp)
                                    tf, tm = cp.parse_csv_response(tp)
                                    s_interp = np.interp(grid, sf, sm)
                                    t_interp = np.interp(grid, tf, tm)
                                    # 电平对齐（与 calculate_correction 算法保持严格一致）
                                    delta_raw = t_interp - s_interp
                                    delta_aligned, level_offset = cp.align_delta_level(grid, delta_raw)
                                    target_aligned = s_interp + delta_aligned
                                    sim_interp = s_interp + comb_resp

                                    def _apply():
                                        if getattr(self, "correction", None) is corr:
                                            corr["source_fr"] = list(s_interp)
                                            corr["target_fr"] = list(target_aligned)
                                            corr["source_curve"] = list(s_interp)
                                            corr["target_curve"] = list(target_aligned)
                                            corr["simulated_curve"] = list(sim_interp)
                                            corr["level_offset_db"] = level_offset
                                            corr["delta_aligned"] = delta_aligned
                                            corr["delta_raw"] = delta_raw
                                            self.plot_view.redraw()

                                            self.source_entry = e1
                                            self.target_entry = e2
                                            self.source_box.set_entry(e1)
                                            self.target_box.set_entry(e2)

                                    self._bg_queue.put(_apply)
                        except Exception as exc:
                            self._log(f"[WARN] 预设耳机声学实测曲线加载异常: {exc}")

                    threading.Thread(target=_fetch_preset_measurement, daemon=True).start()
                except Exception as exc:
                    self._log(f"[WARN] 绘制预设频响曲线失败: {exc}")

            self._set_status_key("gui_status_running")
            self._update_action_states()
            self._refresh_presets()
            self._log(f"[OK] 已载入预设: {res['config'].stem}，输出至: {device}")

        self._run_bg(worker, on_done)

    def _delete_preset_from_card(self, path: Path) -> None:
        confirm_msg = self._t("delete_confirm", name=path.stem)
        if not messagebox.askyesno("EQ Cosplay", confirm_msg):
            return
        try:
            path.unlink(missing_ok=True)
            stem = path.stem
            parent = path.parent
            (parent / f"{stem}_fir_left.wav").unlink(missing_ok=True)
            (parent / f"{stem}_fir_right.wav").unlink(missing_ok=True)
            self._log(f"[OK] 已删除预设方案: {path.name}")
        except Exception as e:
            self._log(f"[ERR] 删除预设失败: {e}")
        self._refresh_presets()

    def _load_preset_from_menubar(self, path: Path) -> None:
        self._load_preset_from_card(path)

    # -----------------------------------------------------------------------
    # 菜单栏与窗口控制
    # -----------------------------------------------------------------------

    def _install_menubar(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            import menubar_macos

            self._menubar = menubar_macos.install(self)
        except Exception:
            pass

    def _rebuild_menubar(self) -> None:
        if self._menubar is not None:
            try:
                self._menubar.rebuild()
            except Exception:
                pass

    def _show_window(self, *_args) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
        if sys.platform == "darwin":
            try:
                from AppKit import NSApplication

                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass

    def _hide_to_menubar(self) -> None:
        try:
            self.root.withdraw()
        except Exception:
            pass

    def _quit_app(self, *_args) -> None:
        self._on_stop()
        try:
            self.root.destroy()
        except Exception:
            pass

    def _on_close(self) -> None:
        # If menubar is active, hide to menubar; else quit
        if self._menubar is not None:
            self._hide_to_menubar()
        else:
            self._quit_app()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self._update_action_states()

    def _run_bg(self, worker, on_done) -> None:
        def target():
            try:
                res = worker()
                self._bg_queue.put((on_done, res, None))
            except Exception as exc:
                tb = traceback.format_exc()
                err_text = f"{exc}\n{tb}"
                self._bg_queue.put((on_done, None, err_text))

        threading.Thread(target=target, daemon=True).start()

    def _poll_log(self) -> None:
        # Process background thread callbacks safely on the main thread
        while hasattr(self, "_bg_queue") and not self._bg_queue.empty():
            try:
                item = self._bg_queue.get_nowait()
                if callable(item):
                    item()
                elif isinstance(item, tuple) and len(item) == 3:
                    cb, res, err = item
                    if cb:
                        cb(res, err)
            except queue.Empty:
                break
            except Exception as exc:
                self._log(f"[ERR] Background callback exception: {exc}")

        # Check engine process liveness
        if self.engine_proc is not None:
            ret = self.engine_proc.poll()
            if ret is not None:
                self._log(f"[WARN] CamillaDSP 进程已退出 (退出码 {ret})。")
                self.engine_proc = None
                self._set_status_key("gui_status_stopped")
                self._update_action_states()

        # Tail CamillaDSP log file into GUI log queue
        if self.engine_log and self.engine_log.exists():
            try:
                if not hasattr(self, "_engine_log_pos"):
                    self._engine_log_pos = 0
                with self.engine_log.open("r", encoding="utf-8", errors="replace") as f:
                    f.seek(self._engine_log_pos)
                    new_chunk = f.read()
                    self._engine_log_pos = f.tell()
                if new_chunk:
                    for l in new_chunk.splitlines():
                        if l.strip():
                            self.log_q.put(l + "\n")
            except Exception:
                pass

        lines = []
        while not self.log_q.empty():
            try:
                lines.append(self.log_q.get_nowait())
            except queue.Empty:
                break

        if lines:
            self.log_text.configure(state=NORMAL)
            for line in lines:
                tag = None
                if line.startswith("[OK]"):
                    tag = "ok"
                elif line.startswith("[..]"):
                    tag = "wait"
                elif line.startswith("[ERR]"):
                    tag = "err"
                elif line.startswith("[TIP]"):
                    tag = "tip"
                elif line.startswith("[WARN]") or line.startswith("[!]"):
                    tag = "warn"
                elif line.startswith("#"):
                    tag = "comment"

                if tag:
                    self.log_text.insert(END, line, tag)
                else:
                    self.log_text.insert(END, line)

            self.log_text.see(END)
            self.log_text.configure(state=DISABLED)

        self.root.after(60, self._poll_log)

    def _log(self, text: str) -> None:
        print(text, flush=True)
        if hasattr(self, "log_q"):
            self.log_q.put(str(text).rstrip() + "\n")

    def _clear_logs(self) -> None:
        self.log_text.configure(state=NORMAL)
        self.log_text.delete("1.0", END)
        self.log_text.configure(state=DISABLED)


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

def main() -> None:
    _enable_windows_dpi_awareness()
    root = Tk()
    _app = CosplayApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
