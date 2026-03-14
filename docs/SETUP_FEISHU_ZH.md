# NanoClaw + 飞书安装部署指南

本文记录在 macOS 上从零开始安装 NanoClaw 并接入飞书（Feishu）频道的完整步骤，以及过程中遇到的问题与解决方案。

---

## 环境信息

| 项目 | 值 |
|------|-----|
| 操作系统 | macOS |
| Node.js | 25.7.0（通过 Homebrew 安装） |
| 容器运行时 | Docker Desktop（运行中） |
| LLM 后端 | 阿里云 DashScope（通义千问）via 本地网关 |
| 消息频道 | 飞书 WebSocket 长连接 |

---

## 步骤一：Fork 并配置 Git

直接克隆原仓库后需要将其转换为 Fork 工作流：

```bash
# 将 origin 重命名为 upstream（指向官方仓库）
git remote rename origin upstream

# 添加自己的 fork 为 origin
git remote add origin https://github.com/<your-username>/nanoclaw.git

# 推送
git push --force origin main
```

验证结果：
```
origin    https://github.com/<your-username>/nanoclaw.git (fetch/push)
upstream  https://github.com/qwibitai/nanoclaw.git (fetch/push)
```

---

## 步骤二：Bootstrap

```bash
bash setup.sh
```

输出中关注：
- `NODE_OK: true` — Node.js 版本符合要求（需 ≥ 22）
- `DEPS_OK: true` — npm 依赖安装成功
- `NATIVE_OK: true` — better-sqlite3 原生模块加载成功

---

## 步骤三：构建容器镜像

macOS 上默认使用 Docker：

```bash
npx tsx setup/index.ts --step container -- --runtime docker
```

输出中关注：
- `BUILD_OK: true`
- `TEST_OK: true`

---

## 步骤四：配置 Claude 认证

编辑 `.env`，选择以下其中一种方式：

```bash
# 方式 A：Anthropic API Key
ANTHROPIC_API_KEY=sk-...

# 方式 B：Claude Pro/Max 订阅 Token（先运行 `claude setup-token` 获取）
CLAUDE_CODE_OAUTH_TOKEN=...
```

---

## 步骤五：添加飞书频道

飞书 skill 已包含在项目中，通过 skills engine 安装：

```bash
npx tsx scripts/apply-skill.ts .claude/skills/add-feishu
npm run build
```

### 飞书应用配置要求

在 [飞书开放平台](https://open.feishu.cn/app) 创建应用时需确保：

1. **事件订阅** → 启用**长连接（WebSocket）模式**（非 Webhook）
2. **添加事件**：`im.message.receive_v1`（接收消息）
3. **权限**：
   - `im:message:send_as_bot`（以机器人身份发送）
   - `im:message`（读取消息）
4. **发布应用**（草稿状态不接收事件）

在 `.env` 中配置：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxx
```

---

## 步骤六：配置挂载目录（可选）

```bash
npx tsx setup/index.ts --step mounts -- --json '{
  "allowedRoots": [
    {"path": "/path/to/your/data", "permission": "readwrite"}
  ],
  "blockedPatterns": [],
  "nonMainReadOnly": false
}'
```

---

## 步骤七：启动服务

```bash
npx tsx setup/index.ts --step service
```

macOS 使用 launchd 管理服务，plist 写入 `~/Library/LaunchAgents/com.nanoclaw.plist`。

常用命令：
```bash
# 重启
launchctl kickstart -k gui/$(id -u)/com.nanoclaw

# 停止
launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist

# 查看状态（PID 非 - 表示正在运行）
launchctl list | grep nanoclaw
```

---

## 步骤八：注册飞书群组

服务启动后，向 Bot 发一条消息，Chat ID 会出现在数据库中：

```bash
sqlite3 store/messages.db "SELECT jid FROM chats WHERE jid LIKE '%@feishu'"
```

注册群组（`requires_trigger=0` 表示无需 @ 即可触发）：

```sql
INSERT INTO registered_groups (jid, name, folder, trigger_pattern, added_at, requires_trigger)
VALUES ('{chat_id}@feishu', 'feishu', 'feishu', '@Claude', datetime('now'), 0);
```

然后重启服务使注册生效。

---

## 常见问题与解决方案

### 问题 1：端口 3001 被占用（EADDRINUSE）

**现象：**
```
Error: listen EADDRINUSE: address already in use 127.0.0.1:3001
```

**原因：** 旧的 nanoclaw 进程未退出，仍占用 credential proxy 端口。

**解决：**
```bash
lsof -ti :3001 | xargs kill -9
launchctl kickstart -k gui/$(id -u)/com.nanoclaw
```

---

### 问题 2：Credential Proxy 连接 DashScope 网关失败（ECONNRESET）

**现象：**
```
Credential proxy upstream error: socket hang up (ECONNRESET)
url: "/v1/messages?beta=true"
```

**原因：** `.env` 中 `ANTHROPIC_BASE_URL=http://host.docker.internal:8005`。`host.docker.internal` 是 Docker 容器内专用域名，在宿主机上解析到 `198.18.8.94`（Docker 虚拟 IP），但 DashScope 网关只监听 `127.0.0.1`，无法通过该 IP 访问。

**解决：** 将 `.env` 中的地址改为 `127.0.0.1`：

```bash
# 错误配置
ANTHROPIC_BASE_URL=http://host.docker.internal:8005

# 正确配置
ANTHROPIC_BASE_URL=http://127.0.0.1:8005
```

> **说明：** Credential Proxy 运行在宿主机上（不在容器内），因此应使用 `127.0.0.1` 而非 `host.docker.internal`。容器内的 Agent 通过 `host.docker.internal:3001` 连接到 Credential Proxy，不直接访问 `ANTHROPIC_BASE_URL`。

---

### 问题 3：服务启动后 verify 显示 CONFIGURED_CHANNELS 为空

**现象：**
```
CONFIGURED_CHANNELS:
CHANNEL_AUTH: {}
STATUS: failed
```

**原因：** `verify` 脚本目前不识别飞书频道，但不影响实际功能。只要日志中出现以下内容，即表示正常：

```
Feishu bot info fetched
Connected to Feishu via WebSocket
NanoClaw running
```

---

## 网络架构说明（重要）

```
飞书服务器
    ↓ WebSocket 长连接
宿主机 NanoClaw 主进程
    ↓ 收到消息，启动容器
Docker 容器（agent）
    ↓ HTTP 请求 host.docker.internal:3001
宿主机 Credential Proxy（127.0.0.1:3001）
    ↓ 转发到 ANTHROPIC_BASE_URL
127.0.0.1:8005（DashScope 网关）
    ↓
阿里云 DashScope API（通义千问）
```

关键点：`ANTHROPIC_BASE_URL` 由 **Credential Proxy（宿主机进程）** 读取，所以必须使用宿主机可访问的地址（`127.0.0.1`），而非容器专用的 `host.docker.internal`。

---

## 验证正常运行的日志特征

```
INFO: Feishu bot info fetched          # Bot 身份识别成功
INFO: Connected to Feishu via WebSocket # 长连接建立
INFO: NanoClaw running (trigger: @Andy) # 服务就绪
INFO: Processing messages               # 收到消息
INFO: Spawning container agent          # 容器启动
INFO: Agent output: ...                 # Agent 生成回复
INFO: Feishu message sent               # 回复发送成功
```

---

## 日常运维

```bash
# 查看实时日志
tail -f logs/nanoclaw.log

# 重启服务
launchctl kickstart -k gui/$(id -u)/com.nanoclaw

# 查看注册的群组
sqlite3 store/messages.db "SELECT * FROM registered_groups"

# 拉取上游更新
git fetch upstream && git merge upstream/main
```
