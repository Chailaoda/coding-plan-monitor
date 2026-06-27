"""
火山方舟 Coding Plan 用量查询 API 封装
使用 urllib 实现，零外部依赖
"""

import json
import gzip
import urllib.request
import urllib.error
import os
from typing import Optional


API_URL = "https://console.volcengine.com/api/top/ark/cn-beijing/2024-01-01/GetCodingPlanUsage?"

# 火山方舟 Level 字段含义映射
LEVEL_LABELS = {
    "session": "5 小时",
    "weekly": "本周",
    "monthly": "本月",
}


class AuthError(Exception):
    """认证失败（cookie 过期等）"""
    pass


class APIError(Exception):
    """接口调用失败"""
    pass


DEFAULT_CONFIG = {
    "auth": {"mode": "auto", "cookie": "", "csrf_token": ""},
    "polling": {"interval_seconds": 60, "timeout_seconds": 10, "max_retries": 3},
    "ui": {
        "position": {"x": 1500, "y": 80},
        "collapsed": False,
        "always_on_top": True,
        "alpha": 0.92,
        "theme": "dark",
    },
    "alerts": {
        "session": {"warn": 70, "critical": 90, "emergency": 98},
        "weekly": {"warn": 80, "critical": 95},
        "monthly": {"warn": 80, "critical": 95},
        "mimo": {"warn": 60, "critical": 90},
        "sound_enabled": True,
        "notify_enabled": True,
    },
    "storage": {"history_enabled": True, "history_keep_days": 90},
    "targets": {
        "volcano": {"enabled": True},
        "mimo": {"enabled": False},
        "stepfun": {"enabled": False},
        "xfyun": {"enabled": False},
    },
}


