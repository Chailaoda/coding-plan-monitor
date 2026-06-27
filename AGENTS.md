# AGENTS.md — Coding Plan Monitor

## 项目概述
多模型平台额度桌面监控悬浮窗（Tkinter），支持火山方舟/MiMo/阶跃星辰/讯飞 MaaS。

## 技术栈
- Python 3.11，Tkinter，urllib（零外部依赖除 cryptography/pystray/Pillow）
- 360 浏览器 Cookie AES-128-CBC + PBKDF2('peanuts') 解密

## 运行命令
```bash
python3.11 main.py                    # 启动
python3.11 test_api.py                # 验证火山方舟 API
systemctl --user restart coding-plan-monitor  # 重启服务
```

## 架构
- `main.py`：App 类，TARGET_PRESETS（多目标预设），_fetch_loop 调度各目标
- `api.py`：各平台 API 封装 + 凭据解析 + DEFAULT_CONFIG
- `cookie_loader.py`：360 浏览器 Cookie 解密（火山/MiMo/阶跃各自 loader）
- `ui.py`：FloatingWindow，QuotaRow（火山三窗口），TargetRow（其他平台）
- `tray.py`：TrayManager，pystray 托盘图标
- `notifier.py`：AlertManager 阈值检测 + 防重复
- `storage.py`：SQLite usage_history + alert_history

## 多目标框架
- `TARGET_PRESETS` 硬编码预设，`implemented=True/False` 标记是否已接入
- config.json `targets.<id>.enabled` 控制启用
- 未实现目标显示"待接入" + "打开"按钮跳转控制台
- 新增目标：添加 preset → 实现 cookie_loader + api 函数 → main.py _fetch_xxx() → ui 自动适配

## 阶跃星辰接入要点
- Connect/gRPC-Web JSON 模式，非 protobuf
- Oasis-Token 约 30 分钟 JWT，自动 RefreshToken 续期
- 请求头需 `Oasis-Token`/`Oasis-Webid`/`Oasis-Platform: web`/`Oasis-appID: 10300`/`Connect-Protocol-Version: 1`

## 火山方舟注意
- `csrfToken` 在 360 浏览器 Cookie DB 中可能缺失，需用户先刷新控制台页面
- `reset_ts=-1` 表示"当前窗口无调用"，不应视为已过期
