# Cookie 导出指南（手动模式）

本项目默认使用 **auto 模式**，会从本机 360 浏览器 Cookie 数据库读取登录态。只有在自动模式不可用、或你使用其他浏览器时，才需要按本指南手动导出 Cookie。

## 重要安全提醒

- Cookie、`digest`、`serviceToken`、`csrfToken` 等同于账号登录凭据。
- 不要把这些内容提交到 GitHub、截图公开或发给他人。
- 手动配置文件 `config.json` 已被 `.gitignore` 忽略。

## 火山方舟 Cookie 导出

### 1. 打开控制台

用已登录的浏览器访问火山方舟控制台订阅/套餐页面。

### 2. 打开开发者工具

按 `F12`，切到 **Network / 网络**，过滤 **Fetch/XHR**。

### 3. 触发接口

刷新页面，搜索：

```text
GetCodingPlanUsage
```

### 4. 复制请求头

点击该请求，在 **Headers / 标头** 中复制：

- `Cookie`：完整 Cookie 字符串
- `X-Csrf-Token`：CSRF 请求头值

示例（仅为占位符，不是真实凭据）：

```text
Cookie: AccountID=<ACCOUNT_ID>; digest=<DIGEST_JWT>; userInfo=<USERINFO_JWT>; csrfToken=<CSRF_TOKEN>
X-Csrf-Token: <CSRF_TOKEN>
```

## MiMo Cookie 导出

MiMo 手动模式一般只需要复制 `platform.xiaomimimo.com` 相关请求中的完整 `Cookie` 请求头。

打开 MiMo 订阅管理页，在开发者工具中搜索：

```text
tokenPlan/usage
```

复制该请求的 `Cookie` 请求头。

## 写入 config.json

```bash
cp config.example.json config.json
chmod 600 config.json
```

修改 `config.json`：

```json
{
  "auth": {
    "mode": "manual",
    "cookie": "粘贴火山方舟完整 Cookie 字符串",
    "csrf_token": "<CSRF_TOKEN>",
    "mimo_cookie": "粘贴 MiMo 完整 Cookie 字符串"
  }
}
```

## 验证

```bash
python3.11 test_api.py
```

如果报 401/403 或提示 Cookie 过期，请重新登录对应平台并重新导出。