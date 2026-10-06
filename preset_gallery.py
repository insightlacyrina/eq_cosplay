"""Compact vector-only preset gallery for EQ Cosplay.

This module is intentionally self-contained so the Tk view can be embedded as a
bottom drawer or used as a narrow standalone pane.
"""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from queue import Empty, Queue
from threading import RLock
from tkinter import BOTH, LEFT, RIGHT, X, Y, Canvas, Frame, Label, Scrollbar

import numpy as np

import cosplay as cp
import theme as ui_theme
import vector_icons


_CACHE_LIMIT = 64
_RESPONSE_CACHE: OrderedDict[tuple[str, int, int, tuple[tuple[str, int, int], ...]], dict] = OrderedDict()
_CACHE_LOCK = RLock()
_COPY = {
    "en": {
        "title": "PRESET LIBRARY", "refresh": "Refresh", "empty": "No saved presets",
        "load": "LOAD", "active": "ACTIVE", "delete": "DELETE", "details": "DETAILS",
        "hide": "HIDE", "fir": "FIR", "peq": "PEQ", "taps": "taps",
        "rmse": "RMSE", "combined": "combined", "missing": "FIR file missing",
        "no_eq": "Filter data unavailable", "preset": "Preset", "no_metrics": "No saved metrics",
        "loading": "Preparing response", "no_curve": "No response data", "curve": "COMPENSATION · dB",
        "active_fir": "active", "saved_fir": "saved",
    },
    "zh": {
        "title": "本地方案", "refresh": "刷新", "empty": "暂无已保存方案",
        "load": "载入", "active": "使用中", "delete": "删除", "details": "详情",
        "hide": "收起", "fir": "FIR", "peq": "PEQ", "taps": "抽头",
        "rmse": "误差", "combined": "综合", "missing": "FIR 文件缺失",
        "no_eq": "滤波器信息不可用", "preset": "方案", "no_metrics": "无保存指标",
        "loading": "正在读取响应", "no_curve": "无响应数据", "curve": "补偿响应 · dB",
        "active_fir": "启用", "saved_fir": "已保存",
    },
    "ja": {
        "title": "プリセット", "refresh": "更新", "empty": "保存済みのプリセットはありません",
        "load": "読込", "active": "使用中", "delete": "削除", "details": "詳細",
        "hide": "閉じる", "fir": "FIR", "peq": "PEQ", "taps": "タップ",
        "rmse": "誤差", "combined": "合成", "missing": "FIR ファイルなし",
        "no_eq": "フィルター情報なし", "preset": "プリセット", "no_metrics": "保存済み指標なし",
        "loading": "応答を読み込み中", "no_curve": "応答データなし", "curve": "補正応答 · dB",
        "active_fir": "有効", "saved_fir": "保存済み",
    },
}


def _language() -> str:
    code = str(getattr(cp, "LANG", "en")).lower()
    return code if code in _COPY else "en"


def _label(path: Path) -> tuple[str, str, str]:
    """Return source, target, and a readable pair from the saved filename."""
    stem = path.stem
    if stem.startswith("cosplay_"):
        stem = stem[len("cosplay_"):]
    parts = stem.split("_to_", 1)
    if len(parts) != 2:
        return "", "", stem.replace("_", " ")

    def readable(value: str) -> str:
        # Filenames include a provider suffix after the last underscore. Keep it
        # visible as provenance instead of pretending it is part of the model.
        return value.replace("_", " ").strip()

    source, target = readable(parts[0]), readable(parts[1])
    return source, target, f"{source}  →  {target}"


def _cache_key(path: Path) -> tuple[str, int, int, tuple[tuple[str, int, int], ...]]:
    resolved = path.resolve()
    st = resolved.stat()
    companions = []
    try:
        left, right = cp.companion_fir_wav_paths(resolved)
        for wav in (left, right):
            try:
                wst = wav.stat()
                companions.append((str(wav.resolve()), wst.st_mtime_ns, wst.st_size))
            except OSError:
                companions.append((str(wav.resolve()), 0, 0))
    except Exception:
        pass
    return str(resolved), st.st_mtime_ns, st.st_size, tuple(companions)


