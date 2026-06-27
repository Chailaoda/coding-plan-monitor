#!/usr/bin/env python3.11
"""
Coding Plan Monitor 主程序
- 启动 Tk 悬浮窗
- 后台线程每 60 秒拉取一次用量
- 触发提醒 + 持久化历史
"""

import json
import os
import subprocess
import sys
import threading
import time
import traceback

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS_DIR)

from api import load_config, fetch_and_parse, fetch_mimo_usage, fetch_stepfun_usage, resolve_mimo_credentials, resolve_stepfun_credentials, AuthError, APIError
from storage import Storage
from notifier import AlertManager
from ui import FloatingWindow
from tray import TrayManager


CONFIG_PATH = os.path.join(THIS_DIR, "config.json")

TARGET_PRESETS = {
    "volcano": {
        "id": "volcano",
        "name": "火山方舟",
        "url": "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?advancedActiveKey=subscribe",
        "enabled": True,
        "implemented": True,
    },
    "mimo": {
        "id": "mimo",
        "name": "MiMo",
        "url": "https://platform.xiaomimimo.com/console/plan-manage",
        "enabled": False,
        "implemented": True,
    },
    "stepfun": {
        "id": "stepfun",
        "name": "阶跃星辰",
        "url": "https://platform.stepfun.com/plan-subscribe",
        "enabled": False,
        "implemented": True,
    },
    "xfyun": {
        "id": "xfyun",
        "name": "讯飞 MaaS",
        "url": "https://maas.xfyun.cn/modelService",
        "enabled": False,
        "implemented": False,
    },
}


