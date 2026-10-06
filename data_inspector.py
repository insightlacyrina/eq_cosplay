"""Exact response table and full-resolution CSV export, separate from rendering."""
from __future__ import annotations

from tkinter import BooleanVar, Frame, Label, StringVar, Toplevel, filedialog, messagebox, ttk

import cosplay as cp
import theme as theme
from visual_data import build_response, export_response_csv


_COPY = {
    "zh": ("精确频响数据", "原始目标电平", "导出完整 CSV", "频率 Hz", "当前 dB", "目标 dB", "模拟 dB", "残差 dB",
           "完整计算网格 · 残差 = 目标 − 模拟 · 不是实时测量", "目标已按参考频带对齐", "目标原始测量电平", "暂无频响数据"),
    "en": ("Exact response data", "Original target level", "Export full CSV", "Frequency Hz", "Source dB", "Target dB", "Simulated dB", "Residual dB",
           "Full calculation grid · residual = target − simulated · not a live measurement", "Target aligned to reference band", "Original target measurement level", "No response data yet"),
    "ja": ("正確な周波数データ", "目標の元のレベル", "全データをCSV出力", "周波数 Hz", "現在 dB", "目標 dB", "模擬 dB", "残差 dB",
           "全計算グリッド · 残差 = 目標 − 模擬 · リアルタイム測定ではありません", "目標は基準帯域で整列済み", "目標の元の測定レベル", "データはまだありません"),
}
_MODE_LABELS = {
    "zh": {"eq": "频率响应", "comp": "补偿"},
    "en": {"eq": "Response", "comp": "Compensation"},
    "ja": {"eq": "周波数応答", "comp": "補正"},
}


class ResponseInspector:
    """Own one reusable nonmodal window; never read audio or change DSP state."""

    def __init__(self, parent, fonts):
        self.parent = parent
        self.fonts = fonts
        self.window = None
        self.correction = None
        self.mode = "eq"

    def set_data(self, correction, mode="eq"):
        self.correction = correction
        self.mode = mode if mode in ("eq", "comp") else "eq"
        if self.window is not None and self.window.winfo_exists():
            self.view_mode.set(self._mode_label(self.mode))
            self._populate()

    def _language(self):
        return cp.LANG if cp.LANG in _COPY else "en"

    def _mode_label(self, mode):
        return _MODE_LABELS[self._language()][mode]

    def _selected_mode(self):
        labels = _MODE_LABELS[self._language()]
        return next((mode for mode, label in labels.items() if label == self.view_mode.get()), self.mode)

    def show(self, correction=None, mode="eq"):
        self.set_data(correction, mode)
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return
        self.window = Toplevel(self.parent)
        self.window.configure(bg=theme.BG)
        self.window.geometry("900x570")
        self.window.minsize(740, 430)
        self.window.transient(self.parent)
        self.raw = BooleanVar(self.window, value=False)
        self.view_mode = StringVar(self.window, value=self._mode_label(self.mode))
        top = Frame(self.window, bg=theme.BG, padx=16, pady=12)
        top.pack(fill="x")
        title_font = self.fonts.get("subhead", self.fonts.get("ui14", (theme.ui_family(), 13)))
        self.title = Label(top, bg=theme.BG, fg=theme.TEXT, font=title_font)
        self.title.pack(side="left")
        self.export = ttk.Button(top, command=self._export, style="Primary.TButton")
        self.export.pack(side="right")
        options = Frame(self.window, bg=theme.BG, padx=16)
        options.pack(fill="x", pady=(0, 6))
        self.mode_box = ttk.Combobox(options, textvariable=self.view_mode,
                                     values=tuple(_MODE_LABELS[self._language()].values()),
                                     state="readonly", width=16)
        self.mode_box.pack(side="left", padx=(0, 12))
        self.mode_box.bind("<<ComboboxSelected>>", lambda _e: self._populate())
        self.raw_check = ttk.Checkbutton(options, variable=self.raw, command=self._populate)
        self.raw_check.pack(side="left")
        self.note = Label(self.window, bg=theme.BG, fg=theme.MUTED, font=self.fonts["ui10"], anchor="w", padx=16, pady=8)
        self.note.pack(fill="x")
        box = Frame(self.window, bg=theme.PANEL)
        box.pack(fill="both", expand=True, padx=16)
        columns = ("freq", "source", "target", "simulated", "residual")
        self.tree = ttk.Treeview(box, columns=columns, show="headings", selectmode="browse", style="Numeric.Treeview")
        widths = {"freq": 142, "source": 142, "target": 142, "simulated": 142, "residual": 142}
        for name in columns:
            self.tree.column(name, anchor="e", width=widths[name], minwidth=96, stretch=True)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.foot = Label(self.window, bg=theme.BG, fg=theme.MUTED, font=self.fonts["ui10"], anchor="w", padx=16, pady=10)
        self.foot.pack(fill="x")
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self.refresh_language()

    def refresh_language(self):
        if self.window is None or not self.window.winfo_exists():
            return
        language = self._language()
        copy = _COPY[language]
        self.view_mode.set(self._mode_label(self.mode))
        self.mode_box.configure(values=tuple(_MODE_LABELS[language].values()))
        self.window.title(copy[0])
        self.title.configure(text=copy[0])
        self.export.configure(text=copy[2])
        self.raw_check.configure(text=copy[1])
        for column, text in zip(self.tree["columns"], copy[3:8]):
            self.tree.heading(column, text=text)
        self.foot.configure(text=copy[8])
        self._populate()

    def _populate(self):
        if self.window is None or not self.window.winfo_exists():
            return
        copy = _COPY.get(self._language(), _COPY["en"])
        corr = self.correction or {}
        aligned = build_response(corr)
        raw_available = aligned.target_available and (corr.get("target_raw_fr") is not None or aligned.level_offset_db is not None)
        self.raw_check.configure(state="normal" if raw_available else "disabled")
        if not raw_available:
            self.raw.set(False)
        self.mode = self._selected_mode()
        data = build_response(corr, self.mode, self.raw.get())
        self.tree.delete(*self.tree.get_children())
        for i, freq in enumerate(data.freqs):
            def value(values, available=True):
                if not available or not len(values):
                    return "—"
                import math
                return f"{values[i]:+.4f}" if math.isfinite(values[i]) else "—"
            self.tree.insert("", "end", values=(f"{freq:.4f}", value(data.source, data.source_available),
                                               value(data.target), value(data.simulated), value(data.residual)))
        basis = copy[10] if self.raw.get() else copy[9]
        self.note.configure(text=f"{basis} · {len(data.freqs)} samples · {'IIR + FIR' if data.use_fir else 'IIR'}" if len(data.freqs) else copy[11])
        self.export.configure(state="normal" if len(data.freqs) else "disabled")

    def _export(self):
        if self.correction is None:
            return
        path = filedialog.asksaveasfilename(parent=self.window, title=_COPY[self._language()][2],
                                          defaultextension=".csv", initialfile="eq-cosplay-response.csv", filetypes=(("CSV", "*.csv"),))
        if path:
            try:
                export_response_csv(path, self.correction, self.mode, self.raw.get())
            except OSError as error:
                messagebox.showerror("EQ Cosplay", str(error), parent=self.window)
