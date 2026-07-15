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
        self._fir_toggle_prev: bool | None = None  # 部署失败时回滚 FIR 开关
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
            # 未探测到时优先扬声器类回退，避免写死「外置耳机」导致启动失败
            self.var_output.set(cp.localized_default_playback_label("speakers"))

    def _resolved_output_device(self) -> str:
        """将界面播放设备字段解析为本机真实 CoreAudio 设备名，并回写到输入框。"""
        user = (self.var_output.get() or "").strip()
        detected = None
        available: list[str] = []
        if self.system_name == "Darwin":
            available = cp.list_macos_playback_devices()
            detected = cp.detect_macos_default_playback_device()
        resolved = cp.resolve_playback_device_name(user, detected, available)
        if resolved and resolved != user:
            self.var_output.set(resolved)
            self._log(
                self._t("gui_output_resolved", user=user or "(empty)", device=resolved)
            )
        return resolved

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

        self.left_mid = mid  # 可滚动区域（Canvas + 滚动条），供触控板命中检测
        self.left_canvas = Canvas(mid, highlightthickness=0, borderwidth=0)
        # 显式包装 yview，避免部分 macOS/ttk 主题下滚动条拖动方向异常
        self.left_vsb = ttk.Scrollbar(
            mid, orient=VERTICAL, command=self._left_scrollbar_command
        )
        self.left_canvas.configure(yscrollcommand=self._left_yscrollcommand_set)
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
            bf, text="", command=self._on_toggle_fir, state=DISABLED
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

    def _left_scrollbar_command(self, *args) -> None:
        """滚动条 → Canvas（兼容 moveto / scroll）。"""
        try:
            self.left_canvas.yview(*args)
        except Exception:
            pass

    def _left_yscrollcommand_set(self, first, last) -> None:
        """Canvas → 滚动条位置同步。"""
        try:
            self.left_vsb.set(first, last)
        except Exception:
            pass

    def _setup_left_mousewheel(self) -> None:
        """左侧核心菜单滚动（兼容 Tk 8.x 鼠标滚轮 + Tk 9 触控板）。

        关键：Homebrew Tcl/Tk **9.0**（TIP 684）起，Mac 触控板双指滑动
        发送的是 ``<TouchpadScroll>``，**不再**发送 ``<MouseWheel>``。
        旧逻辑只绑 MouseWheel，所以触控板完全无反应，只有拖滚动条有效。
        """
        if not hasattr(self, "left_canvas"):
            return
        self._left_wheel_bound = True
        self._left_wheel_last_serial = None

        # --- 全局：Tk 9 触控板（必须）---
        try:
            self.root.bind_all(
                "<TouchpadScroll>", self._on_touchpad_scroll_global, add="+"
            )
        except Exception:
            pass
        # --- 全局：传统鼠标滚轮 / 旧 Tk 触控板回退 ---
        self.root.bind_all("<MouseWheel>", self._on_mousewheel_global, add="+")
        self.root.bind_all("<Button-4>", self._on_mousewheel_global, add="+")
        self.root.bind_all("<Button-5>", self._on_mousewheel_global, add="+")
        try:
            self.root.bind_all(
                "<Shift-MouseWheel>", self._on_mousewheel_global, add="+"
            )
        except Exception:
            pass

        # 左侧子树直接绑定（覆盖 Treeview 等默认 TouchpadScroll，避免只滚表格）
        targets = [self.left_canvas, self.left_inner]
        if getattr(self, "left_mid", None) is not None:
            targets.append(self.left_mid)
        if getattr(self, "left_vsb", None) is not None:
            targets.append(self.left_vsb)
        for w in targets:
            self._bind_wheel_recursive(w)

        self.left_canvas.bind("<Enter>", self._on_left_canvas_enter, add="+")
        self.left_inner.bind("<Enter>", self._on_left_canvas_enter, add="+")
        if getattr(self, "left_mid", None) is not None:
            self.left_mid.bind("<Enter>", self._on_left_canvas_enter, add="+")

    def _on_left_canvas_enter(self, _event=None) -> None:
        try:
            self._refresh_left_scrollregion()
        except Exception:
            pass
        # 进入左侧时清掉触控板 scan 连续态，避免跨区域手势粘连
        self._left_scan_active = False

    def _bind_wheel_recursive(self, widget) -> None:
        # TouchpadScroll：Tk 9 触控板；MouseWheel：鼠标 / 旧 Tk
        for seq in (
            "<TouchpadScroll>",
            "<MouseWheel>",
            "<Button-4>",
            "<Button-5>",
        ):
            try:
                if seq == "<TouchpadScroll>":
                    widget.bind(seq, self._on_touchpad_scroll_direct)
                else:
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
            req_w = max(int(self.left_inner.winfo_reqwidth()), 1)
            req_h = max(int(self.left_inner.winfo_reqheight()), 1)
            try:
                cw = max(int(self.left_canvas.winfo_width()), 1)
            except Exception:
                cw = req_w
            # 始终用 (0,0) 起点，避免 bbox 负偏移导致滚动条拖动方向反了
            self.left_canvas.configure(scrollregion=(0, 0, max(req_w, cw), req_h))
        except Exception:
            pass
        self._invalidate_left_scroll_cache()
        self._left_scan_active = False

    def _widget_is_descendant_of(self, widget, ancestors) -> bool:
        """判断 widget 是否属于 ancestors 中任一控件的子树。"""
        if widget is None:
            return False
        try:
            anc_set = set(ancestors)
        except Exception:
            anc_set = {a for a in ancestors if a is not None}
        w = widget
        seen = set()
        while w is not None and id(w) not in seen:
            seen.add(id(w))
            if w in anc_set:
                return True
            try:
                path = str(w)
                for a in anc_set:
                    try:
                        if path == str(a) or path.startswith(str(a) + "."):
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                parent = w.winfo_parent()
                w = w.nametowidget(parent) if parent else None
            except Exception:
                break
        return False

    def _left_scroll_ancestors(self) -> list:
        items = []
        for name in ("left_mid", "left_canvas", "left_inner", "left_vsb", "left"):
            w = getattr(self, name, None)
            if w is not None:
                items.append(w)
        return items

    def _pointer_over_left_scroll(self, event=None) -> bool:
        """是否应把滚轮交给左侧核心菜单（Canvas + 滚动条整块）。"""
        ancestors = self._left_scroll_ancestors()
        if not ancestors:
            return False

        # 1) event.widget 祖先链（子树直接绑定时最可靠）
        w = getattr(event, "widget", None) if event is not None else None
        if self._widget_is_descendant_of(w, ancestors):
            return True

        # 2) 指针下控件
        try:
            x, y = self.root.winfo_pointerxy()
            containing = self.root.winfo_containing(x, y)
            if self._widget_is_descendant_of(containing, ancestors):
                return True
        except Exception:
            x = y = None

        # 3) 几何命中：整个 mid（含滚动条），不单 Canvas
        try:
            if x is None or y is None:
                x, y = self.root.winfo_pointerxy()
            area = getattr(self, "left_mid", None) or self.left_canvas
            ax = int(area.winfo_rootx())
            ay = int(area.winfo_rooty())
            aw = max(int(area.winfo_width()), 0)
            ah = max(int(area.winfo_height()), 0)
            if aw > 1 and ah > 1 and ax <= x < ax + aw and ay <= y < ay + ah:
                return True
        except Exception:
            pass
        return False

    def _is_over_log_panel(self) -> bool:
        """指针是否在右侧日志上（此时把滚轮留给日志）。"""
        try:
            x, y = self.root.winfo_pointerxy()
            w = self.root.winfo_containing(x, y)
            log = getattr(self, "log", None)
            frm = getattr(self, "frm_log", None)
            while w is not None:
                if log is not None and (w is log or str(w).startswith(str(log))):
                    return True
                if frm is not None and (w is frm or str(w).startswith(str(frm))):
                    return True
                try:
                    cls = w.winfo_class()
                except Exception:
                    cls = ""
                # 仅当明确在右侧日志区的 Text 才放行；不要把左侧 Treeview 误判成日志
                if cls == "Text" and log is not None:
                    try:
                        if int(w.winfo_rootx()) >= int(self.right.winfo_rootx()):
                            return True
                    except Exception:
                        pass
                try:
                    parent = w.winfo_parent()
                    w = w.nametowidget(parent) if parent else None
                except Exception:
                    break
        except Exception:
            pass
        return False

    def _invalidate_left_scroll_cache(self) -> None:
        self._left_scroll_cache = None  # (content_h, view_h, can_scroll)

    def _left_scroll_metrics(self, *, force: bool = False) -> tuple[float, float, bool]:
        """缓存内容高度 / 视口高度，避免触控板 60Hz 下反复 update_idletasks。"""
        cache = getattr(self, "_left_scroll_cache", None)
        if cache is not None and not force:
            return cache
        canvas = self.left_canvas
        content_h = 1.0
        view_h = 1.0
        try:
            sr = str(canvas.cget("scrollregion")).split()
            if len(sr) == 4:
                content_h = max(float(sr[3]) - float(sr[1]), 1.0)
        except Exception:
            pass
        if content_h <= 1.0:
            try:
                content_h = float(max(int(self.left_inner.winfo_reqheight()), 1))
            except Exception:
                content_h = 1.0
        try:
            view_h = float(max(int(canvas.winfo_height()), 1))
        except Exception:
            view_h = 1.0
        can = content_h > view_h + 2.0
        if not can:
            try:
                first, last = canvas.yview()
                can = float(last) - float(first) < 0.999
            except Exception:
                can = True
        self._left_scroll_cache = (content_h, view_h, can)
        return self._left_scroll_cache

    def _left_canvas_can_scroll(self) -> bool:
        return self._left_scroll_metrics()[2]

    def _left_content_height(self) -> int:
        return int(self._left_scroll_metrics()[0])

    def _precise_scroll_deltas(self, event) -> tuple[float, float]:
        """解析 TouchpadScroll / MouseWheel 的 (deltaX, deltaY)。

        Tk 9：``tk::PreciseScrollDeltas %D``；失败则退回 event.delta。
        """
        d = getattr(event, "delta", 0)
        try:
            parts = self.root.tk.splitlist(
                self.root.tk.call("tk::PreciseScrollDeltas", d)
            )
            if len(parts) >= 2:
                return float(parts[0]), float(parts[1])
        except Exception:
            pass
        try:
            return 0.0, float(d or 0)
        except Exception:
            return 0.0, 0.0

    def _scroll_left_by_pixels(self, delta_y: float) -> None:
        """按触控板像素增量滚动左侧 Canvas（跟手）。

        使用 Canvas ``scan_mark`` / ``scan_dragto`` 做 1:1 像素拖动，
        比反复 yview_moveto + update_idletasks 更跟手、更少掉帧。
        手势间歇 >120ms 视为新滑动并重置 mark。
        """
        if delta_y == 0:
            return
        canvas = self.left_canvas
        content_h, view_h, can = self._left_scroll_metrics()
        if not can:
            return

        try:
            scaled = float(self.root.tk.call("tk::ScaleNum", delta_y))
        except Exception:
            scaled = float(delta_y)
        if scaled == 0:
            return

        import time as _time

        now = _time.monotonic()
        last_t = float(getattr(self, "_left_scan_t", 0.0) or 0.0)
        # 新双指手势：重置 scan 原点
        if (
            not getattr(self, "_left_scan_active", False)
            or (now - last_t) > 0.12
        ):
            try:
                canvas.scan_mark(0, 0)
            except Exception:
                pass
            self._left_scan_y = 0
            self._left_scan_active = True
        self._left_scan_t = now

        # Text 默认：yview scroll -$deltaY pixels。
        # 实测 scan_dragto(0, +N) 与「scroll -N pixels」同向（first 减小看上方）。
        try:
            step = int(round(scaled))
            if step == 0:
                step = 1 if scaled > 0 else -1
            self._left_scan_y = int(getattr(self, "_left_scan_y", 0)) + step
            canvas.scan_dragto(0, self._left_scan_y, gain=1)
        except Exception:
            # 回退 moveto（不刷新 layout）
            try:
                first, last = canvas.yview()
                first, last = float(first), float(last)
                page = last - first
                if page < 1e-6:
                    page = min(1.0, view_h / max(content_h, 1.0))
                frac = (-scaled) / max(content_h, 1.0)
                canvas.yview_moveto(
                    max(0.0, min(first + frac, max(0.0, 1.0 - page)))
                )
            except Exception:
                pass

    def _scroll_left_canvas(self, event) -> str:
        """传统 MouseWheel / Button-4/5。"""
        canvas = self.left_canvas
        if not self._left_canvas_can_scroll():
            return "break"

        serial = getattr(event, "serial", None)
        if serial is not None and serial == getattr(self, "_left_wheel_last_serial", None):
            return "break"
        self._left_wheel_last_serial = serial
        # 鼠标滚轮与触控板手势分开，打断 scan 连续态
        self._left_scan_active = False

        num = getattr(event, "num", None)
        try:
            delta = float(getattr(event, "delta", 0) or 0)
        except Exception:
            delta = 0.0

        units = 0
        if num == 4:
            units = -3
        elif num == 5:
            units = 3
        elif delta != 0:
            if sys.platform == "darwin":
                step = int(-delta)
                if step == 0:
                    step = -1 if delta > 0 else 1
                if abs(step) == 1:
                    step = 2 if step > 0 else -2
                units = max(-15, min(15, step))
            else:
                step = int(-delta / 120)
                if step == 0:
                    step = -1 if delta > 0 else 1
                units = step * 3
        else:
            return "break"

        try:
            canvas.yview_scroll(units, "units")
        except Exception:
            try:
                first, last = canvas.yview()
                page = max(float(last) - float(first), 0.08)
                direction = 1 if units > 0 else -1
                new_first = max(
                    0.0,
                    min(float(first) + direction * page * 0.15, max(0.0, 1.0 - page)),
                )
                canvas.yview_moveto(new_first)
            except Exception:
                pass
        return "break"

    def _scroll_left_touchpad(self, event) -> str:
        """Tk 9 ``<TouchpadScroll>``：双指滑动主路径（低开销、跟手）。"""
        serial = getattr(event, "serial", None)
        if serial is not None and serial == getattr(self, "_left_wheel_last_serial", None):
            return "break"
        self._left_wheel_last_serial = serial

        if not self._left_canvas_can_scroll():
            return "break"

        _dx, dy = self._precise_scroll_deltas(event)
        if dy == 0:
            return "break"

        self._scroll_left_by_pixels(dy)
        return "break"

    def _on_touchpad_scroll_direct(self, event):
        """左侧子控件上的触控板事件：已在左栏，跳过昂贵的指针命中检测。"""
        if not getattr(self, "_left_wheel_bound", False):
            return
        return self._scroll_left_touchpad(event)

    def _on_touchpad_scroll_global(self, event):
        if not getattr(self, "_left_wheel_bound", False):
            return
        # 快速路径：event.widget 已在左侧子树则不必查指针
        if self._widget_is_descendant_of(
            getattr(event, "widget", None), self._left_scroll_ancestors()
        ):
            return self._scroll_left_touchpad(event)
        if self._is_over_log_panel():
            return
        if not self._pointer_over_left_scroll(event):
            return
        return self._scroll_left_touchpad(event)

    def _on_mousewheel_direct(self, event):
        """绑在左侧子控件上的直接回调（鼠标滚轮）。"""
        if not getattr(self, "_left_wheel_bound", False):
            return
        if self._is_over_log_panel():
            return
        return self._scroll_left_canvas(event)

    def _on_mousewheel(self, event):
        return self._on_mousewheel_direct(event)

    def _on_mousewheel_global(self, event):
        if not getattr(self, "_left_wheel_bound", False):
            return
        if self._is_over_log_panel():
            return
        if not self._pointer_over_left_scroll(event):
            return
        return self._scroll_left_canvas(event)

    def _on_left_inner_configure(self, _event=None) -> None:
        self._refresh_left_scrollregion()
        # 子控件变化后重新挂滚轮（语言切换 / 动态控件）
        try:
            self._bind_wheel_recursive(self.left_inner)
            if getattr(self, "left_mid", None) is not None:
                self._bind_wheel_recursive(self.left_mid)
        except Exception:
            pass

    def _on_left_canvas_configure(self, event) -> None:
        # 内层宽度跟随 canvas，避免横向裁切
        try:
            self.left_canvas.itemconfigure(self._left_win, width=max(event.width, 200))
        except Exception:
            pass
        self._refresh_left_scrollregion()
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
        self._refresh_fir_button()

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

    def _config_path_for_fir(self) -> Path | None:
        """当前可用于 FIR 开关的 YAML 路径（计算结果或最近部署/加载的预设）。"""
        if self.source_entry and self.target_entry:
            try:
                return cp.build_config_path(self.source_entry, self.target_entry)
            except Exception:
                pass
        if self.last_config and Path(self.last_config).is_file():
            return Path(self.last_config)
        return None

    def _has_fir_data(self) -> bool:
        """是否仍有可重新开启的 FIR（内存冲激 或 磁盘 companion WAV）。"""
        if self.correction:
            fir_ir = self.correction.get("fir_ir")
            try:
                if fir_ir is not None and len(fir_ir) > 0:
                    return True
            except Exception:
                pass
        path = self._config_path_for_fir()
        if path is not None and cp.config_has_companion_fir_wavs(path):
            return True
        return False

    def _fir_currently_on(self) -> bool:
        if self.correction is not None:
            return bool(self.correction.get("use_fir"))
        path = self._config_path_for_fir()
        if path is not None:
            return cp.config_uses_fir_conv(path)
        return False

    def _refresh_fir_button(self) -> None:
        """按 FIR 开/关状态切换按钮文案（停止 FIR / 开启 FIR）与可用性。"""
        if not hasattr(self, "btn_stop_fir"):
            return
        has_fir = self._has_fir_data()
        use_fir = self._fir_currently_on()
        if has_fir and use_fir:
            label_key = "gui_stop_fir"
        elif has_fir:
            label_key = "gui_enable_fir"
        else:
            label_key = "gui_stop_fir"
        state = NORMAL if (has_fir and not self.busy) else DISABLED
        self.btn_stop_fir.configure(text=self._t(label_key), state=state)

    @staticmethod
    def _fmt_rmse(value) -> str:
        """格式化 RMSE；未知时显示 —，避免误显示 0.00 dB。"""
        if value is None:
            return "—"
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "—"
        # 未写入指标时 correction 里可能残留显式 None；0.0 可能是真实完美拟合（极少）
        return f"{v:.3f} dB"

    @staticmethod
    def _metric_float(correction: dict | None, key: str):
        """读取指标；键不存在或为 None 时返回 None（不要用 or 0 吞掉合法值）。"""
        if not correction or key not in correction:
            return None
        val = correction.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _apply_metrics_dict(self, metrics: dict | None, *, prefer_existing: bool = True) -> None:
        """把预设/摘要中的指标合并进 self.correction。"""
        if not metrics:
            return
        if self.correction is None:
            self.correction = {
                "use_fir": bool(metrics.get("use_fir", False)),
                "peq": [],
            }
        for key in (
            "peq_rmse",
            "combined_rmse",
            "fir_rmse",
            "response_peak",
            "response_valley",
            "iir_response_peak",
            "fir_response_peak",
            "level_offset_db",
            "fir_n_taps",
        ):
            if key not in metrics or metrics[key] is None:
                continue
            if prefer_existing and self.correction.get(key) is not None:
                try:
                    existing = self.correction.get(key)
                    if existing is not None and float(existing) != 0.0:
                        # combined_rmse：若现有值几乎等于 peq_rmse（被 IIR 模式污染），
                        # 而磁盘有更好的联合 RMSE，则允许覆盖
                        if key == "combined_rmse":
                            peq_v = self._metric_float(self.correction, "peq_rmse")
                            incoming = float(metrics[key])
                            if (
                                peq_v is not None
                                and abs(float(existing) - peq_v) < 1e-9
                                and incoming + 1e-12 < peq_v
                            ):
                                pass  # fall through to write
                            else:
                                continue
                        else:
                            continue
                except (TypeError, ValueError):
                    pass
            try:
                if key == "fir_n_taps":
                    self.correction[key] = int(metrics[key])
                else:
                    self.correction[key] = float(metrics[key])
            except (TypeError, ValueError):
                pass
        # 规范快照键：有 combined 时同步 fir_combined_rmse（仅当尚未有更好快照）
        comb = self._metric_float(self.correction, "combined_rmse")
        peq = self._metric_float(self.correction, "peq_rmse")
        if comb is not None and (peq is None or abs(comb - peq) > 1e-9):
            snap = self._metric_float(self.correction, "fir_combined_rmse")
            if snap is None or snap > comb:
                self.correction["fir_combined_rmse"] = comb
        if self.correction.get("fir_response_peak") is None and metrics.get(
            "fir_response_peak"
        ) is not None:
            try:
                self.correction["fir_response_peak"] = float(metrics["fir_response_peak"])
            except (TypeError, ValueError):
                pass
        if self.correction.get("iir_response_peak") is None and metrics.get(
            "iir_response_peak"
        ) is not None:
            try:
                self.correction["iir_response_peak"] = float(metrics["iir_response_peak"])
            except (TypeError, ValueError):
                pass

    def _display_rmse_for_mode(self, use_fir: bool):
        """按当前模式选择应显示的 RMSE（FIR→联合，IIR→peq）。"""
        peq_rmse = self._metric_float(self.correction, "peq_rmse")
        # 联合值：优先永不被 IIR 模式污染的快照
        comb = self._metric_float(self.correction, "fir_combined_rmse")
        if comb is None:
            comb = self._metric_float(self.correction, "combined_rmse")
        if use_fir:
            return comb if comb is not None else peq_rmse
        return peq_rmse

    def _display_peak_for_mode(self, use_fir: bool):
        """按模式选择 preamp/显示用的响应峰值。"""
        if use_fir:
            peak = self._metric_float(self.correction, "fir_response_peak")
            if peak is None:
                peak = self._metric_float(self.correction, "response_peak")
            return peak
        peak = self._metric_float(self.correction, "iir_response_peak")
        if peak is None:
            peak = self._metric_float(self.correction, "response_peak")
        return peak

    def _refresh_result_labels(self) -> None:
        if not self.correction:
            # 无 correction 时仍可能通过磁盘 WAV 切换 FIR（加载预设场景）
            path = self._config_path_for_fir()
            if path is not None and (
                cp.config_has_companion_fir_wavs(path) or cp.config_uses_fir_conv(path)
            ):
                metrics = cp.load_config_metrics(path)
                peq_rmse = metrics.get("peq_rmse")
                comb = metrics.get("combined_rmse")
                if comb is None:
                    comb = peq_rmse
                taps = int(metrics.get("fir_n_taps") or 0)
                if taps <= 0 and cp.config_has_companion_fir_wavs(path):
                    _ir, _sr = cp.load_fir_ir_from_companion_wavs(path)
                    taps = int(len(_ir)) if _ir is not None else 0
                fir_on = cp.config_uses_fir_conv(path)
                if fir_on:
                    self.var_fir.set(
                        self._t(
                            "gui_fir_on",
                            taps=taps,
                            rmse=self._fmt_rmse(comb),
                        )
                    )
                else:
                    self.var_fir.set(
                        self._t(
                            "gui_fir_paused",
                            rmse=self._fmt_rmse(peq_rmse),
                        )
                    )
                if fir_on:
                    peak = metrics.get("fir_response_peak", metrics.get("response_peak"))
                else:
                    peak = metrics.get("iir_response_peak", metrics.get("response_peak"))
                offset = metrics.get("level_offset_db")
                if peak is not None or offset is not None:
                    try:
                        self.var_metrics.set(
                            self._t(
                                "gui_metrics",
                                peak=float(peak or 0.0),
                                offset=float(offset or 0.0),
                            )
                        )
                    except Exception:
                        pass
            else:
                self.var_fir.set("")
            self._refresh_fir_button()
            return
        use_fir = bool(self.correction.get("use_fir"))
        rmse_show = self._display_rmse_for_mode(use_fir)
        peak = self._display_peak_for_mode(use_fir)
        offset = self._metric_float(self.correction, "level_offset_db")
        if use_fir:
            taps = int(self.correction.get("fir_n_taps") or 0)
            self.var_fir.set(
                self._t("gui_fir_on", taps=taps, rmse=self._fmt_rmse(rmse_show))
            )
        elif self._has_fir_data():
            self.var_fir.set(
                self._t("gui_fir_paused", rmse=self._fmt_rmse(rmse_show))
            )
        else:
            self.var_fir.set(
                self._t("gui_fir_off", rmse=self._fmt_rmse(rmse_show))
            )
        self._refresh_fir_button()
        if peak is not None or offset is not None:
            self.var_metrics.set(
                self._t(
                    "gui_metrics",
                    peak=float(peak if peak is not None else 0.0),
                    offset=float(offset if offset is not None else 0.0),
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
            # FIR 切换按钮：有 FIR 数据时可停止或重新开启
            self._refresh_fir_button()
        elif busy:
            self.btn_deploy.configure(state=DISABLED)
            self.btn_stop_fir.configure(state=DISABLED)
        else:
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

    def _run_job(self, worker, on_done, status_key: str, **status_kw) -> bool:
        if self.busy:
            messagebox.showinfo(
                self._t("gui_window_title"),
                self._t("gui_status_busy_wait"),
            )
            return False
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
        return True

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
        # 固化 FIR / IIR 两套指标，开关模式时互不覆盖
        try:
            comb = self._metric_float(self.correction, "combined_rmse")
            peq = self._metric_float(self.correction, "peq_rmse")
            peak = self._metric_float(self.correction, "response_peak")
            if comb is not None:
                self.correction["fir_combined_rmse"] = comb
            if peak is not None and bool(self.correction.get("use_fir")):
                self.correction["fir_response_peak"] = peak
            elif peak is not None:
                self.correction["iir_response_peak"] = peak
            # 无 FIR 时 combined == peq，仍保留 peq 供显示
            if peq is not None and not bool(self.correction.get("use_fir")):
                self.correction["iir_response_peak"] = (
                    peak if peak is not None else self.correction.get("iir_response_peak")
                )
        except Exception:
            pass
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

    def _peq_bands_for_response(self) -> list[dict]:
        return [
            {
                "type": b["filter_type"],
                "frequency": float(b["frequency"]),
                "gain": float(b["gain"]),
                "Q": float(b["Q"]),
            }
            for b in self.peq_list
        ]

    def _disable_fir_in_correction(self) -> None:
        """关闭 FIR 显示/部署标志。

        不修改 peq_rmse / combined_rmse 数值本身——两套 RMSE 始终保留，
        界面按 use_fir 选择展示哪一个。
        """
        if not self.correction:
            return
        # 首次关闭时固化 FIR 联合指标快照（之后反复开关也不丢）
        if self._has_fir_data():
            comb = self._metric_float(self.correction, "combined_rmse")
            peq = self._metric_float(self.correction, "peq_rmse")
            # 仅当 combined 看起来是真正的联合值（与 peq 不同或尚无快照）时写入
            if comb is not None:
                snap = self._metric_float(self.correction, "fir_combined_rmse")
                if snap is None or (
                    peq is not None and abs(comb - peq) > 1e-9 and comb < snap
                ):
                    if peq is None or abs(comb - peq) > 1e-9:
                        self.correction["fir_combined_rmse"] = comb
            peak = self._metric_float(self.correction, "response_peak")
            if peak is not None and self.correction.get("fir_response_peak") is None:
                if bool(self.correction.get("use_fir")):
                    self.correction["fir_response_peak"] = peak
            if self.correction.get("fir_response_valley") is None and bool(
                self.correction.get("use_fir")
            ):
                self.correction["fir_response_valley"] = self.correction.get(
                    "response_valley"
                )
            if self.correction.get("fir_combined_resp") is None and bool(
                self.correction.get("use_fir")
            ):
                self.correction["fir_combined_resp"] = self.correction.get(
                    "combined_resp"
                )

        self.correction["use_fir"] = False
        # 故意保留 fir_ir / fir_n_taps / combined_rmse，供「开启 FIR」与指标显示
        try:
            import numpy as np

            fs = float(self.var_sr.get() or cp.DEFAULT_SAMPLE_RATE)
            grid = self.correction.get("grid_freqs")
            if grid is None:
                grid = cp.make_log_freqs(512)
            peq_resp = cp.peq_response_db(
                np.asarray(grid, dtype=float), self._peq_bands_for_response(), fs=fs
            )
            iir_peak = float(np.max(peq_resp))
            iir_valley = float(np.min(peq_resp))
            self.correction["iir_response_peak"] = iir_peak
            self.correction["iir_response_valley"] = iir_valley
            # response_peak 用于 preamp：IIR 模式用 IIR 峰
            self.correction["response_peak"] = iir_peak
            self.correction["response_valley"] = iir_valley
            # 绝不把 combined_rmse 改成 peq_rmse
        except Exception:
            pass
        self._refresh_result_labels()

    def _enable_fir_in_correction(self) -> None:
        """重新开启 FIR：恢复联合峰值；RMSE 显示走 fir_combined_rmse / combined_rmse。"""
        if not self.correction or not self._has_fir_data():
            return
        self.correction["use_fir"] = True

        # 恢复联合 RMSE（若曾被旧逻辑污染成 peq_rmse）
        snap_rmse = self._metric_float(self.correction, "fir_combined_rmse")
        peq_rmse = self._metric_float(self.correction, "peq_rmse")
        comb = self._metric_float(self.correction, "combined_rmse")
        if snap_rmse is not None:
            self.correction["combined_rmse"] = snap_rmse
        elif comb is not None and peq_rmse is not None and abs(comb - peq_rmse) < 1e-9:
            # combined 已被污染且无快照：无法还原真实联合值，保持 peq 并在 UI 用 —
            pass

        peak = self._metric_float(self.correction, "fir_response_peak")
        valley = self.correction.get("fir_response_valley")
        comb_resp = self.correction.get("fir_combined_resp")
        if peak is not None:
            self.correction["response_peak"] = float(peak)
            if valley is not None:
                try:
                    self.correction["response_valley"] = float(valley)
                except (TypeError, ValueError):
                    pass
            if comb_resp is not None:
                self.correction["combined_resp"] = comb_resp
        else:
            try:
                import numpy as np

                fs = float(self.var_sr.get() or cp.DEFAULT_SAMPLE_RATE)
                grid = self.correction.get("grid_freqs")
                if grid is None:
                    grid = cp.make_log_freqs(512)
                grid_arr = np.asarray(grid, dtype=float)
                peq_resp = cp.peq_response_db(
                    grid_arr, self._peq_bands_for_response(), fs=fs
                )
                fir_resp = cp.fir_response_db(
                    grid_arr, self.correction["fir_ir"], fs=fs
                )
                combined = peq_resp + fir_resp
                fir_peak = float(np.max(combined))
                fir_valley = float(np.min(combined))
                self.correction["response_peak"] = fir_peak
                self.correction["response_valley"] = fir_valley
                self.correction["fir_response_peak"] = fir_peak
                self.correction["fir_response_valley"] = fir_valley
                self.correction["combined_resp"] = combined
                self.correction["fir_combined_resp"] = combined
            except Exception:
                pass
        self._refresh_result_labels()

    def _ensure_fir_ir_in_correction(self) -> bool:
        """保证 correction['fir_ir'] 可用：优先内存，否则从 companion WAV 加载。"""
        if self._has_fir_data() and self.correction:
            fir_ir = self.correction.get("fir_ir")
            try:
                if fir_ir is not None and len(fir_ir) > 0:
                    return True
            except Exception:
                pass
        path = self._config_path_for_fir()
        if path is None:
            return False
        ir, wav_sr = cp.load_fir_ir_from_companion_wavs(path)
        if ir is None:
            return False
        if self.correction is None:
            self.correction = {"use_fir": False}
            # 从预设注释恢复 RMSE，避免占位 0.00
            self._apply_metrics_dict(cp.load_config_metrics(path), prefer_existing=False)
        self.correction["fir_ir"] = ir
        self.correction["fir_n_taps"] = int(len(ir))
        if wav_sr:
            self.correction["fir_wav_sr"] = int(wav_sr)
        return True

    def _revert_fir_flag(self, use_fir: bool) -> None:
        """部署失败时把 use_fir 标志恢复到切换前。"""
        if self.correction is not None:
            self.correction["use_fir"] = bool(use_fir)
            if use_fir and self.correction.get("fir_response_peak") is not None:
                self.correction["response_peak"] = self.correction.get(
                    "fir_response_peak"
                )
                self.correction["combined_rmse"] = self.correction.get(
                    "fir_combined_rmse", self.correction.get("combined_rmse")
                )
        self._refresh_result_labels()

    def _on_toggle_fir(self) -> None:
        """切换 FIR：关闭后按钮变为「开启 FIR」，可再次部署带 FIR 的链路。

        支持两条路径：
        1) 本会话已计算（correction + source/target）→ 完整重新生成
        2) 仅加载了带 companion WAV 的预设 → 解析 YAML 后开关 FIR（修复扬声器场景下
           无 correction 时无法重新开启的问题）
        """
        if self.busy:
            messagebox.showinfo(
                self._t("gui_window_title"), self._t("gui_status_busy_wait")
            )
            return

        has_disk_or_mem = self._has_fir_data()
        if not has_disk_or_mem:
            messagebox.showinfo(
                self._t("gui_window_title"),
                self._t(
                    "gui_msg_enable_fir_need"
                    if not self._fir_currently_on()
                    else "gui_msg_stop_fir_need"
                ),
            )
            return

        currently_on = self._fir_currently_on()
        want_fir = not currently_on
        self._fir_toggle_prev = currently_on

        # 开启时确保内存中有 ir（可从磁盘 WAV 恢复）
        if want_fir and not self._ensure_fir_ir_in_correction():
            # 无 correction 也可以走磁盘 regenerate 路径
            path = self._config_path_for_fir()
            if path is None or not cp.config_has_companion_fir_wavs(path):
                self._fir_toggle_prev = None
                messagebox.showinfo(
                    self._t("gui_window_title"), self._t("gui_msg_enable_fir_need")
                )
                return

        # 路径 A：有完整计算结果 → 改 correction 后走标准部署
        if self.correction and self.source_entry and self.target_entry and self.peq_list:
            if want_fir:
                self._enable_fir_in_correction()
                self._log(self._t("gui_fir_enabled_log"))
                self._on_deploy(
                    status_key="gui_status_enable_fir",
                    fir_toggle_prev=currently_on,
                )
            else:
                self._disable_fir_in_correction()
                self._log(self._t("gui_fir_stopped_log"))
                self._on_deploy(
                    status_key="gui_status_stop_fir",
                    fir_toggle_prev=currently_on,
                )
            return

        # 路径 B：仅有预设 YAML + companion WAV（常见：加载预设后在扬声器上开关 FIR）
        path = self._config_path_for_fir()
        if path is None or not Path(path).is_file():
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_need_calc")
            )
            return
        if not self._ensure_runtime_gui():
            return

        if self.engine_proc is not None:
            try:
                if self.engine_log:
                    cp.append_camilladsp_log_marker(self.engine_log)
            except Exception:
                pass
            self.engine_proc = None
            self.engine_log = None
            self.btn_stop.configure(state=DISABLED)

        output = self._resolved_output_device()
        debug = bool(self.var_debug.get())
        fir_ir = None
        if self.correction:
            fir_ir = self.correction.get("fir_ir")
        status_key = "gui_status_enable_fir" if want_fir else "gui_status_stop_fir"
        self._log(
            self._t("gui_fir_enabled_log" if want_fir else "gui_fir_stopped_log")
        )

        # 先更新 UI 标志，失败时在 done 里回滚
        if self.correction is not None:
            if want_fir:
                self._enable_fir_in_correction()
            else:
                self._disable_fir_in_correction()
        else:
            self._refresh_fir_button()

        def worker():
            summary = cp.regenerate_config_fir_mode(
                path,
                use_fir=want_fir,
                output_device=output,
                fir_ir=fir_ir if want_fir else None,
            )
            cp.localized_print("output_device_set", device=output)
            if want_fir:
                cp.localized_print("fir_camilladsp_deploy_notice")
            else:
                cp.localized_print("deploy_iir_only_notice")
            proc, log_path = cp.run_camilladsp(path, debug=debug)
            return {
                "config": path,
                "proc": proc,
                "log": log_path,
                "use_fir": want_fir,
                "fir_toggle_prev": currently_on,
                "fir_summary": summary,
            }

        if not self._run_job(worker, self._on_deploy_done, status_key):
            self._revert_fir_flag(currently_on)
            self._fir_toggle_prev = None

    def _on_deploy(
        self,
        status_key: str = "gui_status_deploy",
        fir_toggle_prev: bool | None = None,
    ) -> None:
        if not self.correction or not self.source_entry or not self.target_entry:
            messagebox.showwarning(
                self._t("gui_window_title"), self._t("gui_msg_need_calc")
            )
            if fir_toggle_prev is not None:
                self._revert_fir_flag(fir_toggle_prev)
                self._fir_toggle_prev = None
            return
        if not self._ensure_runtime_gui():
            if fir_toggle_prev is not None:
                self._revert_fir_flag(fir_toggle_prev)
                self._fir_toggle_prev = None
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

        # preamp 按当前模式峰值：FIR 用联合峰，IIR 用 iir 峰
        peak = self._display_peak_for_mode(bool(self.correction.get("use_fir")))
        if peak is None:
            peak = float(self.correction.get("response_peak") or 0.0)
        else:
            peak = float(peak)
        pre_amp = self._compute_preamp(peak)
        # 必须解析为真实设备名：界面可能显示别名或旧预设残留的「外置耳机」
        output = self._resolved_output_device()
        try:
            fs = int(self.var_sr.get())
        except ValueError:
            fs = cp.DEFAULT_SAMPLE_RATE

        use_fir = bool(self.correction.get("use_fir"))
        fir_ir = self.correction.get("fir_ir") if use_fir else None
        # 开启 FIR 时若内存 ir 丢失，从 companion WAV 恢复，并与 WAV 采样率对齐
        if use_fir and fir_ir is None:
            cfg_guess = cp.build_config_path(self.source_entry, self.target_entry)
            fir_ir, wav_sr = cp.load_fir_ir_from_companion_wavs(cfg_guess)
            if fir_ir is not None:
                self.correction["fir_ir"] = fir_ir
                self.correction["fir_n_taps"] = int(len(fir_ir))
                if wav_sr:
                    fs = int(wav_sr)
                    self.var_sr.set(str(fs))
            else:
                use_fir = False
        elif use_fir and self.correction.get("fir_wav_sr"):
            # 磁盘 FIR 的原生采样率优先，减少扬声器 44.1k / 默认 48k 不一致
            try:
                fs = int(self.correction["fir_wav_sr"])
            except Exception:
                pass

        peq = list(self.peq_list)
        src, tgt = self.source_entry, self.target_entry
        debug = bool(self.var_debug.get())
        # 把计算得到的 RMSE 等写入预设，供下次加载 / 开关 FIR 时恢复
        metrics = cp.metrics_from_correction(self.correction)
        metrics["use_fir"] = bool(use_fir)
        if use_fir and fir_ir is not None:
            try:
                metrics["fir_n_taps"] = int(len(fir_ir))
            except Exception:
                pass

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
                fir_ir=fir_ir if use_fir else None,
                metrics=metrics,
            )
            cp.localized_print("output_device_set", device=output)
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
                "fir_toggle_prev": fir_toggle_prev,
            }

        if not self._run_job(worker, self._on_deploy_done, status_key):
            if fir_toggle_prev is not None:
                self._revert_fir_flag(fir_toggle_prev)
                self._fir_toggle_prev = None

    def _on_deploy_done(self, result, err) -> None:
        if err:
            prev = self._fir_toggle_prev
            if prev is not None:
                self._revert_fir_flag(bool(prev))
            self._fir_toggle_prev = None
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
        # 磁盘路径切换后同步 peq / fir / RMSE 到会话，便于继续切换
        summary = result.get("fir_summary")
        if summary and (not self.peq_list):
            self.peq_list = list(summary.get("peq") or [])
            if self.peq_list:
                self._fill_peq_table(self.peq_list)
        if summary:
            metrics = summary.get("metrics") or {}
            # 摘要顶层字段也并入 metrics
            for k in (
                "peq_rmse",
                "combined_rmse",
                "response_peak",
                "level_offset_db",
                "fir_n_taps",
            ):
                if summary.get(k) is not None and k not in metrics:
                    metrics[k] = summary[k]
            # 若摘要没带 metrics，直接读 YAML 注释
            if not metrics and result.get("config"):
                metrics = cp.load_config_metrics(Path(result["config"]))
            if self.correction is None:
                self.correction = {
                    "use_fir": bool(summary.get("use_fir")),
                    "fir_ir": summary.get("fir_ir"),
                    "fir_n_taps": int(summary.get("fir_n_taps") or 0),
                    "peq": list(summary.get("peq") or []),
                }
                self._apply_metrics_dict(metrics, prefer_existing=False)
                if summary.get("fir_ir") is not None:
                    sr = summary.get("samplerate")
                    if sr:
                        self.correction["fir_wav_sr"] = int(sr)
            else:
                if summary.get("fir_ir") is not None:
                    self.correction["fir_ir"] = summary["fir_ir"]
                    self.correction["fir_n_taps"] = int(
                        summary.get("fir_n_taps") or 0
                    )
                self.correction["use_fir"] = bool(summary.get("use_fir"))
                # 会话若只有 0 占位，用磁盘真实指标覆盖
                self._apply_metrics_dict(metrics, prefer_existing=True)
        elif result.get("config"):
            # 普通部署：从刚写入的 YAML 回读 metrics（双保险）
            self._apply_metrics_dict(
                cp.load_config_metrics(Path(result["config"])),
                prefer_existing=True,
            )
        self._refresh_presets()
        self._refresh_result_labels()
        if self.engine_proc is None:
            prev = result.get("fir_toggle_prev", self._fir_toggle_prev)
            if prev is not None:
                self._revert_fir_flag(bool(prev))
            self._fir_toggle_prev = None
            self._set_status_key("gui_status_engine_fail")
            self.btn_stop.configure(state=DISABLED)
            messagebox.showerror(
                self._t("gui_window_title"), self._t("gui_msg_start_fail")
            )
            return
        self._fir_toggle_prev = None
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
        # 用界面当前播放设备覆盖预设 YAML 中的旧 device（常见：外置耳机已拔出）
        output = self._resolved_output_device()

        def worker():
            if not cp.set_config_playback_device(path, output):
                # 无法改写时仍尝试启动，但打日志便于排查
                print(
                    f"[WARN] Could not update playback device in preset: {path}",
                    flush=True,
                )
            else:
                cp.localized_print("output_device_set", device=output)
            use_fir = cp.config_uses_fir_conv(path)
            # 若 YAML 已去掉 FIR 但仍有 companion WAV，保持 IIR；不自动强开
            if use_fir:
                cp.localized_print("fir_camilladsp_deploy_notice")
            proc, log_path = cp.run_camilladsp(path, debug=debug)
            summary = None
            try:
                # 供 GUI 显示 FIR 状态 / RMSE / 允许随后「停止/开启 FIR」
                ir, wav_sr = (
                    cp.load_fir_ir_from_companion_wavs(path)
                    if cp.config_has_companion_fir_wavs(path)
                    else (None, None)
                )
                basics = cp.parse_camilladsp_config_for_regen(path)
                metrics = cp.load_config_metrics(path)
                taps = int(metrics.get("fir_n_taps") or 0)
                if taps <= 0 and ir is not None:
                    taps = int(len(ir))
                summary = {
                    "use_fir": use_fir,
                    "fir_ir": ir,
                    "fir_n_taps": taps,
                    "samplerate": int(
                        wav_sr or (basics or {}).get("samplerate") or 0
                    )
                    or None,
                    "peq": list((basics or {}).get("peq") or []),
                    "path": path,
                    "metrics": metrics,
                    "peq_rmse": metrics.get("peq_rmse"),
                    "combined_rmse": metrics.get("combined_rmse"),
                    "response_peak": metrics.get("response_peak"),
                    "level_offset_db": metrics.get("level_offset_db"),
                }
            except Exception:
                summary = None
            return {
                "config": path,
                "proc": proc,
                "log": log_path,
                "use_fir": use_fir,
                "fir_summary": summary,
            }

        self._run_job(worker, self._on_deploy_done, "gui_status_preset")

    # ----- 关闭 -----

    def _on_close(self) -> None:
        self._left_wheel_bound = False
        try:
            self.root.unbind_all("<TouchpadScroll>")
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")
            self.root.unbind_all("<Shift-MouseWheel>")
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
