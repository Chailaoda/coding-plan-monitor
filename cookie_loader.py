"""
360 浏览器（UOS）Cookie 自动读取模块
原理：
  1. ~/.config/com.360.browser/Default/Cookies 是 SQLite，直接拷贝读
  2. 加密 value 以 b'v10' 前缀，AES-128-CBC + 'peanuts' 硬编码密钥 + PBKDF2(iter=1, salt='saltysalt')
     （Chromium Linux 老版本回退方案，360 浏览器沿用）
  3. 解析 digest（JWT）的 exp 字段获取过期时间
  4. csrfToken 单独从 cookies 表中提取作为 X-Csrf-Token header

依赖: cryptography（系统已装）
"""

import json
import os
import shutil
import sqlite3
import tempfile
import time
import base64
from typing import Optional, Tuple

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


DEFAULT_COOKIES_DB = os.path.expanduser(
    "~/.config/com.360.browser/Default/Cookies"
)
TARGET_HOSTS = (".volcengine.com", "console.volcengine.com")


class CookieLoadError(Exception):
    pass


def _derive_key(password: bytes = b"peanuts") -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=16,
        salt=b"saltysalt",
        iterations=1,
    )
    return kdf.derive(password)


_AES_KEY = None


def _get_key() -> bytes:
    global _AES_KEY
    if _AES_KEY is None:
        _AES_KEY = _derive_key()
    return _AES_KEY


def _decrypt_v10(enc: bytes) -> Optional[str]:
    """解密 Chromium v10 加密的 cookie value"""
    if not enc or not enc.startswith(b"v10"):
        return None
    try:
        cipher = Cipher(algorithms.AES(_get_key()), modes.CBC(b" " * 16))
        d = cipher.decryptor()
        plain = d.update(enc[3:]) + d.finalize()
        pad = plain[-1]
        if 1 <= pad <= 16 and all(plain[-i] == pad for i in range(1, pad + 1)):
            plain = plain[:-pad]
        return plain.decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_jwt_exp(jwt: str) -> Optional[int]:
    """从 JWT 解析 exp 字段（unix 秒）"""
    try:
        parts = jwt.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        j = json.loads(base64.urlsafe_b64decode(payload))
        return int(j.get("exp", 0)) or None
    except Exception:
        return None


def load_from_360(db_path: Optional[str] = None) -> Tuple[str, str, Optional[int]]:
    """
    从 360 浏览器读取 console.volcengine.com 的 Cookie 与 csrfToken。

    Returns:
        (cookie_header, csrf_token, digest_exp_unix_seconds_or_None)

    Raises:
        CookieLoadError: 数据库不存在 / 解密失败 / 关键字段缺失
    """
    db_path = db_path or DEFAULT_COOKIES_DB
    if not os.path.exists(db_path):
        raise CookieLoadError(
            f"360 浏览器 Cookie 数据库不存在: {db_path}\n"
            "请确认浏览器已安装并至少登录过 console.volcengine.com 一次。"
        )

    # 必须拷贝 —— 浏览器运行时数据库被 WAL 锁定，直接读会拿到脏数据
    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy(db_path, tmp)
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        cur.execute(
            """SELECT host_key, name, encrypted_value, expires_utc
               FROM cookies
               WHERE host_key IN (?, ?)""",
            TARGET_HOSTS,
        )
        rows = cur.fetchall()
        conn.close()
    except sqlite3.Error as e:
        raise CookieLoadError(f"读取 SQLite 失败: {e}")
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    if not rows:
        raise CookieLoadError(
            "Cookie 数据库中未找到 volcengine.com 的记录，请先在 360 浏览器中登录控制台。"
        )

    cookies = {}
    csrf_token = None
    digest_exp = None
    decrypt_failures = 0

    # 按 host 顺序处理，console.volcengine.com 优先级高于 .volcengine.com
    rows_sorted = sorted(rows, key=lambda r: 0 if r[0] == ".volcengine.com" else 1)
    for host, name, enc, _exp in rows_sorted:
        val = _decrypt_v10(enc)
        if val is None:
            decrypt_failures += 1
            continue
        cookies[name] = val  # 后处理覆盖前面，console.* 最终生效
        if name == "csrfToken":
            csrf_token = val
        elif name == "digest":
            digest_exp = _parse_jwt_exp(val)

    if not cookies:
        raise CookieLoadError(
            f"成功读取数据库但所有 cookie 解密失败（{decrypt_failures} 条）。\n"
            "可能是浏览器升级后改用了 GNOME Keyring 加密，请联系作者更新解密方案。"
        )

    if "digest" not in cookies:
        raise CookieLoadError("未找到 digest cookie，请先在 360 浏览器中登录控制台。")
    if not csrf_token:
        raise CookieLoadError(
            "未找到 csrfToken。请刷新一次 https://console.volcengine.com/ark 后重试。"
        )

    # 检查 digest 是否过期
    now = int(time.time())
    if digest_exp and digest_exp < now:
        raise CookieLoadError(
            f"digest 已过期（{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(digest_exp))}）。\n"
            "请在 360 浏览器中重新登录 console.volcengine.com。"
        )

    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    return cookie_header, csrf_token, digest_exp


