"""Data-driven Tk sound stage for EQ Cosplay.

The widget deliberately keeps its drawing surface quiet: the grid is rebuilt only
when its geometry changes, while response curves are retained canvas items.  It
uses ``visual_data`` as the shared response model for all plotted values.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import Canvas, Frame, Label
from time import perf_counter

import numpy as np
import theme as ui_theme
import cosplay as cp
from visual_data import build_response, display_indices


class FrequencyResponsePlot(Frame):
    """A logarithmic, interactive response stage with a retained Tk canvas."""

    F_MIN, F_MAX = 20.0, 20000.0
    LOG_SPAN = math.log10(1000.0)
    COLORS = {
        "source": ui_theme.PLOT_SRC, "target": ui_theme.PLOT_TGT,
        "sim": ui_theme.PLOT_SIM, "residual": ui_theme.PLOT_DELTA,
        "grid": ui_theme.PLOT_GRID, "axis": ui_theme.MUTED,
        "face": ui_theme.PLOT_FACE, "panel": ui_theme.PANEL,
        "rim": ui_theme.BORDER, "muted": ui_theme.MUTED,
        "text": ui_theme.TEXT, "lens": ui_theme.GOLD,
        "quiet": ui_theme.BORDER_SUBTLE, "highlight": ui_theme.BORDER_SPECULAR,
    }

    @staticmethod
    def _mix_color(foreground, background, amount):
        """Return a quiet Tk-compatible blend for the membrane underlay."""
        try:
            fg = tuple(int(foreground[i:i + 2], 16) for i in (1, 3, 5))
            bg = tuple(int(background[i:i + 2], 16) for i in (1, 3, 5))
            return "#" + "".join(f"{round(b + (f-b)*amount):02x}" for f, b in zip(fg, bg))
        except (TypeError, ValueError, IndexError):
            return background

    def __init__(self, parent, fonts: dict):
        super().__init__(parent, bg=ui_theme.PANEL, highlightthickness=1,
                         highlightbackground=ui_theme.BORDER,
                         highlightcolor=ui_theme.BORDER_SPECULAR)
        self.fonts = fonts
        self.result_data = None
        self.response = None
        self.mode = "eq"
        self._t_fn = None
        self._activity = ""
        self._source_name = ""
        self._target_name = ""
        self._selected_band = None
        self.on_band_selected = None
        self._motion_enabled = True
        self._quality = "auto"
        self._after_ids = set()
        self._resize_job = None
        self._hover_job = None
        self._animation_job = None
        self._animation_deadline = None
        self._last_animation_tick = None
        self._slow_frame = False
        self._destroyed = False
        self._layout = None
        self._coords = {}
        self._hover_freq = None
        self._display_data = None
        self._frame_data = None
        self._transition = None
        self._suppress_morph_once = False
        self._last_pointer = None
        self._empty = False
        self._base_range = (-15.0, 15.0)
        self.view_style = "membrane"
        self._range_locked = True
        self._locked_ranges = {}
        self.frame_stats = {"frame_ms": 0.0, "points": 0}
        self._node_items = {}
        self._ribbon_items = {}
        self._ribbon_rule_items = {}
        self._residual_item = None
        self._resid_strip_item = None
        self._lens_items = {}
        self._band_response_cache = {}

        self._make_header()
        self.canvas = Canvas(self, bg=self.COLORS["face"], bd=0,
                             highlightthickness=0, takefocus=True)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Destroy>", self._on_canvas_destroy, add="+")
        self._sync_controls()
        self._update_mode_label()

    def _font(self, key, fallback):
        return self.fonts.get(key, fallback)

    def _make_header(self):
        self.header = Frame(self, bg=ui_theme.PANEL)
        self.header.pack(fill=tk.X, padx=14, pady=(11, 7))
        self.headline = Frame(self.header, bg=ui_theme.PANEL)
        self.headline.pack(fill=tk.X)
        self.controls = Frame(self.header, bg=ui_theme.PANEL)
        self.controls.pack(fill=tk.X, pady=(7, 0))
        left = Frame(self.headline, bg=ui_theme.PANEL)
        left.pack(side=tk.LEFT, fill=tk.Y)
        self.lbl_mode_title = Label(left, text="EQ", bg=ui_theme.PANEL,
                                    fg=self.COLORS["text"], font=self._font("ui11", ("Arial", 11, "bold")))
        self.lbl_mode_title.pack(side=tk.LEFT)
        self.btn_toggle_mode = Label(self.controls, text="", bg=ui_theme.BTN,
                                     fg=self.COLORS["muted"], padx=8, pady=4,
                                     font=self._font("ui9", ("Arial", 9)), cursor="hand2",
                                     takefocus=1,highlightthickness=1,highlightbackground=ui_theme.BORDER)
        self.btn_toggle_mode.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_toggle_mode.bind("<Button-1>", lambda _e: self.toggle_mode())
        self.btn_toggle_mode.bind("<Enter>", lambda _e: self.btn_toggle_mode.configure(fg=self.COLORS["text"]))
        self.btn_toggle_mode.bind("<Leave>", lambda _e: self.btn_toggle_mode.configure(fg=self.COLORS["muted"]))
        self.btn_toggle_mode.bind("<Return>", lambda _e: self._keyboard_toggle_mode())
        self.btn_toggle_mode.bind("<space>", lambda _e: self._keyboard_toggle_mode())
        self.btn_toggle_mode.bind("<FocusIn>", lambda _e: self.btn_toggle_mode.configure(highlightbackground=ui_theme.GOLD,fg=self.COLORS["text"]))
        self.btn_toggle_mode.bind("<FocusOut>", lambda _e: self.btn_toggle_mode.configure(highlightbackground=ui_theme.BORDER,fg=self.COLORS["muted"]))

        self.btn_view = Label(self.controls, text="", bg=ui_theme.BTN,
                              fg=self.COLORS["lens"], padx=8, pady=4,
                              font=self._font("ui9", ("Arial", 9)), cursor="hand2",
                              takefocus=1,highlightthickness=1,highlightbackground=ui_theme.BORDER)
        self.btn_view.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_view.bind("<Button-1>", lambda _e: self.set_view_style("flat" if self.view_style == "membrane" else "membrane"))
        self.btn_view.bind("<Return>", lambda _e: self._keyboard_toggle_view())
        self.btn_view.bind("<space>", lambda _e: self._keyboard_toggle_view())
        self.btn_view.bind("<FocusIn>", lambda _e: self.btn_view.configure(highlightbackground=ui_theme.GOLD))
        self.btn_view.bind("<FocusOut>", lambda _e: self.btn_view.configure(highlightbackground=ui_theme.BORDER))
        self.btn_lock = Label(self.controls, text="", bg=ui_theme.BTN,
                              fg=self.COLORS["lens"], padx=8, pady=4,
                              font=self._font("ui9", ("Arial", 9)), cursor="hand2",
                              takefocus=1,highlightthickness=1,highlightbackground=ui_theme.BORDER)
        self.btn_lock.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_lock.bind("<Button-1>", lambda _e: self.set_scale_locked(not self._range_locked))
        self.btn_lock.bind("<Return>", lambda _e: self._keyboard_toggle_lock())
        self.btn_lock.bind("<space>", lambda _e: self._keyboard_toggle_lock())
        self.btn_lock.bind("<FocusIn>", lambda _e: self.btn_lock.configure(highlightbackground=ui_theme.GOLD))
        self.btn_lock.bind("<FocusOut>", lambda _e: self.btn_lock.configure(highlightbackground=ui_theme.BORDER))
        self.stage_label = Label(self.headline, text="", bg=ui_theme.PANEL,
                                 fg=self.COLORS["muted"], font=self._font("ui9", ("Arial", 9)))
        self.stage_label.pack(side=tk.RIGHT)
        self.legend_box = Frame(self.headline, bg=ui_theme.PANEL)
        self.legend_box.pack(side=tk.RIGHT, padx=(8, 0))
        self.lbl_src = self._legend(self.legend_box, self.COLORS["source"], "Current")
        self.lbl_tgt = self._legend(self.legend_box, self.COLORS["target"], "Target")
        self.lbl_sim = self._legend(self.legend_box, self.COLORS["sim"], "Simulated")
        self.identity_label = Label(self.controls, text="", bg=ui_theme.PANEL,
                                    fg=self.COLORS["muted"], anchor="w", font=self._font("ui9", ("Arial", 9)))
        self.identity_label.pack(side=tk.RIGHT, padx=(8, 0))

    def _legend(self, parent, color, text):
        wrap = Frame(parent, bg=ui_theme.PANEL)
        wrap.pack(side=tk.LEFT, padx=(0, 10))
        Canvas(wrap, width=14, height=10, bg=ui_theme.PANEL, bd=0,
               highlightthickness=0).pack(side=tk.LEFT)
        marker = wrap.winfo_children()[0]
        marker.create_line(1, 5, 13, 5, fill=color, width=2)
        label = Label(wrap, text=text, bg=ui_theme.PANEL, fg=self.COLORS["muted"],
                      font=self._font("ui9", ("Arial", 9)))
        label.pack(side=tk.LEFT, padx=(5, 0))
        return label

    def toggle_mode(self):
        self.set_mode("comp" if self.mode == "eq" else "eq")

    def _keyboard_toggle_mode(self):
        self.toggle_mode();return "break"

    def _keyboard_toggle_view(self):
        self.set_view_style("flat" if self.view_style=="membrane" else "membrane");return "break"

    def _keyboard_toggle_lock(self):
        self.set_scale_locked(not self._range_locked);return "break"

    def _sync_controls(self):
        membrane=self.view_style=="membrane"
        self.btn_view.configure(text=self._control_text("plot_control_membrane" if membrane else "plot_control_flat",
                                                       "Membrane" if membrane else "Flat") + "  ✓",
                                fg=self.COLORS["lens"] if membrane else self.COLORS["text"])
        self.btn_lock.configure(text=self._control_text("plot_control_locked" if self._range_locked else "plot_control_auto",
                                                        "Range locked" if self._range_locked else "Auto range"),
                                fg=self.COLORS["lens"] if self._range_locked else self.COLORS["muted"])
        mode_key = "plot_control_response" if self.mode == "eq" else "plot_control_compensation"
        mode_fallback = "Response" if self.mode == "eq" else "Compensation"
        self.btn_toggle_mode.configure(text=self._control_text(mode_key, mode_fallback) + "  /  " +
                                       self._control_text("plot_control_compensation" if self.mode == "eq" else "plot_control_response",
                                                          "Compensation" if self.mode == "eq" else "Response") + "  ↗")

    def _control_text(self, key, fallback):
        if self._t_fn:
            try:
                value = self._t_fn(key)
                if value and value != key:
                    return value
            except Exception:
                pass
        return fallback

    def set_mode(self, mode: str):
        if mode not in ("eq", "comp") or mode == self.mode:
            return
        self.mode = mode
        self._update_mode_label()
        self._suppress_morph_once = True
        self.set_data(self.result_data)

    def _update_mode_label(self):
        t = self._t_fn
        mode_text = (t("plot_mode_comp") if t else "Compensation") if self.mode == "comp" else (t("plot_mode_eq") if t else "EQ response")
        self.lbl_mode_title.configure(text=mode_text)
        self._sync_controls()

    def refresh_language(self):
        self._sync_controls()
        self._update_mode_label()
        self._schedule_redraw(structural=True)

    def set_data(self, correction: dict | None):
        old_frame = self._frame_data
        if old_frame is None:
            old_frame = self._display_data
        self.result_data = correction
        self.response = None
        if correction is not None:
            self.response = build_response(correction, mode=self.mode)
        new = self._arrays_for_display(self.response)
        self._display_data = new
        self._frame_data = new
        self._selected_band = self._selected_band if self._has_band(self._selected_band) else None
        self._band_response_cache.clear()
        animate = self._motion_enabled and not self._suppress_morph_once
        if animate and self._animation_job is None:
            self._last_animation_tick=None
            self._slow_frame=False
            self._animation_deadline=time.monotonic()+1/60
        self._suppress_morph_once = False
        if old_frame is not None and new is not None and animate:
            previous = self._resample_frame(old_frame, new)
            self._transition = (time.monotonic(), 0.42, previous, new)
            self._frame_data = previous
            self._ensure_animation()
        elif old_frame is None and new is not None and animate:
            previous = dict(new)
            previous["simulated"] = new["source"].copy()
            previous["residual"] = new["before_residual"].copy()
            self._transition = (time.monotonic(), 0.42, previous, new)
            self._frame_data = previous
            self._ensure_animation()
        else:
            self._transition = None
        self._schedule_redraw(structural=True)

    @staticmethod
    def _resample_frame(previous, target):
        """Move an in-flight frame onto the new logarithmic frequency grid."""
        result = dict(target)
        old_freqs = np.asarray(previous.get("freqs", ()), dtype=float)
        new_freqs = np.asarray(target.get("freqs", ()), dtype=float)
        if not len(old_freqs) or not len(new_freqs):
            return result
        valid_freqs = np.isfinite(old_freqs) & (old_freqs > 0)
        if not np.any(valid_freqs):
            return result
        old_log = np.log(old_freqs[valid_freqs])
        for key in ("source", "target", "simulated", "residual", "before_residual", "filter"):
            old_values = np.asarray(previous.get(key, ()), dtype=float)
            target_values = np.asarray(target.get(key, ()), dtype=float)
            if len(target_values) != len(new_freqs) or len(old_values) != len(old_freqs):
                continue
            valid = valid_freqs & np.isfinite(old_values)
            if np.any(valid):
                result[key] = np.interp(np.log(new_freqs), np.log(old_freqs[valid]), old_values[valid])
        return result

    def set_view_style(self, style):
        if style not in ("membrane", "flat") or style == self.view_style:
            return
        self.view_style = style
        self._sync_controls()
        self._schedule_redraw(structural=True)

    def set_scale_locked(self, locked):
        self._range_locked = bool(locked)
        if self._range_locked and self._display_data is not None and len(self._display_data["freqs"]):
            self._locked_ranges[self.mode] = self._calculate_range()
        self._sync_controls()
        self._schedule_redraw(structural=True)

    @staticmethod
    def _get(d, key, default=None):
        if d is None:
            return default
        if isinstance(d, dict):
            return d.get(key, default)
        return getattr(d, key, default)

    def _arrays_for_display(self, d):
        if d is None:
            return None
        try:
            freqs = np.asarray(self._get(d, "freqs", []), dtype=float)
            source = np.asarray(self._get(d, "source", []), dtype=float)
            target = np.asarray(self._get(d, "target", []), dtype=float)
            sim = np.asarray(self._get(d, "simulated", []), dtype=float)
            residual = np.asarray(self._get(d, "residual", []), dtype=float)
            before_residual = np.asarray(self._get(d, "before_residual", []), dtype=float)
            filt = np.asarray(self._get(d, "filter_response", []), dtype=float)
            n = len(freqs)
            if n == 0:
                return None
            return {"freqs": freqs, "source": source if len(source)==n else np.zeros(n),
                    "target": target if len(target)==n else np.array([]),
                    "simulated": sim if len(sim)==n else np.zeros(n),
                    "residual": residual if len(residual)==n else np.array([]),
                    "before_residual": before_residual if len(before_residual)==n else np.array([]),
                    "filter": filt if len(filt)==n else np.zeros(n),
                    "bands": self._get(d, "bands", ()) or (),
                    "source_available": bool(self._get(d, "source_available", False)),
                    "target_available": bool(self._get(d, "target_available", False)),
                    "use_fir": bool(self._get(d, "use_fir", False)),
                    "mode": self._get(d, "mode", self.mode)}
        except Exception:
            raise

    def update_labels(self, src_text="Current", tgt_text="Target", sim_text="Simulated"):
        self.lbl_src.configure(text=src_text or "Current")
        self.lbl_tgt.configure(text=tgt_text or "Target")
        self.lbl_sim.configure(text=sim_text or "Simulated")

    def set_activity(self, stage: str):
        self._activity = str(stage or "")
        self.stage_label.configure(text=self._activity)

    def set_identity(self, source: str, target: str):
        self._source_name, self._target_name = str(source or ""), str(target or "")
        self.identity_label.configure(text=(f"{self._source_name}  →  {self._target_name}" if self._source_name or self._target_name else ""))

    def set_selected_band(self, index):
        self._selected_band = index
        self._schedule_redraw()

    def set_motion_enabled(self, enabled: bool):
        self._motion_enabled = bool(enabled)
        if not self._motion_enabled:
            self._cancel_animation()
            self._last_animation_tick=None
            self._slow_frame=False
            self._transition = None
            self._display_data = self._arrays_for_display(self.response)
            self._frame_data = self._display_data
            self._schedule_redraw()

    def set_quality(self, quality: str):
        if quality in ("auto", "high", "low"):
            self._quality = quality
            self._schedule_redraw(structural=True)

    def _has_band(self, index):
        return index is not None and self._display_data is not None and 0 <= int(index) < len(self._display_data["bands"])

    def _schedule_redraw(self, structural=False):
        if self._destroyed:
            return
        if structural:
            self._layout = None
        if self._resize_job is None:
            try:
                self._resize_job = self.after_idle(self._redraw_now)
            except tk.TclError:
                self._resize_job = None

    def _on_resize(self, _event=None):
        self._schedule_redraw(structural=True)

    def redraw(self):
        self._schedule_redraw(structural=True)

    def _redraw_now(self):
        self._resize_job = None
        if self._destroyed:
            return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 120 or h < 100:
            return
        layout = self._geometry(w, h)
        # Rebuild the static grid only after a resize or mode/quality change.
        if self._layout != layout:
            self.canvas.delete("static")
            self.canvas.delete("curve")
            self._layout = layout
            self._draw_grid(layout)
            self._coords = {}
            self._node_items = {}
            self._ribbon_items = {}
            self._ribbon_rule_items = {}
            self._lens_items = {}
            self._residual_item = None
            self._resid_strip_item = None
            self._draw_response(layout, update=True)
            self._draw_interaction(layout)
        else:
            self._draw_response(layout, update=True)
            self._draw_interaction(layout, update=True)

    def _geometry(self, w, h):
        left, right, top, bottom = 48, 18, 20, 54
        if w < 520:
            left, right = 43, 12
        return (w, h, left, right, top, bottom, w-left-right, h-top-bottom)

    def _x(self, freq, g):
        _, _, left, _, _, _, pw, _ = g
        f = min(self.F_MAX, max(self.F_MIN, float(freq)))
        return left + (math.log10(f / self.F_MIN) / self.LOG_SPAN) * pw

    def _y(self, value, g):
        _, _, _, _, top, _, _, ph = g
        lo, hi = self._base_range
        return top + (hi-float(value))/(hi-lo)*ph

    @staticmethod
    def _clip_y(y, g):
        top, bottom = g[4], g[4]+g[7]
        return max(top, min(bottom, float(y)))

    def _draw_grid(self, g):
        w, h, left, right, top, bottom, pw, ph = g
        lo, hi = self._range_for_data()
        self._base_range = lo, hi
        x0, x1, y0, y1 = left, left+pw, top, top+ph
        c = self.canvas
        c.create_rectangle(x0, y0, x1, y1, fill=self.COLORS["face"], outline=self.COLORS["rim"], tags="static")
        # Subtle inner shelf and side rails give the response stage depth without bitmap effects.
        c.create_line(x0+1, y0+1, x1-1, y0+1, fill=self.COLORS["quiet"], tags="static")
        for f, text in ((20,"20"),(50,"50"),(100,"100"),(200,"200"),(500,"500"),(1000,"1k"),(2000,"2k"),(5000,"5k"),(10000,"10k"),(20000,"20k")):
            x = self._x(f,g)
            major = f in (20,100,1000,10000,20000)
            c.create_line(x,y0,x,y1, fill=self.COLORS["quiet"] if major else self.COLORS["grid"], width=1,
                          dash=() if major else (2,5), tags="static")
            anchor="w" if f==20 else "e" if f==20000 else "center"
            c.create_text(x,y1+15,text=text,fill=self.COLORS["axis"],font=self._font("mono9",("Menlo",9)),anchor=anchor,tags="static")
        strip_y=y1+35
        if self._has_acoustic_data():
            c.create_line(x0,strip_y,x1,strip_y,fill=self.COLORS["quiet"],tags="static")
            c.create_text(x0-28,strip_y,text="Δ",fill=self.COLORS["residual"],font=self._font("mono9",("Menlo",8)),anchor="e",tags="static")
            c.create_text(x0-7,strip_y-8,text="+5",fill=self.COLORS["muted"],font=self._font("mono9",("Menlo",7)),anchor="e",tags="static")
            c.create_text(x0-7,strip_y+8,text="−5",fill=self.COLORS["muted"],font=self._font("mono9",("Menlo",7)),anchor="e",tags="static")
        step = self._tick_step(hi-lo)
        while ph * step / (hi-lo) < 24:
            step *= 2
        db = math.ceil(lo/step)*step
        while db <= hi+0.01:
            y=self._y(db,g)
            zero=abs(db)<0.01
            c.create_line(x0,y,x1,y,fill=self.COLORS["highlight"] if zero else self.COLORS["grid"],width=1,
                          dash=() if zero else (2,5),tags="static")
            c.create_text(x0-7,y,text=f"{db:g}",fill=self.COLORS["axis"],font=self._font("mono9",("Menlo",9)),anchor="e",tags="static")
            db+=step
        c.create_text(x0,y0-2,text="dB",fill=self.COLORS["muted"],font=self._font("mono9",("Menlo",8)),anchor="sw",tags="static")
        c.create_text(x1,y0-2,text="Hz",fill=self.COLORS["muted"],font=self._font("mono9",("Menlo",8)),anchor="se",tags="static")
        if self._range_overflow():
            label=self._control_text("plot_locked_overflow", "Outside locked range · unlock to fit")
            width=max(248,len(label)*5.3)
            c.create_rectangle(x1-width,y0+9,x1-8,y0+29,fill=ui_theme.GOLD_BG,outline=ui_theme.BORDER,tags="static")
            c.create_text(x1-width+8,y0+19,text=label,fill=ui_theme.GOLD,
                          font=self._font("mono9",("Menlo",8)),anchor="w",tags="static")
        self._empty = self._display_data is None or not len(self._display_data["freqs"])
        if self._empty:
            self._draw_empty(g)
        elif not self._has_acoustic_data():
            c.create_text(x0+9,y0+9,text=self._control_text("plot_filter_only", "Filter response only · no measurement"),
                          fill=self.COLORS["muted"],font=self._font("mono9",("Menlo",8)),anchor="nw",tags="static")

    @staticmethod
    def _tick_step(span):
        return 10 if span > 55 else 5 if span > 28 else 2 if span > 12 else 1

    def _range_for_data(self):
        if self._range_locked and self.mode in self._locked_ranges:
            return self._locked_ranges[self.mode]
        computed = self._calculate_range()
        if self._range_locked and self._display_data is not None and len(self._display_data["freqs"]):
            self._locked_ranges[self.mode] = computed
        return computed

    def _calculate_range(self):
        d = self._display_data
        if d is None:
            return (-24., 24.) if self.mode == "eq" else (-12.,12.)
        arrs=[]
        keys=("source","target","simulated") if self.mode=="eq" else ("source","target","simulated")
        for key in keys:
            a=d[key]
            if len(a) and (key!="target" or d["target_available"]):
                finite=a[np.isfinite(a)]
                if finite.size: arrs.extend(finite.tolist())
        if not arrs:
            return (-24.,24.) if self.mode=="eq" else (-12.,12.)
        low,high=min(arrs),max(arrs)
        pad=max(3.0,(high-low)*0.12)
        low,high=low-pad,high+pad
        if high-low<10:
            mid=(high+low)/2; low,high=mid-5,mid+5
        if self.mode=="eq" and not d["source_available"]:
            low=min(low,-15); high=max(high,15)
        return low,high

    def _range_overflow(self):
        if not self._range_locked or self._display_data is None:
            return False
        lo,hi=self._base_range
        d=self._display_data
        arrays=[]
        if d["source_available"]:arrays.append(d["source"])
        if d["target_available"]:arrays.append(d["target"])
        arrays.append(d["simulated"])
        for values in arrays:
            finite=np.asarray(values)[np.isfinite(values)]
            if finite.size and (float(finite.min())<lo-0.01 or float(finite.max())>hi+0.01):
                return True
        return False

    def _has_acoustic_data(self):
        return bool(self._display_data and self._display_data["target_available"] and len(self._display_data["target"]))

    def _draw_empty(self,g):
        _,_,left,_,top,_,pw,ph=g
        cx,cy=left+pw*.52,top+ph*.49
        c=self.canvas
        # Calm, deliberately static membrane rings mark the empty measurement field.
        for r, color, width in ((34,self.COLORS["grid"],1),(24,self.COLORS["quiet"],1),(13,self.COLORS["muted"],1)):
            c.create_oval(cx-r,cy-r,cx+r,cy+r,outline=color,width=width,tags="static")
        c.create_oval(cx-2,cy-2,cx+2,cy+2,fill=self.COLORS["target"],outline="",tags="static")
        t=self._t_fn
        try: hint=t("plot_empty_state") if t else "No response loaded"
        except Exception: hint="No response loaded"
        c.create_text(cx,cy+57,text=hint,fill=self.COLORS["muted"],font=self._font("ui11",("Arial",11)),tags="static")

    def _sample_indices(self, freqs, width):
        n=len(freqs)
        limit=900 if self._quality=="high" else 96 if self._quality=="low" else max(80,min(192,int(width/5.0)))
        if self._quality=="auto" and self._slow_frame and self._transition:
            limit=64
        return display_indices(freqs, width, max_points=limit)

    def _draw_response(self,g,update=False):
        frame_started=perf_counter()
        d=self._display_data
        if d is None: return
        freqs=d["freqs"]
        ids=self._sample_indices(freqs,g[6])
        # Materialize animation only while a data transition is active.
        values={k:d[k] for k in ("source","target","simulated","residual")}
        frame = dict(d)
        tr=self._transition
        if tr and self._motion_enabled:
            started,duration,before,after=tr
            alpha=min(1.,(time.monotonic()-started)/duration)
            for key in values:
                start=np.asarray(before.get(key,()))
                end=np.asarray(after.get(key,()))
                if len(start)==len(values[key])==len(end) and len(values[key]):
                    values[key]=start*(1-alpha)+end*alpha
            frame.update(values)
            if alpha>=1: self._transition=None
        else:
            frame.update(values)
        self._frame_data = frame
        if not update:
            self.canvas.delete("curve")
            self._coords = {}
            self._node_items = {}
            self._ribbon_items = {}
            self._ribbon_rule_items = {}
            self._lens_items = {}
            self._residual_item = None
            self._resid_strip_item = None
        residual_points=[]
        if self.mode=="eq" and d["target_available"] and len(values["residual"])==len(freqs):
            residual_points=self._between_coords(freqs,values["target"],values["simulated"],ids,g)
        if residual_points:
            if self._residual_item is None:
                self._residual_item=self.canvas.create_polygon(*residual_points,fill=self._mix_color(self.COLORS["residual"],self.COLORS["face"],.16),outline="",tags=("curve","residual-fill"))
            else:self.canvas.coords(self._residual_item,*residual_points)
        elif self._residual_item is not None:
            self.canvas.delete(self._residual_item); self._residual_item=None
        self._draw_residual_strip(freqs,values["residual"],ids,g,d["target_available"])
        if self.view_style=="membrane":
            self._draw_ribbons(freqs,values,ids,g,update)
        else:
            self._clear_ribbons()
        series=(("source",self.COLORS["source"],1.5,"source-line"),
                ("target",self.COLORS["target"],1.8,"target-line"),
                ("simulated",self.COLORS["sim"],2.35,"sim-line"))
        for key,color,width,tag in series:
            if (key=="target" and not d["target_available"]) or (key=="source" and not d["source_available"]):
                item=self._coords.pop(tag,None)
                if item is not None:self.canvas.delete(item)
                continue
            coords=self._line_coords(freqs,values[key],ids,g)
            if len(coords)<4: continue
            item=self._coords.get(tag) if update else None
            if item:
                self.canvas.coords(item,*coords)
            else:
                item=self.canvas.create_line(*coords,fill=color,width=width,capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,smooth=False,tags=("curve",tag))
                self._coords[tag]=item
        # Selected filter contribution is a restrained lens around the band's center.
        self._draw_band_lens(g,ids,update)
        self._draw_band_nodes(g)
        if self._transition:
            self._ensure_animation()
        self.frame_stats={"frame_ms":(perf_counter()-frame_started)*1000.0,"points":len(ids)}

    def _line_coords(self,freqs,values,ids,g):
        if len(values)!=len(freqs): return []
        pts=[]
        for i in ids:
            v=float(values[i]); f=float(freqs[i])
            if math.isfinite(v) and self.F_MIN<=f<=self.F_MAX:
                pts.extend((self._x(f,g),self._clip_y(self._y(v,g),g)))
        return pts

    def _between_coords(self,freqs,a,b,ids,g):
        points=[]
        for i in ids:
            f=float(freqs[i]);v=float(a[i])
            if self.F_MIN<=f<=self.F_MAX and math.isfinite(v):points.extend((self._x(f,g),self._clip_y(self._y(v,g),g)))
        for i in ids[::-1]:
            f=float(freqs[i]);v=float(b[i])
            if self.F_MIN<=f<=self.F_MAX and math.isfinite(v):points.extend((self._x(f,g),self._clip_y(self._y(v,g),g)))
        return points

    def _draw_residual_strip(self,freqs,residual,ids,g,available):
        if not available or len(residual)!=len(freqs):
            if self._resid_strip_item is not None:
                self.canvas.delete(self._resid_strip_item);self._resid_strip_item=None
            return
        center=g[4]+g[7]+35
        pts=[]
        for i in ids:
            f=float(freqs[i]);v=float(residual[i])
            if self.F_MIN<=f<=self.F_MAX and math.isfinite(v):
                pts.extend((self._x(f,g),center-max(-8.,min(8.,v*1.6))))
        if len(pts)>=4:
            if self._resid_strip_item is None:
                self._resid_strip_item=self.canvas.create_line(*pts,fill=self.COLORS["residual"],width=1.5,
                    capstyle=tk.ROUND,joinstyle=tk.ROUND,tags=("curve","residual-strip"))
            else:self.canvas.coords(self._resid_strip_item,*pts)

    def _draw_ribbons(self,freqs,values,ids,g,update):
        sheets=(("source", self.COLORS["source"]),
                ("target", self.COLORS["target"]),
                ("simulated", self.COLORS["sim"]))
        for key,semantic in sheets:
            available=(key!="target" or self._display_data["target_available"]) and (key!="source" or self._display_data["source_available"])
            if not available or len(values[key])!=len(freqs):
                item=self._ribbon_items.pop(key,None)
                if item is not None:self.canvas.delete(item)
                for tag in [tag for tag in self._ribbon_rule_items if tag[0]==key]:
                    self.canvas.delete(self._ribbon_rule_items.pop(tag))
                continue
            visible=(freqs>=self.F_MIN)&(freqs<=self.F_MAX)
            has_gap=(not np.all(np.isfinite(freqs))) or (np.any(visible) and not np.all(np.isfinite(values[key][visible])))
            if has_gap or np.any(np.diff(freqs)<=0):
                item=self._ribbon_items.pop(key,None)
                if item is not None:self.canvas.delete(item)
                for tag in [tag for tag in self._ribbon_rule_items if tag[0]==key]:
                    self.canvas.delete(self._ribbon_rule_items.pop(tag))
                continue
            pts=self._line_coords(freqs,values[key],ids,g)
            if len(pts)<4:continue
            # A five-pixel contour keeps the membrane readable without the old
            # deep, opaque slabs. Reverse complete coordinate pairs so Tk gets
            # a simple perimeter instead of a bow-tie polygon.
            depth=5.0
            back=[]
            for j in range(0,len(pts),2):
                back.extend((pts[j],self._clip_y(pts[j+1]+depth,g)))
            reversed_back=[coord for j in range(len(back)-2,-1,-2) for coord in (back[j],back[j+1])]
            polygon=pts+reversed_back
            item=self._ribbon_items.get(key)
            fill=self._mix_color(semantic, self.COLORS["face"], .13)
            edge=self._mix_color(semantic, self.COLORS["face"], .48)
            if item:
                self.canvas.coords(item,*polygon)
                self.canvas.itemconfigure(item, fill=fill)
            else:self._ribbon_items[key]=self.canvas.create_polygon(*polygon,fill=fill,outline="",tags=("curve","ribbon"))
            item=self._ribbon_rule_items.get((key,"edge"))
            if item:
                self.canvas.coords(item,*back)
                self.canvas.itemconfigure(item, fill=edge)
            else:self._ribbon_rule_items[(key,"edge")]=self.canvas.create_line(*back,fill=edge,width=1,
                capstyle=tk.ROUND,joinstyle=tk.ROUND,tags=("curve","ribbon"))
            for tag in [tag for tag in self._ribbon_rule_items if tag[0]==key and tag[1]!="edge"]:
                self.canvas.delete(self._ribbon_rule_items.pop(tag))

    def _clear_ribbons(self):
        for item in self._ribbon_items.values():self.canvas.delete(item)
        self._ribbon_items.clear()
        for item in self._ribbon_rule_items.values():self.canvas.delete(item)
        self._ribbon_rule_items.clear()

    def _polygon_between(self,freqs,a,b,ids,g,color,tag,alpha=.16):
        # Tk has no alpha fill; a low-contrast warm tint supplies the residual cue.
        points=[]
        for i in ids:
            f=float(freqs[i]); v=float(a[i])
            if self.F_MIN<=f<=self.F_MAX and math.isfinite(v): points.extend((self._x(f,g),self._y(v,g)))
        for i in ids[::-1]:
            f=float(freqs[i]); v=float(b[i])
            if self.F_MIN<=f<=self.F_MAX and math.isfinite(v): points.extend((self._x(f,g),self._y(v,g)))
        if len(points)>=6:
            self.canvas.create_polygon(*points,fill=self._mix_color(self.COLORS["residual"],self.COLORS["face"],.16),outline="",tags=("curve","residual-fill"))

    def _draw_band_lens(self,g,ids,update):
        if not self._has_band(self._selected_band):
            for item in self._lens_items.values():self.canvas.delete(item)
            self._lens_items.clear()
            return
        band=self._display_data["bands"][int(self._selected_band)]
        freq=self._band_value(band,"frequency",self._band_value(band,"freq",None))
        if not freq or freq<=0:return
        curve=self._individual_band_curve(int(self._selected_band))
        if curve is None:return
        frame=self._frame_data or self._display_data
        f=frame["freqs"]
        gain_curve=frame["source"] if self.mode=="eq" and frame["source_available"] else np.zeros(len(f))
        vals=gain_curve+curve
        mask=(f>=float(freq)/2.3)&(f<=float(freq)*2.3)
        lens_freqs=f[mask];lens_vals=vals[mask]
        lens_ids=np.arange(len(lens_freqs))
        coords=self._line_coords(lens_freqs,lens_vals,lens_ids,g)
        item=self._lens_items.get("curve")
        if len(coords)>=4:
            if item:self.canvas.coords(item,*coords)
            else:self._lens_items["curve"]=self.canvas.create_line(*coords,fill=self.COLORS["lens"],width=3.2,
                capstyle=tk.ROUND,joinstyle=tk.ROUND,tags=("curve","band-lens"))
        x=self._x(freq,g)
        item=self._lens_items.get("guide")
        coords=(x,g[4],x,g[4]+g[7])
        if item:self.canvas.coords(item,*coords)
        else:self._lens_items["guide"]=self.canvas.create_line(*coords,fill=self.COLORS["quiet"],dash=(2,4),tags=("curve","band-lens"))

    def _individual_band_curve(self,index):
        if index in self._band_response_cache:return self._band_response_cache[index]
        try:
            b=self._display_data["bands"][index]
            f=self._display_data["freqs"]
            filter_type=self._band_value(b,"filter_type",self._band_value(b,"type","Peaking"))
            h=cp.biquad_response(f,str(filter_type),
                float(self._band_value(b,"frequency")),float(self._band_value(b,"gain",0.0)),
                float(self._band_value(b,"Q",0.707)),
                fs=float(self.result_data.get("samplerate",48000.0)))
            curve=20.0*np.log10(np.maximum(np.abs(h),1e-12))
            self._band_response_cache[index]=curve
            return curve
        except (KeyError,TypeError,ValueError,OverflowError):
            return None

    def _draw_band_nodes(self,g):
        """Expose fitted PEQ centers as visible, directly selectable handles."""
        if not self._display_data or self._empty:
            return
        d=self._display_data
        live=set()
        for i,band in enumerate(d["bands"]):
            freq=self._band_value(band,"frequency",self._band_value(band,"freq",None))
            if freq is None or not self.F_MIN<=float(freq)<=self.F_MAX:
                continue
            x,y,r=self._band_node_position(i,float(freq),g)
            selected=(self._selected_band is not None and int(self._selected_band)==i)
            color=self.COLORS["lens"] if selected else self.COLORS["source"]
            live.add(i)
            items=self._node_items.get(i)
            if not items:
                outer=self.canvas.create_oval(x-r,y-r,x+r,y+r,fill=self.COLORS["face"],outline=color,width=1.4,
                                    tags=("curve","band-node",f"band:{i}"))
                inner=self.canvas.create_oval(x-1.2,y-1.2,x+1.2,y+1.2,fill=color,outline="",
                                    tags=("curve","band-node",f"band:{i}"))
                self._node_items[i]=(outer,inner)
            else:
                outer,inner=items
                self.canvas.coords(outer,x-r,y-r,x+r,y+r);self.canvas.itemconfigure(outer,outline=color)
                self.canvas.coords(inner,x-1.2,y-1.2,x+1.2,y+1.2);self.canvas.itemconfigure(inner,fill=color)
        for i in set(self._node_items)-live:
            for item in self._node_items.pop(i):self.canvas.delete(item)

    @staticmethod
    def _band_value(band,key,default=None):
        return band.get(key,default) if isinstance(band,dict) else getattr(band,key,default)

    def _draw_interaction(self,g,update=False):
        self.canvas.delete("interaction")
        if self._hover_freq is None:return
        x=self._x(self._hover_freq,g)
        self.canvas.create_line(x,g[4],x,g[4]+g[7],fill=self.COLORS["highlight"],dash=(2,3),tags="interaction")
        d=self._display_data
        if d is None:return
        try:
            result=self._interpolate(self._hover_freq,self._frame_data or d)
        except Exception:
            result=self._interpolate(self._hover_freq,d)
        # Small data readout anchored near the cursor, clamped inside plot bounds.
        parts=[f"{self._hover_freq:,.2f} Hz"]
        for name,key,color in (("SRC","source",self.COLORS["source"]),("TGT","target",self.COLORS["target"]),("SIM","simulated",self.COLORS["sim"]),("Δ","residual",self.COLORS["residual"])):
            v=result.get(key) if result else None
            if v is not None and (key!="source" or d["source_available"]) and (key!="target" or d["target_available"]):
                parts.append(f"{name} {float(v):+.2f}")
        text="   ".join(parts)
        box_w=min(g[6]-16,max(245,len(text)*6.8+18))
        tx=min(max(x+12,g[2]+8),g[2]+g[6]-box_w-8)
        ty=g[4]+12
        self.canvas.create_rectangle(tx-7,ty-8,tx+box_w,ty+13,fill=self.COLORS["panel"],outline=self.COLORS["rim"],tags="interaction")
        self.canvas.create_text(tx,ty,text=text,fill=self.COLORS["text"],anchor="w",font=self._font("mono9",("Menlo",8)),tags="interaction")
        if self._has_acoustic_data() and len(d["residual"]):
            v=self._interpolate(self._hover_freq,self._frame_data or d).get("residual")
            if v is not None:
                yy=self._y(v,g)
                yy=self._clip_y(yy,g)
                self.canvas.create_oval(x-3,yy-3,x+3,yy+3,fill=self.COLORS["residual"],outline=self.COLORS["face"],width=1,tags="interaction")

    def _interpolate(self,freq,d):
        result={}
        f=d["freqs"]
        if not len(f):return result
        x=np.log(np.maximum(f,1e-9)); q=math.log(max(float(freq),1e-9))
        for key in ("source","target","simulated","residual"):
            a=d[key]
            result[key]=float(np.interp(q,x,a)) if len(a)==len(f) and (key!="target" or d["target_available"]) else None
        return result

    def _on_motion(self,event):
        self._last_pointer=(event.x,event.y)
        if self._hover_job is None:
            try:self._hover_job=self.after(16,self._process_hover)
            except tk.TclError:pass

    def _process_hover(self):
        self._hover_job=None
        if not self._last_pointer or not self._layout:return
        x,y=self._last_pointer; g=self._layout
        if g[2]<=x<=g[2]+g[6] and g[4]<=y<=g[4]+g[7]:
            ratio=(x-g[2])/g[6]
            self._hover_freq=self.F_MIN*10**(ratio*self.LOG_SPAN)
        else:self._hover_freq=None
        self._draw_interaction(g)

    def _on_leave(self,_event):
        self._last_pointer=None; self._hover_freq=None
        if self._layout:self._draw_interaction(self._layout)

    def _on_click(self,event):
        if not self._display_data or not self._layout:return
        g=self._layout; bands=self._display_data["bands"]
        if not bands:return
        best=None; dist=12
        for i,b in enumerate(bands):
            f=self._band_value(b,"frequency",self._band_value(b,"freq",None))
            if f is None:continue
            x,y,_r=self._band_node_position(i,float(f),g)
            delta=math.hypot(x-event.x,y-event.y)
            if delta<dist:best,dist=i,delta
        if best is not None:
            self.set_selected_band(best)
            if callable(self.on_band_selected):self.on_band_selected(best)

    def _band_node_position(self,index,freq,g):
        frame=self._frame_data or self._display_data
        vals=frame["simulated"]
        freqs=frame["freqs"]
        yval=float(np.interp(math.log(freq),np.log(freqs),vals)) if len(vals)==len(freqs) else 0.0
        radius=5.4 if self._selected_band is not None and int(self._selected_band)==index else 3.4
        y=self._clip_y(self._y(yval,g),g)
        y=max(g[4]+radius,min(g[4]+g[7]-radius,y))
        return self._x(freq,g),y,radius

    def _ensure_animation(self):
        if not self._motion_enabled or self._animation_job is not None or self._destroyed:return
        if self._animation_deadline is None:
            self._animation_deadline=time.monotonic()+1/60
        delay=max(0,int((self._animation_deadline-time.monotonic())*1000))
        try:self._animation_job=self.after(delay,self._animation_tick)
        except tk.TclError:self._animation_job=None

    def _animation_tick(self):
        self._animation_job=None
        if self._destroyed:return
        now=time.monotonic()
        if self._last_animation_tick is not None and (now-self._last_animation_tick)>0.018:
            self._slow_frame=True
        self._last_animation_tick=now
        next_deadline=self._animation_deadline+1/60 if self._animation_deadline is not None else now+1/60
        if next_deadline<=now:
            next_deadline=now+1/60
        self._animation_deadline=next_deadline
        if self._resize_job is not None:
            try:self.after_cancel(self._resize_job)
            except tk.TclError:pass
            self._resize_job=None
        self._redraw_now()
        if self._transition:
            self._ensure_animation()
        elif self._slow_frame:
            self._slow_frame=False
        if not self._transition:
            self._animation_deadline=None

    def _cancel_animation(self):
        if self._animation_job is not None:
            try:self.after_cancel(self._animation_job)
            except tk.TclError:pass
            self._animation_job=None
        self._animation_deadline=None

    def _on_canvas_destroy(self,event):
        if event.widget is not self.canvas:return
        self._destroyed=True
        self._cancel_animation()
        for attr in ("_resize_job","_hover_job"):
            job=getattr(self,attr,None)
            if job is not None:
                try:self.after_cancel(job)
                except tk.TclError:pass
                setattr(self,attr,None)
