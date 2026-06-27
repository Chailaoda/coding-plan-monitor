"""
Tkinter 桌面悬浮窗 UI
- 无边框 / 置顶 / 半透明
- 三条进度条（5h / 周 / 月）+ MiMo 行
- 可拖动 / 可折叠 / 可关闭
"""

import tkinter as tk
import time
from datetime import datetime
from typing import Callable, Optional


COLOR_BG = "#1c1c1e"
COLOR_BG_LIGHT = "#2c2c2e"
COLOR_FG = "#ffffff"
COLOR_FG_DIM = "#9e9e9e"
COLOR_BAR_BG = "#3a3a3c"

COLOR_GREEN = "#30D158"
COLOR_ORANGE = "#FF9F0A"
COLOR_RED = "#FF375F"

WIN_WIDTH = 280
WIN_HEIGHT_COLLAPSED = 28

LEVEL_ORDER = ("session", "weekly", "monthly")
LEVEL_LABELS = {
    "session": "5 小时",
    "weekly": "本周",
    "monthly": "本月",
}


def color_for_percent(pct: float) -> str:
    if pct >= 90:
        return COLOR_RED
    if pct >= 60:
        return COLOR_ORANGE
    return COLOR_GREEN


def format_reset(ts: int) -> str:
    if ts <= 0:
        return "暂无调用"
    diff = ts - int(time.time())
    if diff <= 0:
        return "即将重置"
    h = diff // 3600
    m = (diff % 3600) // 60
    if h >= 24:
        return f"{h // 24} 天 {h % 24} 小时"
    if h >= 1:
        return f"{h} 小时 {m} 分"
    return f"{m} 分 {diff % 60} 秒"


class QuotaRow:
    """单个额度行：标签 + 百分比 + 进度条 + 重置时间"""

    BAR_WIDTH = 256
    BAR_HEIGHT = 6

    def __init__(self, parent, level: str):
        self.level = level
        self.last_q: Optional[dict] = None
        self._packed = True

        self.frame = tk.Frame(parent, bg=COLOR_BG)
        self.frame.pack(fill="x", padx=8, pady=(4, 0))

        top = tk.Frame(self.frame, bg=COLOR_BG)
        top.pack(fill="x")

        self.label_var = tk.StringVar(value="—")
        self.percent_var = tk.StringVar(value="—")

        tk.Label(top, textvariable=self.label_var, bg=COLOR_BG, fg=COLOR_FG,
                 font=("Sans", 9), anchor="w").pack(side="left")
        self.percent_label = tk.Label(top, textvariable=self.percent_var, bg=COLOR_BG, fg=COLOR_FG,
                 font=("Sans", 9, "bold"), anchor="e")
        self.percent_label.pack(side="right")

        self.canvas = tk.Canvas(
            self.frame, width=self.BAR_WIDTH, height=4,
            bg=COLOR_BAR_BG, highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill="x", pady=(1, 0))
        self.bar_rect = self.canvas.create_rectangle(
            0, 0, 0, 4, fill=COLOR_GREEN, outline=""
        )

        self.reset_var = tk.StringVar(value="")
        tk.Label(self.frame, textvariable=self.reset_var, bg=COLOR_BG, fg=COLOR_FG_DIM,
                 font=("Sans", 7), anchor="w").pack(fill="x")

    def set_visible(self, visible: bool):
        if visible and not self._packed:
            self.frame.pack(fill="x", padx=8, pady=(4, 0))
            self._packed = True
        elif not visible and self._packed:
            self.frame.pack_forget()
            self._packed = False

    def update(self, q: dict):
        self.last_q = q
        self.label_var.set(q.get("label", self.level))
        pct = float(q.get("percent", 0))
        self.percent_var.set(f"{pct:.1f}%")
        color = color_for_percent(pct)
        self.percent_label.config(fg=color)
        # 用 canvas 实际宽度计算（首帧可能为 1，回退到 BAR_WIDTH）
        self.canvas.update_idletasks()
        bar_w = self.canvas.winfo_width()
        if bar_w <= 1:
            bar_w = self.BAR_WIDTH
        fill_w = int(min(pct, 100) / 100 * bar_w)
        self.canvas.coords(self.bar_rect, 0, 0, fill_w, 4)
        self.canvas.itemconfig(self.bar_rect, fill=color)
        reset_ts = int(q.get("reset_ts", 0))
        if reset_ts <= 0:
            if self.level == "session":
                self.reset_var.set("距重置：5 小时 0 分")
            else:
                self.reset_var.set("暂无调用")
        else:
            self.reset_var.set(f"距重置：{format_reset(reset_ts)}")

    def tick_reset(self):
        if self.last_q:
            reset_ts = int(self.last_q.get("reset_ts", 0))
            if reset_ts <= 0:
                if self.level == "session":
                    self.reset_var.set("距重置：5 小时 0 分")
                else:
                    self.reset_var.set("暂无调用")
            else:
                self.reset_var.set(f"距重置：{format_reset(reset_ts)}")