MIMO_TARGET_HOSTS = (".platform.xiaomimimo.com", "platform.xiaomimimo.com", ".xiaomimimo.com", "xiaomimimo.com")


def load_from_360_mimo(db_path: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    从 360 浏览器读取 xiaomimimo.com 的 Cookie（用于 MiMo 用量查询）。

    Returns:
        (cookie_header, current_period_end_str_or_None)

    Raises:
        CookieLoadError: 数据库不存在 / 解密失败 / 关键字段缺失
    """
    db_path = db_path or DEFAULT_COOKIES_DB
    if not os.path.exists(db_path):
        raise CookieLoadError(
            f"360 浏览器 Cookie 数据库不存在: {db_path}\n"
            "请确认浏览器已安装并至少登录过 platform.xiaomimimo.com 一次。"
        )

    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy(db_path, tmp)
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        ph = ",".join("?" for _ in MIMO_TARGET_HOSTS)
        cur.execute(
            f"SELECT host_key, name, encrypted_value FROM cookies WHERE host_key IN ({ph})",
            MIMO_TARGET_HOSTS,
        )
        rows = cur.fetchall()
        conn.close()
    except sqlite3.Error as e:
        raise CookieLoadError(f"读取 SQLite 失败: {e}")
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    if not rows:
        raise CookieLoadError(
            "Cookie 数据库中未找到 xiaomimimo.com 的记录，请先在 360 浏览器中登录 MiMo 平台。"
        )

    cookies = {}
    for host, name, enc in rows:
        val = _decrypt_v10(enc)
        if val:
            cookies[name] = val

    if "serviceToken" not in cookies and "api-platform_serviceToken" not in cookies:
        raise CookieLoadError(
            "未找到 MiMo serviceToken，请先在 360 浏览器中登录 platform.xiaomimimo.com。"
        )

    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    return cookie_header, None


def remaining_seconds(digest_exp: Optional[int]) -> int:
    if not digest_exp:
        return -1
    return digest_exp - int(time.time())


if __name__ == "__main__":
    # CLI: 测试读取
    try:
        cookie, csrf, exp = load_from_360()
    except CookieLoadError as e:
        print(f"[FAIL] {e}")
        raise SystemExit(1)
    print(f"[OK] cookie 长度={len(cookie)}")
    print(f"[OK] csrfToken={csrf[:20]}...")
    if exp:
        rem = remaining_seconds(exp)
        print(
            f"[OK] digest 过期: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp))} "
            f"（剩余 {rem // 3600} 小时 {(rem % 3600) // 60} 分钟）"
        )