def _preset_data(path: Path) -> dict:
    """Read actual saved PEQ/FIR data and memoize it by config/WAV file state."""
    try:
        key = _cache_key(path)
    except OSError:
        return {"bands": [], "response": None, "fir_taps": None, "fir_missing": False, "metrics": {}, "metadata": {}}
    with _CACHE_LOCK:
        cached = _RESPONSE_CACHE.get(key)
        if cached is not None:
            _RESPONSE_CACHE.move_to_end(key)
            return cached

    bands: list[dict] = []
    sample_rate = 48000
    try:
        config = cp.parse_camilladsp_config_for_regen(path)
        if config:
            bands = list(config.get("peq") or [])
            sample_rate = int(config.get("samplerate") or sample_rate)
    except Exception:
        pass

    response = None
    uses_fir = False
    fir_ir = None
    fir_sr = None
    try:
        uses_fir = bool(cp.config_uses_fir_conv(path))
    except Exception:
        pass
    if bands:
        try:
            freqs = np.logspace(np.log10(20.0), np.log10(min(20000.0, sample_rate * 0.48)), 180)
            normalized = [
                {"type": b["filter_type"], "frequency": float(b["frequency"]),
                 "gain": float(b["gain"]), "Q": float(b["Q"])}
                for b in bands
            ]
            total = cp.peq_response_db(freqs, normalized, sample_rate)
            if uses_fir:
                fir_ir, fir_sr = cp.load_fir_ir_from_companion_wavs(path)
                if fir_ir is not None and fir_sr:
                    total = total + cp.fir_response_db(freqs, np.asarray(fir_ir, dtype=float), float(fir_sr))
            response = (freqs, total)
        except Exception:
            response = None

    fir_taps = None
    fir_missing = False
    try:
        left, right = cp.companion_fir_wav_paths(path)
        available = cp.config_has_companion_fir_wavs(path)
        if uses_fir and available:
            if fir_ir is None:
                fir_ir, fir_sr = cp.load_fir_ir_from_companion_wavs(path)
            if fir_ir is not None:
                fir_taps = int(np.asarray(fir_ir).size)
        elif uses_fir:
            fir_missing = True
        elif left.exists() or right.exists():
            # Companion files indicate an optional FIR even when current YAML
            # does not route through it. Report the asset's measured tap count.
            fir_ir, fir_sr = cp.load_fir_ir_from_companion_wavs(path)
            if fir_ir is not None:
                fir_taps = int(np.asarray(fir_ir).size)
    except Exception:
        pass

    try:
        metrics = cp.load_config_metrics(path) or {}
    except Exception:
        metrics = {}
    metadata = {}
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(16):
                line = handle.readline()
                if not line:
                    break
                if line.strip().startswith("# eq_cosplay_meta:"):
                    raw = line.strip().split(":", 1)[1].strip()
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        metadata = parsed
                    break
                if line.strip() and not line.lstrip().startswith("#"):
                    break
    except Exception:
        pass
    result = {"bands": bands, "response": response, "fir_taps": fir_taps,
              "fir_missing": fir_missing, "fir_active": uses_fir,
              "metrics": metrics, "metadata": metadata}
    with _CACHE_LOCK:
        _RESPONSE_CACHE[key] = result
        while len(_RESPONSE_CACHE) > _CACHE_LIMIT:
            _RESPONSE_CACHE.popitem(last=False)
    return result