def save_config(cfg: dict):
    """保存配置（用于持久化窗口位置/折叠状态）"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.chmod(CONFIG_PATH, 0o600)
    except Exception as e:
        print(f"[save_config] {e}")


def normalize_targets(config: dict) -> list:
    saved = config.get("targets", {})
    if isinstance(saved, list):
        saved = {item.get("id"): item for item in saved if isinstance(item, dict)}
    if not isinstance(saved, dict):
        saved = {}
    targets = []
    for tid, preset in TARGET_PRESETS.items():
        item = dict(preset)
        old = saved.get(tid, {})
        if isinstance(old, bool):
            item["enabled"] = old
        elif isinstance(old, dict):
            item.update({k: v for k, v in old.items() if k in ("enabled", "name", "url")})
        targets.append(item)
    config["targets"] = {item["id"]: {"enabled": bool(item.get("enabled"))} for item in targets}
    return targets


def target_enabled(config: dict, target_id: str) -> bool:
    targets = normalize_targets(config)
    for item in targets:
        if item.get("id") == target_id:
            return bool(item.get("enabled"))
    return False


class App:
    def __init__(self, config: dict):
        self.config = config
        self.targets = normalize_targets(self.config)
        save_config(self.config)
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
            on_update_click=self._open_console_for_update,
            on_target_toggle=self._on_target_toggle,
            on_open_target=self._open_target_console,
            initial_x=pos.get("x", 1500),
            initial_y=pos.get("y", 80),
            initial_collapsed=ui_cfg.get("collapsed", False),
            alpha=ui_cfg.get("alpha", 0.92),
            always_on_top=ui_cfg.get("always_on_top", True),
        )
        self.win.set_targets(self.targets)

        self._stop_evt = threading.Event()
        self._consec_fail = 0
        self._mimo_cookie = None
        self._mimo_last_alert_pct = -1
        self._stepfun_creds = None
        self._stepfun_last_alert_pct = -1
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

            if target_enabled(self.config, "volcano"):
                self._fetch_volcano()
            else:
                self._consec_fail = 0

            if target_enabled(self.config, "mimo"):
                self._fetch_mimo()

            if target_enabled(self.config, "stepfun"):
                self._fetch_stepfun()

            self._mark_unimplemented_targets()

            # 顺手清理过期数据（每次拉取都做开销很小）
            try:
                keep = self.config.get("storage", {}).get("history_keep_days", 90)
                self.storage.cleanup_old(keep)
                self.storage.cleanup_alerts_before(int(time.time()))
            except Exception:
                pass

    def _fetch_volcano(self):
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
            return
        except APIError as e:
            self._consec_fail += 1
            msg = f"接口错误: {e}"
            print(f"[fetch] {msg}")
            self._safe_call(self.win.update_error, msg)
            try:
                self.tray.update_error("volcano", str(e))
            except Exception:
                pass
            return
        except Exception as e:
            self._consec_fail += 1
            print(f"[fetch] 未知错误: {e}")
            traceback.print_exc()
            self._safe_call(self.win.update_error, f"错误: {e}")
            try:
                self.tray.update_error("volcano", str(e))
            except Exception:
                pass
            return

        self._consec_fail = 0
        try:
            self.storage.save_snapshot(data)
        except Exception as e:
            print(f"[storage] {e}")
        try:
            self.alert_mgr.evaluate(data)
        except Exception as e:
            print(f"[alert] {e}")
            traceback.print_exc()
        self._safe_call(self.win.update_data, data)
        try:
            self.tray.update_volcano(data)
        except Exception as e:
            print(f"[tray] update_volcano 失败: {e}")

    def _mark_unimplemented_targets(self):
        for item in self.targets:
            if item.get("enabled") and not item.get("implemented"):
                self._safe_call(
                    self.win.update_target_error,
                    item.get("id"),
                    "待接入自动抓取，点击打开控制台",
                )

    def _fetch_mimo(self):
        """拉取 MiMo 用量并推送到 UI 与托盘"""
        try:
            if not self._mimo_cookie:
                self._mimo_cookie = resolve_mimo_credentials(self.config)
            data = fetch_mimo_usage(self._mimo_cookie)
            self._safe_call(self.win.update_target, "mimo", data)
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
            self._safe_call(self.win.update_target_error, "mimo", str(e))
            try:
                self.tray.update_error("mimo", str(e))
            except Exception:
                pass
        except APIError as e:
            print(f"[mimo] 接口错误: {e}")
            self._safe_call(self.win.update_target_error, "mimo", str(e))
            try:
                self.tray.update_error("mimo", str(e))
            except Exception:
                pass
        except Exception as e:
            print(f"[mimo] 未知错误: {e}")
            traceback.print_exc()
            self._safe_call(self.win.update_target_error, "mimo", str(e))
            try:
                self.tray.update_error("mimo", str(e))
            except Exception:
                pass

    def _fetch_stepfun(self):
        """拉取阶跃星辰用量并推送到 UI"""
        try:
            if not self._stepfun_creds:
                self._stepfun_creds = resolve_stepfun_credentials(self.config)
            token, webid, cookie = self._stepfun_creds
            data = fetch_stepfun_usage(token, webid, cookie)
            self._safe_call(self.win.update_target, "stepfun", data)
            try:
                self.tray.update_target("stepfun", data)
            except Exception:
                pass
            try:
                pct = data["percent"]
                bucket = int(pct // 5) * 5
                if bucket != self._stepfun_last_alert_pct and bucket >= 60:
                    self._stepfun_last_alert_pct = bucket
                    from notifier import send_notification
                    if bucket >= 90:
                        from notifier import play_sound
                        send_notification("阶跃星辰额度告警", f"阶跃星辰已使用 {pct:.1f}%", urgency="critical")
                        if self.config.get("alerts", {}).get("sound_enabled", True):
                            play_sound()
                        self._safe_call(self.win.flash_warning, 4)
                    else:
                        send_notification("阶跃星辰额度提醒", f"阶跃星辰已使用 {pct:.1f}%", urgency="normal")
            except Exception as e:
                print(f"[stepfun-alert] {e}")
        except AuthError as e:
            print(f"[stepfun] 认证失败: {e}")
            self._stepfun_creds = None
            self._safe_call(self.win.update_target_error, "stepfun", str(e))
            try:
                self.tray.update_error("stepfun", str(e))
            except Exception:
                pass
        except APIError as e:
            print(f"[stepfun] 接口错误: {e}")
            self._safe_call(self.win.update_target_error, "stepfun", str(e))
            try:
                self.tray.update_error("stepfun", str(e))
            except Exception:
                pass
        except Exception as e:
            print(f"[stepfun] 未知错误: {e}")
            traceback.print_exc()
            self._safe_call(self.win.update_target_error, "stepfun", str(e))
            try:
                self.tray.update_error("stepfun", str(e))
            except Exception:
                pass

    def _trigger_refresh(self):
        """托盘"刷新"菜单：唤醒后台线程立即拉取一次"""
        try:
            self._refresh_evt.set()
        except Exception:
            pass

    def _open_url(self, url: str) -> bool:
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            self._safe_call(self.win.update_error, f"打开控制台失败: {e}")
            return False

    def _open_target_console(self, target_id: str):
        item = TARGET_PRESETS.get(target_id)
        if not item:
            return
        if not self._open_url(item.get("url", "")):
            return
        self._safe_call(self.win.mark_target_update_opened, target_id)
        try:
            self.win.root.after(15000, self._trigger_refresh)
            self.win.root.after(45000, self._trigger_refresh)
        except Exception:
            self._trigger_refresh()

    def _open_console_for_update(self):
        for item in self.targets:
            if item.get("enabled"):
                self._open_target_console(item.get("id"))
                return
        self._open_target_console("volcano")

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

    def _on_target_toggle(self, target_id: str, enabled: bool):
        if target_id not in TARGET_PRESETS:
            return
        self.config.setdefault("targets", {}).setdefault(target_id, {})["enabled"] = bool(enabled)
        self.targets = normalize_targets(self.config)
        save_config(self.config)
        self._safe_call(self.win.set_targets, self.targets)
        self._trigger_refresh()

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
