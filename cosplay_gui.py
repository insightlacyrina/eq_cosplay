#!/usr/bin/env python3
"""
EQ Cosplay — Tkinter 图形界面包装。

- 任意窗口大小自适应（含左下角提示区 wrap）
- 多语言 en / zh / ja（与 cosplay.py MESSAGES 同步，可运行时切换）
"""

from __future__ import annotations

import difflib
import queue
import sys
import tempfile
import threading
import traceback
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _enable_windows_dpi_awareness() -> None:
    """Avoid blurry UI / layout bugs on high-DPI Windows displays."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # Per-monitor DPI awareness v2 when available
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _show_startup_error(title: str, message: str) -> None:
    """Show a blocking error even when Tk is unavailable (Windows MessageBox)."""
    printed = f"{title}\n\n{message}"
    try:
        sys.stderr.write(printed + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
            return
        except Exception:
            pass
    try:
        # Last resort: Tk messagebox if import works partially
        import tkinter as _tk
        from tkinter import messagebox as _mb

        r = _tk.Tk()
        r.withdraw()
        _mb.showerror(title, message)
        r.destroy()
    except Exception:
        pass


# Defer hard failure: give a readable error instead of a silent crash on Windows
try:
    from tkinter import (
        BOTH,
        DISABLED,
        END,
        HORIZONTAL,
        LEFT,
        NORMAL,
        RIGHT,
        VERTICAL,
        WORD,
        BooleanVar,
        Canvas,
        DoubleVar,
        StringVar,
        Tk,
        Toplevel,
        X,
        Y,
        messagebox,
        ttk,
    )
    from tkinter.scrolledtext import ScrolledText
except Exception as _tk_import_err:  # pragma: no cover
    _show_startup_error(
        "EQ Cosplay",
        "Failed to import Tkinter (GUI toolkit).\n\n"
        f"{_tk_import_err}\n\n"
        "Windows: reinstall Python from https://www.python.org/downloads/\n"
        "and enable “tcl/tk and IDLE”.\n"
        "Or run:  start_cli.bat   /   python cosplay.py",
    )
    raise SystemExit(1) from _tk_import_err

try:
    import cosplay as cp
except Exception as _cp_import_err:  # pragma: no cover
    _show_startup_error(
        "EQ Cosplay",
        "Failed to import cosplay core module.\n\n"
        f"{_cp_import_err}\n\n"
        "Install deps:  python -m pip install -r requirements.txt",
    )
    raise SystemExit(1) from _cp_import_err


# ---------------------------------------------------------------------------
# 日志重定向
# ---------------------------------------------------------------------------

class _QueueWriter:
    """print / localized_print → 队列 + logs/ 文件。"""

    def __init__(self, q: queue.Queue, file_path: Path | None = None):
        self._q = q
        self._buf = ""
        self._file_path = Path(file_path) if file_path else None
        self._fh = None
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self._file_path, "a", encoding="utf-8", buffering=1)
            self._fh.write(
                f"# EQ Cosplay GUI session log\n"
                f"# started: {__import__('time').strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"# file: {self._file_path.resolve()}\n"
                f"# ---\n"
            )
            self._fh.flush()

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self._fh is not None:
            try:
                self._fh.write(s)
            except Exception:
                pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._q.put(line + "\n")
        return len(s)

    def flush(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
            except Exception:
                pass
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
# 对话框
# ---------------------------------------------------------------------------

def ask_provider(parent, entries: list[dict]) -> dict:
    """多测量源选择。entries 为空时回退安全值；关闭窗口未选时用默认第一项。"""
    if not entries:
        raise ValueError("ask_provider: empty entries")
    if len(entries) == 1:
        return entries[0]

    result: dict = {"value": entries[0], "done": False}
    win = Toplevel(parent)
    title = (cp.translate("provider_list_header") or "Provider").strip().lstrip("\n")
    win.title(title or "Provider")
    try:
        win.transient(parent)
    except Exception:
        pass
    win.geometry("520x320")
    win.minsize(360, 240)
    # 置顶，避免被主窗口挡住（部分平台 grab 异常时仍可用）
    try:
        win.lift()
        win.focus_force()
        win.grab_set()
    except Exception:
        pass

    ttk.Label(win, text=title).pack(anchor="w", padx=10, pady=(10, 4))

    lb_frame = ttk.Frame(win)
    lb_frame.pack(fill=BOTH, expand=True, padx=10, pady=4)
    lb_frame.rowconfigure(0, weight=1)
    lb_frame.columnconfigure(0, weight=1)

    scroll = ttk.Scrollbar(lb_frame, orient=VERTICAL)
    lb = ttk.Treeview(
        lb_frame,
        columns=("model", "provider"),
        show="headings",
        yscrollcommand=scroll.set,
        height=10,
        selectmode="browse",
    )
    scroll.config(command=lb.yview)
    lb.heading("model", text=cp.translate("gui_provider_model"))
    lb.heading("provider", text=cp.translate("gui_provider_source"))
    lb.column("model", width=280, stretch=True, anchor="w")
    lb.column("provider", width=180, stretch=True, anchor="w")
    lb.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")

    for idx, item in enumerate(entries):
        provider = item.get("provider") or cp.extract_provider_label(
            item.get("relative_path", "") or ""
        )
        display = item.get("display_name", "") or ""
        # iid 用 p{idx}，避免纯数字 iid 在部分 Tcl/Tk 上的兼容问题
        lb.insert("", END, iid=f"p{idx}", values=(display, provider))

    first_iid = "p0"
    try:
        lb.selection_set(first_iid)
        lb.focus(first_iid)
        lb.see(first_iid)
    except Exception:
        pass

    def _selected_entry() -> dict:
        sel = lb.selection()
        if not sel:
            return entries[0]
        iid = str(sel[0])
        if iid.startswith("p") and iid[1:].isdigit():
            i = int(iid[1:])
            if 0 <= i < len(entries):
                return entries[i]
        if iid.isdigit():
            i = int(iid)
            if 0 <= i < len(entries):
                return entries[i]
        return entries[0]

    def on_ok(_event=None) -> None:
        if result["done"]:
            return
        result["done"] = True
        result["value"] = _selected_entry()
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()

    def on_cancel() -> None:
        # 关闭窗口：保留默认第一项，不抛异常
        if result["done"]:
            return
        result["done"] = True
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()

    lb.bind("<Double-1>", on_ok)
    lb.bind("<Return>", on_ok)
    win.protocol("WM_DELETE_WINDOW", on_cancel)

    btn = ttk.Frame(win)
    btn.pack(fill=X, padx=10, pady=10)
    ttk.Button(btn, text=cp.translate("gui_msg_ok"), command=on_ok).pack(side=RIGHT)
    ttk.Button(btn, text=cp.translate("gui_msg_cancel"), command=on_cancel).pack(
        side=RIGHT, padx=(0, 8)
    )

    try:
        parent.wait_window(win)
    except Exception:
        win.wait_window()
    return result["value"]


def resolve_headphone_gui(parent, user_input: str, prompt_type: str = "target") -> dict | None:
    if not cp.AUTOEQ_DATABASE:
        cp.localized_print("db_not_loaded")
        return None
    text = (user_input or "").strip()
    if not text:
        return None
    cp.localized_print("searching_headphone", user_input=text, prompt_type=prompt_type)
    lower_names = list(cp.AUTOEQ_DATABASE.keys())
    matches = difflib.get_close_matches(text.lower(), lower_names, n=1, cutoff=0.3)
    if not matches:
        cp.localized_print("no_match_found")
        return None
    best = matches[0]
    items = cp.AUTOEQ_DATABASE[best]
    selected = ask_provider(parent, items)
    cp.localized_print(
        "match_success",
        prompt_type=prompt_type,
        display_name=selected["display_name"],
    )
    return selected


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class CosplayApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(cp.translate("gui_window_title"))
        self.root.geometry("1000x740")
        self.root.minsize(720, 520)

        self.log_q: queue.Queue = queue.Queue()
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
        self._model_count = 0
        self._status_key = "gui_status_loading"
        self._status_kwargs: dict = {}

        self.var_source = StringVar()
        self.var_target = StringVar()
        self.var_sr = StringVar(value=str(cp.DEFAULT_SAMPLE_RATE))
        self.var_output = StringVar()
        self.var_preamp_mode = StringVar(value="safe")
        self.var_preamp_custom = DoubleVar(value=-3.0)
        self.var_debug = BooleanVar(value=False)
        self.var_status = StringVar(value="…")
        self.var_fir = StringVar(value="")
        self.var_metrics = StringVar(value="")
        self.var_tip = StringVar(value="")
        self.var_lang = StringVar(value=cp.LANG if cp.LANG in ("en", "zh", "ja") else "en")

        # 需要在换语言时更新 text 的控件引用
        self._i18n_widgets: dict = {}

        self._init_output_default()
        self._build_ui()
        self._apply_language(refresh_dynamic=True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.root.after(80, self._poll_log)
        self.root.after(200, self._bootstrap)

    def _init_output_default(self) -> None:
        detected = None
        if self.system_name == "Darwin":
            detected = cp.detect_macos_default_playback_device()
        if detected:
            self.var_output.set(detected)
        else:
            self.var_output.set(cp.localized_default_playback_label("headphones"))

    # ----- 布局 -----

    def _build_ui(self) -> None:
        style = ttk.Style()
        # Windows: prefer native themes; clam is a portable fallback
        theme_candidates: list[str]
        if self.system_name == "Darwin":
            theme_candidates = ["aqua", "clam"]
        elif self.system_name == "Windows":
            theme_candidates = ["vista", "xpnative", "winnative", "clam", "default"]
        else:
            theme_candidates = ["clam", "alt", "default"]
        for name in theme_candidates:
            try:
                style.theme_use(name)
                break
            except Exception:
                continue

        self.outer = ttk.Frame(self.root, padding=8)
        self.outer.pack(fill=BOTH, expand=True)
        self.outer.rowconfigure(1, weight=1)
        self.outer.columnconfigure(0, weight=1)

        # 顶栏
        top = ttk.Frame(self.outer)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        top.columnconfigure(1, weight=1)

        self.lbl_title = ttk.Label(top, text="EQ Cosplay", font=("", 16, "bold"))
        self.lbl_title.grid(row=0, column=0, sticky="w")
        self.lbl_status = ttk.Label(top, textvariable=self.var_status, foreground="#555")
        self.lbl_status.grid(row=0, column=1, sticky="e", padx=(8, 8))

        lang_fr = ttk.Frame(top)
        lang_fr.grid(row=0, column=2, sticky="e")
        self.lbl_lang = ttk.Label(lang_fr, text="")
        self.lbl_lang.pack(side=LEFT, padx=(0, 4))
        self.lang_combo = ttk.Combobox(
            lang_fr,
            textvariable=self.var_lang,
            values=["en", "zh", "ja"],
            state="readonly",
            width=6,
        )
        self.lang_combo.pack(side=LEFT)
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        # 主体水平分割
        self.body = ttk.Panedwindow(self.outer, orient=HORIZONTAL)
        self.body.grid(row=1, column=0, sticky="nsew")

        self.left = ttk.Frame(self.body)
        self.right = ttk.Frame(self.body)
        self.body.add(self.left, weight=2)
        self.body.add(self.right, weight=3)

        self._build_left(self.left)
        self._build_right(self.right)

        # 初始 sash + 滚轮（必须在左右面板都建完后，再给左侧整棵子树绑滚轮）
        self.root.after(100, self._init_sash)
        self._setup_left_mousewheel()
        self.root.after(200, self._setup_left_mousewheel)
        self.root.after(800, self._setup_left_mousewheel)

    def _init_sash(self) -> None:
        try:
            w = max(self.root.winfo_width(), 720)
            self.body.sashpos(0, int(w * 0.38))
        except Exception:
            pass

    def _build_left(self, parent: ttk.Frame) -> None:
        """左侧：可滚动表单 + 固定底栏提示（自适应 wrap）。"""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        # --- 可滚动中部 ---
        mid = ttk.Frame(parent)
        mid.grid(row=0, column=0, sticky="nsew")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        self.left_canvas = Canvas(mid, highlightthickness=0, borderwidth=0)
        self.left_vsb = ttk.Scrollbar(mid, orient=VERTICAL, command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=self.left_vsb.set)
        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        self.left_vsb.grid(row=0, column=1, sticky="ns")

        self.left_inner = ttk.Frame(self.left_canvas, padding=(0, 0, 6, 0))
        self._left_win = self.left_canvas.create_window((0, 0), window=self.left_inner, anchor="nw")

        self.left_inner.bind("<Configure>", self._on_left_inner_configure)
        self.left_canvas.bind("<Configure>", self._on_left_canvas_configure)

        self._build_left_form(self.left_inner)
        # 滚轮绑定在整窗构建完后安装（见 _build_ui 末尾），避免遗漏子控件

        # --- 底栏：提示 / 平台 / 捕获 / 日志目录（始终可见，随宽换行）---
        tip_box = ttk.LabelFrame(parent, text="", padding=8)
        tip_box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        tip_box.columnconfigure(0, weight=1)
        self.tip_frame = tip_box
        self._i18n_widgets["tip_frame"] = tip_box

        self.lbl_tip = ttk.Label(
            tip_box,
            textvariable=self.var_tip,
            foreground="#444",
            justify=LEFT,
            anchor="w",
        )
        self.lbl_tip.grid(row=0, column=0, sticky="ew")

        self.lbl_platform = ttk.Label(tip_box, text="", foreground="#666", justify=LEFT, anchor="w")
        self.lbl_platform.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self.lbl_capture = ttk.Label(tip_box, text="", foreground="#666", justify=LEFT, anchor="w")
        self.lbl_capture.grid(row=2, column=0, sticky="ew", pady=(2, 0))

        self.lbl_logs = ttk.Label(tip_box, text="", foreground="#666", justify=LEFT, anchor="w")
        self.lbl_logs.grid(row=3, column=0, sticky="ew", pady=(2, 0))

        tip_box.bind("<Configure>", self._on_tip_configure, add="+")

    def _build_left_form(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        # 预设
        self.frm_presets = ttk.LabelFrame(parent, text="", padding=8)
        self.frm_presets.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.frm_presets.columnconfigure(0, weight=1)
        self.preset_combo = ttk.Combobox(self.frm_presets, state="readonly")
        self.preset_combo.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        pbtn = ttk.Frame(self.frm_presets)
        pbtn.grid(row=1, column=0, sticky="ew")
        self.btn_refresh = ttk.Button(pbtn, text="", command=self._refresh_presets)
        self.btn_refresh.pack(side=LEFT)
        self.btn_load_preset = ttk.Button(pbtn, text="", command=self._load_preset)
        self.btn_load_preset.pack(side=LEFT, padx=4)

        # Cosplay 表单
        self.frm_cosplay = ttk.LabelFrame(parent, text="", padding=8)
        self.frm_cosplay.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.frm_cosplay.columnconfigure(1, weight=1)

        self.lbl_sr = ttk.Label(self.frm_cosplay, text="")
        self.lbl_sr.grid(row=0, column=0, sticky="w", pady=2, padx=(0, 8))
        self.cmb_sr = ttk.Combobox(
            self.frm_cosplay,
            textvariable=self.var_sr,
            values=["44100", "48000", "88200", "96000", "192000"],
            state="readonly",
            width=12,
        )
        self.cmb_sr.grid(row=0, column=1, sticky="ew", pady=2)

        self.lbl_source = ttk.Label(self.frm_cosplay, text="")
        self.lbl_source.grid(row=1, column=0, sticky="w", pady=2, padx=(0, 8))
        ttk.Entry(self.frm_cosplay, textvariable=self.var_source).grid(
            row=1, column=1, sticky="ew", pady=2
        )

        self.lbl_target = ttk.Label(self.frm_cosplay, text="")
        self.lbl_target.grid(row=2, column=0, sticky="w", pady=2, padx=(0, 8))
        ttk.Entry(self.frm_cosplay, textvariable=self.var_target).grid(
            row=2, column=1, sticky="ew", pady=2
        )

        self.lbl_playback = ttk.Label(self.frm_cosplay, text="")
        self.lbl_playback.grid(row=3, column=0, sticky="w", pady=2, padx=(0, 8))
        ttk.Entry(self.frm_cosplay, textvariable=self.var_output).grid(
            row=3, column=1, sticky="ew", pady=2
        )

        # 前级
        self.frm_preamp = ttk.LabelFrame(parent, text="", padding=8)
        self.frm_preamp.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.frm_preamp.columnconfigure(0, weight=1)

        self.rb_safe = ttk.Radiobutton(
            self.frm_preamp, text="", variable=self.var_preamp_mode, value="safe"
        )
        self.rb_mod = ttk.Radiobutton(
            self.frm_preamp, text="", variable=self.var_preamp_mode, value="moderate"
        )
        self.rb_custom = ttk.Radiobutton(
            self.frm_preamp, text="", variable=self.var_preamp_mode, value="custom"
        )
        self.rb_none = ttk.Radiobutton(
            self.frm_preamp, text="", variable=self.var_preamp_mode, value="none"
        )
        for i, rb in enumerate((self.rb_safe, self.rb_mod, self.rb_custom, self.rb_none)):
            rb.grid(row=i, column=0, sticky="w")

        crow = ttk.Frame(self.frm_preamp)
        crow.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        self.lbl_custom_db = ttk.Label(crow, text="")
        self.lbl_custom_db.pack(side=LEFT)
        ttk.Entry(crow, textvariable=self.var_preamp_custom, width=10).pack(side=LEFT, padx=6)

        self.chk_debug = ttk.Checkbutton(parent, text="", variable=self.var_debug)
        self.chk_debug.grid(row=3, column=0, sticky="w", pady=2)

        # 操作按钮
        bf = ttk.Frame(parent)
        bf.grid(row=4, column=0, sticky="ew", pady=8)
        bf.columnconfigure(0, weight=1)
        self.btn_calc = ttk.Button(bf, text="", command=self._on_calculate)
        self.btn_calc.grid(row=0, column=0, sticky="ew", pady=2)
        self.btn_deploy = ttk.Button(
            bf, text="", command=self._on_deploy, state=DISABLED
        )
        self.btn_deploy.grid(row=1, column=0, sticky="ew", pady=2)
        self.btn_stop = ttk.Button(bf, text="", command=self._on_stop, state=DISABLED)
        self.btn_stop.grid(row=2, column=0, sticky="ew", pady=2)
        # 与「计算校正」等同宽全宽按钮，避免小窗口挤占绿色 FIR 文案
        self.btn_stop_fir = ttk.Button(
            bf, text="", command=self._on_stop_fir, state=DISABLED
        )
        self.btn_stop_fir.grid(row=3, column=0, sticky="ew", pady=2)

        # 绿色 FIR 提示、指标提示单独占行，位于操作按钮下方（小窗口可随左侧滚动查看）
        self.lbl_fir = ttk.Label(
            parent, textvariable=self.var_fir, foreground="#0a6", justify=LEFT, anchor="w"
        )
        self.lbl_fir.grid(row=5, column=0, sticky="ew", pady=(6, 0))

        self.lbl_metrics = ttk.Label(
            parent, textvariable=self.var_metrics, foreground="#333", justify=LEFT, anchor="w"
        )
        self.lbl_metrics.grid(row=6, column=0, sticky="ew", pady=(4, 0))

    def _build_right(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=2)
        parent.columnconfigure(0, weight=1)

        self.frm_peq = ttk.LabelFrame(parent, text="", padding=6)
        self.frm_peq.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        self.frm_peq.rowconfigure(0, weight=1)
        self.frm_peq.columnconfigure(0, weight=1)

        cols = ("band", "type", "freq", "gain", "q")
        self.tree = ttk.Treeview(self.frm_peq, columns=cols, show="headings")
        sy = ttk.Scrollbar(self.frm_peq, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        for c, w in (("band", 48), ("type", 100), ("freq", 90), ("gain", 80), ("q", 70)):
            self.tree.column(c, width=w, anchor="center", stretch=True)

        self.frm_log = ttk.LabelFrame(parent, text="", padding=6)
        self.frm_log.grid(row=1, column=0, sticky="nsew")
        self.frm_log.rowconfigure(0, weight=1)
        self.frm_log.columnconfigure(0, weight=1)
        font = ("Menlo", 11) if self.system_name == "Darwin" else ("Consolas", 10)
        self.log = ScrolledText(self.frm_log, wrap=WORD, font=font)
        self.log.grid(row=0, column=0, sticky="nsew")
        self.log.configure(state=DISABLED)

    # ----- 自适应 -----

    def _setup_left_mousewheel(self) -> None:
        """macOS 触控板 + Canvas 内嵌表单的可靠滚轮方案。

        关键点（macOS / Aqua Tk）：
        - bind_all 收到的 MouseWheel 里 event.widget 常常是根窗口，不是指针下控件
        - event.x_root / y_root 也经常不可用，必须用 winfo_pointerxy()
        - 子控件不会把滚轮冒泡给 Canvas
        """
        if not hasattr(self, "left_canvas"):
            return
        self._left_wheel_bound = True

        # 全局绑定（macOS 触控板主要靠这条）
        # 不用 add='+'，保证我们的逻辑一定会跑到
        self.root.bind_all("<MouseWheel>", self._on_mousewheel_global)
        self.root.bind_all("<Button-4>", self._on_mousewheel_global)
        self.root.bind_all("<Button-5>", self._on_mousewheel_global)

        # 再给左侧子树直接 bind 一份（Windows/部分 Linux 更吃这套）
        self._bind_wheel_recursive(self.left_canvas)
        self._bind_wheel_recursive(self.left_inner)

        # 进入左侧时强制刷新 scrollregion
        self.left_canvas.bind("<Enter>", self._on_left_canvas_enter, add="+")
        self.left_inner.bind("<Enter>", self._on_left_canvas_enter, add="+")

    def _on_left_canvas_enter(self, _event=None) -> None:
        try:
            self._refresh_left_scrollregion()
        except Exception:
            pass

    def _bind_wheel_recursive(self, widget) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                widget.bind(seq, self._on_mousewheel_direct)
            except Exception:
                pass
        try:
            for child in widget.winfo_children():
                self._bind_wheel_recursive(child)
        except Exception:
            pass

    def _refresh_left_scrollregion(self) -> None:
        try:
            self.left_inner.update_idletasks()
            # create_window 的实际需求尺寸
            req_w = max(int(self.left_inner.winfo_reqwidth()), 1)
            req_h = max(int(self.left_inner.winfo_reqheight()), 1)
            bbox = self.left_canvas.bbox("all")
            if bbox:
                # 取 bbox 与 req 的较大高度，避免 scrollregion 偏矮导致“滚不动”
                x0, y0, x1, y1 = bbox
                y1 = max(y1, req_h)
                x1 = max(x1, req_w)
                self.left_canvas.configure(scrollregion=(x0, y0, x1, y1))
            else:
                self.left_canvas.configure(scrollregion=(0, 0, req_w, req_h))
        except Exception:
            pass

    def _pointer_over_left_scroll(self, event=None) -> bool:
        """是否在左侧 Canvas 可视区域内。

        macOS：忽略 event.x_root（触控板事件常不准），始终用实时指针坐标。
        """
        try:
            canvas = self.left_canvas
            # 关键修复：macOS 触控板 + bind_all 时不要信 event.x_root
            x, y = self.root.winfo_pointerxy()
            self.root.update_idletasks()
            cx = int(canvas.winfo_rootx())
            cy = int(canvas.winfo_rooty())
            cw = max(int(canvas.winfo_width()), 0)
            ch = max(int(canvas.winfo_height()), 0)
            if cw <= 1 or ch <= 1:
                return False
            return cx <= x < cx + cw and cy <= y < cy + ch
        except Exception:
            return False

    def _is_over_log_panel(self) -> bool:
        """指针是否在右侧日志 Text 上（此时把滚轮留给日志）。"""
        try:
            x, y = self.root.winfo_pointerxy()
            w = self.root.winfo_containing(x, y)
            log = getattr(self, "log", None)
            while w is not None:
                if log is not None and (w is log or str(w).startswith(str(log))):
                    return True
                # ScrolledText 内部可能是 Text 子控件
                try:
                    cls = w.winfo_class()
                except Exception:
                    cls = ""
                if cls in ("Text", "Listbox") and log is not None:
                    # 粗判：在右侧面板
                    try:
                        if int(w.winfo_rootx()) > int(self.left_canvas.winfo_rootx()) + int(
                            self.left_canvas.winfo_width()
                        ):
                            return True
                    except Exception:
                        pass
                try:
                    w = w.master
                except Exception:
                    break
        except Exception:
            pass
        return False

    def _scroll_left_canvas(self, event) -> str:
        canvas = self.left_canvas
        self._refresh_left_scrollregion()
        try:
            bbox = canvas.bbox("all")
            if not bbox:
                return "break"
            content_h = max(bbox[3] - bbox[1], 1)
            view_h = max(int(canvas.winfo_height()), 1)
            if content_h <= view_h + 2:
                return "break"
        except Exception:
            return "break"

        # --- 方向 ---
        direction = 0  # +1 看下方内容
        num = getattr(event, "num", None)
        if num == 4:
            direction = -1
        elif num == 5:
            direction = 1
        else:
            try:
                # macOS 上 delta 可能是 float
                delta = float(getattr(event, "delta", 0) or 0)
            except Exception:
                delta = 0.0
            if delta == 0:
                return "break"
            # macOS/Windows：delta>0 → 手指上滑 / 滚轮上 → 看上方 → first 减小
            direction = -1 if delta > 0 else 1

        # macOS 触控板：优先用经典 units 公式（社区验证最多）
        if sys.platform == "darwin":
            try:
                delta = float(getattr(event, "delta", 0) or 0)
            except Exception:
                delta = 0.0
            if delta != 0:
                # 触控板 delta 常为 ±1；放大到可感知的步长
                step = int(-delta)
                if step == 0:
                    step = -1 if delta > 0 else 1
                # 一次至少滚 3 units，触控板更跟手
                if abs(step) < 3:
                    step = 3 if step > 0 else -3
                canvas.yview_scroll(step, "units")
                return "break"

        # 其它平台 / 回退：按页比例 moveto
        try:
            first, last = canvas.yview()
            first, last = float(first), float(last)
            page = max(last - first, 0.08)
            step = page * 0.2
            new_first = max(0.0, min(first + direction * step, max(0.0, 1.0 - page)))
            canvas.yview_moveto(new_first)
        except Exception:
            try:
                canvas.yview_scroll(direction * 3, "units")
            except Exception:
                pass
        return "break"

    def _on_mousewheel_direct(self, event):
        """绑在左侧子控件上的直接回调（不依赖指针几何）。"""
        if not getattr(self, "_left_wheel_bound", False):
            return
        return self._scroll_left_canvas(event)

    def _on_mousewheel(self, event):
        return self._on_mousewheel_direct(event)

    def _on_mousewheel_global(self, event):
        if not getattr(self, "_left_wheel_bound", False):
            return
        # 右侧日志优先自己滚
        if self._is_over_log_panel():
            return
        if not self._pointer_over_left_scroll(event):
            return
        return self._scroll_left_canvas(event)

    def _on_left_inner_configure(self, _event=None) -> None:
        self._refresh_left_scrollregion()
        # 子控件变化后重新挂滚轮
        try:
            self._bind_wheel_recursive(self.left_inner)
        except Exception:
            pass

    def _on_left_canvas_configure(self, event) -> None:
        # 内层宽度跟随 canvas，避免横向裁切
        try:
            self.left_canvas.itemconfigure(self._left_win, width=max(event.width, 200))
        except Exception:
            pass
        w = max(event.width - 16, 120)
        for lbl in (self.lbl_fir, self.lbl_metrics):
            try:
                lbl.configure(wraplength=w)
            except Exception:
                pass

    def _on_tip_configure(self, event) -> None:
        # 底栏随左侧面板宽度换行；路径类文字完整显示
        w = max(int(event.width) - 20, 100)
        for lbl in (self.lbl_tip, self.lbl_platform, self.lbl_capture, self.lbl_logs):
            try:
                lbl.configure(wraplength=w)
            except Exception:
                pass

    def _on_root_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        # 顶栏状态在窄窗口时可压缩显示
        try:
            avail = max(event.width - 280, 80)
            self.lbl_status.configure(wraplength=avail)
        except Exception:
            pass

    # ----- 多语言 -----

    def _t(self, key: str, **kwargs) -> str:
        return cp.translate(key, **kwargs)

    def _on_lang_change(self, _event=None) -> None:
        code = self.var_lang.get()
        cp.set_language(code)
        self._apply_language(refresh_dynamic=True)

    def _apply_language(self, refresh_dynamic: bool = False) -> None:
        """刷新所有静态文案；可选刷新依赖状态的动态字符串。"""
        self.root.title(self._t("gui_window_title"))
        self.lbl_title.configure(text=self._t("gui_window_title"))
        self.lbl_lang.configure(text=self._t("gui_language"))

        # Combobox 显示 code，旁注语言名可选
        self.frm_presets.configure(text=self._t("gui_presets"))
        self.btn_refresh.configure(text=self._t("gui_refresh"))
        self.btn_load_preset.configure(text=self._t("gui_load_start"))

        self.frm_cosplay.configure(text=self._t("gui_cosplay"))
        self.lbl_sr.configure(text=self._t("gui_sample_rate"))
        self.lbl_source.configure(text=self._t("gui_source"))
        self.lbl_target.configure(text=self._t("gui_target"))
        self.lbl_playback.configure(text=self._t("gui_playback"))

        self.frm_preamp.configure(text=self._t("gui_preamp"))
        self.rb_safe.configure(text=self._t("gui_preamp_safe"))
        self.rb_mod.configure(text=self._t("gui_preamp_moderate"))
        self.rb_custom.configure(text=self._t("gui_preamp_custom"))
        self.rb_none.configure(text=self._t("gui_preamp_none"))
        self.lbl_custom_db.configure(text=self._t("gui_custom_db"))
        self.chk_debug.configure(text=self._t("gui_debug"))

        self.btn_calc.configure(text=self._t("gui_calc"))
        self.btn_deploy.configure(text=self._t("gui_deploy"))
        self.btn_stop.configure(text=self._t("gui_stop"))
        self.btn_stop_fir.configure(text=self._t("gui_stop_fir"))

        self.frm_peq.configure(text=self._t("gui_peq"))
        self.frm_log.configure(text=self._t("gui_log"))
        # 底栏标题：提示信息（简短）
        self.tip_frame.configure(text=self._t("gui_tip_header"))

        for col, key in (
            ("band", "gui_col_band"),
            ("type", "gui_col_type"),
            ("freq", "gui_col_freq"),
            ("gain", "gui_col_gain"),
            ("q", "gui_col_q"),
        ):
            self.tree.heading(col, text=self._t(key))

        self.var_tip.set(self._t("gui_tip"))
        self.lbl_platform.configure(
            text=f"{self._t('gui_platform')}: {self.system_name} / {self.system_arch}"
        )
        self.lbl_capture.configure(
            text=f"{self._t('gui_capture')}: {self.default_capture}  ({self.backend_type})"
        )
        self.lbl_logs.configure(
            text=f"{self._t('gui_logs_dir')}: {cp.get_logs_dir()}"
        )

        # 恢复状态栏 / FIR / metrics
        if refresh_dynamic:
            self._refresh_status_text()
            self._refresh_result_labels()

        # 触发一次 tip wrap
        self.root.update_idletasks()
        try:
            self._on_tip_configure(
                type("E", (), {"width": self.tip_frame.winfo_width()})()
            )
        except Exception:
            pass

    def _set_status_key(self, key: str, **kwargs) -> None:
        self._status_key = key
        self._status_kwargs = kwargs
        self._refresh_status_text()

    def _refresh_status_text(self) -> None:
        try:
            self.var_status.set(self._t(self._status_key, **self._status_kwargs))
        except Exception:
            self.var_status.set(self._status_key)

    def _refresh_result_labels(self) -> None:
        if not self.correction:
            if hasattr(self, "btn_stop_fir"):
                self.btn_stop_fir.configure(state=DISABLED)
            return
        use_fir = bool(self.correction.get("use_fir"))
        peq_rmse = float(self.correction.get("peq_rmse") or 0)
        comb = float(self.correction.get("combined_rmse") or peq_rmse)
        peak = float(self.correction.get("response_peak") or 0)
        if use_fir:
            taps = int(self.correction.get("fir_n_taps") or 0)
            self.var_fir.set(self._t("gui_fir_on", taps=taps, rmse=comb))
            self.btn_stop_fir.configure(state=NORMAL)
        else:
            self.var_fir.set(self._t("gui_fir_off", rmse=peq_rmse))
            self.btn_stop_fir.configure(state=DISABLED)
        self.var_metrics.set(
            self._t(
                "gui_metrics",
                peak=peak,
                offset=float(self.correction.get("level_offset_db") or 0),
            )
        )

    # ----- 日志 -----

    def _log(self, msg: str) -> None:
        self.log_q.put(msg if msg.endswith("\n") else msg + "\n")

    def _poll_log(self) -> None:
        try:
            while True:
                line = self.log_q.get_nowait()
                self.log.configure(state=NORMAL)
                self.log.insert(END, line)
                self.log.see(END)
                self.log.configure(state=DISABLED)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_log)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = DISABLED if busy else NORMAL
        self.btn_calc.configure(state=state)
        if not busy and self.correction:
            self.btn_deploy.configure(state=NORMAL)
            # FIR 停止按钮仅在 use_fir 时可用
            if bool(self.correction.get("use_fir")):
                self.btn_stop_fir.configure(state=NORMAL)
            else:
                self.btn_stop_fir.configure(state=DISABLED)
        elif busy:
            self.btn_deploy.configure(state=DISABLED)
            self.btn_stop_fir.configure(state=DISABLED)

    # ----- 启动 -----

    def _bootstrap(self) -> None:
        self._set_status_key("gui_status_loading")
        self._refresh_presets()
        self._run_bg(self._load_db_worker, self._on_db_done)

    def _load_db_worker(self):
        return cp.load_autoeq_database()

    def _on_db_done(self, result, err):
        if err:
            self._set_status_key("gui_status_db_fail")
            messagebox.showerror(
                self._t("gui_window_title"),
                self._t("gui_msg_db_fail", error=err),
            )
            return
        cp.AUTOEQ_DATABASE = result or {}
        self.db_ready = bool(cp.AUTOEQ_DATABASE)
        n = len(cp.AUTOEQ_DATABASE) if cp.AUTOEQ_DATABASE else 0
        self._model_count = n
        self._set_status_key("gui_status_ready", count=n)
        self._log(self._t("gui_db_ok", count=n))

    def _refresh_presets(self) -> None:
        try:
            presets = cp.list_saved_presets()
        except Exception:
            presets = []
        labels = [p.name for p in presets]
        self._preset_paths = {p.name: p for p in presets}
        self.preset_combo["values"] = labels
        if labels:
            self.preset_combo.current(0)
        else:
            self.preset_combo.set("")

    # ----- 后台任务 -----

    def _run_bg(self, worker, on_done) -> None:
        def target():
            try:
                res = worker()
                self.root.after(0, lambda: on_done(res, None))
            except Exception as exc:
                tb = traceback.format_exc()
                self.root.after(0, lambda: on_done(None, f"{exc}\n{tb}"))

        threading.Thread(target=target, daemon=True).start()

    def _run_job(self, worker, on_done, status_key: str, **status_kw) -> None:
        if self.busy:
            messagebox.showinfo(
                self._t("gui_window_title"),
                self._t("gui_status_busy_wait"),
            )
            return
        self._set_busy(True)
        self._set_status_key(status_key, **status_kw)

        def target():
            try:
                res = worker()
                self.root.after(0, lambda: self._job_finish(on_done, res, None))
            except Exception as exc:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._job_finish(on_done, None, f"{exc}\n{tb}"))

        threading.Thread(target=target, daemon=True).start()

    def _job_finish(self, on_done, res, err) -> None:
        self._set_busy(False)
        on_done(res, err)

    # ----- 计算 -----

    def _on_calculate(self) -> None:
        if not self.db_ready:
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_db_not_ready")
            )
            return
        src = self.var_source.get().strip()
        tgt = self.var_target.get().strip()
        if not src or not tgt:
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_fill_models")
            )
            return

        source_entry = resolve_headphone_gui(self.root, src, "source")
        if not source_entry:
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_not_found", name=src)
            )
            return
        target_entry = resolve_headphone_gui(self.root, tgt, "target")
        if not target_entry:
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_not_found", name=tgt)
            )
            return

        self.source_entry = source_entry
        self.target_entry = target_entry
        try:
            fs = int(self.var_sr.get())
        except ValueError:
            fs = cp.DEFAULT_SAMPLE_RATE

        def worker():
            temp_dir = Path(tempfile.mkdtemp(prefix="autoeq_gui_"))
            sp = cp.download_headphone_csv(source_entry, temp_dir)
            tp = cp.download_headphone_csv(target_entry, temp_dir)
            if not sp or not tp:
                raise RuntimeError(cp.translate("cannot_generate_peq"))
            cp.print_delta_summary(sp, tp)
            correction = cp.calculate_correction(sp, tp, fs=fs)
            return {"correction": correction, "fs": fs}

        self._run_job(worker, self._on_calc_done, "gui_status_calc")

    def _on_calc_done(self, result, err) -> None:
        if err:
            self._set_status_key("gui_status_calc_fail")
            messagebox.showerror(
                self._t("gui_window_title"),
                self._t("gui_msg_calc_fail", error=err),
            )
            return
        assert result is not None
        self.correction = result["correction"]
        self.peq_list = list(self.correction.get("peq") or [])
        self._fill_peq_table(self.peq_list)
        self._refresh_result_labels()
        self.btn_deploy.configure(state=NORMAL)
        self._set_status_key("gui_status_calc_done")
        self._log(self._t("gui_calc_ok"))

    def _fill_peq_table(self, peq_list: list[dict]) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, band in enumerate(peq_list, start=1):
            self.tree.insert(
                "",
                END,
                values=(
                    idx,
                    band.get("filter_type", ""),
                    f"{float(band.get('frequency', 0)):.1f}",
                    f"{float(band.get('gain', 0)):.2f}",
                    f"{float(band.get('Q', 0)):.2f}",
                ),
            )

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

    # ----- 部署 -----

    def _ensure_runtime_gui(self) -> bool:
        if not cp.is_blackhole_installed():
            cp.localized_print("blackhole_not_installed")
            if self.system_name == "Darwin":
                if messagebox.askyesno(
                    self._t("gui_window_title"), self._t("gui_msg_bh_ask")
                ):
                    if not cp.install_blackhole():
                        messagebox.showwarning(
                            self._t("gui_window_title"), self._t("gui_msg_bh_fail")
                        )
                else:
                    messagebox.showinfo(
                        self._t("gui_window_title"), self._t("gui_msg_bh_later")
                    )
            else:
                messagebox.showinfo(
                    self._t("gui_window_title"), self._t("gui_msg_virt_other")
                )
        else:
            cp.localized_print("blackhole_installed")

        if not cp.is_camilladsp_installed():
            cp.localized_print("camilladsp_not_installed")
            if not messagebox.askyesno(
                self._t("gui_window_title"), self._t("gui_msg_cdsp_ask")
            ):
                return False
            self._set_status_key("gui_status_download")
            self.root.update_idletasks()
            ok = cp.download_camilladsp()
            if not ok:
                messagebox.showerror(
                    self._t("gui_window_title"), self._t("gui_msg_cdsp_fail")
                )
                return False
        else:
            cp.localized_print("camilladsp_installed")
        return True

    def _disable_fir_in_correction(self) -> None:
        """关闭当前计算结果中的 FIR，并按 IIR 响应刷新峰值指标。"""
        if not self.correction:
            return
        self.correction["use_fir"] = False
        self.correction["fir_ir"] = None
        # 峰值改用 IIR 响应（若可算），避免仍按 FIR 联合峰值做 preamp
        try:
            import numpy as np

            fs = float(self.var_sr.get() or cp.DEFAULT_SAMPLE_RATE)
            grid = self.correction.get("grid_freqs")
            if grid is None:
                grid = cp.make_log_freqs(512)
            bands = [
                {
                    "type": b["filter_type"],
                    "frequency": float(b["frequency"]),
                    "gain": float(b["gain"]),
                    "Q": float(b["Q"]),
                }
                for b in self.peq_list
            ]
            peq_resp = cp.peq_response_db(np.asarray(grid, dtype=float), bands, fs=fs)
            self.correction["response_peak"] = float(np.max(peq_resp))
            self.correction["response_valley"] = float(np.min(peq_resp))
            self.correction["combined_rmse"] = float(self.correction.get("peq_rmse") or 0.0)
            self.correction["combined_resp"] = peq_resp
        except Exception:
            pass
        self._refresh_result_labels()

    def _on_stop_fir(self) -> None:
        """关闭 FIR 并以仅 IIR 配置重新部署/启动 CamillaDSP。"""
        if not self.correction or not bool(self.correction.get("use_fir")):
            messagebox.showinfo(
                self._t("gui_window_title"), self._t("gui_msg_stop_fir_need")
            )
            return
        if not self.source_entry or not self.target_entry:
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_need_calc")
            )
            return
        self._disable_fir_in_correction()
        self._log(self._t("gui_fir_stopped_log"))
        # 重新生成 YAML（无 FIR）并重启引擎
        self._on_deploy(status_key="gui_status_stop_fir")

    def _on_deploy(self, status_key: str = "gui_status_deploy") -> None:
        if not self.correction or not self.source_entry or not self.target_entry:
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_need_calc")
            )
            return
        if not self._ensure_runtime_gui():
            return

        # 本 GUI 持有的旧句柄先摘掉；真正杀进程由 run_camilladsp 统一单实例处理
        if self.engine_proc is not None:
            try:
                if self.engine_log:
                    cp.append_camilladsp_log_marker(self.engine_log)
            except Exception:
                pass
            self.engine_proc = None
            self.engine_log = None
            self.btn_stop.configure(state=DISABLED)

        peak = float(self.correction.get("response_peak") or 0.0)
        pre_amp = self._compute_preamp(peak)
        output = self.var_output.get().strip() or self.var_output.get()
        try:
            fs = int(self.var_sr.get())
        except ValueError:
            fs = cp.DEFAULT_SAMPLE_RATE

        use_fir = bool(self.correction.get("use_fir"))
        fir_ir = self.correction.get("fir_ir") if use_fir else None
        peq = list(self.peq_list)
        src, tgt = self.source_entry, self.target_entry
        debug = bool(self.var_debug.get())

        def worker():
            config_path = cp.build_config_path(src, tgt)
            # 关闭 FIR 时不写入 fir_*.wav 引用，生成纯 IIR 流水线
            cp.generate_camilladsp_config(
                peq,
                output,
                config_path,
                pre_amp,
                samplerate=fs,
                backend_type=self.backend_type,
                capture_device=self.default_capture,
                fir_ir=fir_ir,
            )
            if use_fir:
                cp.localized_print("fir_camilladsp_deploy_notice")
            else:
                cp.localized_print("deploy_iir_only_notice")
            # 内部会检测/停止已有 camilladsp，仅在确有停止时提示
            proc, log_path = cp.run_camilladsp(config_path, debug=debug)
            return {
                "config": config_path,
                "proc": proc,
                "log": log_path,
                "use_fir": use_fir,
            }

        self._run_job(worker, self._on_deploy_done, status_key)

    def _on_deploy_done(self, result, err) -> None:
        if err:
            self._set_status_key("gui_status_deploy_fail")
            messagebox.showerror(
                self._t("gui_window_title"),
                self._t("gui_msg_deploy_fail", error=err),
            )
            return
        assert result is not None
        self.last_config = result["config"]
        self.engine_proc = result["proc"]
        self.engine_log = result["log"]
        self._refresh_presets()
        if self.engine_proc is None:
            self._set_status_key("gui_status_engine_fail")
            self.btn_stop.configure(state=DISABLED)
            messagebox.showerror(
                self._t("gui_window_title"), self._t("gui_msg_start_fail")
            )
            return
        self.btn_stop.configure(state=NORMAL)
        self._set_status_key("gui_status_running")
        if result.get("use_fir"):
            cp.localized_print("fir_camilladsp_running_notice")
        cp.localized_print("usage_instructions")
        self._log(self._t("gui_config_ok", path=self.last_config))
        self._watch_engine()

    def _watch_engine(self) -> None:
        proc = self.engine_proc
        if proc is None:
            return
        if proc.poll() is not None:
            self._log(self._t("gui_engine_exit", code=proc.returncode))
            self.btn_stop.configure(state=DISABLED)
            self._set_status_key("gui_status_exited")
            self.engine_proc = None
            return
        self.root.after(800, self._watch_engine)

    def _on_stop(self) -> None:
        if self.engine_proc is None:
            return
        cp.terminate_camilladsp(self.engine_proc, self.engine_log)
        self.engine_proc = None
        self.btn_stop.configure(state=DISABLED)
        self._set_status_key("gui_status_stopped")
        self._log(self._t("gui_engine_stopped"))

    # ----- 预设 -----

    def _load_preset(self) -> None:
        name = self.preset_combo.get().strip()
        if not name or name not in getattr(self, "_preset_paths", {}):
            messagebox.showinfo(
                self._t("gui_window_title"), self._t("gui_msg_pick_preset")
            )
            return
        path = self._preset_paths[name]
        if not self._ensure_runtime_gui():
            return
        # 旧会话句柄交由 run_camilladsp 单实例清理
        if self.engine_proc is not None:
            self.engine_proc = None
            self.engine_log = None
            self.btn_stop.configure(state=DISABLED)
        debug = bool(self.var_debug.get())

        def worker():
            if cp.config_uses_fir_conv(path):
                cp.localized_print("fir_camilladsp_deploy_notice")
            proc, log_path = cp.run_camilladsp(path, debug=debug)
            return {
                "config": path,
                "proc": proc,
                "log": log_path,
                "use_fir": cp.config_uses_fir_conv(path),
            }

        self._run_job(worker, self._on_deploy_done, "gui_status_preset")

    # ----- 关闭 -----

    def _on_close(self) -> None:
        self._left_wheel_bound = False
        try:
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")
        except Exception:
            pass
        try:
            if self.engine_proc is not None and self.engine_proc.poll() is None:
                cp.terminate_camilladsp(self.engine_proc, self.engine_log)
        except Exception:
            pass
        try:
            self._io_writer.close()
        except Exception:
            pass
        sys.stdout = self._stdout_backup
        sys.stderr = self._stderr_backup
        self.root.destroy()


def main() -> None:
    import os

    try:
        os.chdir(_SCRIPT_DIR)
    except Exception as exc:
        _show_startup_error("EQ Cosplay", f"Cannot access project directory:\n{_SCRIPT_DIR}\n\n{exc}")
        raise SystemExit(1) from exc

    _enable_windows_dpi_awareness()

    try:
        logs_dir = cp.get_logs_dir()
    except Exception:
        logs_dir = _SCRIPT_DIR / "logs"

    try:
        root = Tk()
    except Exception as exc:
        _show_startup_error(
            "EQ Cosplay",
            "Failed to create the GUI window (Tk).\n\n"
            f"{exc}\n\n"
            "Windows tips:\n"
            "• Use python.org installer with “tcl/tk and IDLE”\n"
            "• Or run start_cli.bat for the terminal UI\n"
            "• Double-click start.bat (not start.command)",
        )
        raise SystemExit(1) from exc

    try:
        # Reasonable default size; Windows high-DPI handled via awareness + optional scaling
        if sys.platform == "win32":
            try:
                # Mild scaling only when Tk reports a very dense display
                dpi = root.winfo_fpixels("1i")
                if dpi and float(dpi) > 120:
                    root.tk.call("tk", "scaling", float(dpi) / 72.0 * 0.9)
            except Exception:
                pass
        elif sys.platform != "darwin":
            try:
                root.tk.call("tk", "scaling", 1.15)
            except Exception:
                pass

        app = CosplayApp(root)
        app._log(app._t("gui_session_log", path=app.session_log_path))
        app._log(app._t("gui_logs_info", path=logs_dir))
        if sys.platform == "win32":
            app._log("[INFO] Windows: use start.bat to launch GUI; start.command is for macOS/Linux.\n")
        root.mainloop()
    except SystemExit:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            messagebox.showerror("EQ Cosplay", f"{exc}\n\n{tb[:1500]}")
        except Exception:
            _show_startup_error("EQ Cosplay", f"{exc}\n\n{tb[:1500]}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
