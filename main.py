#!/usr/bin/env python3.11
"""
Coding Plan Monitor 主程序
- 启动 Tk 悬浮窗
- 后台线程每 60 秒拉取一次用量
- 触发提醒 + 持久化历史
"""

import json
import os
import sys
import threading
import time
import traceback

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS_DIR)

from api import load_config, fetch_and_parse, fetch_mimo_usage, resolve_mimo_credentials, AuthError, APIError
from storage import Storage
from notifier import AlertManager
from ui import FloatingWindow
from tray import TrayManager


CONFIG_PATH = os.path.join(THIS_DIR, "config.json")


def save_config(cfg: dict):
    """保存配置（用于持久化窗口位置/折叠状态）"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.chmod(CONFIG_PATH, 0o600)
    except Exception as e:
        print(f"[save_config] {e}")


class App:
    def __init__(self, config: dict):
        self.config = config
        self.storage = Storage()
        self.alert_mgr = AlertManager(
            self.storage,
            sound_enabled=config.get("alerts", {}).get("sound_enabled", True),
            notify_enabled=config.get("alerts", {}).get("notify_enabled", True),
            on_critical=lambda: self._safe_call(self.win.flash_warning, 6),
            custom_thresholds=config.get("alerts"),
        )

        ui_cfg = config.get("ui", {})
        pos = ui_cfg.get("position", {"x": 1500, "y": 80})
        self.win = FloatingWindow(
            on_close=self._on_close,
            on_position_change=self._on_position_change,
            on_collapse_change=self._on_collapse_change,
            initial_x=pos.get("x", 1500),
            initial_y=pos.get("y", 80),
            initial_collapsed=ui_cfg.get("collapsed", False),
            alpha=ui_cfg.get("alpha", 0.92),
            always_on_top=ui_cfg.get("always_on_top", True),
        )

        self._stop_evt = threading.Event()
        self._consec_fail = 0
        self._mimo_cookie = None
        self._mimo_last_alert_pct = -1
        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)

        # 系统托盘
        self.tray = TrayManager(
            on_toggle_window=lambda: self._safe_call(self.win.toggle_visible),
            on_show_window=lambda: self._safe_call(self.win.show),
            on_quit=self._on_tray_quit,
            on_refresh=self._trigger_refresh,
        )
        self._refresh_evt = threading.Event()

    # ------------------------- 后台拉取线程 -------------------------
    def _fetch_loop(self):
        # 启动后立即拉一次
        first = True
        while not self._stop_evt.is_set():
            if not first:
                interval = self.config.get("polling", {}).get("interval_seconds", 60)
                # 等待时支持被刷新事件唤醒
                woken = self._refresh_evt.wait(interval)
                if self._stop_evt.is_set():
                    break
                if woken:
                    self._refresh_evt.clear()
            first = False

            try:
                data = fetch_and_parse(self.config)
            except AuthError as e:
                self._consec_fail += 1
                msg = f"认证失败: {e}"
                print(f"[fetch] {msg}")
                self._safe_call(self.win.update_error, msg)
                try:
                    self.tray.update_error("volcano", str(e))
                except Exception:
                    pass
                if self._consec_fail >= 3:
                    self.alert_mgr.notify_auth_failure()
                # 即使火山失败，也继续拉 MiMo
                self._fetch_mimo()
                continue
            except APIError as e:
                self._consec_fail += 1
                msg = f"接口错误: {e}"
                print(f"[fetch] {msg}")
                self._safe_call(self.win.update_error, msg)
                try:
                    self.tray.update_error("volcano", str(e))
                except Exception:
                    pass
                self._fetch_mimo()
                continue
            except Exception as e:
                self._consec_fail += 1
                print(f"[fetch] 未知错误: {e}")
                traceback.print_exc()
                self._safe_call(self.win.update_error, f"错误: {e}")
                try:
                    self.tray.update_error("volcano", str(e))
                except Exception:
                    pass
                self._fetch_mimo()
                continue

            self._consec_fail = 0
            # 持久化
            try:
                self.storage.save_snapshot(data)
            except Exception as e:
                print(f"[storage] {e}")
            # 检查阈值（在子线程做，发通知是 fire-and-forget 的子进程）
            try:
                self.alert_mgr.evaluate(data)
            except Exception as e:
                print(f"[alert] {e}")
                traceback.print_exc()
            # 推到 UI（必须在主线程更新）
            self._safe_call(self.win.update_data, data)
            # 推到托盘
            try:
                self.tray.update_volcano(data)
            except Exception as e:
                print(f"[tray] update_volcano 失败: {e}")

            # --- MiMo 拉取 ---
            self._fetch_mimo()

            # 顺手清理过期数据（每次拉取都做开销很小）
            try:
                keep = self.config.get("storage", {}).get("history_keep_days", 90)
                self.storage.cleanup_old(keep)
                self.storage.cleanup_alerts_before(int(time.time()))
            except Exception:
                pass

    def _fetch_mimo(self):
        """拉取 MiMo 用量并推送到 UI 与托盘"""
        try:
            if not self._mimo_cookie:
                self._mimo_cookie = resolve_mimo_credentials(self.config)
            data = fetch_mimo_usage(self._mimo_cookie)
            self._safe_call(self.win.update_mimo, data)
            try:
                self.tray.update_mimo(data)
            except Exception as e:
                print(f"[tray] update_mimo 失败: {e}")
            # MiMo 阈值检查：每跨越 5% 提醒一次
            try:
                pct = data["percent"]
                bucket = int(pct // 5) * 5  # 0,5,10,...,95
                if bucket != self._mimo_last_alert_pct and bucket >= 60:
                    self._mimo_last_alert_pct = bucket
                    from notifier import send_notification
                    if bucket >= 90:
                        from notifier import play_sound
                        send_notification("MiMo 额度告警", f"MiMo 已使用 {pct:.1f}%", urgency="critical")
                        if self.config.get("alerts", {}).get("sound_enabled", True):
                            play_sound()
                        self._safe_call(self.win.flash_warning, 4)
                    else:
                        send_notification("MiMo 额度提醒", f"MiMo 已使用 {pct:.1f}%", urgency="normal")
            except Exception as e:
                print(f"[mimo-alert] {e}")
        except AuthError as e:
            print(f"[mimo] 认证失败: {e}")
            self._mimo_cookie = None
            try:
                self.tray.update_error("mimo", str(e))
            except Exception:
                pass
        except APIError as e:
            print(f"[mimo] 接口错误: {e}")
            try:
                self.tray.update_error("mimo", str(e))
            except Exception:
                pass
        except Exception as e:
            print(f"[mimo] 未知错误: {e}")
            traceback.print_exc()
            try:
                self.tray.update_error("mimo", str(e))
            except Exception:
                pass

    def _trigger_refresh(self):
        """托盘"刷新"菜单：唤醒后台线程立即拉取一次"""
        try:
            self._refresh_evt.set()
        except Exception:
            pass

    def _on_tray_quit(self):
        """托盘"退出"菜单：彻底退出程序"""
        # 先停托盘自身
        try:
            self.tray.stop()
        except Exception:
            pass
        # 然后让 Tk 主线程销毁窗口
        try:
            self.win.root.after(0, self.win.quit_app)
        except Exception:
            try:
                self.win.quit_app()
            except Exception:
                pass

    def _safe_call(self, fn, *args):
        """从子线程把回调投递到 Tk 主线程"""
        try:
            self.win.root.after(0, lambda: fn(*args))
        except Exception:
            pass

    # ------------------------- 配置回写 -------------------------
    def _on_position_change(self, x: int, y: int):
        self.config.setdefault("ui", {}).setdefault("position", {})
        self.config["ui"]["position"]["x"] = x
        self.config["ui"]["position"]["y"] = y
        save_config(self.config)

    def _on_collapse_change(self, collapsed: bool):
        self.config.setdefault("ui", {})["collapsed"] = collapsed
        save_config(self.config)

    def _on_close(self):
        self._stop_evt.set()
        try:
            self.storage.close()
        except Exception:
            pass

    # ------------------------- 主入口 -------------------------
    def run(self):
        self.tray.start()
        self._fetch_thread.start()
        try:
            self.win.run()
        except KeyboardInterrupt:
            pass
        finally:
            self._stop_evt.set()
            try:
                self.tray.stop()
            except Exception:
                pass


def main():
    # 加载配置（缺失则用 DEFAULT_CONFIG，auto 模式即可工作）
    if not os.path.exists(CONFIG_PATH):
        print(f"[info] 未找到 {CONFIG_PATH}，将使用默认配置（auto 模式 + 360 浏览器）")

    try:
        config = load_config(CONFIG_PATH)
    except Exception as e:
        print(f"[fatal] 配置加载失败: {e}")
        return 2

    auth = config.get("auth", {})
    mode = (auth.get("mode") or "auto").lower()
    if mode == "manual":
        if not auth.get("cookie") or "粘贴" in auth.get("cookie", ""):
            print("[fatal] 手动模式下 config.json 的 cookie 还是占位符，请按指南填写")
            return 3
    else:
        # auto 模式：开机时先尝试一次，失败给出友好提示但不阻止启动
        try:
            from cookie_loader import load_from_360
            cookie, csrf, exp = load_from_360()
            print(f"[auto-cookie] 已从 360 浏览器读取 Cookie（csrf={csrf[:8]}...）")
            if exp:
                import time as _t
                rem = exp - int(_t.time())
                print(f"[auto-cookie] digest 剩余有效期 {rem // 3600} 小时 {(rem % 3600) // 60} 分钟")
        except Exception as e:
            print(f"[auto-cookie] 警告: {e}")
            print("[auto-cookie] 程序仍将启动，后台拉取若失败会通过通知提醒")

    app = App(config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
