"""Small keyboard-accessible vector controls and a debounced headphone picker."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import theme as theme
from vector_icons import draw_icon


class IconButton(tk.Canvas):
    def __init__(self, parent, icon, command=None, bg=None, color=None, size=30, **kwargs):
        super().__init__(parent, width=size, height=size, bg=bg or theme.PANEL,
                         highlightthickness=1, highlightbackground=bg or theme.PANEL,
                         highlightcolor=theme.BORDER_SPECULAR, bd=0, takefocus=bool(command),
                         cursor="hand2" if command else "", **kwargs)
        self.command = command
        self.base_color = color or theme.MUTED
        self._hovered = False
        self._focused = False
        draw_icon(self, icon, (size - 16) / 2, (size - 16) / 2, 16, self.base_color, "icon")
        self.bind("<Button-1>", self._activate)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<FocusIn>", lambda _e: self._set_focus(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<FocusOut>", lambda _e: self._set_focus(False))

    def _color(self, color):
        # A tag can contain lines, arcs or polygons, each with different options.
        for item in self.find_withtag("icon"):
            if self.type(item) in ("line", "text"):
                self.itemconfigure(item, fill=color)
            elif self.type(item) == "polygon":
                self.itemconfigure(item, fill=color, outline=color)
            else:
                self.itemconfigure(item, outline=color)

    def _set_hover(self, active):
        self._hovered = active
        self._update_emphasis()

    def _set_focus(self, active):
        self._focused = active
        self._update_emphasis()

    def _update_emphasis(self):
        emphasized = self._hovered or self._focused
        self.configure(highlightbackground=theme.FOCUS if emphasized else self.cget("bg"))
        self._color(theme.TEXT if emphasized else self.base_color)

    def _activate(self, _event=None):
        if callable(self.command):
            self.command()
        return "break"


class HeadphoneSearchBox(tk.Frame):
    """Search suggestions preserve provider provenance and never alter DSP state."""
    def __init__(self, parent, fonts=None, placeholder="", on_change=None, search_fn=None, accent=None):
        super().__init__(parent, bg=theme.PANEL, height=48, highlightthickness=1,
                         highlightbackground=theme.BORDER, highlightcolor=accent or theme.FOCUS)
        self.pack_propagate(False)
        self.fonts = fonts or {"ui13": (theme.ui_family(), 13), "ui11": (theme.ui_family(), 11), "mono9": (theme.mono_family(), 9)}
        self.on_change = on_change
        self.search_fn = search_fn or (lambda _q, limit: [])
        self.accent = accent or theme.FOCUS
        self.placeholder = placeholder
        self.selected_entry = None
        self._popup = None
        self._items = []
        self._hover_idx = -1
        self._search_job = None
        self._hide_job = None
        self._rows = []
        self._enabled = True
        self.var_query = tk.StringVar(self)
        self.lbl_icon = IconButton(self, "search", color=self.accent, size=28, bg=theme.PANEL)
        self.lbl_icon.pack(side="left", padx=(7, 4))
        self.btn_clear = IconButton(self, "close", self.clear_selection, size=28, bg=theme.PANEL)
        self.selected_frame = tk.Frame(self, bg=theme.PANEL, cursor="hand2")
        self.lbl_selected = tk.Label(self.selected_frame, bg=theme.PANEL, fg=theme.TEXT, font=self.fonts.get("ui13", self.fonts["ui11"]), anchor="w")
        self.lbl_selected.pack(fill="x")
        self.lbl_provider = tk.Label(self.selected_frame, bg=theme.PANEL, fg=theme.MUTED, font=self.fonts["mono9"], anchor="w")
        self.lbl_provider.pack(fill="x")
        for widget in (self.selected_frame, self.lbl_selected, self.lbl_provider):
            widget.bind("<Button-1>", lambda _e: self._edit_selection())
        self.entry = tk.Entry(self, textvariable=self.var_query, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.TEXT,
                              font=self.fonts.get("ui13", self.fonts["ui11"]), relief="flat", bd=0, highlightthickness=0)
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=7)
        self.hint = tk.Label(self, text=placeholder, fg=theme.MUTED, bg=theme.PANEL, font=self.fonts["ui11"], anchor="w")
        self.hint.bind("<Button-1>", lambda _e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda _e: self.configure(highlightbackground=self.accent))
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Down>", self._on_arrow_down)
        self.entry.bind("<Up>", self._on_arrow_up)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Escape>", lambda _e: self._hide_popup())
        self.var_query.trace_add("write", self._query_changed)
        self.bind("<Destroy>", self._destroyed, add="+")
        self._show_hint()

    def _show_hint(self):
        self.hint.place_forget()
        if not self.selected_entry and not self.var_query.get():
            self.hint.place(in_=self.entry, x=2, rely=.5, anchor="w", relwidth=.95)

    def set_placeholder(self, text):
        self.placeholder = text
        self.hint.configure(text=text)
        self._show_hint()

    def set_entry(self, entry):
        self._cancel_search()
        self.selected_entry = entry
        self._hide_popup()
        self.hint.place_forget()
        if entry:
            self.entry.pack_forget()
            self.lbl_selected.configure(text=entry.get("display_name") or entry.get("name") or "")
            self.lbl_provider.configure(text=entry.get("provider") or "")
            self.selected_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.btn_clear.pack(side="right", padx=(0, 6))
            self.configure(highlightbackground=self.accent)
        else:
            self.selected_frame.pack_forget()
            self.btn_clear.pack_forget()
            self.var_query.set("")
            self.entry.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=7)
            self._show_hint()
            self.configure(highlightbackground=theme.BORDER)
        if self.on_change:
            self.on_change(entry)

    def clear_selection(self):
        if not self._enabled:
            return
        self.set_entry(None)
        self.entry.focus_set()

    def _edit_selection(self):
        if self._enabled and self.selected_entry:
            name = self.selected_entry.get("display_name") or self.selected_entry.get("name") or ""
            self.set_entry(None)
            self.var_query.set(name)
            self.entry.focus_set()
            self.entry.icursor("end")

    def _cancel_search(self):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
            self._search_job = None

    def _query_changed(self, *_args):
        self._show_hint()
        self._cancel_search()
        if not self.selected_entry:
            self._search_job = self.after(120, self._trigger_search)

    def _trigger_search(self):
        self._search_job = None
        if not self._enabled:
            return
        query = self.var_query.get().strip()
        if not query or self.selected_entry:
            self._hide_popup()
            return
        results = self.search_fn(query, limit=16)
        if results:
            self._show_popup(results)
        else:
            self._hide_popup()

    def _show_popup(self, items):
        self._hide_popup()
        self._items = items
        self._hover_idx = 0
        self._popup = tk.Toplevel(self.winfo_toplevel())
        self._popup.overrideredirect(True)
        self._popup.configure(bg=theme.BORDER)
        self._scroller = tk.Canvas(self._popup, bg=theme.PANEL_GLASS, bd=0, highlightthickness=0)
        self._scroller.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        scroll = ttk.Scrollbar(self._popup, orient="vertical", command=self._scroller.yview)
        scroll.pack(side="right", fill="y")
        self._scroller.configure(yscrollcommand=scroll.set, yscrollincrement=40)
        self._popup_inner = tk.Frame(self._scroller, bg=theme.PANEL_GLASS)
        win = self._scroller.create_window(0, 0, window=self._popup_inner, anchor="nw")
        self._scroller.bind("<Configure>", lambda e: self._scroller.itemconfigure(win, width=e.width))
        self._rows = []
        for i, item in enumerate(items):
            row = tk.Frame(self._popup_inner, bg=theme.PANEL_GLASS, height=40, cursor="hand2")
            row.pack(fill="x")
            row.pack_propagate(False)
            name = tk.Label(row, text=item.get("display_name") or item.get("name") or "", font=self.fonts["ui11"], bg=theme.PANEL_GLASS, fg=theme.TEXT, anchor="w")
            name.pack(side="left", fill="x", expand=True, padx=10)
            provider = tk.Label(row, text=item.get("provider") or "", font=self.fonts["mono9"], bg=theme.PANEL_GLASS, fg=theme.MUTED)
            provider.pack(side="right", padx=8)
            for widget in (row, name, provider):
                widget.bind("<Button-1>", lambda _e, it=item: self.set_entry(it))
                widget.bind("<Enter>", lambda _e, idx=i: self._highlight_row(idx, scroll=False))
                widget.bind("<MouseWheel>", self._wheel)
                widget.bind("<Button-4>", lambda _e: self._scroller.yview_scroll(-1, "units"))
                widget.bind("<Button-5>", lambda _e: self._scroller.yview_scroll(1, "units"))
            self._rows.append(row)
        self._popup_inner.update_idletasks()
        height = min(280, len(items) * 40)
        width = min(max(self.winfo_width(), 320), self.winfo_screenwidth() - 24)
        x = min(self.winfo_rootx(), self.winfo_screenwidth() - width - 12)
        below = self.winfo_rooty() + self.winfo_height() + 4
        y = below if below + height < self.winfo_screenheight() else max(10, self.winfo_rooty() - height - 4)
        self._popup.geometry(f"{width}x{height}+{max(0, x)}+{y}")
        self._scroller.configure(scrollregion=(0, 0, width, len(items) * 40))
        self._highlight_row(0)
        self._popup.lift()

    def _wheel(self, event):
        self._scroller.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _highlight_row(self, index, scroll=True):
        self._hover_idx = index
        for i, row in enumerate(self._rows):
            color = theme.SLOT if i == index else theme.PANEL_GLASS
            row.configure(bg=color)
            for child in row.winfo_children():
                child.configure(bg=color)
        if scroll and self._popup:
            first, last = self._scroller.yview()
            start, end = index / len(self._rows), (index + 1) / len(self._rows)
            if start < first:
                self._scroller.yview_moveto(start)
            elif end > last:
                self._scroller.yview_moveto(max(0, end - (last - first)))

    def _on_arrow_down(self, _event):
        if self._items:
            self._highlight_row(min(self._hover_idx + 1, len(self._items) - 1))
        else:
            self._trigger_search()
        return "break"

    def _on_arrow_up(self, _event):
        if self._items:
            self._highlight_row(max(0, self._hover_idx - 1))
        return "break"

    def _on_return(self, _event):
        if self._enabled and self._popup and self._items:
            self.set_entry(self._items[max(0, self._hover_idx)])
        return "break"

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.entry.configure(state="normal" if enabled else "disabled")
        for widget in (self.selected_frame, self.lbl_selected, self.lbl_provider, self.btn_clear):
            widget.configure(cursor="hand2" if enabled else "")
        if not enabled:
            self._cancel_search()
            self._hide_popup()

    def _on_focus_out(self, _event):
        self.configure(highlightbackground=self.accent if self.selected_entry else theme.BORDER)
        if self._hide_job is not None:
            self.after_cancel(self._hide_job)
        self._hide_job = self.after(150, self._hide_popup)

    def _hide_popup(self):
        if self._hide_job is not None:
            self.after_cancel(self._hide_job)
        self._hide_job = None
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
        self._items = []
        self._rows = []

    def _destroyed(self, event):
        if event.widget is self:
            self._cancel_search()
            if self._hide_job is not None:
                self.after_cancel(self._hide_job)
            self._hide_popup()