class PresetGallery(Frame):
    """Scrollable preset cards with genuine PEQ response miniatures."""

    def __init__(self, parent, fonts: dict, on_load=None, on_delete=None, on_refresh=None):
        super().__init__(parent, bg=ui_theme.PANEL, highlightthickness=1,
                         highlightbackground=ui_theme.BORDER)
        self.fonts = fonts
        self.on_load, self.on_delete, self.on_refresh = on_load, on_delete, on_refresh
        self.presets: list[Path] = []
        self._active_path: Path | None = None
        self._selected = 0
        self._details_path: Path | None = None
        self._rows: dict[str, dict] = {}
        self._generation = 0
        self._pending: set[tuple[int, str]] = set()
        self._result_queue: Queue = Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preset-preview")
        self._poll_job = None
        self._columns = 1
        self._destroyed = False
        self._lang = _language()
        self._build()
        self.bind("<Up>", self._move_selection)
        self.bind("<Down>", self._move_selection)
        self.bind("<Left>", self._move_selection)
        self.bind("<Right>", self._move_selection)
        self.bind("<Return>", self._load_selected)
        self.bind("<Delete>", self._delete_selected)
        self.bind("<BackSpace>", self._delete_selected)
        self.bind("<Map>", lambda _event: self.after_idle(self._request_visible))
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _t(self, key: str) -> str:
        return _COPY[self._lang][key]

    def _build(self) -> None:
        header = Frame(self, bg=ui_theme.PANEL)
        header.pack(fill=X, padx=9, pady=(6, 4))
        self.lbl_title = Label(header, text=self._t("title"), bg=ui_theme.PANEL,
                               fg=ui_theme.TEXT, font=self.fonts["ui10"], anchor="w")
        self.lbl_title.pack(side=LEFT)
        self._count = Label(header, text="", bg=ui_theme.PANEL, fg=ui_theme.MUTED,
                            font=self.fonts["mono9"])
        self._count.pack(side=LEFT, padx=(7, 0))
        self._refresh = Canvas(header, width=26, height=24, bg=ui_theme.BTN,
                               highlightthickness=1, highlightbackground=ui_theme.BORDER_SUBTLE,
                               cursor="hand2")
        self._refresh.pack(side=RIGHT)
        vector_icons.draw_icon(self._refresh, "refresh", 3, 2, 18, ui_theme.MUTED)
        self._refresh.bind("<Button-1>", lambda _e: self._refresh_click())
        self._refresh.bind("<Enter>", lambda _e: self._refresh.configure(bg=ui_theme.BTN_HOVER))
        self._refresh.bind("<Leave>", lambda _e: self._refresh.configure(bg=ui_theme.BTN))

        body = Frame(self, bg=ui_theme.PANEL)
        body.pack(fill=BOTH, expand=True, padx=5, pady=(0, 5))
        self.canvas = Canvas(body, bg=ui_theme.PANEL, highlightthickness=0, bd=0,
                             yscrollcommand=self._on_scroll)
        self.scrollbar = Scrollbar(body, orient="vertical", command=self.canvas.yview,
                                   troughcolor=ui_theme.PANEL, bg=ui_theme.PANEL_GLASS,
                                   activebackground=ui_theme.BORDER_SPECULAR,
                                   highlightthickness=0, width=8)
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self._content = Frame(self.canvas, bg=ui_theme.PANEL)
        self._window = self.canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind("<Configure>", self._sync_scroll)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"))
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _button(self, parent, text, callback, compact=False, primary=False, destructive=False):
        bg = ui_theme.PRIMARY_BG if primary else ui_theme.BTN
        fg = ui_theme.PRIMARY_FG if primary else ui_theme.MUTED
        rim = ui_theme.PRIMARY_LINE if primary else ui_theme.BORDER_SUBTLE
        button = Label(parent, text=text, bg=bg, fg=fg,
                       font=self.fonts["mono9"], padx=6 if compact else 7, pady=2,
                       cursor="hand2", takefocus=1, highlightthickness=1,
                       highlightbackground=rim)
        button.bind("<Button-1>", lambda _e: callback())
        button.bind("<Return>", lambda _e: callback())
        button.bind("<space>", lambda _e: callback())
        button._industrial_hover = False
        button._industrial_focus = False
        hover_bg = ui_theme.PRIMARY_HOVER if primary else ui_theme.BTN_HOVER
        hover_fg = ui_theme.PRIMARY_FG if primary else (ui_theme.ROSE if destructive else ui_theme.TEXT)
        def update_state():
            emphasized = button._industrial_hover or button._industrial_focus
            button.configure(fg=hover_fg if emphasized else fg,
                             bg=hover_bg if emphasized else bg,
                             highlightbackground=ui_theme.FOCUS if emphasized else rim)
        button.bind("<Enter>", lambda _e: (setattr(button, "_industrial_hover", True), update_state()))
        button.bind("<Leave>", lambda _e: (setattr(button, "_industrial_hover", False), update_state()))
        button.bind("<FocusIn>", lambda _e: (setattr(button, "_industrial_focus", True), update_state()))
        button.bind("<FocusOut>", lambda _e: (setattr(button, "_industrial_focus", False), update_state()))
        return button

    def _refresh_click(self):
        if self.on_refresh:
            self.on_refresh()

    def _sync_scroll(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._request_visible()

    def _on_scroll(self, first, last):
        self.scrollbar.set(first, last)
        self._request_visible()

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        columns = 2 if event.width >= 650 else 1
        if columns != self._columns:
            self._columns = columns
            for column in range(2):
                self._content.columnconfigure(column, weight=0, uniform="")
            for index, record in enumerate(self._rows.values()):
                record["card"].grid_configure(row=index // columns, column=index % columns)
            for column in range(columns):
                self._content.columnconfigure(column, weight=1, uniform="preset-card")
        self._request_visible()

    def _wheel(self, event):
        delta = getattr(event, "delta", 0)
        self.canvas.yview_scroll(-1 if delta > 0 else 1, "units")
        return "break"

    def set_presets(self, presets: list[Path], active_path: Path | None = None) -> None:
        self._generation += 1
        self._pending.clear()
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        self.presets = [Path(p) for p in presets]
        self._active_path = Path(active_path) if active_path else None
        self._selected = min(self._selected, max(0, len(self.presets) - 1))
        self._details_path = None
        self._rows.clear()
        self._draw_detail = {}
        for child in self._content.winfo_children():
            child.destroy()
        self._count.configure(text=str(len(self.presets)))
        if not self.presets:
            Label(self._content, text=self._t("empty"), bg=ui_theme.PANEL,
                  fg=ui_theme.MUTED, font=self.fonts["ui10"]).pack(pady=24)
            return
        for column in range(self._columns):
            self._content.columnconfigure(column, weight=1, uniform="preset-card")
        for index, path in enumerate(self.presets):
            self._make_card(path, index)
        self._refresh_selection()
        self.after_idle(self._request_visible)

    def _is_active(self, path: Path) -> bool:
        try:
            return self._active_path is not None and path.resolve() == self._active_path.resolve()
        except Exception:
            return False

    def _make_card(self, path: Path, index: int):
        _source, _target, name = _label(path)
        active = self._is_active(path)
        base = ui_theme.SLOT if active else ui_theme.PANEL_GLASS
        card = Frame(self._content, bg=base, highlightthickness=1,
                     highlightbackground=ui_theme.PLOT_TGT if active else ui_theme.BORDER_SUBTLE)
        card.grid(row=index // self._columns, column=index % self._columns,
                  sticky="ew", padx=3, pady=3)
        card.columnconfigure(0, weight=1)
        headline = Frame(card, bg=base)
        headline.pack(fill=X, padx=8, pady=(5, 2))
        name_label = Label(headline, text=name, bg=base, fg=ui_theme.TEXT,
                           font=self.fonts["ui10"], anchor="w")
        name_label.pack(side=LEFT, fill=X, expand=True)
        badge = Label(headline, text=self._t("active") if active else "",
                      bg=ui_theme.PRIMARY_BG if active else base,
                      fg=ui_theme.TEXT if active else ui_theme.MUTED,
                      font=self.fonts["mono9"], padx=4)
        if active:
            badge.pack(side=RIGHT, padx=(3, 0))

        plot = Canvas(card, height=43, bg=ui_theme.PLOT_FACE,
                      highlightthickness=1, highlightbackground=ui_theme.BORDER_SUBTLE)
        plot.pack(fill=X, padx=8, pady=(0, 3))
        plot.bind("<Configure>", lambda _e, c=plot, k=str(path): self._redraw_card(k, "plot", c))
        meta = Frame(card, bg=base)
        meta.pack(fill=X, padx=8, pady=(0, 5))
        info_label = Label(meta, text=self._t("loading"), bg=base, fg=ui_theme.MUTED,
                           font=self.fonts["mono9"], anchor="w")
        info_label.pack(side=LEFT, fill=X, expand=True)
        metric_label = Label(meta, text="", bg=base, fg=ui_theme.MUTED,
                             font=self.fonts["mono9"], anchor="e")
        metric_label.pack(side=LEFT, padx=(6, 8))
        actions = Frame(meta, bg=base)
        actions.pack(side=RIGHT)
        self._button(actions, self._t("load"), lambda p=path: self._load(p), primary=True).pack(anchor="e", pady=(0, 2))
        self._button(actions, self._t("delete"), lambda p=path: self._delete(p), compact=True, destructive=True).pack(anchor="e", pady=(0, 2))
        self._button(actions, self._t("details"), lambda p=path: self._toggle_details(p), compact=True).pack(anchor="e")

        detail = Frame(card, bg=ui_theme.PANEL, highlightthickness=1,
                       highlightbackground=ui_theme.BORDER_SUBTLE)
        detail_name = Label(detail, text=name, bg=ui_theme.PANEL, fg=ui_theme.TEXT,
                            font=self.fonts["ui10"], anchor="w")
        detail_name.pack(fill=X, padx=7, pady=(6, 2))
        detail_plot = Canvas(detail, height=76, bg=ui_theme.PLOT_FACE,
                             highlightthickness=1, highlightbackground=ui_theme.BORDER_SUBTLE)
        detail_plot.pack(fill=X, padx=7, pady=3)
        detail_plot.bind("<Configure>", lambda _e, c=detail_plot, k=str(path): self._redraw_card(k, "detail_plot", c))
        detail_info = Label(detail, text="", bg=ui_theme.PANEL, fg=ui_theme.MUTED,
                            font=self.fonts["mono9"], anchor="w", justify=LEFT, wraplength=820)
        detail_info.pack(fill=X, padx=7, pady=(1, 6))
        row = {"card": card, "plot": plot, "active": active, "index": index,
               "info": info_label, "metrics": metric_label, "detail": detail,
               "detail_plot": detail_plot, "detail_info": detail_info,
               "name_label": name_label, "detail_name": detail_name, "name": name,
               "data": None, "requested": False, "path": path}
        self._rows[str(path)] = row
        card.bind("<Button-1>", lambda _e, i=index: self._select(i))
        name_label.bind("<Button-1>", lambda _e, i=index: self._select(i))
        plot.bind("<Button-1>", lambda _e, i=index: self._select(i))
        self._bind_wheel_tree(card)
        self._draw_detail[str(path)] = row

    def _draw_response(self, canvas: Canvas, response):
        canvas.delete("all")
        width = max(20, canvas.winfo_width())
        height = max(20, canvas.winfo_height())
        canvas.create_text(7, 5, text=self._t("curve"), fill=ui_theme.MUTED,
                           font=self.fonts["mono9"], anchor="nw")
        for y in (height * .33, height * .66):
            canvas.create_line(1, y, width - 1, y, fill=ui_theme.PLOT_GRID, width=1)
        for x in (width * .25, width * .5, width * .75):
            canvas.create_line(x, 1, x, height - 1, fill=ui_theme.PLOT_GRID, width=1)
        canvas.create_line(1, height / 2, width - 1, height / 2,
                           fill=ui_theme.BORDER_SPECULAR, width=1)
        if response is None:
            canvas.create_text(width / 2, height / 2 + 5, text=self._t("no_curve"), fill=ui_theme.MUTED,
                               font=self.fonts["mono9"])
            return
        _freqs, vals = response
        vals = np.asarray(vals, dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size < 2:
            return
        limit = max(3.0, float(np.ceil(np.max(np.abs(vals)) / 3.0) * 3.0))
        pad_x, pad_y = 5, 5
        points = []
        for i, value in enumerate(vals):
            x = pad_x + i * (width - pad_x * 2 - 1) / max(1, len(vals) - 1)
            y = height / 2 - np.clip(float(value), -limit, limit) / limit * (height / 2 - pad_y)
            points.extend((x, y))
        if len(points) >= 4:
            canvas.create_line(*points, fill=ui_theme.PLOT_TGT, width=1.6, smooth=True,
                               splinesteps=16, capstyle="round", joinstyle="round")

    def _redraw_card(self, key, field, canvas):
        record = self._rows.get(key)
        response = (record.get("data") or {}).get("response") if record else None
        self._draw_response(canvas, response)

    def _request_visible(self):
        if self._destroyed or not self.presets or not self.winfo_ismapped():
            return
        try:
            top = self.canvas.canvasy(0)
            bottom = top + max(1, self.canvas.winfo_height())
            margin = max(80, self.canvas.winfo_height() * .7)
        except Exception:
            return
        for key, record in self._rows.items():
            if record["requested"]:
                continue
            card = record["card"]
            try:
                y0 = card.winfo_y()
                y1 = y0 + max(1, card.winfo_height())
            except Exception:
                continue
            if y1 < top - margin or y0 > bottom + margin:
                continue
            record["requested"] = True
            generation = self._generation
            self._pending.add((generation, key))
            future = self._executor.submit(_preset_data, record["path"])
            future.add_done_callback(lambda done, gen=generation, item=key:
                                     self._queue_result(gen, item, done))
        self._ensure_poll()

    def _queue_result(self, generation, key, future):
        try:
            result, error = future.result(), None
        except BaseException as exc:
            result, error = None, exc
        self._result_queue.put((generation, key, result, error))

    def _ensure_poll(self):
        if self._pending and self._poll_job is None and not self._destroyed:
            self._poll_job = self.after(45, self._poll_results)

    def _poll_results(self):
        self._poll_job = None
        while True:
            try:
                generation, key, data, error = self._result_queue.get_nowait()
            except Empty:
                break
            self._pending.discard((generation, key))
            if self._destroyed or generation != self._generation:
                continue
            record = self._rows.get(key)
            if record is None:
                continue
            if error is not None:
                data = {"bands": [], "response": None, "fir_taps": None,
                        "fir_missing": False, "fir_active": False,
                        "metrics": {}, "metadata": {}}
            self._apply_data(record, data)
        if self._pending and not self._destroyed:
            self._poll_job = self.after(70, self._poll_results)

    def _apply_data(self, record, data):
        record["data"] = data
        metadata = data.get("metadata") or {}
        source = str(metadata.get("source_model") or "").strip()
        target = str(metadata.get("target_model") or "").strip()
        if source and target:
            name = f"{source}  →  {target}"
            record["name"] = name
            record["name_label"].configure(text=name)
            record["detail_name"].configure(text=name)
        response = data.get("response")
        self._draw_response(record["plot"], response)
        self._draw_response(record["detail_plot"], response)
        if data.get("fir_taps") is not None:
            fir_txt = f"{self._t('fir')} · {data['fir_taps']} {self._t('taps')}"
        elif data.get("fir_missing"):
            fir_txt = self._t("missing")
        else:
            fir_txt = ""
        bands = data.get("bands") or []
        peq_txt = f"{len(bands)} {self._t('peq')}" if bands else self._t("no_eq")
        record["info"].configure(text="  ·  ".join(v for v in (peq_txt, fir_txt) if v))
        metrics = data.get("metrics") or {}
        metric_parts = []
        if metrics.get("peq_rmse") is not None:
            metric_parts.append(f"PEQ {float(metrics['peq_rmse']):.2f} dB")
        if metrics.get("combined_rmse") is not None and data.get("fir_active"):
            metric_parts.append(f"{self._t('combined')} {float(metrics['combined_rmse']):.2f} dB")
        record["metrics"].configure(text="  ·  ".join(metric_parts) if metric_parts else self._t("no_metrics"))
        details = [f"PEQ bands: {len(bands)}"]
        src_provider = str(metadata.get("source_provider") or "").strip()
        tgt_provider = str(metadata.get("target_provider") or "").strip()
        if src_provider or tgt_provider:
            details.append(f"Providers: {src_provider or '—'} → {tgt_provider or '—'}")
        details.append("FIR: " + (f"{data['fir_taps']} taps ({self._t('active_fir') if data.get('fir_active') else self._t('saved_fir')})" if data.get("fir_taps") is not None
                                   else (self._t("missing") if data.get("fir_missing") else "not configured")))
        for metric, title in (("peq_rmse", "PEQ RMSE"), ("fir_rmse", "FIR RMSE"),
                              ("combined_rmse", "Combined RMSE"), ("level_offset_db", "Level offset")):
            if metrics.get(metric) is not None:
                details.append(f"{title}: {float(metrics[metric]):.2f} dB")
        record["detail_info"].configure(text="  ·  ".join(details))

    def _bind_wheel_tree(self, widget):
        widget.bind("<MouseWheel>", self._wheel, add="+")
        widget.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"), add="+")
        widget.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"), add="+")
        for child in widget.winfo_children():
            self._bind_wheel_tree(child)

    def _toggle_details(self, path: Path):
        if self._details_path == path:
            self._details_path = None
        else:
            self._details_path = path
        for key, record in self._rows.items():
            if key == str(self._details_path):
                record["detail"].pack(fill=X, padx=7, pady=(0, 6))
            else:
                record["detail"].pack_forget()
        self._sync_scroll()

    def _select(self, index):
        self._selected = index
        self.focus_set()
        self._refresh_selection()

    def _refresh_selection(self):
        for index, path in enumerate(self.presets):
            row = self._rows.get(str(path))
            if not row:
                continue
            card, active = row["card"], row["active"]
            selected = index == self._selected
            card.configure(highlightbackground=ui_theme.FOCUS if selected else ui_theme.PLOT_TGT if active else ui_theme.BORDER_SUBTLE)
            card.configure(highlightthickness=2 if selected else 1)

    def _move_selection(self, event):
        if not self.presets:
            return
        step = self._columns if event.keysym in ("Up", "Down") else 1
        if event.keysym in ("Up", "Left"):
            self._selected = max(0, self._selected - step)
        elif event.keysym in ("Down", "Right"):
            self._selected = min(len(self.presets) - 1, self._selected + step)
        else:
            return
        self._refresh_selection()
        rows = max(1, (len(self.presets) + self._columns - 1) // self._columns)
        self.canvas.yview_moveto((self._selected // self._columns) / rows)
        self.after_idle(self._request_visible)
        return "break"

    def _selected_path(self):
        return self.presets[self._selected] if self.presets else None

    def _load_selected(self, _event=None):
        path = self._selected_path()
        if path:
            self._load(path)
            return "break"

    def _delete_selected(self, _event=None):
        path = self._selected_path()
        if path:
            if self.on_delete:
                self.on_delete(path)
            return "break"

    def _load(self, path):
        if self.on_load:
            self.on_load(path)

    def _delete(self, path):
        if self.on_delete:
            self.on_delete(path)

    def _on_destroy(self, event):
        if event.widget is self:
            self._destroyed = True
            if self._poll_job is not None:
                try:
                    self.after_cancel(self._poll_job)
                except Exception:
                    pass
                self._poll_job = None
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _collapse_expanded(self, immediate: bool = False) -> None:
        """Compatibility hook for the previous gallery's expanded overlay."""
        self._details_path = None
        for key in list(getattr(self, "_draw_detail", {})):
            detail = self._draw_detail[key]["detail"]
            try:
                detail.pack_forget()
            except Exception:
                pass

    def refresh_language(self):
        self._lang = _language()
        self.lbl_title.configure(text=self._t("title"))
        self.set_presets(self.presets, self._active_path)


# Compatibility for the GUI's existing import site during migration.
PresetsLibraryView = PresetGallery
