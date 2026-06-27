# Cookie 导出指南

## 通用说明

自动模式（默认）下程序直接从 360 浏览器读取 Cookie，无需手动操作。以下仅在使用其他浏览器或需要手动模式时参考。

## 火山方舟

### 需要提取的字段

| 字段 | 来源 | 说明 |
|------|------|------|
| Cookie | 请求标头 | 完整 Cookie 字符串（含 digest） |
| X-Csrf-Token | 请求标头 | 32 位十六进制字符串 |

### 操作步骤

1. 用浏览器访问 `https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?advancedActiveKey=subscribe`
2. F12 → Network → Fetch/XHR → 刷新页面
3. 过滤 `GetCodingPlanUsage`，点击该请求 → Headers → Request Headers
4. 复制 `Cookie:` 后的完整内容
5. 复制 `X-Csrf-Token:` 的值
6. 填入 config.json：
   ```json
   { "auth": { "mode": "manual", "cookie": "粘贴Cookie", "csrf_token": "粘贴token" } }
   ```
7. `chmod 600 config.json`

### 有效期

- `digest`（JWT）：约 2 天
- `AccountID / userInfo`：约 30 天

## MiMo（小米）

### 需要提取的字段

| 字段 | 来源 | 说明 |
|------|------|------|
| Cookie | 请求标头 | 含 serviceToken |

### 操作步骤

1. 用浏览器访问 `https://platform.xiaomimimo.com/console/plan-manage`
2. F12 → Network → 任意 API 请求 → Headers → Request Headers
3. 复制完整 Cookie（确保含 `serviceToken` 字段）
4. 填入 config.json：
   ```json
   { "auth": { "mode": "manual", "mimo_cookie": "粘贴Cookie" } }
   ```

## 阶跃星辰

### 需要提取的字段

| 字段 | 来源 | 说明 |
|------|------|------|
| Oasis-Token | Cookie / LocalStorage | JWT，约 30 分钟过期，程序自动续期 |
| Oasis-Webid | Cookie | 设备标识 |
| Cookie | 请求标头 | 完整 Cookie（含 INGRESSCOOKIE 等） |

### 操作步骤

1. 用浏览器访问 `https://platform.stepfun.com/plan-subscribe`
2. F12 → Application → Cookies → `platform.stepfun.com`
3. 复制 `Oasis-Token` 和 `Oasis-Webid` 的值
4. F12 → Network → 任意 `/api/` 请求 → Headers → Request Headers → 复制完整 Cookie
5. 填入 config.json：
   ```json
   { "auth": { "mode": "manual", "stepfun_cookie": "粘贴完整Cookie" } }
   ```

**注意**：阶跃星辰 Oasis-Token 约 30 分钟过期，程序会自动通过 RefreshToken 接口续期，无需频繁手动更新。

## 通用提示

- Cookie 等同于密码，`config.json` 务必 `chmod 600`
- 不需要 URL 解码，原样粘贴即可
- 自动模式下程序每 60 秒重新读一次浏览器 Cookie DB，浏览器续期后自动跟进
