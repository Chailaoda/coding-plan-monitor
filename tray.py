"""
系统托盘单图标管理（火山 + MiMo 嵌套圆环）

设计：
- 22x22 单图标
- 外环：火山 5h 百分比（颜色按阈值，扇形长度按百分比）
- 内环：MiMo 百分比（颜色按阈值，但偏暗，用明暗区分内外）
- 中心：无（去掉中心点）
- 颜色阈值：<60 绿、60-90 黄、>=90 红、无数据灰
- tooltip：火山 5h:xx%, 周:xx%, 月:xx% | MiMo:xx%
- 左键点击：切换悬浮窗显示/隐藏

依赖：pystray, Pillow
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

# ============================================================
# Monkey-patches
# ============================================================

if HAS_PYSTRAY:
    try:
        import Xlib.X
        _orig_create_window = pystray._xorg.Icon._create_window

        def _patched_create_window(self):
            win = _orig_create_window(self)
            try:
                win.change_attributes(
                    event_mask=(
                        Xlib.X.ExposureMask
                        | Xlib.X.StructureNotifyMask
                        | Xlib.X.ButtonPressMask
                    )
                )
            except Exception as e:
                print(f"[tray] patch ButtonPressMask failed: {e}")
            return win

        pystray._xorg.Icon._create_window = _patched_create_window
    except Exception as e:
        print(f"[tray] patch ButtonPressMask failed: {e}")

    try:
        import Xlib.xobject.drawable
        _orig_set_wm_name = Xlib.xobject.drawable.Window.set_wm_name

        def _patched_set_wm_name(self, name):
            try:
                utf8_atom = self.display.get_atom("UTF8_STRING")
                net_wm_name = self.display.get_atom("_NET_WM_NAME")
                self.change_text_property(net_wm_name, utf8_atom, name)
            except Exception:
                pass
            try:
                _orig_set_wm_name(self, name)
            except Exception:
                pass

        Xlib.xobject.drawable.Window.set_wm_name = _patched_set_wm_name
    except Exception as e:
        print(f"[tray] patch UTF-8 tooltip failed: {e}")

# ============================================================
# 图标生成
# ============================================================

ICON_SIZE = 22

# 标准颜色（饱和，外环用）
COLOR_GREEN = (48, 209, 88, 255)
COLOR_ORANGE = (255, 159, 10, 255)
COLOR_RED = (255, 55, 95, 255)
COLOR_GRAY = (140, 140, 140, 255)

# 暗色版（内环用，明暗区分内外）
COLOR_GREEN_DIM = (24, 134, 56, 255)
COLOR_ORANGE_DIM = (180, 110, 0, 255)
COLOR_RED_DIM = (170, 30, 60, 255)
COLOR_GRAY_DIM = (90, 90, 90, 255)

COLOR_TRACK = (60, 60, 64, 255)
COLOR_BG = (35, 35, 38, 255)


def _color_for_percent(pct, dim=False):
    if pct is None:
        return COLOR_GRAY_DIM if dim else COLOR_GRAY
    if pct >= 90:
        return COLOR_RED_DIM if dim else COLOR_RED
    if pct >= 60:
        return COLOR_ORANGE_DIM if dim else COLOR_ORANGE
    return COLOR_GREEN_DIM if dim else COLOR_GREEN


def _draw_arc_ring(draw, bbox, percent, color, track_color, width):
    """画一个圆环：先画完整轨道，再叠加进度弧线（空心环）"""
    draw.arc(bbox, start=0, end=360, fill=track_color, width=width)
    if percent is None or percent <= 0:
        return
    pct = max(0.0, min(100.0, float(percent)))
    start_angle = -90
    end_angle = start_angle + (pct / 100.0) * 360.0
    draw.arc(bbox, start=start_angle, end=end_angle, fill=color, width=width)


def _make_icon(volcano_pct, mimo_pct):
    """固定图标：22x22 黑底 + 中央橙色实心圆 + 窄白圈。
    在 DDE 任务栏 22x22 下清晰可辨，不依赖外部图片资源。
    保留参数仅为兼容旧调用。"""
    return _build_static_icon()


_STATIC_ICON_CACHE = None


def _build_static_icon():
    global _STATIC_ICON_CACHE
    if _STATIC_ICON_CACHE is not None:
        return _STATIC_ICON_CACHE

    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)

    # 整体深底圆角（看似不是矩形）
    d.rounded_rectangle((0, 0, ICON_SIZE - 1, ICON_SIZE - 1), radius=4,
                        fill=(20, 20, 22, 255))

    # 外圈白色环（让中央色块从黑底跳出来）
    d.ellipse((2, 2, ICON_SIZE - 3, ICON_SIZE - 3),
              outline=(255, 255, 255, 255), width=1)

    # 中央橙色实心圆
    d.ellipse((4, 4, ICON_SIZE - 5, ICON_SIZE - 5),
              fill=(255, 159, 10, 255))

    _STATIC_ICON_CACHE = img
    return img


# ============================================================
# 辅助
# ============================================================

def _xdg_open(url):
    try:
        subprocess.Popen(["xdg-open", url],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[tray] xdg-open error: {e}")


VOLCANO_URL = "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?advancedActiveKey=subscribe"
MIMO_URL = "https://platform.xiaomimimo.com/console/plan-manage"


# ============================================================
# 托盘管理器（单图标）
# ============================================================

class TrayManager:
    """单图标管理器：外环=火山5h，内环=MiMo"""

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

        # 缓存数据
        self._volcano_data: Optional[dict] = None
        self._mimo_data: Optional[dict] = None
        self._volcano_5h_pct: Optional[float] = None
        self._mimo_pct: Optional[float] = None
        self._volcano_error: Optional[str] = None
        self._mimo_error: Optional[str] = None
        self._target_data: dict = {}
        self._target_errors: dict = {}

        self.icon = None
        self._thread: Optional[threading.Thread] = None

        if not HAS_PYSTRAY:
            print("[tray] pystray not installed, tray disabled")
            return

        self.icon = pystray.Icon(
            "cpm",
            _make_icon(None, None),
            self._build_title(),
            menu=pystray.Menu(
                pystray.MenuItem(
                    "切换悬浮窗",
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

    def _build_title(self):
        """tooltip：火山 5h:xx%, 周:xx%, 月:xx% | MiMo:xx%"""
        parts = []

        if self._volcano_error:
            parts.append(f"火山 错误: {self._volcano_error[:30]}")
        elif self._volcano_data:
            quotas = self._volcano_data.get("quotas", {})
            v_parts = []
            for level, label in (("session", "5h"), ("weekly", "周"), ("monthly", "月")):
                q = quotas.get(level)
                if q:
                    v_parts.append(f"{label}:{float(q.get('percent', 0)):.1f}%")
            if v_parts:
                parts.append("火山 " + ", ".join(v_parts))
            else:
                parts.append("火山 无数据")
        else:
            parts.append("火山 等待数据…")

        if self._mimo_error:
            parts.append(f"MiMo 错误: {self._mimo_error[:30]}")
        elif self._mimo_data:
            pct = self._mimo_data.get("percent")
            if pct is None:
                parts.append("MiMo 无数据")
            else:
                title = f"MiMo:{float(pct):.1f}%"
                period_end = self._mimo_data.get("period_end", "") or ""
                try:
                    if period_end:
                        end_dt = datetime.strptime(period_end[:19], "%Y-%m-%d %H:%M:%S")
                        diff = end_dt - datetime.now()
                        if diff.total_seconds() > 0:
                            title += f"  剩{diff.days}天"
                except Exception:
                    pass
                parts.append(title)
        else:
            parts.append("MiMo 等待数据…")

        for tid, tdata in self._target_data.items():
            if tid == "mimo":
                continue
            if tid in self._target_errors:
                parts.append(f"{tid} 错误: {self._target_errors[tid][:20]}")
            elif tdata:
                pct = tdata.get("percent")
                if pct is not None:
                    parts.append(f"{tid}:{float(pct):.1f}%")
                else:
                    parts.append(f"{tid} 无数据")

        ts = datetime.now().strftime("%H:%M:%S")
        return " | ".join(parts) + f" ({ts})"

    def _refresh_icon(self):
        """根据缓存重绘图标 + 更新 tooltip"""
        if self.icon is None:
            return
        try:
            self.icon.icon = _make_icon(self._volcano_5h_pct, self._mimo_pct)
        except Exception as e:
            print(f"[tray] update icon error: {e}")
        try:
            self.icon.title = self._build_title()
        except Exception as e:
            print(f"[tray] update title error: {e}")

    # ---------- 启停 ----------
    def start(self):
        if not HAS_PYSTRAY or self.icon is None:
            return
        self._thread = threading.Thread(target=self.icon.run, daemon=True, name="tray")
        self._thread.start()
        time.sleep(0.3)

    def stop(self):
        if self.icon is None:
            return
        try:
            self.icon.stop()
        except Exception:
            pass

    # ---------- 数据更新 ----------
    def update_volcano(self, data: dict):
        """火山数据：外环只看 5h 百分比，但 tooltip 仍带三档"""
        self._volcano_data = data
        self._volcano_error = None
        # 外环只取 session（5h）
        quotas = data.get("quotas", {}) if isinstance(data, dict) else {}
        session = quotas.get("session")
        if session:
            self._volcano_5h_pct = float(session.get("percent", 0))
        else:
            self._volcano_5h_pct = None
        self._refresh_icon()

    def update_mimo(self, data: dict):
        """MiMo 数据：内环显示总用量百分比"""
        self._mimo_data = data
        self._mimo_error = None
        pct = data.get("percent") if isinstance(data, dict) else None
        self._mimo_pct = float(pct) if pct is not None else None
        self._refresh_icon()

    def update_target(self, target_id: str, data: dict):
        self._target_data[target_id] = data
        self._target_errors.pop(target_id, None)
        self._refresh_icon()

    def update_error(self, source: str, msg: str):
        if source == "volcano":
            self._volcano_error = str(msg)
            self._volcano_5h_pct = None
        elif source == "mimo":
            self._mimo_error = str(msg)
            self._mimo_pct = None
        self._refresh_icon()
