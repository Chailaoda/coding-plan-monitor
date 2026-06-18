"""
系统托盘双图标管理（火山方舟 + MiMo）

- 用 pystray (XEmbed 后端) 实现，在 UOS DDE 任务栏右下角显示两个图标
- 图标内容：22x22 进度环，按用量百分比绘制
  - 火山图标：取 5h/周/月 三者中"最高百分比"作为显示
  - MiMo 图标：直接用 MiMo 总用量百分比
- 颜色阈值：<60 绿、60-90 黄、>=90 红、无数据灰
- tooltip：英文/ASCII，因 X11 WM_NAME 协议限制 latin-1（中文会崩）
- pystray XEmbed 后端不支持右键菜单；左键点击触发 default action（切换悬浮窗）

依赖：pystray, Pillow（已通过 requirements.txt）
"""

import threading
import subprocess
import time
from datetime import datetime
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    HAS_PYSTRAY = True
except Exception:
    HAS_PYSTRAY = False
    pystray = None  # type: ignore


def _safe_title(s: str) -> str:
    """转成 latin-1 安全字符串（X11 WM_NAME 协议限制）。中文会被替换为 ?"""
    try:
        s.encode("latin-1")
        return s
    except UnicodeEncodeError:
        return s.encode("ascii", "replace").decode("ascii")


ICON_SIZE = 22

COLOR_GREEN = (48, 209, 88, 255)
COLOR_ORANGE = (255, 159, 10, 255)
COLOR_RED = (255, 55, 95, 255)
COLOR_GRAY = (140, 140, 140, 255)
COLOR_TRACK = (60, 60, 64, 255)


def _color_for_percent(pct: Optional[float]):
    if pct is None:
        return COLOR_GRAY
    if pct >= 90:
        return COLOR_RED
    if pct >= 60:
        return COLOR_ORANGE
    return COLOR_GREEN


def _make_icon(percent: Optional[float]) -> "Image.Image":
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((1, 1, ICON_SIZE - 2, ICON_SIZE - 2), outline=COLOR_TRACK, width=2)

    if percent is None:
        d.ellipse((4, 4, ICON_SIZE - 5, ICON_SIZE - 5), fill=COLOR_GRAY)
        try:
            font = ImageFont.load_default()
            d.text((7, 4), "?", fill=(0, 0, 0, 255), font=font)
        except Exception:
            pass
        return img

    color = _color_for_percent(percent)
    pct = max(0.0, min(100.0, float(percent)))
    bbox = (1, 1, ICON_SIZE - 2, ICON_SIZE - 2)
    start_angle = -90
    end_angle = start_angle + (pct / 100.0) * 360.0
    d.pieslice(bbox, start=start_angle, end=end_angle, fill=color, outline=color)

    cx = ICON_SIZE / 2
    cy = ICON_SIZE / 2
    r = 4
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    return img


def _xdg_open(url: str):
    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[tray] xdg-open error: {e}")


VOLCANO_URL = "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?advancedActiveKey=subscribe"
MIMO_URL = "https://platform.xiaomimimo.com/console/plan-manage"


class TrayManager:
    """管理两个 pystray.Icon 实例（火山 + MiMo）"""

    def __init__(
        self,
        on_toggle_window: Callable[[], None],
        on_show_window: Callable[[], None],
        on_quit: Callable[[], None],
        on_refresh: Callable[[], None],
    ):
        self.on_toggle_window = on_toggle_window
        self.on_show_window = on_show_window
        self.on_quit = on_quit
        self.on_refresh = on_refresh

        self._volcano_data: Optional[dict] = None
        self._mimo_data: Optional[dict] = None

        self.volcano_icon = None
        self.mimo_icon = None
        self._threads = []

        if not HAS_PYSTRAY:
            print("[tray] pystray not installed, tray disabled")
            return

        # XEmbed 后端不支持右键菜单。default=True 让左键单击触发 toggle
        self.volcano_icon = pystray.Icon(
            "cpm-volcano",
            _make_icon(None),
            _safe_title("Volcano (no data)"),
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Toggle window",
                    lambda _icon, _item: self._safe(self.on_toggle_window),
                    default=True,
                ),
            ),
        )
        self.mimo_icon = pystray.Icon(
            "cpm-mimo",
            _make_icon(None),
            _safe_title("MiMo (no data)"),
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Toggle window",
                    lambda _icon, _item: self._safe(self.on_toggle_window),
                    default=True,
                ),
            ),
        )

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:
            print(f"[tray] callback error: {e}")

    def start(self):
        if not HAS_PYSTRAY:
            return
        for icon in (self.volcano_icon, self.mimo_icon):
            if icon is None:
                continue
            t = threading.Thread(target=icon.run, daemon=True, name=f"tray-{icon.name}")
            t.start()
            self._threads.append(t)
        time.sleep(0.3)

    def stop(self):
        for icon in (self.volcano_icon, self.mimo_icon):
            if icon is None:
                continue
            try:
                icon.stop()
            except Exception:
                pass

    def update_volcano(self, data: dict):
        if self.volcano_icon is None:
            return
        self._volcano_data = data
        quotas = data.get("quotas", {})
        max_pct = -1.0
        for level in ("session", "weekly", "monthly"):
            q = quotas.get(level)
            if q:
                p = float(q.get("percent", 0))
                if p > max_pct:
                    max_pct = p
        if max_pct < 0:
            self.volcano_icon.icon = _make_icon(None)
            self.volcano_icon.title = _safe_title("Volcano (no data)")
            return
        self.volcano_icon.icon = _make_icon(max_pct)
        parts = []
        for level, label in (("session", "5h"), ("weekly", "wk"), ("monthly", "mo")):
            q = quotas.get(level)
            if q:
                parts.append(f"{label}:{float(q.get('percent',0)):.1f}%")
        ts = datetime.now().strftime("%H:%M:%S")
        self.volcano_icon.title = _safe_title(
            "Volcano  " + "  ".join(parts) + f"  ({ts})"
        )

    def update_mimo(self, data: dict):
        if self.mimo_icon is None:
            return
        self._mimo_data = data
        pct = data.get("percent")
        if pct is None:
            self.mimo_icon.icon = _make_icon(None)
            self.mimo_icon.title = _safe_title("MiMo (no data)")
            return
        self.mimo_icon.icon = _make_icon(float(pct))
        period_end = data.get("period_end", "") or ""
        plan = data.get("plan_name", "") or ""
        rem = ""
        try:
            if period_end:
                end_dt = datetime.strptime(period_end[:19], "%Y-%m-%d %H:%M:%S")
                diff = end_dt - datetime.now()
                if diff.total_seconds() > 0:
                    rem = f"  rem {diff.days}d"
        except Exception:
            pass
        ts = datetime.now().strftime("%H:%M:%S")
        title = f"MiMo  {float(pct):.1f}%"
        if plan:
            title += f"  ({plan})"
        title += rem + f"  ({ts})"
        self.mimo_icon.title = _safe_title(title)

    def update_error(self, source: str, msg: str):
        icon = self.volcano_icon if source == "volcano" else self.mimo_icon
        if icon is None:
            return
        icon.icon = _make_icon(None)
        prefix = "Volcano" if source == "volcano" else "MiMo"
        icon.title = _safe_title(f"{prefix} error: {msg[:60]}")
