#!/usr/bin/env python3
"""EQ Cosplay: data-driven sound stage with exact response inspection.

Tk components share a pure response model; audio processing remains in cosplay.
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
    simpledialog,
    ttk,
)
from tkinter.scrolledtext import ScrolledText

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import numpy as np
import cosplay as cp
import theme as ui_theme
from ui_controls import HeadphoneSearchBox, IconButton
from sound_stage import FrequencyResponsePlot
from preset_gallery import PresetsLibraryView
from data_inspector import ResponseInspector
from visual_data import build_response


def _launch_engine(config):
    """Treat the core's non-running return as a failure, before applying UI state."""
    proc, log = cp.run_camilladsp(config, debug=False)
    if proc is None or proc.poll() is not None:
        raise RuntimeError("CamillaDSP did not start. Check the engine installation and log.")
    return proc, log


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


_VISUAL_COPY = {
    "zh": {"header_subtitle": "SOUND TRANSFORMATION STUDIO", "library_tab": "音色作品", "peq_tab": "滤波参数", "logs_tab": "诊断日志", "exact_data": "精确数据 / CSV", "render_quality": "视觉质量", "motion": "启用过渡动效", "stage_choose": "选择两个音色", "stage_fit": "正在拟合", "stage_ready": "校正已生成 · 尚未启用", "stage_running": "滤波运行中", "stage_review": "预览新方案 · 原滤波仍运行", "stage_sr": "采样率已变更 · 请重新拟合", "stage_failed": "操作未完成 · 查看诊断", "stage_loading": "正在读取数据", "stage_deploy": "正在启用滤波", "custom_gain": "前级增益（dB）", "plot_mode_toggle": "频响 / 补偿", "preamp_safe": "安全", "preamp_moderate": "折中", "preamp_none": "不调整", "blackhole_warning": "系统音频捕获需要 BlackHole 2ch。可先选择耳机并查看校正结果。"},
    "en": {"header_subtitle": "SOUND TRANSFORMATION STUDIO", "library_tab": "Sound works", "peq_tab": "Filter parameters", "logs_tab": "Diagnostics", "exact_data": "Exact data / CSV", "render_quality": "Visual quality", "motion": "Animate transitions", "stage_choose": "Choose two sounds", "stage_fit": "Fitting response", "stage_ready": "Correction ready · not applied", "stage_running": "Filters running", "stage_review": "New preview · previous filters running", "stage_sr": "Sample rate changed · fit again", "stage_failed": "Action failed · see diagnostics", "stage_loading": "Loading data", "stage_deploy": "Applying filters", "custom_gain": "Preamp gain (dB)", "plot_mode_toggle": "Response / Compensation", "preamp_safe": "Safe", "preamp_moderate": "Moderate", "preamp_none": "No adjustment", "blackhole_warning": "System audio capture needs BlackHole 2ch. You can still select headphones and inspect a correction."},
    "ja": {"header_subtitle": "SOUND TRANSFORMATION STUDIO", "library_tab": "音色コレクション", "peq_tab": "フィルター設定", "logs_tab": "診断ログ", "exact_data": "正確なデータ / CSV", "render_quality": "描画品質", "motion": "トランジションを有効化", "stage_choose": "二つの音色を選択", "stage_fit": "応答を計算中", "stage_ready": "補正完了 · 未適用", "stage_running": "フィルター動作中", "stage_review": "新しいプレビュー · 以前の補正は動作中", "stage_sr": "サンプルレート変更 · 再計算してください", "stage_failed": "操作失敗 · 診断を確認", "stage_loading": "データ読み込み中", "stage_deploy": "フィルターを適用中", "custom_gain": "プリアンプゲイン（dB）", "plot_mode_toggle": "周波数応答 / 補正", "preamp_safe": "安全", "preamp_moderate": "中庸", "preamp_none": "調整なし", "blackhole_warning": "システム音声の取得には BlackHole 2ch が必要です。ヘッドホンの選択と補正の確認は可能です。"},
}
for _language_code, _strings in _VISUAL_COPY.items():
    UI_STRINGS[_language_code].update(_strings)

