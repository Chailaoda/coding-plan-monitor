# Coding Plan Monitor

多模型平台额度桌面监控悬浮窗（UOS / Linux）。

支持火山方舟、MiMo（小米）、阶跃星辰等多个 AI 平台的额度用量实时监控，未接入平台显示"待接入"并可一键打开控制台。

## 特性

- **多平台监控**：火山方舟（三窗口）+ MiMo + 阶跃星辰，可勾选启用/禁用
- **桌面常驻**：基于 Tkinter，无需打开浏览器
- **火山方舟三窗口**：5 小时 / 周 / 月 三条进度条
- **颜色预警**：<60% 绿、60-89% 橙、≥90% 红
- **桌面通知**：跨阈值时 notify-send 弹通知 + paplay 铃声
- **自动 Cookie**：直接从 360 浏览器（UOS 版）解密读取，免维护
- **阶跃星辰自动刷新**：Oasis-Token 过期时自动 RefreshToken
- **系统托盘**：pystray 托盘图标，左键切换悬浮窗，右键菜单
- **窗口可拖动 / 可折叠 / 可关闭**，位置自动持久化
- **历史存档**：SQLite 保存每次快照，便于将来画趋势图
- **零外部依赖**：仅需 Python 3.11 标准库 + cryptography（pystray + Pillow 用于托盘图标）

## 已支持平台

| 平台 | 状态 | 自动读取 Cookie | API 方式 |
|------|------|-----------------|----------|
| 火山方舟 | 已接入 | 360 浏览器 → digest + csrfToken | GetCodingPlanUsage 内部接口 |
| MiMo（小米） | 已接入 | 360 浏览器 → serviceToken | 公开 REST API |
| 阶跃星辰 | 已接入 | 360 浏览器 → Oasis-Token + Webid | Connect/gRPC-Web JSON 模式 |
| 讯飞 MaaS | 待接入 | — | — |

## 文件结构

```
coding-plan-monitor/
├── main.py                       # 程序入口 + 多目标调度
├── api.py                        # 各平台 API 封装 + 凭据解析
├── cookie_loader.py              # 360 浏览器 Cookie 自动解密
├── ui.py                         # Tkinter 悬浮窗
├── tray.py                       # 系统托盘图标
├── notifier.py                   # 桌面通知 + 阈值判定
├── storage.py                    # SQLite 存储
├── test_api.py                   # 验证脚本
├── config.example.json           # 配置模板
├── coding-plan-monitor.service   # systemd user service
├── 安装说明.md                    # 详细使用文档
├── cookie导出指南.md              # 手动模式 Cookie 提取教程
└── README.md                     # 本文件
```

## 快速开始

只要 360 浏览器登录过对应平台：

```bash
cd ~/Desktop/工作区/coding-plan-monitor
python3.11 main.py          # 启动
```

首次启动默认启用火山方舟。点击悬浮窗标题栏"标的"按钮可勾选其他平台。

详细步骤见 `安装说明.md`。

## 技术选型

- **GUI**：Tkinter（标准库，ARM64 完美兼容）
- **HTTP**：urllib.request（标准库）
- **存储**：sqlite3（标准库）
- **通知**：notify-send / paplay
- **托盘**：pystray + Pillow
- **认证**：浏览器 Cookie 复用（均为控制台内部 API）
- **Cookie 解密**：AES-128-CBC + PBKDF2('peanuts', salt='saltysalt')

## 配置

参考 `config.example.json`。关键配置项：

- `auth.mode`：`auto`（自动读 360 浏览器）或 `manual`（手动填 Cookie）
- `targets.<id>.enabled`：启用/禁用监控目标
- `alerts`：各窗口阈值 + 通知/铃声开关
- `ui`：窗口位置、透明度、置顶

## 已知限制

- Cookie 自动模式仅支持 360 浏览器（UOS 版）
- 阶跃星辰 Oasis-Token 约 30 分钟过期，程序自动 RefreshToken 续期
- 讯飞 MaaS 尚未接入
- 仅在 UOS DDE 桌面环境下测试通过
