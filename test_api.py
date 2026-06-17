#!/usr/bin/env python3.11
"""
API 测试脚本：验证 cookie 配置是否正确
用法: python3.11 test_api.py
"""

import sys
import os
import time
from datetime import datetime

# 把当前目录加入 path，便于直接运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import load_config, fetch_and_parse, AuthError, APIError


def format_reset(ts: int) -> str:
    """把重置时间戳格式化为相对时间"""
    diff = ts - int(time.time())
    if diff <= 0:
        return "即将重置"
    h = diff // 3600
    m = (diff % 3600) // 60
    if h >= 24:
        return f"{h // 24} 天 {h % 24} 小时"
    return f"{h} 小时 {m} 分"


def main():
    print("=" * 60)
    print("火山方舟 Coding Plan 用量查询测试")
    print("=" * 60)

    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"\n[错误] {e}")
        return 1

    print("\n正在调用 GetCodingPlanUsage 接口...")

    try:
        data = fetch_and_parse(config)
    except AuthError as e:
        print(f"\n[认证失败] {e}")
        print("请重新从浏览器导出 Cookie，参考 cookie导出指南.md")
        return 2
    except APIError as e:
        print(f"\n[接口错误] {e}")
        return 3

    print(f"\n套餐状态: {data['status']}")
    print(f"数据更新于: {datetime.fromtimestamp(data['update_ts']).strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(f"{'窗口':<8} {'已用':>10}   {'距重置':<20}")
    print("-" * 50)

    for level in ("session", "weekly", "monthly"):
        q = data["quotas"].get(level)
        if not q:
            continue
        pct = q["percent"]
        bar_len = 30
        filled = int(min(pct, 100) / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        if pct >= 90:
            color = "\033[91m"  # 红
        elif pct >= 70:
            color = "\033[93m"  # 黄
        else:
            color = "\033[92m"  # 绿
        reset_color = "\033[0m"
        print(f"{q['label']:<8} {color}{pct:>8.4f}%{reset_color}   {format_reset(q['reset_ts'])}")
        print(f"         {color}{bar}{reset_color}")

    print()
    print("[OK] 测试通过，配置正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