_INSTRUMENT_COPY = {
    "zh": {"header_subtitle": "声音校正工作台", "library_tab": "本地方案",
           "motion": "过渡动效",
           "plot_control_response": "响应", "plot_control_compensation": "补偿",
           "plot_control_membrane": "曲面", "plot_control_flat": "平面",
           "plot_control_locked": "范围锁定", "plot_control_auto": "自动范围",
           "plot_empty_state": "尚无响应数据", "plot_filter_only": "滤波响应 · 无测量数据",
           "plot_locked_overflow": "超出锁定范围 · 解锁以适配",
           "quality_auto": "自动", "quality_high": "高", "quality_low": "低"},
    "en": {"header_subtitle": "Sound correction workspace", "library_tab": "Presets",
           "motion": "Motion",
           "plot_control_response": "Response", "plot_control_compensation": "Compensation",
           "plot_control_membrane": "Membrane", "plot_control_flat": "Flat",
           "plot_control_locked": "Range locked", "plot_control_auto": "Auto range",
           "plot_empty_state": "No response loaded", "plot_filter_only": "Filter response · no measurements",
           "plot_locked_overflow": "Outside locked range · unlock to fit",
           "quality_auto": "Auto", "quality_high": "High", "quality_low": "Low"},
    "ja": {"header_subtitle": "音響補正ワークスペース", "library_tab": "プリセット",
           "motion": "アニメーション",
           "plot_control_response": "周波数応答", "plot_control_compensation": "補正",
           "plot_control_membrane": "曲面", "plot_control_flat": "平面",
           "plot_control_locked": "範囲固定", "plot_control_auto": "自動範囲",
           "plot_empty_state": "応答データがありません", "plot_filter_only": "フィルター応答 · 測定データなし",
           "plot_locked_overflow": "固定範囲外 · 解除して調整",
           "quality_auto": "自動", "quality_high": "高", "quality_low": "低"},
}
for _language_code, _strings in _INSTRUMENT_COPY.items():
    UI_STRINGS[_language_code].update(_strings)


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
        self.fonts = fonts
        self._metrics = (None, None, None, False)
        self._build()

    def _build(self) -> None:
        # Keep measurements in one instrument-style row above the table.
        self.header = Frame(self, bg=ui_theme.PANEL)
        self.header.pack(fill=X, padx=12, pady=(12, 10))

        self.lbl_title = Label(
            self.header,
            text="参数均衡器 (10-Band PEQ)",
            bg=ui_theme.PANEL,
            fg=ui_theme.TEXT,
            font=self.fonts.get("subhead", self.fonts["ui12"]),
            anchor="w",
        )
        self.lbl_title.pack(side=LEFT)

        # Numerical readouts share a baseline rather than consuming three rows.
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
        self.lbl_iir_rmse.pack(side=LEFT, padx=(16, 0))

        self.lbl_fir_rmse = Label(
            self.metrics_box,
            text="IIR + FIR RMSE: —",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self.fonts["mono9"],
            anchor="e",
        )
        self.lbl_fir_rmse.pack(side=LEFT, padx=(16, 0))

        self.lbl_fir_taps = Label(
            self.metrics_box,
            text="FIR Taps: —",
            bg=ui_theme.PANEL,
            fg=ui_theme.MUTED,
            font=self.fonts["mono9"],
            anchor="e",
        )
        self.lbl_fir_taps.pack(side=LEFT, padx=(16, 0))

        # Treeview Box
        tree_frame = Frame(self, bg=ui_theme.PANEL)
        tree_frame.pack(fill=BOTH, expand=True, padx=12, pady=(0, 12))

        cols = ("idx", "type", "freq", "gain", "q")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=10,
                                 style="Numeric.Treeview")
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
        self._metrics = (iir_rmse, fir_rmse, fir_taps, use_fir)
        iir_str = f"{iir_rmse:.2f} dB" if iir_rmse is not None else "—"
        fir_str = f"{fir_rmse:.2f} dB" if (use_fir and fir_rmse is not None) else "—"
        taps_str = f"{fir_taps}" if (use_fir and fir_taps and fir_taps > 0) else "—"

        self.lbl_iir_rmse.configure(text=f"IIR RMSE: {iir_str}")
        self.lbl_fir_rmse.configure(text=f"IIR + FIR RMSE: {fir_str}")
        taps_label = {"zh": "FIR 抽头", "ja": "FIR タップ"}.get(cp.LANG, "FIR taps")
        self.lbl_fir_taps.configure(text=f"{taps_label}: {taps_str}")

    def refresh_language(self):
        self.set_metrics(*self._metrics)

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

class CosplayApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("EQ Cosplay")
        self.root.geometry("1120x820")
        self.root.minsize(960, 720)

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
        self._poll_job = self.root.after(100, self._poll_log)
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
    # Shared alignment grid for the desktop workspace.
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._drawer = None
        self._settings_open = False
        self._drawer_layout_job = None
        self._restoring_selection = False
        self._selection_revision = 0
        self._correction_revision = None
        self._correction_sr = None
        self._loaded_preset = False
        self._display_is_applied = False
        self._motion = BooleanVar(self.root, value=True)
        self._render_quality = StringVar(self.root, value="auto")
        self._quality_label = StringVar(self.root)
        self.outer = Frame(self.root, bg=ui_theme.BG)
        self.outer.pack(fill=BOTH, expand=True)

        pad = 80 if self._is_macos_integrated else 24
        self.top_bar = Frame(self.outer, bg=ui_theme.BG, height=58)
        self.top_bar.pack(fill=X, padx=(pad, 24), pady=(8, 12))
        self.top_bar.pack_propagate(False)
        self.brand_box = Frame(self.top_bar, bg=ui_theme.BG)
        self.brand_box.pack(side=LEFT)
        ui_theme.make_mark(self.brand_box, size=28).pack(side=LEFT, padx=(0, 12))
        brand_text = Frame(self.brand_box, bg=ui_theme.BG)
        brand_text.pack(side=LEFT)
        self.lbl_app_title = Label(brand_text, text="EQ Cosplay", bg=ui_theme.BG,
                                   fg=ui_theme.TEXT, font=self._theme.get("hero", self._theme["ui14"]))
        self.lbl_app_title.pack(anchor="w")
        self.lbl_subtitle = Label(brand_text, bg=ui_theme.BG, fg=ui_theme.MUTED,
                                 font=self._theme.get("caption", self._theme["ui9"]))
        self.lbl_subtitle.pack(anchor="w", pady=(2, 0))

        def start_drag(event):
            self._win_drag_start = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

        def drag(event):
            if hasattr(self, "_win_drag_start"):
                dx, dy = self._win_drag_start
                self.root.geometry(f"+{event.x_root-dx}+{event.y_root-dy}")

        for widget in (self.top_bar, self.brand_box, brand_text, self.lbl_app_title, self.lbl_subtitle):
            widget.bind("<Button-1>", start_drag)
            widget.bind("<B1-Motion>", drag)

        self.top_right = Frame(self.top_bar, bg=ui_theme.BG)
        self.top_right.pack(side=RIGHT)
        self.status_pill = Frame(self.top_right, bg=ui_theme.BG, padx=0, pady=6)
        self.status_pill.pack(side=LEFT, padx=(0, 10))
        self.status_dot = Canvas(self.status_pill, width=8, height=8, bg=ui_theme.BG, highlightthickness=0, bd=0)
        self.status_dot.pack(side=LEFT, padx=(0, 7))
        self._dot_id = self.status_dot.create_rectangle(1, 1, 7, 7, fill=ui_theme.MUTED, outline="")
        self.lbl_status = Label(self.status_pill, textvariable=self.var_status, bg=ui_theme.BG,
                                fg=ui_theme.MUTED, font=self._theme["ui10"])
        self.lbl_status.pack(side=LEFT)
        self.cmb_lang = ttk.Combobox(self.top_right, textvariable=self.var_lang,
                                    values=["zh", "en", "ja"], state="readonly", width=4)
        self.cmb_lang.pack(side=LEFT)
        self.cmb_lang.bind("<<ComboboxSelected>>", self._on_lang_change)

        self.picker_frame = Frame(self.outer, bg=ui_theme.BG)
        self.picker_frame.pack(fill=X, padx=24, pady=(0, 12))
        self.picker_frame.columnconfigure(0, weight=1, uniform="picker")
        self.picker_frame.columnconfigure(1, weight=1, uniform="picker")
        self.col_source = Frame(self.picker_frame, bg=ui_theme.BG)
        self.col_source.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.col_target = Frame(self.picker_frame, bg=ui_theme.BG)
        self.col_target.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.lbl_source_title = Label(self.col_source, bg=ui_theme.BG, fg=ui_theme.MUTED,
                                      font=self._theme["ui10"], anchor="w")
        self.lbl_source_title.pack(fill=X, pady=(0, 5))
        self.source_box = HeadphoneSearchBox(self.col_source, self.fonts, on_change=self._on_source_selected,
                                             search_fn=search_headphones, accent=ui_theme.PLOT_SRC)
        self.source_box.pack(fill=X)
        self.lbl_target_title = Label(self.col_target, bg=ui_theme.BG, fg=ui_theme.MUTED,
                                      font=self._theme["ui10"], anchor="w")
        self.lbl_target_title.pack(fill=X, pady=(0, 5))
        self.target_box = HeadphoneSearchBox(self.col_target, self.fonts, on_change=self._on_target_selected,
                                             search_fn=search_headphones, accent=ui_theme.PLOT_TGT)
        self.target_box.pack(fill=X)

        self.control_bar = Frame(self.outer, bg=ui_theme.PANEL, padx=12, pady=8,
                                 highlightthickness=1, highlightbackground=ui_theme.BORDER)
        self.control_bar.pack(fill=X, padx=24, pady=(0, 12))
        self.phase_label = Label(self.control_bar, bg=ui_theme.PANEL, fg=ui_theme.MUTED, font=self._theme["ui10"], anchor="w")
        self.phase_label.pack(side=LEFT)
        self.actions_box = Frame(self.control_bar, bg=ui_theme.PANEL)
        self.actions_box.pack(side=RIGHT)
        self.btn_toggle_fir = ttk.Button(self.actions_box, command=self._on_toggle_fir)
        self.btn_calc = ttk.Button(self.actions_box, command=self._on_calculate)
        self.btn_calc.pack(side=LEFT, padx=(0, 8))
        self.btn_deploy = ttk.Button(self.actions_box, command=self._on_deploy, style="Primary.TButton")
        self.btn_deploy.pack(side=LEFT, padx=(0, 8))
        self.btn_stop = ttk.Button(self.actions_box, command=self._on_stop)
        self.btn_settings = IconButton(self.actions_box, "settings", self._toggle_settings, bg=ui_theme.PANEL)
        self.btn_settings.pack(side=LEFT)

        # Settings are available without competing with the response stage.
        self.settings_bar = ui_theme.make_glass_frame(self.outer, padding=12)
        self.settings_bar.configure(pady=8)
        self.settings_bar.columnconfigure(2, weight=1)
        def field(column, label, variable=None, width=10, values=(), readonly=True):
            box = Frame(self.settings_bar, bg=ui_theme.PANEL)
            box.grid(row=0, column=column, sticky="ew", padx=(0, 14))
            caption = Label(box, bg=ui_theme.PANEL, fg=ui_theme.MUTED, font=self._theme["ui10"])
            caption.pack(anchor="w", pady=(0, 4))
            combo = ttk.Combobox(box, textvariable=variable, width=width, values=values,
                                  state="readonly" if readonly else "normal")
            combo.pack(fill=X)
            return caption, combo, box
        self.preamp_values = ["safe", "moderate", "custom", "none"]
        self.lbl_preamp, self.cmb_preamp, _ = field(0, "", width=16)
        self.cmb_preamp.bind("<<ComboboxSelected>>", self._on_preamp_change)
        self.lbl_sr, self.cmb_sr, _ = field(1, "", self.var_sr, width=10,
                                          values=["44100", "48000", "88200", "96000", "192000"])
        self.cmb_sr.bind("<<ComboboxSelected>>", self._on_sample_rate_change)
        self.lbl_playback, self.cmb_output, device_box = field(2, "", self.var_output, width=22, readonly=self.system_name == "Darwin")
        self.cmb_output.bind("<<ComboboxSelected>>", self._on_output_device_change)
        if self.system_name != "Darwin":
            self.cmb_output.bind("<Return>", self._on_output_device_change)
        self.btn_refresh_dev = IconButton(device_box, "refresh", self._refresh_output_devices, size=24)
        self.btn_refresh_dev.place(relx=1, x=-24, y=-2)
        self.lbl_quality, self.cmb_quality, _ = field(3, "", self._quality_label, width=7)
        self.cmb_quality.bind("<<ComboboxSelected>>", self._on_render_quality_change)
        self.motion_check = ttk.Checkbutton(self.settings_bar, variable=self._motion,
                                             command=lambda: self.plot_view.set_motion_enabled(self._motion.get()))
        self.motion_check.grid(row=0, column=4, sticky="sw", pady=(0, 3))

        self.bh_banner = Frame(self.outer, bg=ui_theme.GOLD_BG, padx=12, pady=8,
                                highlightthickness=1, highlightbackground=ui_theme.BORDER)
        self.lbl_bh_warn = Label(self.bh_banner, bg=ui_theme.GOLD_BG, fg=ui_theme.GOLD,
                                 font=self._theme["ui10"], wraplength=720, justify=LEFT)
        self.lbl_bh_warn.pack(side=LEFT)
        self.btn_install_bh = ttk.Button(self.bh_banner, command=self._on_install_blackhole, style="Gold.TButton")
        self.btn_install_bh.pack(side=RIGHT)

        # Reserve the footer first so the expanding stage never clips controls.
        self.footer = Frame(self.outer, bg=ui_theme.BG)
        self.footer.pack(side=BOTTOM, fill=X, padx=24, pady=(12, 16))
        self.drawer_buttons = {}
        for key in ("library", "peq", "logs"):
            button = ttk.Button(self.footer, command=lambda k=key: self._toggle_drawer(k), style="Tab.TButton")
            button.pack(side=LEFT, padx=(0, 8))
            self.drawer_buttons[key] = button
        self.btn_exact = ttk.Button(self.footer, command=self._show_exact_data, style="Ghost.TButton")
        self.btn_exact.pack(side=RIGHT)
        self.device_summary = Label(self.footer, bg=ui_theme.BG, fg=ui_theme.MUTED,
                                    font=self._theme["mono9"])
        self.device_summary.pack(side=RIGHT, padx=(8, 16))
        self.bottom_row = Frame(self.outer, bg=ui_theme.BG, height=250)
        self.bottom_row.pack_propagate(False)
        self.bottom_row.bind("<Configure>", lambda _e: self._schedule_drawer_layout())
        self.bottom_row.bind("<Map>", lambda _e: self._schedule_drawer_layout())
        self.presets_view = PresetsLibraryView(self.bottom_row, self._theme,
            on_load=self._load_preset_from_card, on_delete=self._delete_preset_from_card, on_refresh=self._refresh_presets)
        self.peq_view = PEQTableView(self.bottom_row, self._theme)
        self.peq_view.tree.bind("<<TreeviewSelect>>", self._on_peq_selected)
        self.peq_view.tree.bind("<Double-1>", lambda _e: self._show_exact_data())
        self.log_card = ui_theme.make_glass_frame(self.bottom_row, padding=12)
        log_header = Frame(self.log_card, bg=ui_theme.PANEL)
        log_header.pack(fill=X, pady=(0, 6))
        self.lbl_log_title = Label(log_header, bg=ui_theme.PANEL, fg=ui_theme.MUTED, font=self._theme["mono10"])
        self.lbl_log_title.pack(side=LEFT)
        self.btn_clear_log = ttk.Button(log_header, command=self._clear_logs, style="Ghost.TButton")
        self.btn_clear_log.pack(side=RIGHT)
        self.log_text = ScrolledText(self.log_card, wrap=WORD, bd=0, relief="flat")
        self.log_text.pack(fill=BOTH, expand=True)
        ui_theme.style_log_widget(self.log_text, self._theme["mono10"])
        self.log_text.configure(state=DISABLED)
        for tag, color in (("ok", ui_theme.EMERALD), ("wait", ui_theme.TEAL), ("err", ui_theme.ROSE),
                            ("tip", ui_theme.GOLD), ("warn", ui_theme.GOLD), ("comment", ui_theme.MUTED)):
            self.log_text.tag_configure(tag, foreground=color)

        self.display_row = Frame(self.outer, bg=ui_theme.BG)
        self.display_row.pack(fill=BOTH, expand=True, padx=24, pady=(0, 0))
        self.plot_view = FrequencyResponsePlot(self.display_row, self._theme)
        self.plot_view._t_fn = self._t
        self.plot_view.on_band_selected = self._on_stage_band_selected
        self.plot_view.pack(fill=BOTH, expand=True)
        self.data_inspector = ResponseInspector(self.root, self._theme)
        self.root.bind("<Configure>", self._on_workspace_resize, add="+")
        self._update_action_states()

    def _toggle_settings(self):
        self._settings_open = not self._settings_open
        if self._settings_open:
            self.settings_bar.pack(fill=X, padx=24, pady=(0, 12), before=self.display_row)
        else:
            self.settings_bar.pack_forget()
        self._schedule_drawer_layout()

    def _toggle_drawer(self, key):
        for view in (self.presets_view, self.peq_view, self.log_card):
            view.pack_forget()
        if self._drawer == key:
            self.bottom_row.pack_forget()
            self._drawer = None
        else:
            self._drawer = key
            self.bottom_row.pack(side=BOTTOM, fill=X, padx=24, pady=(12, 0), before=self.display_row)
            {"library": self.presets_view, "peq": self.peq_view, "logs": self.log_card}[key].pack(fill=BOTH, expand=True)
        for name, button in self.drawer_buttons.items():
            button.configure(style="Selected.Tab.TButton" if name == self._drawer else "Tab.TButton")
        self._schedule_drawer_layout()

    def _on_workspace_resize(self, event):
        if event.widget is self.root:
            self._schedule_drawer_layout()

    def _schedule_drawer_layout(self):
        if self._drawer_layout_job is None:
            self._drawer_layout_job = self.root.after_idle(self._fit_drawer)

    def _fit_drawer(self):
        self._drawer_layout_job = None
        if self._drawer is None or not self.bottom_row.winfo_ismapped():
            return
        # Give the response field a useful minimum height even when settings and
        # a drawer are both open on a small screen. Tables remain scrollable.
        height = self.bottom_row.winfo_height() + self.display_row.winfo_height() - 240
        height = min(250, max(96, height))
        if abs(height - self.bottom_row.winfo_height()) > 2:
            self.bottom_row.configure(height=height)

    def _show_exact_data(self):
        self.data_inspector.show(self.correction, self.plot_view.mode)

    def _on_peq_selected(self, _event=None):
        selected = self.peq_view.tree.selection()
        if selected:
            self.plot_view.set_selected_band(self.peq_view.tree.index(selected[0]))

    def _on_stage_band_selected(self, index):
        rows = self.peq_view.tree.get_children()
        if 0 <= index < len(rows):
            self.peq_view.tree.selection_set(rows[index])
            self.peq_view.tree.see(rows[index])
            if self._drawer != "peq":
                self._toggle_drawer("peq")

    def _on_sample_rate_change(self, _event=None):
        self._update_action_states()

    def _sync_visual_data(self):
        self.plot_view.set_data(self.correction)
        self.data_inspector.set_data(self.correction, self.plot_view.mode)
        if self.correction is not None:
            data = build_response(self.correction)
            self.peq_view.populate(self.peq_list)
            self.peq_view.set_metrics(data.iir_rmse, data.combined_rmse, data.fir_taps, data.use_fir)

    def _selection_changed(self):
        source = (self.source_entry or {}).get("display_name") or ""
        target = (self.target_entry or {}).get("display_name") or ""
        self.plot_view.set_identity(source, target)
        if not self._restoring_selection:
            self._selection_revision += 1
            self.correction = None
            self.peq_list = []
            self._loaded_preset = False
            self._sync_visual_data()
            self.peq_view.populate([])
            self.peq_view.set_metrics(None, None, None, False)
        self._update_action_states()

    def _set_status_key(self, key: str, **kwargs) -> None:
        self._status_key = key
        self._status_kwargs = dict(kwargs)
        self._refresh_status_pill()

    def _engine_running(self):
        return self.engine_proc is not None and self.engine_proc.poll() is None

    def _refresh_status_pill(self) -> None:
        self.var_status.set(self._t(self._status_key, **self._status_kwargs))
        fail = self._status_key.endswith("_fail")
        color = ui_theme.ROSE if fail else ui_theme.TEAL if self.busy else ui_theme.EMERALD if self._engine_running() else ui_theme.MUTED
        self.status_dot.itemconfig(self._dot_id, fill=color)
        self.lbl_status.configure(fg=color if fail or self.busy else ui_theme.TEXT)
        self._refresh_phase()

    def _refresh_phase(self):
        if self.busy:
            phase = "stage_fit" if self._status_key == "gui_status_calc" else "stage_deploy" if self._status_key in ("gui_status_deploy", "gui_status_preset") else "stage_loading"
        elif self._status_key.endswith("_fail"):
            phase = "stage_failed"
        elif self.correction and self._correction_sr != int(self.var_sr.get() or cp.DEFAULT_SAMPLE_RATE):
            phase = "stage_sr"
        elif self._engine_running():
            phase = "stage_review" if self.correction is None or not getattr(self, "_display_is_applied", False) else "stage_running"
        else:
            phase = "stage_ready" if self.correction else "stage_choose"
        self.phase_label.configure(text=self._t(phase))
        self.plot_view.set_activity(self._t(phase))
        self.device_summary.configure(text=f"{int(self.var_sr.get()) / 1000:g} kHz")

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
        self.peq_view.refresh_language()

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

        self.lbl_subtitle.configure(text=self._t("header_subtitle"))
        for key, button in self.drawer_buttons.items():
            button.configure(text=self._t({"library": "library_tab", "peq": "peq_tab", "logs": "logs_tab"}[key]))
        self.btn_exact.configure(text=self._t("exact_data"))
        self.lbl_quality.configure(text=self._t("render_quality"))
        qualities = ("auto", "high", "low")
        self.cmb_quality["values"] = [self._t(f"quality_{quality}") for quality in qualities]
        self.cmb_quality.current(qualities.index(self._render_quality.get()))
        self.motion_check.configure(text=self._t("motion"))
        self.presets_view.refresh_language()
        self.plot_view.refresh_language()
        self.data_inspector.refresh_language()
        self._update_action_states()
        self._refresh_status_pill()

    def _on_render_quality_change(self, _event=None):
        index = self.cmb_quality.current()
        if index >= 0:
            quality = ("auto", "high", "low")[index]
            self._render_quality.set(quality)
            self.plot_view.set_quality(quality)

    def _on_preamp_change(self, _event=None) -> None:
        idx = self.cmb_preamp.current()
        modes = ["safe", "moderate", "custom", "none"]
        if 0 <= idx < len(modes):
            chosen = modes[idx]
            self.var_preamp_mode.set(chosen)
            if chosen == "custom":
                value = simpledialog.askfloat("EQ Cosplay", self._t("custom_gain"), parent=self.root,
                                               initialvalue=self.var_preamp_custom.get(), minvalue=-120, maxvalue=24)
                if value is not None:
                    self.var_preamp_custom.set(value)

    def _on_source_selected(self, entry: dict | None) -> None:
        self.source_entry = entry
        self._selection_changed()

    def _on_target_selected(self, entry: dict | None) -> None:
        self.target_entry = entry
        self._selection_changed()

    def _update_action_states(self) -> None:
        self.source_box.set_enabled(not self.busy)
        self.target_box.set_enabled(not self.busy)
        for combo in (self.cmb_preamp, self.cmb_sr):
            combo.configure(state=DISABLED if self.busy else "readonly")
        self.cmb_output.configure(state=DISABLED if self.busy else "readonly" if self.system_name == "Darwin" else NORMAL)
        can_calc = bool(self.db_ready and self.source_entry and self.target_entry
                        and self.source_entry.get("relative_path") and self.target_entry.get("relative_path") and not self.busy)
        self.btn_calc.configure(state=NORMAL if can_calc else DISABLED)
        valid_correction = bool(self.correction and self._correction_revision == self._selection_revision
                                and self._correction_sr == int(self.var_sr.get()))
        self.btn_deploy.configure(state=NORMAL if valid_correction and not self.busy and not self._loaded_preset else DISABLED)
        is_running = self._engine_running()
        self.btn_stop.configure(state=DISABLED if self.busy else NORMAL)
        if is_running:
            self.btn_stop.pack(side=LEFT, padx=(0, 8), before=self.btn_settings)
        else:
            self.btn_stop.pack_forget()
        has_fir = bool(self.correction and (self.correction.get("fir_ir") is not None or self.correction.get("has_companion_fir")))
        if has_fir:
            self.btn_toggle_fir.configure(text=self._t("fir_stop" if self.correction.get("use_fir", False) else "fir_enable"),
                                          state=NORMAL if valid_correction and not self.busy else DISABLED)
            self.btn_toggle_fir.pack(side=LEFT, padx=(0, 8), before=self.btn_calc)
        else:
            self.btn_toggle_fir.pack_forget()
        self.btn_exact.configure(state=NORMAL if self.correction else DISABLED)
        self._refresh_phase()

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
        if self.busy:
            return
        device = self.var_output.get()
        if self._engine_running() and self.last_config:
            config = self.last_config
            self._log(f"[..] 重新定向输出声卡至: {device}...")
            def worker():
                cp.set_config_playback_device(config, device)
                return _launch_engine(config)
            def on_done(result, err):
                self._set_busy(False)
                if err:
                    self._set_status_key("gui_status_deploy_fail")
                    self._log(f"[ERR] Audio output change failed: {err}")
                    return
                self.engine_proc, self.engine_log = result
                self._engine_log_pos = 0
                self._set_status_key("gui_status_running")
                self._update_action_states()
                self._rebuild_menubar()
                self._log(f"[OK] 引擎已重新定向至: {device}")
            self._set_status_key("gui_status_deploy")
            self._set_busy(True)
            self._run_bg(worker, on_done)

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
        if self.busy or not self.source_entry or not self.target_entry or not self.source_entry.get("relative_path") or not self.target_entry.get("relative_path"):
            messagebox.showwarning("EQ Cosplay", self._t("search_placeholder"))
            return

        try:
            fs = int(self.var_sr.get())
        except ValueError:
            fs = cp.DEFAULT_SAMPLE_RATE

        source_entry = self.source_entry
        target_entry = self.target_entry
        revision = self._selection_revision

        def worker():
            temp_dir = Path(tempfile.mkdtemp(prefix="autoeq_gui_"))
            sp = cp.download_headphone_csv(source_entry, temp_dir)
            tp = cp.download_headphone_csv(target_entry, temp_dir)
            if not sp or not tp:
                raise RuntimeError("Failed to download headphone measurement curves.")
            correction = cp.calculate_correction(sp, tp, fs=fs)
            correction["samplerate"] = fs
            return {"correction": correction, "fs": fs, "revision": revision}

        self._set_busy(True)
        self._set_status_key("gui_status_calc")
        self._run_bg(worker, self._on_calc_done)

    def _on_calc_done(self, result, err) -> None:
        self._set_busy(False)
        if err:
            self._set_status_key("gui_status_calc_fail")
            self._log(f"[ERR] Calculation failed: {err}")
            messagebox.showerror("EQ Cosplay", str(err))
            return
        if result["revision"] != self._selection_revision or result["fs"] != int(self.var_sr.get()):
            self._log("[TIP] Selection changed while fitting; calculate again for the new selection.")
            self._set_status_key("gui_status_ready", count=len(cp.AUTOEQ_DATABASE or {}))
            return
        self.correction = result["correction"]
        self.peq_list = list(self.correction.get("peq") or [])
        self._correction_revision = result["revision"]
        self._correction_sr = result["fs"]
        self._loaded_preset = False
        self._display_is_applied = False
        self.plot_view.set_mode("eq")
        self._sync_visual_data()
        self._set_status_key("gui_status_calc_done")
        self._update_action_states()
        data = build_response(self.correction)
        self._log(f"[OK] Fit complete: IIR RMSE {data.iir_rmse:.3f} dB; combined RMSE {data.combined_rmse:.3f} dB")

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
        if self.busy or not self.correction or not self.source_entry or not self.target_entry:
            return
        fs = int(self.var_sr.get())
        if self._correction_revision != self._selection_revision or self._correction_sr != fs or self._loaded_preset:
            return
        device = self._resolved_output_device()
        correction = self.correction
        source, target = dict(self.source_entry), dict(self.target_entry)
        bands = list(self.peq_list)
        response = build_response(correction)
        peak = float(np.nanmax(response.filter_response)) if len(response.freqs) else 0.0
        preamp_gain = self._compute_preamp(peak)
        revision = self._selection_revision

        def worker():
            cfg_path = cp.build_config_path(source, target)
            cp.generate_camilladsp_config(
                peq_list=bands, output_device=device, config_path=cfg_path,
                pre_amp=preamp_gain, samplerate=fs,
                fir_ir=correction.get("fir_ir") if correction.get("use_fir") else None,
                metrics=cp.metrics_from_correction(correction),
            )
            proc, log_path = _launch_engine(cfg_path)
            return {"config": cfg_path, "proc": proc, "log": log_path, "correction": correction, "revision": revision}

        self._set_status_key("gui_status_deploy")
        self._set_busy(True)
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
        self._display_is_applied = res.get("correction") is self.correction and res.get("revision") == self._selection_revision

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

        self._display_is_applied = False
        self._active_preset_path = None
        self._set_status_key("gui_status_stopped")
        self._update_action_states()
        self._refresh_presets()
        self._log("[OK] CamillaDSP 滤波引擎已停止。")

    def _on_toggle_fir(self) -> None:
        if self.busy or not self.correction or self._correction_sr != int(self.var_sr.get()):
            return
        correction = self.correction
        old_state = bool(correction.get("use_fir", False))
        new_state = not old_state
        if new_state and correction.get("fir_ir") is None and not correction.get("has_companion_fir"):
            return
        correction["use_fir"] = new_state
        correction.pop("simulated_curve", None)
        self._display_is_applied = False
        self._sync_visual_data()
        self._update_action_states()
        if self._loaded_preset and self.last_config:
            path, device = self.last_config, self._resolved_output_device()
            running = self._engine_running()
            def worker():
                cp.regenerate_config_fir_mode(path, use_fir=new_state, output_device=device,
                                              fir_ir=correction.get("fir_ir"), samplerate=self._correction_sr)
                if running:
                    proc, log = _launch_engine(path)
                else:
                    proc, log = None, None
                return proc, log
            def on_done(result, err):
                self._set_busy(False)
                if err:
                    correction["use_fir"] = old_state
                    if self.correction is correction:
                        self._sync_visual_data()
                    self._set_status_key("gui_status_deploy_fail")
                    self._log(f"[ERR] FIR switch failed: {err}")
                    return
                self.engine_proc, self.engine_log = result
                self._engine_log_pos = 0
                self._display_is_applied = running and self.correction is correction
                self._set_status_key("gui_status_running" if running else "gui_status_calc_done")
                self._update_action_states()
                self._refresh_presets()
            self._set_status_key("gui_status_deploy")
            self._set_busy(True)
            self._run_bg(worker, on_done)
        elif self._engine_running():
            self._on_deploy()

    def _load_preset_from_card(self, path: Path) -> None:
        if self.busy or not path.is_file():
            return
        device = self._resolved_output_device()
        revision = self._selection_revision

        def worker():
            basics = cp.parse_camilladsp_config_for_regen(path)
            if not basics:
                raise ValueError("Preset has no readable PEQ filter parameters")
            metrics = cp.load_config_metrics(path)
            bands = list(basics["peq"])
            fs = int(basics.get("samplerate") or cp.DEFAULT_SAMPLE_RATE)
            grid = cp.make_log_freqs(512)
            peq = cp.peq_response_db(grid, cp._bands_from_peq_list(bands), fs=fs)
            fir_ir, fir_sr = cp.load_fir_ir_from_companion_wavs(path)
            has_fir = bool(basics.get("use_fir"))
            if has_fir and fir_ir is None:
                raise ValueError("Preset requires a missing FIR impulse response")
            combined = peq + cp.fir_response_db(grid, fir_ir, fs=float(fir_sr or fs)) if fir_ir is not None else peq.copy()
            correction = {"peq": bands, "samplerate": fs, "grid_freqs": grid, "peq_resp": peq,
                          "combined_resp": combined, "fir_ir": fir_ir,
                          "use_fir": has_fir, "has_companion_fir": fir_ir is not None,
                          "fir_n_taps": len(fir_ir) if fir_ir is not None else None,
                          "peq_rmse": metrics.get("peq_rmse"), "combined_rmse": metrics.get("combined_rmse"),
                          "level_offset_db": metrics.get("level_offset_db")}
            cp.set_config_playback_device(path, device)
            proc, log_path = _launch_engine(path)
            return {"config": path, "proc": proc, "log": log_path, "correction": correction}

        def on_done(result, err):
            self._set_busy(False)
            if err:
                self._set_status_key("gui_status_engine_fail")
                self._log(f"[ERR] Preset load failed: {err}")
                messagebox.showerror("EQ Cosplay", str(err))
                return
            self.last_config, self.engine_proc, self.engine_log = result["config"], result["proc"], result["log"]
            self._engine_log_pos = 0
            self._active_preset_path = path
            if revision == self._selection_revision:
                correction = result["correction"]
                self.correction = correction
                self.peq_list = list(correction["peq"])
                self._loaded_preset = True
                self._correction_sr = correction["samplerate"]
                self.var_sr.set(str(self._correction_sr))
                stem = path.stem.removeprefix("cosplay_")
                names = stem.split("_to_", 1)
                self._restoring_selection = True
                try:
                    self.source_box.set_entry({"display_name": names[0].replace("_", " ")})
                    self.target_box.set_entry({"display_name": names[1].replace("_", " ") if len(names) > 1 else "—"})
                finally:
                    self._restoring_selection = False
                self._correction_revision = self._selection_revision
                self._display_is_applied = True
                self.plot_view.set_mode("comp")
                self._sync_visual_data()
                self._fetch_preset_measurements(path, correction)
            else:
                self._display_is_applied = False
            self._set_status_key("gui_status_running")
            self._update_action_states()
            self._refresh_presets()
            self._log(f"[OK] Loaded preset: {path.stem}")

        self._set_status_key("gui_status_preset")
        self._set_busy(True)
        self._run_bg(worker, on_done)

    def _fetch_preset_measurements(self, path, correction):
        def worker():
            first, second = _match_preset_headphone_entries(path)
            if not first or not second:
                return None
            cache_dir = cp.get_writable_dir() / ".csv_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            source_csv = cp.download_headphone_csv(first, cache_dir)
            target_csv = cp.download_headphone_csv(second, cache_dir)
            if not source_csv or not target_csv:
                return None
            sf, sm = cp.parse_csv_response(source_csv)
            tf, tm = cp.parse_csv_response(target_csv)
            grid = correction["grid_freqs"]
            source, raw_target = np.interp(grid, sf, sm), np.interp(grid, tf, tm)
            aligned, offset = cp.align_delta_level(grid, raw_target - source)
            return first, second, source, raw_target, source + aligned, offset

        def on_done(result, err):
            if self.correction is not correction:
                return
            if err or not result:
                if err:
                    self._log(f"[WARN] Preset measurement data unavailable: {err}")
                return
            first, second, source, raw_target, target, offset = result
            correction.update(source_fr=source, target_raw_fr=raw_target, target_fr=target, level_offset_db=offset)
            self._restoring_selection = True
            try:
                self.source_box.set_entry(first)
                self.target_box.set_entry(second)
            finally:
                self._restoring_selection = False
            self._sync_visual_data()
            self._update_action_states()

        self._run_bg(worker, on_done)

    def _delete_preset_from_card(self, path: Path) -> None:
        if self.busy:
            return
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
        while not self.log_q.empty() and len(lines) < 250:
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

            total_lines = int(self.log_text.index("end-1c").split(".")[0])
            if total_lines > 3000:
                self.log_text.delete("1.0", f"{total_lines-2500}.0")
            self.log_text.see(END)
            self.log_text.configure(state=DISABLED)

        self._poll_job = self.root.after(100, self._poll_log)

    def _log(self, text: str) -> None:
        print(text, flush=True)

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