def load_config(config_path: Optional[str] = None) -> dict:
    """加载配置文件；不存在则返回默认配置（auto 模式）"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if not os.path.exists(config_path):
        return json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_usage(cookie: str, csrf_token: str, timeout: int = 10) -> dict:
    """
    调用 GetCodingPlanUsage 接口

    Returns:
        {
            "Status": "Running",
            "UpdateTimestamp": 1781584858,
            "QuotaUsage": [
                {"Level": "session", "Percent": 0.92, "ResetTimestamp": 1781601656},
                {"Level": "weekly",  "Percent": 3.63, "ResetTimestamp": 1782057600},
                {"Level": "monthly", "Percent": 1.82, "ResetTimestamp": 1784131199}
            ]
        }

    Raises:
        AuthError: cookie 失效（401/403）
        APIError: 其他接口错误
    """
    if not cookie or not csrf_token:
        raise AuthError("cookie 或 csrf_token 为空，请先填写 config.json")

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh",
        "Content-Type": "application/json",
        "Cookie": cookie,
        "Origin": "https://console.volcengine.com",
        "Referer": "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?advancedActiveKey=subscribe",
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.251 Safari/537.36",
        "X-Csrf-Token": csrf_token,
        "Accept-Encoding": "gzip",
    }

    req = urllib.request.Request(
        API_URL,
        data=b"{}",
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # 处理 gzip
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthError(f"认证失败 ({e.code})，cookie 可能已过期")
        raise APIError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise APIError(f"网络错误: {e.reason}")
    except json.JSONDecodeError as e:
        raise APIError(f"响应不是合法 JSON: {e}")

    # 校验响应结构
    if "Result" not in data:
        # 火山引擎错误响应通常含 ResponseMetadata.Error
        err = data.get("ResponseMetadata", {}).get("Error", {})
        if err:
            code = err.get("Code", "")
            msg = err.get("Message", "")
            if "auth" in code.lower() or "credential" in code.lower():
                raise AuthError(f"{code}: {msg}")
            raise APIError(f"{code}: {msg}")
        raise APIError(f"响应缺少 Result 字段: {data}")

    return data["Result"]


def parse_usage(result: dict) -> dict:
    """
    将 API 响应解析为结构化数据

    Returns:
        {
            "status": "Running",
            "update_ts": 1781584858,
            "quotas": {
                "session": {"percent": 0.92, "reset_ts": 1781601656, "label": "5 小时"},
                "weekly":  {"percent": 3.63, "reset_ts": 1782057600, "label": "本周"},
                "monthly": {"percent": 1.82, "reset_ts": 1784131199, "label": "本月"}
            }
        }
    """
    quotas = {}
    for item in result.get("QuotaUsage", []):
        level = item["Level"]
        quotas[level] = {
            "percent": float(item.get("Percent", 0)),
            "reset_ts": int(item.get("ResetTimestamp", 0)),
            "label": LEVEL_LABELS.get(level, level),
        }
    return {
        "status": result.get("Status", "Unknown"),
        "update_ts": int(result.get("UpdateTimestamp", 0)),
        "quotas": quotas,
    }


def resolve_credentials(config: dict):
    """
    根据 config.auth.mode 返回 (cookie, csrf_token, exp_ts_or_None)。

    mode = "auto"   : 从 360 浏览器读取（默认，免维护）
    mode = "manual" : 使用 config.auth.cookie / csrf_token

    auto 模式失败时若 config 中有手填 cookie 则回退到手填。
    """
    auth = config.get("auth", {})
    mode = (auth.get("mode") or "auto").lower()

    if mode == "auto":
        try:
            from cookie_loader import load_from_360, CookieLoadError
            cookie, csrf, exp = load_from_360()
            return cookie, csrf, exp
        except Exception as e:
            # 自动失败，看有没有手填的可作为回退
            manual_cookie = auth.get("cookie", "")
            manual_csrf = auth.get("csrf_token", "")
            if manual_cookie and "粘贴" not in manual_cookie and manual_csrf:
                return manual_cookie, manual_csrf, None
            raise AuthError(f"自动读取 360 浏览器 Cookie 失败: {e}")

    # 手动模式
    cookie = auth.get("cookie", "")
    csrf = auth.get("csrf_token", "")
    if not cookie or "粘贴" in cookie:
        raise AuthError("手动模式下 config.auth.cookie 未填写")
    return cookie, csrf, None


MIMO_USAGE_URL = "https://platform.xiaomimimo.com/api/v1/tokenPlan/usage"
MIMO_DETAIL_URL = "https://platform.xiaomimimo.com/api/v1/tokenPlan/detail"


def fetch_mimo_usage(cookie: str, timeout: int = 10) -> dict:
    """
    调用小米 MiMo Token Plan 用量接口

    Returns:
        {
            "percent": 61.43,          # 总用量百分比 0~100
            "period_end": "2026-06-22 23:59:59",
            "plan_name": "Standard",
            "used": 6757476871,
            "limit": 11000000000,
        }

    Raises:
        AuthError: cookie 失效
        APIError: 其他接口错误
    """
    if not cookie:
        raise AuthError("MiMo cookie 为空")

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
        "Referer": "https://platform.xiaomimimo.com/console/plan-manage",
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.251 Safari/537.36",
        "Accept-Encoding": "gzip",
    }

    usage_data = {}
    detail_data = {}

    for label, url in [("usage", MIMO_USAGE_URL), ("detail", MIMO_DETAIL_URL)]:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                data = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AuthError(f"MiMo 认证失败 ({e.code})，cookie 可能已过期")
            raise APIError(f"MiMo HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise APIError(f"MiMo 网络错误: {e.reason}")
        except json.JSONDecodeError as e:
            raise APIError(f"MiMo 响应不是合法 JSON: {e}")

        if data.get("code") != 0:
            msg = data.get("message", "")
            raise APIError(f"MiMo API 错误: code={data.get('code')} msg={msg}")

        if label == "usage":
            usage_data = data.get("data", {})
        else:
            detail_data = data.get("data", {})

    month = usage_data.get("monthUsage", usage_data.get("usage", {}))
    pct = float(month.get("percent", 0)) * 100

    items = month.get("items", [])
    used = 0
    limit = 0
    for it in items:
        if it.get("name") in ("month_total_token", "plan_total_token"):
            used = it.get("used", 0)
            limit = it.get("limit", 0)
            break

    return {
        "percent": round(pct, 2),
        "period_end": detail_data.get("currentPeriodEnd", ""),
        "plan_name": detail_data.get("planName", ""),
        "used": used,
        "limit": limit,
    }


def resolve_mimo_credentials(config: dict):
    """
    返回 MiMo 平台的 cookie。
    auto 模式从 360 浏览器读取，manual 模式从 config 读取。
    """
    auth = config.get("auth", {})
    mode = (auth.get("mode") or "auto").lower()

    if mode == "auto":
        try:
            from cookie_loader import load_from_360_mimo, CookieLoadError
            cookie, exp = load_from_360_mimo()
            return cookie
        except Exception as e:
            manual = auth.get("mimo_cookie", "")
            if manual and "粘贴" not in manual:
                return manual
            raise AuthError(f"自动读取 MiMo Cookie 失败: {e}")

    manual = auth.get("mimo_cookie", "")
    if not manual or "粘贴" in manual:
        raise AuthError("手动模式下 config.auth.mimo_cookie 未填写")
    return manual


STEPFUN_API_BASE = "https://platform.stepfun.com/api"
STEPFUN_SERVICE = "step.openapi.devcenter.Dashboard"
STEPFUN_PASSPORT_URL = "https://platform.stepfun.com/passport/proto.api.passport.v1.PassportService/RefreshToken"


def _stepfun_headers(token: str, webid: str, cookie: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Connect-Protocol-Version": "1",
        "Oasis-Token": token,
        "Oasis-Webid": webid,
        "Oasis-Platform": "web",
        "Oasis-appID": "10300",
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.251 Safari/537.36",
        "Referer": "https://platform.stepfun.com/plan-subscribe",
        "Origin": "https://platform.stepfun.com",
        "Accept-Encoding": "gzip",
    }


def _stepfun_request(url: str, headers: dict, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthError(f"阶跃星辰认证失败 ({e.code})，token 可能已过期")
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise APIError(f"阶跃星辰 HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise APIError(f"阶跃星辰网络错误: {e.reason}")
    except json.JSONDecodeError as e:
        raise APIError(f"阶跃星辰响应不是合法 JSON: {e}")


def fetch_stepfun_usage(token: str, webid: str, cookie: str, timeout: int = 10) -> dict:
    """
    调用阶跃星辰 QueryStepPlanRateLimit 接口。
    如果 token 过期，自动通过 RefreshToken 刷新后重试一次。

    Returns:
        {
            "percent": 2.03,          # 已用量百分比 0~100
            "reset_ts": 1784360153,   # 订阅额度重置时间（unix 秒）
            "period_end": "2026-07-18 15:35:53",
            "info": "剩余 98.0%",
        }

    Raises:
        AuthError: token 过期且刷新失败
        APIError: 其他接口错误
    """
    url = f"{STEPFUN_API_BASE}/{STEPFUN_SERVICE}/QueryStepPlanRateLimit"
    headers = _stepfun_headers(token, webid, cookie)

    try:
        return _parse_stepfun_rate_limit(_stepfun_request(url, headers, timeout))
    except AuthError:
        refreshed_token, refreshed_cookie = _stepfun_refresh(token, webid, cookie, timeout)
        headers = _stepfun_headers(refreshed_token, webid, refreshed_cookie)
        return _parse_stepfun_rate_limit(_stepfun_request(url, headers, timeout))


def _stepfun_refresh(token: str, webid: str, cookie: str, timeout: int = 10) -> tuple:
    """刷新 Oasis-Token，返回 (new_token, updated_cookie_header)"""
    headers = _stepfun_headers(token, webid, cookie)
    data = _stepfun_request(STEPFUN_PASSPORT_URL, headers, timeout)
    new_token = data.get("accessToken", {}).get("raw", "")
    if not new_token:
        raise AuthError("阶跃星辰 RefreshToken 未返回新 token")
    new_cookie = cookie
    if new_token:
        import re
        new_cookie = re.sub(r'Oasis-Token=[^;]+', f'Oasis-Token={new_token}', cookie)
        if 'Oasis-Token=' not in new_cookie:
            new_cookie = f'Oasis-Token={new_token}; {cookie}'
    return new_token, new_cookie


def _parse_stepfun_rate_limit(data: dict) -> dict:
    """解析 QueryStepPlanRateLimit 响应为统一的用量格式"""
    credit = data.get("plan_credit_rate_limit", {})
    left_rate = float(credit.get("subscription_credit_left_rate", 0))
    percent = round((1 - left_rate) * 100, 2)

    reset_ts_str = credit.get("subscription_credit_reset_time", "0")
    reset_ts = int(reset_ts_str) if reset_ts_str else 0

    period_end = ""
    info = f"剩余 {left_rate * 100:.1f}%"

    buckets = credit.get("credit_buckets", [])
    for b in buckets:
        btype = b.get("type", 0)
        if btype == 1:
            expire_at = int(b.get("expire_at", "0"))
            if expire_at:
                import time
                period_end = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expire_at))

    return {
        "percent": percent,
        "reset_ts": reset_ts,
        "period_end": period_end,
        "info": info,
    }


def resolve_stepfun_credentials(config: dict):
    """
    返回阶跃星辰平台的 (token, webid, cookie_header)。
    auto 模式从 360 浏览器读取，manual 模式从 config 读取。
    """
    auth = config.get("auth", {})
    mode = (auth.get("mode") or "auto").lower()

    if mode == "auto":
        try:
            from cookie_loader import load_from_360_stepfun, CookieLoadError
            cookie, token, webid = load_from_360_stepfun()
            return token, webid or "", cookie
        except Exception as e:
            manual = auth.get("stepfun_cookie", "")
            if manual and "粘贴" not in manual:
                return "", "", manual
            raise AuthError(f"自动读取阶跃星辰 Cookie 失败: {e}")

    manual = auth.get("stepfun_cookie", "")
    if not manual or "粘贴" in manual:
        raise AuthError("手动模式下 config.auth.stepfun_cookie 未填写")
    return "", "", manual


def fetch_and_parse(config: dict) -> dict:
    """便捷封装：解析凭据 + 拉取 + 解析"""
    cookie, csrf, _exp = resolve_credentials(config)
    polling = config.get("polling", {})
    result = fetch_usage(
        cookie=cookie,
        csrf_token=csrf,
        timeout=polling.get("timeout_seconds", 10),
    )
    return parse_usage(result)