class MimoRow:
    """MiMo 用量行：标签 + 百分比 + 进度条 + 到期时间"""

    BAR_WIDTH = 256

    def __init__(self, parent):
        self.last_data: Optional[dict] = None

        self.frame = tk.Frame(parent, bg=COLOR_BG)
        self.frame.pack(fill="x", padx=8, pady=(4, 0))

        top = tk.Frame(self.frame, bg=COLOR_BG)
        top.pack(fill="x")

        tk.Label(top, text="MiMo", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Sans", 9), anchor="w").pack(side="left")
        self.percent_label = tk.Label(top, text="—", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Sans", 9, "bold"), anchor="e")
        self.percent_label.pack(side="right")

        self.canvas = tk.Canvas(
            self.frame, width=self.BAR_WIDTH, height=4,
            bg=COLOR_BAR_BG, highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill="x", pady=(1, 0))
        self.bar_rect = self.canvas.create_rectangle(
            0, 0, 0, 4, fill=COLOR_GREEN, outline=""
        )

        self.info_var = tk.StringVar(value="")
        tk.Label(self.frame, textvariable=self.info_var, bg=COLOR_BG, fg=COLOR_FG_DIM,
                 font=("Sans", 7), anchor="w").pack(fill="x")

    def update(self, data: dict):
        self.last_data = data
        pct = float(data.get("percent", 0))
        self.percent_label.config(text=f"{pct:.1f}%", fg=color_for_percent(pct))

        self.canvas.update_idletasks()
        bar_w = self.canvas.winfo_width()
        if bar_w <= 1:
            bar_w = self.BAR_WIDTH
        fill_w = int(min(pct, 100) / 100 * bar_w)
        self.canvas.coords(self.bar_rect, 0, 0, fill_w, 4)
        self.canvas.itemconfig(self.bar_rect, fill=color_for_percent(pct))

        period_end = data.get("period_end", "")
        if period_end:
            try:
                from datetime import datetime
                end_dt = datetime.strptime(period_end[:19], "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                diff = end_dt - now
                if diff.total_seconds() > 0:
                    days = diff.days
                    hours = diff.seconds // 3600
                    self.info_var.set(f"距到期：{days}天{hours}小时（有效期至 {period_end[:16]}）")
                else:
                    self.info_var.set(f"已到期（有效期至 {period_end[:16]}）")
            except Exception:
                self.info_var.set(f"有效期至 {period_end[:16]}")
        else:
            self.info_var.set("")

    def tick_reset(self):
        pass


class TargetRow:
    """扩展监控标的行：百分比 / 待接入 / 错误状态"""

    BAR_WIDTH = 256

    def __init__(self, parent, target_id: str, name: str, on_open: Optional[Callable[[str], None]] = None):
        self.target_id = target_id
        self.name = name
        self.on_open = on_open
        self.last_data: Optional[dict] = None
        self._packed = False

        self.frame = tk.Frame(parent, bg=COLOR_BG)
        top = tk.Frame(self.frame, bg=COLOR_BG)
        top.pack(fill="x")

        tk.Label(top, text=name, bg=COLOR_BG, fg=COLOR_FG,
                 font=("Sans", 9), anchor="w").pack(side="left")
        self.open_btn = tk.Label(top, text="打开", bg=COLOR_BG, fg=COLOR_ORANGE,
                                 font=("Sans", 8), cursor="hand2", padx=6)
        self.open_btn.pack(side="right")
        self.open_btn.bind("<Button-1>", lambda e: self.open_console())
        self.percent_label = tk.Label(top, text="待接入", bg=COLOR_BG, fg=COLOR_ORANGE,
                                      font=("Sans", 9, "bold"), anchor="e")
        self.percent_label.pack(side="right")

        self.canvas = tk.Canvas(
            self.frame, width=self.BAR_WIDTH, height=4,
            bg=COLOR_BAR_BG, highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill="x", pady=(1, 0))
        self.bar_rect = self.canvas.create_rectangle(
            0, 0, 0, 4, fill=COLOR_GREEN, outline=""
        )

        self.info_var = tk.StringVar(value="待接入自动抓取，点击打开控制台")
        tk.Label(self.frame, textvariable=self.info_var, bg=COLOR_BG, fg=COLOR_FG_DIM,
                 font=("Sans", 7), anchor="w").pack(fill="x")

    def set_visible(self, visible: bool):
        if visible and not self._packed:
            self.frame.pack(fill="x", padx=8, pady=(4, 0))
            self._packed = True
        elif not visible and self._packed:
            self.frame.pack_forget()
            self._packed = False

    def open_console(self):
        if self.on_open:
            self.on_open(self.target_id)

    def update(self, data: dict):
        self.last_data = data
        pct = data.get("percent")
        if pct is None:
            self.percent_label.config(text="—", fg=COLOR_FG_DIM)
            self.canvas.coords(self.bar_rect, 0, 0, 0, 4)
        else:
            pct = float(pct)
            color = color_for_percent(pct)
            self.percent_label.config(text=f"{pct:.1f}%", fg=color)
            self.canvas.update_idletasks()
            bar_w = self.canvas.winfo_width()
            if bar_w <= 1:
                bar_w = self.BAR_WIDTH
            fill_w = int(min(pct, 100) / 100 * bar_w)
            self.canvas.coords(self.bar_rect, 0, 0, fill_w, 4)
            self.canvas.itemconfig(self.bar_rect, fill=color)
        period_end = data.get("period_end", "")
        info = data.get("info", "已更新")
        if period_end and not info:
            info = f"有效期至 {period_end[:16]}"
        elif period_end and info:
            info = f"{info}  有效期至 {period_end[:16]}"
        self.info_var.set(info)

    def update_unavailable(self, info: str = "待接入自动抓取，点击打开控制台"):
        self.last_data = None
        self.percent_label.config(text="待接入", fg=COLOR_ORANGE)
        self.canvas.coords(self.bar_rect, 0, 0, 0, 4)
        self.info_var.set(info)

    def update_error(self, msg: str):
        self.percent_label.config(text="错误", fg=COLOR_RED)
        self.canvas.coords(self.bar_rect, 0, 0, 0, 4)
        self.info_var.set(str(msg)[:42])

    def tick_reset(self):
        pass


class FloatingWindow:
    """主悬浮窗"""

    def __init__(
        self,
        on_close: Optional[Callable] = None,
        on_position_change: Optional[Callable[[int, int], None]] = None,
        on_collapse_change: Optional[Callable[[bool], None]] = None,
        on_update_click: Optional[Callable[[], None]] = None,
        on_target_toggle: Optional[Callable[[str, bool], None]] = None,
        on_open_target: Optional[Callable[[str], None]] = None,
        initial_x: int = 1500,
        initial_y: int = 80,
        initial_collapsed: bool = False,
        alpha: float = 0.92,
        always_on_top: bool = True,
    ):
        self.on_close_cb = on_close
        self.on_position_change_cb = on_position_change
        self.on_collapse_change_cb = on_collapse_change
        self.on_update_click_cb = on_update_click
        self.on_target_toggle_cb = on_target_toggle
        self.on_open_target_cb = on_open_target

        self.collapsed = initial_collapsed
        self.last_data: Optional[dict] = None
        self.target_defs = []
        self.target_rows = {}
        self.has_error = False
        self.error_msg = ""
        self._visible = True
        self.last_fetch_time: Optional[datetime] = None

        self.root = tk.Tk()
        self.root.title("模型流量监控")
        self.root.overrideredirect(True)
        self.root.configure(bg=COLOR_BG)
        try:
            self.root.attributes("-topmost", bool(always_on_top))
        except Exception:
            pass
        try:
            self.root.attributes("-alpha", float(alpha))
        except Exception:
            pass

        h = WIN_HEIGHT_COLLAPSED if self.collapsed else self._expanded_height()
        self.root.geometry(f"{WIN_WIDTH}x{h}+{initial_x}+{initial_y}")

        self._drag_dx = 0
        self._drag_dy = 0
        self._drag_moved = False
        self._flash_count = 0
        self._flash_after_id = None
        self._target_window = None
        self._target_vars = {}

        self._build_ui()
        self._bind_drag(self.title_bar)
        self._bind_drag(self.title_label)
        if not self.collapsed:
            self._apply_expanded_layout()
        for w in (self.collapse_title, self.collapse_sep,
                  self.collapse_5h, self.collapse_weekly,
                  self.collapse_mimo_sep, self.collapse_mimo):
            self._bind_drag(w)
        # 点击折叠态标题可展开
        self.collapse_title.bind("<Button-1>", lambda e: self.toggle_collapse())

        if self.collapsed:
            self._apply_collapsed_layout()

        self.root.after(1000, self._tick_reset_loop)

    # ---------- UI 构建 ----------
    def _build_ui(self):
        self.title_bar = tk.Frame(self.root, bg=COLOR_BG_LIGHT, height=24)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        self.toggle_btn = tk.Label(
            self.title_bar,
            text="▼" if not self.collapsed else "▶",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 9),
            cursor="hand2", padx=8,
        )
        self.toggle_btn.pack(side="left")
        self.toggle_btn.bind("<Button-1>", lambda e: self.toggle_collapse())

        self.title_label = tk.Label(
            self.title_bar, text="模型流量监控",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 9, "bold"),
        )
        self.title_label.pack(side="left")

        self.targets_btn = tk.Label(
            self.title_bar, text="标的",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG_DIM, font=("Sans", 9),
            cursor="hand2", padx=6,
        )
        self.targets_btn.bind("<Button-1>", lambda e: self.open_targets_window())
        self.targets_btn.bind("<Enter>", lambda e: self.targets_btn.config(fg=COLOR_FG))
        self.targets_btn.bind("<Leave>", lambda e: self.targets_btn.config(fg=COLOR_FG_DIM))

        self.update_btn = tk.Label(
            self.title_bar, text="更新",
            bg=COLOR_BG_LIGHT, fg=COLOR_ORANGE, font=("Sans", 9),
            cursor="hand2", padx=6,
        )
        self.update_btn.bind("<Button-1>", lambda e: self.open_update())
        self.update_btn.bind("<Enter>", lambda e: self.update_btn.config(fg=COLOR_FG))
        self.update_btn.bind("<Leave>", lambda e: self.update_btn.config(fg=COLOR_ORANGE))

        self.close_btn = tk.Label(
            self.title_bar, text="✕",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG_DIM, font=("Sans", 11),
            cursor="hand2", padx=8,
        )
        self.close_btn.bind("<Button-1>", lambda e: self.close())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg=COLOR_RED))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg=COLOR_FG_DIM))

        self.collapse_title = tk.Label(
            self.title_bar, text="火山",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 8, "bold"),
        )
        self.collapse_sep = tk.Label(
            self.title_bar, text="    ",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 8),
        )
        self.collapse_5h = tk.Label(
            self.title_bar, text="",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 8),
        )
        self.collapse_weekly = tk.Label(
            self.title_bar, text="",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 8),
        )
        self.collapse_mimo_sep = tk.Label(
            self.title_bar, text="|",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG_DIM, font=("Sans", 8),
        )
        self.collapse_mimo = tk.Label(
            self.title_bar, text="MiMo:—",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 8),
        )
        self.collapse_update = tk.Label(
            self.title_bar, text="更新",
            bg=COLOR_BG_LIGHT, fg=COLOR_ORANGE, font=("Sans", 8),
            cursor="hand2", padx=4,
        )
        self.collapse_update.bind("<Button-1>", lambda e: self.open_update())
        self.collapse_targets = tk.Label(
            self.title_bar, text="标的",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG_DIM, font=("Sans", 8),
            cursor="hand2", padx=4,
        )
        self.collapse_targets.bind("<Button-1>", lambda e: self.open_targets_window())

        self.body = tk.Frame(self.root, bg=COLOR_BG)
        self.body.pack(fill="both", expand=True)

        self.rows = {}
        for level in LEVEL_ORDER:
            self.rows[level] = QuotaRow(self.body, level)

        self.target_container = tk.Frame(self.body, bg=COLOR_BG)
        self.target_container.pack(fill="x")

        self.footer = tk.Label(
            self.body, text="等待数据…",
            bg=COLOR_BG, fg=COLOR_FG_DIM, font=("Sans", 7), anchor="e",
        )
        self.footer.pack(fill="x", side="bottom", padx=8, pady=(2, 4))

    def _apply_expanded_layout(self):
        for w in (self.collapse_title, self.collapse_sep, self.collapse_5h,
                  self.collapse_weekly, self.collapse_mimo_sep, self.collapse_mimo,
                  self.collapse_update, self.collapse_targets):
            w.pack_forget()
        self.toggle_btn.pack(side="left")
        self.title_label.pack(side="left")
        self.close_btn.pack(side="right")
        self.update_btn.pack(side="right")
        self.targets_btn.pack(side="right")
        self.body.pack(fill="both", expand=True)
        self.toggle_btn.config(text="▼")

    def _apply_collapsed_layout(self):
        self.body.pack_forget()
        self.title_label.pack_forget()
        self.update_btn.pack_forget()
        self.targets_btn.pack_forget()
        self.close_btn.pack_forget()
        self.toggle_btn.pack(side="left")
        self.toggle_btn.config(text="▶")
        self.collapse_title.pack(side="left")
        self.collapse_5h.pack(side="left", padx=(2, 0))
        self.collapse_weekly.pack(side="left", padx=(2, 0))
        self.collapse_mimo_sep.pack(side="left", padx=(1, 0))
        self.collapse_mimo.pack(side="left", padx=(1, 0))
        self.collapse_update.pack(side="right")
        self.collapse_targets.pack(side="right")

    # ---------- 拖动 ----------
    def _bind_drag(self, widget):
        widget.bind("<Button-1>", self._on_drag_start)
        widget.bind("<B1-Motion>", self._on_drag_motion)
        widget.bind("<ButtonRelease-1>", self._on_drag_end)

    def _on_drag_start(self, e):
        self._drag_dx = e.x_root - self.root.winfo_x()
        self._drag_dy = e.y_root - self.root.winfo_y()
        self._drag_moved = False

    def _on_drag_motion(self, e):
        x = e.x_root - self._drag_dx
        y = e.y_root - self._drag_dy
        self.root.geometry(f"+{x}+{y}")
        self._drag_moved = True

    def _on_drag_end(self, e):
        if self._drag_moved and self.on_position_change_cb:
            try:
                self.on_position_change_cb(self.root.winfo_x(), self.root.winfo_y())
            except Exception:
                pass

    # ---------- 折叠 / 关闭 ----------
    def _expanded_height(self):
        enabled_extra = sum(1 for t in self.target_defs if t.get("enabled") and t.get("id") != "volcano")
        return 184 + enabled_extra * 44

    def _resize_expanded(self):
        if not self.collapsed:
            self.root.geometry(f"{WIN_WIDTH}x{self._expanded_height()}")

    def toggle_collapse(self):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.root.geometry(f"{WIN_WIDTH}x{WIN_HEIGHT_COLLAPSED}")
            self._apply_collapsed_layout()
        else:
            self.root.geometry(f"{WIN_WIDTH}x{self._expanded_height()}")
            self._apply_expanded_layout()
        if self.on_collapse_change_cb:
            try:
                self.on_collapse_change_cb(self.collapsed)
            except Exception:
                pass
        self._refresh_compact_label()

    def close(self):
        """✕ 按钮：仅隐藏窗口（托盘图标继续保留）"""
        self.hide()

    def open_update(self):
        if self.on_update_click_cb:
            try:
                self.on_update_click_cb()
            except Exception:
                pass

    def open_targets_window(self):
        if self._target_window is not None:
            try:
                self._target_window.lift()
                return
            except Exception:
                self._target_window = None
        win = tk.Toplevel(self.root)
        self._target_window = win
        win.title("监控标的")
        win.configure(bg=COLOR_BG)
        win.geometry("260x190")
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        win.protocol("WM_DELETE_WINDOW", self._close_targets_window)
        tk.Label(win, text="选择要显示的监控标的", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Sans", 10, "bold"), anchor="w").pack(fill="x", padx=10, pady=(10, 6))
        self._target_vars = {}
        for item in self.target_defs:
            tid = item.get("id")
            var = tk.BooleanVar(value=bool(item.get("enabled")))
            self._target_vars[tid] = var
            cb = tk.Checkbutton(
                win, text=item.get("name", tid), variable=var,
                bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG_LIGHT,
                activebackground=COLOR_BG, activeforeground=COLOR_FG,
                anchor="w", command=lambda t=tid, v=var: self._toggle_target(t, v.get()),
            )
            cb.pack(fill="x", padx=10, pady=2)
        tk.Label(win, text="未接入标的会显示待接入，可点击打开控制台。", bg=COLOR_BG,
                 fg=COLOR_FG_DIM, font=("Sans", 8), anchor="w", wraplength=230).pack(fill="x", padx=10, pady=(6, 0))

    def _close_targets_window(self):
        try:
            self._target_window.destroy()
        except Exception:
            pass
        self._target_window = None

    def _toggle_target(self, target_id: str, enabled: bool):
        if self.on_target_toggle_cb:
            self.on_target_toggle_cb(target_id, enabled)

    def set_targets(self, targets: list):
        self.target_defs = [dict(t) for t in targets]
        enabled = {t.get("id"): bool(t.get("enabled")) for t in self.target_defs}
        for item in self.target_defs:
            tid = item.get("id")
            if tid == "volcano":
                for row in self.rows.values():
                    row.set_visible(enabled.get(tid, True))
                continue
            if tid not in self.target_rows:
                self.target_rows[tid] = TargetRow(
                    self.target_container,
                    tid,
                    item.get("name", tid),
                    on_open=self.on_open_target_cb,
                )
            row = self.target_rows[tid]
            row.name = item.get("name", tid)
            row.set_visible(enabled.get(tid, False))
            if enabled.get(tid, False) and not item.get("implemented", False):
                row.update_unavailable()
        for tid, row in self.target_rows.items():
            if tid not in enabled:
                row.set_visible(False)
        if self._target_window is not None:
            for tid, var in self._target_vars.items():
                if tid in enabled:
                    var.set(enabled[tid])
        self._resize_expanded()
        self._refresh_compact_label()

    def hide(self):
        try:
            self.root.withdraw()
            self._visible = False
        except Exception:
            pass

    def show(self):
        try:
            self.root.deiconify()
            try:
                self.root.lift()
            except Exception:
                pass
            self._visible = True
        except Exception:
            pass

    def toggle_visible(self):
        if getattr(self, "_visible", True):
            self.hide()
        else:
            self.show()

    def quit_app(self):
        """彻底退出（由托盘"退出"菜单调用）"""
        if self.on_close_cb:
            try:
                self.on_close_cb()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- 数据更新 ----------
    def update_data(self, data: dict):
        self.last_data = data
        self.has_error = False
        self.error_msg = ""
        self.last_fetch_time = datetime.now()

        for level in LEVEL_ORDER:
            q = data.get("quotas", {}).get(level)
            if q:
                self.rows[level].update(q)

        self.footer.config(
            text=f"{self.last_fetch_time.strftime('%H:%M:%S')} 已更新",
            fg=COLOR_FG_DIM,
        )
        self._refresh_compact_label()

    def update_error(self, msg: str):
        self.has_error = True
        self.error_msg = msg
        self.footer.config(text=msg[:42], fg=COLOR_RED)
        self._refresh_compact_label()

    def mark_update_opened(self):
        self.has_error = True
        self.error_msg = "已打开控制台，请登录/刷新后等待自动更新"
        self.footer.config(text=self.error_msg, fg=COLOR_ORANGE)
        self._refresh_compact_label()

    def update_target(self, target_id: str, data: dict):
        row = self.target_rows.get(target_id)
        if row:
            row.update(data)
        self._refresh_compact_label()

    def update_target_error(self, target_id: str, msg: str):
        row = self.target_rows.get(target_id)
        if row:
            row.update_error(msg)
        self._refresh_compact_label()

    def mark_target_update_opened(self, target_id: str):
        row = self.target_rows.get(target_id)
        if row:
            row.update_unavailable("已打开控制台，请登录/刷新后等待自动接入")
        self._refresh_compact_label()

    def _refresh_compact_label(self):
        if self.has_error:
            self.collapse_5h.config(text="需更新", fg=COLOR_RED)
            self.collapse_weekly.config(text="", fg=COLOR_RED)
            self.collapse_update.config(fg=COLOR_ORANGE)
        elif not self.last_data:
            if any(t.get("id") == "volcano" and t.get("enabled") for t in self.target_defs):
                self.collapse_5h.config(text="5小时:—", fg=COLOR_FG_DIM)
                self.collapse_weekly.config(text="周:—", fg=COLOR_FG_DIM)
            else:
                self.collapse_5h.config(text="", fg=COLOR_FG_DIM)
                self.collapse_weekly.config(text="", fg=COLOR_FG_DIM)
            self.collapse_update.config(fg=COLOR_ORANGE)
        else:
            for level, widget, short in (
                ("session", self.collapse_5h, "5小时"),
                ("weekly", self.collapse_weekly, "周"),
            ):
                q = self.last_data.get("quotas", {}).get(level)
                if q:
                    pct = q["percent"]
                    reset_ts = int(q.get("reset_ts", 0))
                    if reset_ts > 0 and reset_ts <= int(time.time()):
                        widget.config(text=f"{short}:待刷新", fg=COLOR_ORANGE)
                    else:
                        widget.config(text=f"{short}:{pct:.1f}%", fg=color_for_percent(pct))
                else:
                    widget.config(text=f"{short}:—", fg=COLOR_FG_DIM)
            self.collapse_update.config(fg=COLOR_ORANGE)
        # 其他启用标的
        compact = []
        for item in self.target_defs:
            tid = item.get("id")
            if tid == "volcano" or not item.get("enabled"):
                continue
            row = self.target_rows.get(tid)
            if row and row.last_data and row.last_data.get("percent") is not None:
                compact.append(f"{item.get('name', tid)}:{float(row.last_data.get('percent')):.0f}%")
            else:
                compact.append(f"{item.get('name', tid)}:待接入")
        if compact:
            text = " | ".join(compact)
            self.collapse_mimo.config(text=text[:18], fg=COLOR_ORANGE)
        else:
            self.collapse_mimo.config(text="", fg=COLOR_FG_DIM)

    # ---------- 倒计时 tick ----------
    def _tick_reset_loop(self):
        for row in list(self.rows.values()) + list(self.target_rows.values()):
            row.tick_reset()
        self._mark_expired_quotas()
        try:
            self.root.after(1000, self._tick_reset_loop)
        except Exception:
            pass

    def _mark_expired_quotas(self):
        if not self.last_data:
            return
        now = int(time.time())
        expired = False
        for level, q in self.last_data.get("quotas", {}).items():
            reset_ts = int(q.get("reset_ts", 0))
            if reset_ts > 0 and reset_ts <= now:
                expired = True
                label = LEVEL_LABELS.get(level, level)
                if level in self.rows:
                    self.rows[level].reset_var.set(f"{label} 已到重置点，等待更新")
        if expired and not self.has_error:
            self.footer.config(text="已到重置点，等待接口更新…", fg=COLOR_ORANGE)
        self._refresh_compact_label()

    # ---------- 闪烁警告 ----------
    def flash_warning(self, times: int = 6):
        if self._flash_after_id:
            try:
                self.root.after_cancel(self._flash_after_id)
            except Exception:
                pass
        self._flash_count = times * 2
        self._flash_step()

    def _flash_step(self):
        if self._flash_count <= 0:
            for w in (self.title_bar, self.toggle_btn, self.title_label,
                      self.targets_btn, self.update_btn, self.close_btn, self.collapse_title,
                      self.collapse_5h, self.collapse_weekly,
                      self.collapse_mimo_sep, self.collapse_mimo,
                      self.collapse_update, self.collapse_targets):
                try:
                    w.config(bg=COLOR_BG_LIGHT)
                except Exception:
                    pass
            return
        bg = COLOR_RED if (self._flash_count % 2 == 0) else COLOR_BG_LIGHT
        for w in (self.title_bar, self.toggle_btn, self.title_label,
                  self.targets_btn, self.update_btn, self.close_btn, self.collapse_title,
                  self.collapse_5h, self.collapse_weekly,
                  self.collapse_mimo_sep, self.collapse_mimo,
                  self.collapse_update, self.collapse_targets):
            try:
                w.config(bg=bg)
            except Exception:
                pass
        self._flash_count -= 1
        self._flash_after_id = self.root.after(250, self._flash_step)

    # ---------- 主循环入口 ----------
    def schedule(self, ms: int, fn):
        return self.root.after(ms, fn)

    def run(self):
        self.root.mainloop()
