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
WIN_HEIGHT_EXPANDED = 220
WIN_HEIGHT_COLLAPSED = 28

LEVEL_ORDER = ("session", "weekly", "monthly")


def color_for_percent(pct: float) -> str:
    if pct >= 90:
        return COLOR_RED
    if pct >= 60:
        return COLOR_ORANGE
    return COLOR_GREEN


def format_reset(ts: int) -> str:
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
        self.reset_var.set(f"距重置：{format_reset(q.get('reset_ts', 0))}")

    def tick_reset(self):
        if self.last_q:
            self.reset_var.set(f"距重置：{format_reset(self.last_q.get('reset_ts', 0))}")


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


class FloatingWindow:
    """主悬浮窗"""

    def __init__(
        self,
        on_close: Optional[Callable] = None,
        on_position_change: Optional[Callable[[int, int], None]] = None,
        on_collapse_change: Optional[Callable[[bool], None]] = None,
        initial_x: int = 1500,
        initial_y: int = 80,
        initial_collapsed: bool = False,
        alpha: float = 0.92,
        always_on_top: bool = True,
    ):
        self.on_close_cb = on_close
        self.on_position_change_cb = on_position_change
        self.on_collapse_change_cb = on_collapse_change

        self.collapsed = initial_collapsed
        self.last_data: Optional[dict] = None
        self._visible = True
        self.last_fetch_time: Optional[datetime] = None

        self.root = tk.Tk()
        self.root.title("火山codingplan")
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

        h = WIN_HEIGHT_COLLAPSED if self.collapsed else WIN_HEIGHT_EXPANDED
        self.root.geometry(f"{WIN_WIDTH}x{h}+{initial_x}+{initial_y}")

        self._drag_dx = 0
        self._drag_dy = 0
        self._drag_moved = False
        self._flash_count = 0
        self._flash_after_id = None

        self._build_ui()
        self._bind_drag(self.title_bar)
        self._bind_drag(self.title_label)
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
            self.title_bar, text="火山codingplan|MIMO",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG, font=("Sans", 9, "bold"),
        )
        self.title_label.pack(side="left")



        self.close_btn = tk.Label(
            self.title_bar, text="✕",
            bg=COLOR_BG_LIGHT, fg=COLOR_FG_DIM, font=("Sans", 11),
            cursor="hand2", padx=8,
        )
        self.close_btn.pack(side="right")
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

        self.body = tk.Frame(self.root, bg=COLOR_BG)
        self.body.pack(fill="both", expand=True)

        self.rows = {}
        for level in LEVEL_ORDER:
            self.rows[level] = QuotaRow(self.body, level)

        self.mimo_row = MimoRow(self.body)

        self.footer = tk.Label(
            self.body, text="等待数据…",
            bg=COLOR_BG, fg=COLOR_FG_DIM, font=("Sans", 7), anchor="e",
        )
        self.footer.pack(fill="x", side="bottom", padx=8, pady=(2, 4))

    def _apply_expanded_layout(self):
        for w in (self.collapse_title, self.collapse_sep, self.collapse_5h,
                  self.collapse_weekly, self.collapse_mimo_sep, self.collapse_mimo):
            w.pack_forget()
        self.toggle_btn.pack(side="left")
        self.title_label.pack(side="left")
        self.body.pack(fill="both", expand=True)
        self.toggle_btn.config(text="▼")

    def _apply_collapsed_layout(self):
        self.body.pack_forget()
        self.title_label.pack_forget()
        self.toggle_btn.pack(side="left")
        self.toggle_btn.config(text="▶")
        self.collapse_title.pack(side="left")
        self.collapse_5h.pack(side="left", padx=(2, 0))
        self.collapse_weekly.pack(side="left", padx=(2, 0))
        self.collapse_mimo_sep.pack(side="left", padx=(1, 0))
        self.collapse_mimo.pack(side="left", padx=(1, 0))

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
    def toggle_collapse(self):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.root.geometry(f"{WIN_WIDTH}x{WIN_HEIGHT_COLLAPSED}")
            self._apply_collapsed_layout()
        else:
            self.root.geometry(f"{WIN_WIDTH}x{WIN_HEIGHT_EXPANDED}")
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
        self.footer.config(text=msg[:42], fg=COLOR_RED)

    def update_mimo(self, data: dict):
        self.mimo_row.update(data)
        self._refresh_compact_label()

    def _refresh_compact_label(self):
        if not self.last_data:
            self.collapse_5h.config(text="5小时:—", fg=COLOR_FG_DIM)
            self.collapse_weekly.config(text="周:—", fg=COLOR_FG_DIM)
        else:
            for level, widget, short in (
                ("session", self.collapse_5h, "5小时"),
                ("weekly", self.collapse_weekly, "周"),
            ):
                q = self.last_data.get("quotas", {}).get(level)
                if q:
                    pct = q["percent"]
                    widget.config(text=f"{short}:{pct:.1f}%", fg=color_for_percent(pct))
                else:
                    widget.config(text=f"{short}:—", fg=COLOR_FG_DIM)
        # MiMo
        if self.mimo_row.last_data:
            pct = self.mimo_row.last_data.get("percent", 0)
            self.collapse_mimo.config(text=f"MiMo:{pct:.1f}%", fg=color_for_percent(pct))
        else:
            self.collapse_mimo.config(text="MiMo:—", fg=COLOR_FG_DIM)

    # ---------- 倒计时 tick ----------
    def _tick_reset_loop(self):
        for row in list(self.rows.values()) + [self.mimo_row]:
            row.tick_reset()
        try:
            self.root.after(1000, self._tick_reset_loop)
        except Exception:
            pass

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
                      self.close_btn, self.collapse_title,
                      self.collapse_5h, self.collapse_weekly,
                      self.collapse_mimo_sep, self.collapse_mimo):
                try:
                    w.config(bg=COLOR_BG_LIGHT)
                except Exception:
                    pass
            return
        bg = COLOR_RED if (self._flash_count % 2 == 0) else COLOR_BG_LIGHT
        for w in (self.title_bar, self.toggle_btn, self.title_label,
                  self.close_btn, self.collapse_title,
                  self.collapse_5h, self.collapse_weekly,
                  self.collapse_mimo_sep, self.collapse_mimo):
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
