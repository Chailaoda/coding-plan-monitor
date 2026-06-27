"""
桌面通知与铃声
- 调用系统 notify-send 发送通知
- 用 paplay 播放系统提示音
- 阈值判定 + 防重复（依赖 storage.alert_history）
"""

import shutil
import subprocess
from typing import Callable, Optional


# 阈值定义：每个 level 对应若干阈值，按从低到高
# 同一周期内只在跨越阈值时提醒一次
LEVEL_THRESHOLDS = {
    "session": [
        (70, "normal", "5 小时额度提醒", "已使用 70%"),
        (90, "critical", "5 小时额度紧急告警", "已使用 90%！"),
        (98, "critical", "5 小时额度即将耗尽", "已使用 98%！请暂停使用"),
    ],
    "weekly": [
        (80, "normal", "本周额度提醒", "已使用 80%"),
        (95, "critical", "本周额度紧急告警", "已使用 95%！"),
    ],
    "monthly": [
        (80, "normal", "本月额度提醒", "已使用 80%"),
        (95, "critical", "本月额度紧急告警", "已使用 95%！"),
    ],
}


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def send_notification(title: str, body: str, urgency: str = "normal"):
    """通过 notify-send 发送桌面通知"""
    if not _has("notify-send"):
        print(f"[NOTIFY-FALLBACK] {title}: {body}")
        return
    try:
        subprocess.Popen(
            ["notify-send", "-u", urgency, "-a", "Coding Plan Monitor", "-t", "8000",
             title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[NOTIFY-ERROR] {e}")


def play_sound():
    """播放系统提示音（尽量不阻塞）"""
    candidates = [
        "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga",
        "/usr/share/sounds/freedesktop/stereo/bell.oga",
        "/usr/share/sounds/freedesktop/stereo/complete.oga",
        "/usr/share/sounds/alsa/Front_Center.wav",
    ]
    for p in candidates:
        try:
            import os
            if os.path.exists(p):
                if _has("paplay"):
                    subprocess.Popen(["paplay", p],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                if _has("aplay"):
                    subprocess.Popen(["aplay", "-q", p],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
        except Exception:
            continue
    # 最后兜底：终端 bell
    try:
        print("\a", end="", flush=True)
    except Exception:
        pass


class AlertManager:
    """阈值检测 + 防重复 + 触发通知/铃声/UI闪烁"""

    def __init__(
        self,
        storage,
        sound_enabled: bool = True,
        notify_enabled: bool = True,
        on_critical: Optional[Callable[[], None]] = None,
        custom_thresholds: Optional[dict] = None,
    ):
        self.storage = storage
        self.sound_enabled = sound_enabled
        self.notify_enabled = notify_enabled
        self.on_critical = on_critical
        # 允许 config 覆盖默认阈值（仅替换数值，不改文案）
        self.thresholds = self._build_thresholds(custom_thresholds)

    def _build_thresholds(self, custom: Optional[dict]):
        if not custom:
            return LEVEL_THRESHOLDS
        result = {}
        # custom 形如：{"session": {"warn":70,"critical":90,"emergency":98}, ...}
        for level, defaults in LEVEL_THRESHOLDS.items():
            cfg = custom.get(level, {}) if isinstance(custom, dict) else {}
            result[level] = []
            # 默认按 warn/critical/emergency 顺序映射
            keys = ("warn", "critical", "emergency")
            for i, (def_pct, urg, title, body) in enumerate(defaults):
                if i < len(keys) and keys[i] in cfg:
                    pct = int(cfg[keys[i]])
                else:
                    pct = def_pct
                result[level].append((pct, urg, title, body))
        return result

    def evaluate(self, data: dict):
        """
        检查三个 level 是否跨越阈值。跨越则发送通知（同一周期内不重复）。
        返回是否触发了 critical 级别（供 UI 闪烁）。
        """
        triggered_critical = False
        for level, q in data.get("quotas", {}).items():
            pct = float(q.get("percent", 0))
            cycle_reset = int(q.get("reset_ts", 0))
            label = q.get("label", level)

            for threshold_pct, urgency, title, body in self.thresholds.get(level, []):
                if pct < threshold_pct:
                    continue
                if self.storage.has_alerted(level, threshold_pct, cycle_reset):
                    continue
                # 触发！
                full_title = title
                full_body = f"{label}：{body}（当前 {pct:.2f}%）"
                if self.notify_enabled:
                    send_notification(full_title, full_body, urgency=urgency)
                if self.sound_enabled and urgency == "critical":
                    play_sound()
                self.storage.mark_alerted(level, threshold_pct, cycle_reset)
                if urgency == "critical":
                    triggered_critical = True

        if triggered_critical and self.on_critical:
            try:
                self.on_critical()
            except Exception:
                pass
        return triggered_critical

    def notify_auth_failure(self):
        """认证失败专用提醒（半小时内只发一次）"""
        # 用 storage.alert_history 借位实现：cycle_reset 用半小时后时间戳
        import time
        now = int(time.time())
        bucket = (now // 1800) * 1800  # 半小时桶
        if self.storage.has_alerted("__auth__", 0, bucket):
            return
        send_notification(
            "Coding Plan Monitor 认证失败",
            "Cookie 可能已过期，请重新从浏览器导出。\n参考: cookie导出指南.md",
            urgency="normal",
        )
        self.storage.mark_alerted("__auth__", 0, bucket)
